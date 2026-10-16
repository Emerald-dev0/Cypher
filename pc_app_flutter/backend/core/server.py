import os
import socket
import platform
import psutil
import io
import base64
import json
import uuid
import secrets
import time
import zipfile
import threading
import subprocess
import queue
import re
import hmac
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path

# Detect platform
WINDOWS = platform.system() == 'Windows'

# Standard imports (work everywhere)
from flask import Flask, jsonify, render_template, request, send_file, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO

from .hostguard import cors_origin_list, host_header_allowed

# BUGFIX: Pillow was used in ~8 places (clipboard image capture, window icons,
# thumbnails, guest previews) but never imported. Because the code guards with
# `if not ImageGrab`, the guard itself raised NameError and the route returned
# HTTP 500 — so PC clipboard read, image clipboard paste and all thumbnails were
# silently dead.
#
# The import is tolerant so the node still boots on a minimal/headless Linux
# install without Pillow; routes then degrade to their "unsupported" branches
# instead of crashing the whole server.
try:
    from PIL import Image, ImageGrab
except ImportError:  # pragma: no cover - optional on headless Linux
    Image = None
    ImageGrab = None

# Placeholder for heavy modules (Loaded Lazily)
pyautogui = None
pyperclip = None
gw = None
cv2 = None
np = None
mss = None
AudioUtilities = None
IAudioEndpointVolume = None
ctypes = None
CLSCTX_ALL = None
win32gui = None
win32api = None
win32con = None
win32ui = None

def _load_automation():
    global pyautogui, pyperclip, gw, win32gui, win32api, win32con, win32ui
    if pyautogui is None and WINDOWS:
        import pyautogui as pg
        import pyperclip as pc
        import pygetwindow as g
        import win32gui as wg
        import win32api as wa
        import win32con as wc
        import win32ui as wu
        pyautogui = pg
        pyperclip = pc
        gw = g
        win32gui = wg
        win32api = wa
        win32con = wc
        win32ui = wu
        pyautogui.FAILSAFE = False

def _load_media_engine():
    global cv2, np, mss
    if cv2 is None:
        import cv2 as _cv2
        import numpy as _np
        import mss as _mss
        cv2 = _cv2
        np = _np
        mss = _mss

def _load_audio_engine():
    global AudioUtilities, IAudioEndpointVolume, ctypes, CLSCTX_ALL
    if AudioUtilities is None and WINDOWS:
        from pycaw.pycaw import AudioUtilities as AU, IAudioEndpointVolume as IAEV
        from comtypes import CLSCTX_ALL as CA
        import ctypes as ct
        AudioUtilities = AU
        IAudioEndpointVolume = IAEV
        CLSCTX_ALL = CA
        ctypes = ct

app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / 'templates'))
# P1-S4 / S-07: never CORS(app) with the default "*". Browser pages on the
# internet must not read responses from this node.
_CORS_ORIGINS = cors_origin_list()
CORS(app, origins=_CORS_ORIGINS, supports_credentials=False)

# Use 'threading' as it's the most compatible mode for Windows executables
socketio = SocketIO(app, cors_allowed_origins=_CORS_ORIGINS, async_mode='threading')

@socketio.on('connect')
def handle_connect(auth=None):
    """Verify X-Auth-Token on socket connection."""
    token = request.headers.get("X-Auth-Token")
    if token == INTERNAL_TOKEN or token in valid_tokens:
        return True
    return False

# --- CONSTANTS & SECURITY ---
# Imported first: _get_internal_token() below resolves a path through it.
from .utils import (
    SERVER_PORT,
    get_app_data_dir,
    get_config_path,
    log_event,
)
from .sandbox import Sandbox, SandboxViolation, is_path_in_folders  # noqa: F401 — used by rewired route views
from .auth import is_public_view, public_endpoint_names, public_route
from .version import NODE_VERSION, PROTOCOL_VERSION

# BUGFIX: guest_manager was referenced as a bare module-level name in ~14 route
# handlers (and in the before_request auth hook) but was only ever imported
# *inside* get_guest_manager(). Every one of those call sites raised
# NameError -> HTTP 500, which is why guest links and the shared-file browser
# were reported as "not working".
#
# guest_manager.py pulls in nothing heavier than secrets/threading/datetime, so
# there is no startup cost to importing it eagerly. get_guest_manager() is kept
# for backwards compatibility with the call sites that already use it.
from .guest_manager import guest_manager


def _get_internal_token():
    """
    Token that lets the local desktop shell (Flutter) talk to its own backend
    over the loopback interface without going through the pairing flow.

    SECURITY HISTORY
    ────────────────
    This used to be the hardcoded literal "cypher-internal-pc-app-token-2024",
    committed to a public repository. Anyone on the same LAN could read it from
    GitHub and gain full remote control of every Cypher node — shutdown, file
    read/write, keystroke injection. It is now generated per install.

    The token is persisted next to the other node config and is only ever
    readable by the user that runs the node. The desktop shell reads it from
    disk (see pc_app_flutter/lib/services/bridge_service.dart).
    """
    token_file = get_config_path("internal_token")
    try:
        if token_file.exists():
            existing = token_file.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        token = secrets.token_urlsafe(48)
        token_file.write_text(token, encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass  # POSIX-only; Windows ACLs are inherited from %APPDATA%
        return token
    except OSError as exc:
        # Unwritable config dir: fall back to an ephemeral token rather than a
        # shared constant. Pairing still works; the shell re-reads it on restart.
        print(f"WARN: could not persist internal token ({exc}); using ephemeral")
        return secrets.token_urlsafe(48)

INTERNAL_TOKEN = _get_internal_token()

# These will be loaded lazily
_guest_manager = None
_overlay_manager = None
_discovery = None

def get_guest_manager():
    global _guest_manager
    if _guest_manager is None:
        from .guest_manager import guest_manager
        _guest_manager = guest_manager
    return _guest_manager

def get_overlay_manager():
    global _overlay_manager
    if _overlay_manager is None:
        from .recording_overlay import overlay_manager
        _overlay_manager = overlay_manager
    return _overlay_manager

def get_discovery_node():
    global _discovery
    if _discovery is None:
        from .discovery import start_discovery_thread, get_discovery_instance
        _discovery = (start_discovery_thread, get_discovery_instance)
    return _discovery

# --- GLOBAL STORAGE & PERSISTENCE ---
notifications_list = []
command_history = []
connection_events = []
# [UNIFIED LOG] Storage for dynamic activity log
system_activity_log = []

def add_activity(title, desc, category="Connections", is_urgent=False, attachment=None):
    """Helper to add events to the unified system activity log."""
    log_entry = {
        "id": str(uuid.uuid4()),
        "title": title,
        "desc": desc,
        "category": category,
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": "Today", # Logic for 'Yesterday' can be added if persistence is needed
        "is_urgent": is_urgent,
        "attachment": attachment,
        "timestamp": time.time()
    }
    system_activity_log.insert(0, log_entry)
    if len(system_activity_log) > 200:
        system_activity_log.pop()

    # Also log to internal event tracker
    log_event(category.upper(), {"title": title, "desc": desc})

active_transfers = {}  # Format: {transfer_id: {"name": str, "size": int, "progress": int, "speed": str}}
cancel_all_transfers = False
phone_clipboard = {"content": "", "timestamp": "", "type": "text"}

# --- SCREEN RECORDING STATE ---
recording_state = {
    "is_recording": False,
    "is_paused": False,
    "start_time": None,
    "filename": None,
    "filepath": None,
    "process": None,
    "source": "fullscreen",
    "record_audio": False,
    "audio_source": "system",
    "temp_video_path": None,
    "temp_audio_path": None
}

MACROS_FILE = get_config_path("macros.json")
SETTINGS_FILE = get_config_path("settings.json")
# [FIX] Use cypher_config.json as the master source for shared folders to match the UI
SHARED_FOLDERS_FILE = get_config_path("cypher_config.json")
PAIRED_DEVICES_FILE = get_config_path("paired_devices.json")
# [DYNAMIC CODE] Generate a fresh pairing code on every session for security
#
# Uses `secrets`, not `random`. The Mersenne Twister behind random.randint is
# recoverable from a handful of observed outputs and was never meant for
# security decisions.
PAIRING_CODE_LENGTH = 6

def _generate_dynamic_code():
    # randbelow is uniform over [0, n) — avoids the modulo bias of
    # secrets.randrange over a non-power-of-ten span.
    upper = 10 ** PAIRING_CODE_LENGTH
    new_code = str(secrets.randbelow(upper - 10 ** (PAIRING_CODE_LENGTH - 1)) + 10 ** (PAIRING_CODE_LENGTH - 1))
    try:
        code_path = get_config_path("pairing_code.txt")
        code_path.write_text(new_code, encoding="utf-8")
        try:
            os.chmod(code_path, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return new_code

PAIRING_CODE = _generate_dynamic_code()

# --- PAIRING BRUTE-FORCE GUARD -------------------------------------------
# A 6-digit code is a 10^6 keyspace. Without throttling, an attacker on the LAN
# can exhaust it in minutes with parallel requests, so the code itself is not the
# security boundary — the throttle is. Attempts are tracked per source IP with a
# rolling window and an exponential backoff, and any successful pairing rotates
# the code so a partially-guessed value cannot be replayed.
PAIRING_MAX_ATTEMPTS = 5          # per window, per source IP
PAIRING_WINDOW_SECONDS = 300      # 5 minutes
PAIRING_LOCKOUT_SECONDS = 900     # 15 minutes after the window is exhausted

_pairing_attempts = {}            # ip -> list[timestamp]
_pairing_lockouts = {}            # ip -> lockout_until (epoch)
_pairing_lock = threading.Lock()


def _pairing_throttle(ip):
    """
    Returns (allowed: bool, retry_after_seconds: int).

    Must be called BEFORE the code comparison so that a correct guess from a
    locked-out address is still refused.
    """
    now = time.time()
    with _pairing_lock:
        lockout_until = _pairing_lockouts.get(ip, 0)
        if now < lockout_until:
            return False, int(lockout_until - now)

        window = [t for t in _pairing_attempts.get(ip, []) if now - t < PAIRING_WINDOW_SECONDS]
        if len(window) >= PAIRING_MAX_ATTEMPTS:
            _pairing_lockouts[ip] = now + PAIRING_LOCKOUT_SECONDS
            _pairing_attempts[ip] = []
            return False, PAIRING_LOCKOUT_SECONDS

        window.append(now)
        _pairing_attempts[ip] = window
        return True, 0


def _pairing_reset(ip):
    """Clear the attempt counter for an address that just paired successfully."""
    with _pairing_lock:
        _pairing_attempts.pop(ip, None)
        _pairing_lockouts.pop(ip, None)

paired_devices = {}
valid_tokens = {INTERNAL_TOKEN}

def _get_shared_folders():
    """Helper to get shared folders from the master config file (cypher_config.json)."""
    try:
        if SHARED_FOLDERS_FILE.exists():
            with open(SHARED_FOLDERS_FILE) as f:
                config_data = json.load(f)
                if isinstance(config_data, list):
                    return config_data
                # Return the list of strings if it exists, otherwise empty
                folders = config_data.get("shared_folders", [])
                if isinstance(folders, list):
                    return folders
                return []
    except Exception as e:
        print(f"ERROR: _get_shared_folders: {e}")
    return []


# P1-S2. One helper, every filesystem route. The message is generic on purpose:
# echoing the resolved path helps an attacker map the disk (security-hardening.md
# §3.3 rule 8).
_SANDBOX_DENIED = {"success": False, "error": "path is outside the shared folders"}


def _paired_sandbox() -> Sandbox:
    return Sandbox(_get_shared_folders())


def _require_shared_path(raw, *, need="read"):
    """Resolve `raw` inside the node's shared-folder allowlist.

    Returns (Path, None) on success, or (None, (response, status)) on denial.
    Callers `return err` when the second element is set.
    """
    if not raw:
        return None, (jsonify({"success": False, "error": "No path provided"}), 400)
    try:
        return _paired_sandbox().resolve(raw, need=need), None
    except SandboxViolation:
        return None, (jsonify(_SANDBOX_DENIED), 403)

# --- PERSISTENCE HELPERS ---
def load_paired_devices():
    global paired_devices, valid_tokens
    if PAIRED_DEVICES_FILE.exists():
        try:
            with open(PAIRED_DEVICES_FILE) as f:
                paired_devices = json.load(f)
                for dev in paired_devices.values():
                    valid_tokens.add(dev["token"])
        except Exception as e:
            print(f"Error loading paired devices: {e}")

def save_paired_devices():
    try:
        with open(PAIRED_DEVICES_FILE, 'w') as f:
            json.dump(paired_devices, f, indent=4)
    except Exception as e:
        print(f"Error saving paired devices: {e}")

load_paired_devices()

# --- [UPDATE] RESOURCE MONITORING THREAD ---
resource_usage_history = {"cpu": [], "ram": [], "timestamps": []}
current_system_stats = {
    "cpu_percent": 0.0,
    "ram_percent": 0.0,
    "ram_total": 0.0,
    "ram_used": 0.0,
    "disk_percent": 0.0,
    "disk_total": 0.0,
    "disk_used": 0.0,
    "battery_percent": 100,
    "battery_plugged": True
}

def monitor_resources():
    global current_system_stats
    # Baseline for cpu_percent
    psutil.cpu_percent(interval=None)

    while True:
        try:
            # interval=None is non-blocking, returns usage since last call
            cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()

            # Disk usage can be slow on some systems, try-catch it specifically
            try:
                disk = psutil.disk_usage('/')
                d_percent = disk.percent
                d_total = round(disk.total / (1024**3), 2)
                d_used = round(disk.used / (1024**3), 2)
            except:
                d_percent, d_total, d_used = 0, 0, 0

            ram = vm.percent
            battery = None
            try:
                battery = psutil.sensors_battery()
            except: pass

            current_system_stats = {
                "cpu_percent": cpu,
                "ram_percent": ram,
                "ram_total": round(vm.total / (1024**3), 2),
                "ram_used": round(vm.used / (1024**3), 2),
                "disk_percent": d_percent,
                "disk_total": d_total,
                "disk_used": d_used,
                "battery_percent": battery.percent if battery else 100,
                "battery_plugged": battery.power_plugged if battery else True,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }

            # Broadcast via WebSockets
            socketio.emit('system_stats', current_system_stats)

            # Keep history for charts
            resource_usage_history["cpu"].append(cpu)
            resource_usage_history["ram"].append(ram)
            resource_usage_history["timestamps"].append(current_system_stats["timestamp"])

            if len(resource_usage_history["cpu"]) > 30:
                resource_usage_history["cpu"].pop(0)
                resource_usage_history["ram"].pop(0)
                resource_usage_history["timestamps"].pop(0)
        except Exception as e:
            print(f"Stats Error: {e}")
        time.sleep(2)

def warm_up_engines():
    """Pre-loads heavy libraries in the background so features are instant."""
    try:
        # Give the server a moment to start responding to pings
        time.sleep(2)
        _load_automation()
        _load_media_engine()
        _load_audio_engine()
    except Exception as e:
        print(f"Warming Error: {e}")

# Start background workers
threading.Thread(target=monitor_resources, daemon=True).start()
threading.Thread(target=warm_up_engines, daemon=True).start()

# Ensure directories and persistence files exist
if not MACROS_FILE.parent.exists():
    MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)

if not MACROS_FILE.exists():
    with open(MACROS_FILE, 'w') as f:
        json.dump([], f)

# Default Settings & Battery Threshold Initialization
DEFAULT_SETTINGS = {
    "auto_clipboard_sync": False,
    "clipboard_sync_direction": "manual",
    "server_port": 5000,
    "device_name": "My PC",
    "battery_alert_threshold": 20,
    "battery_alert_enabled": False,
    "notifications_enabled": True
}

if not SETTINGS_FILE.exists():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(DEFAULT_SETTINGS, f, indent=4)
    battery_threshold = 20
else:
    with open(SETTINGS_FILE) as f:
        current_settings = json.load(f)
        battery_threshold = current_settings.get("battery_alert_threshold", 20)

@app.route('/ping', methods=['GET'])
@public_route
def ping():
    return jsonify({
        "message": "pong",
        "status": "ok",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "version": NODE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
    })

# --- SECURITY & LOGGING MIDDLEWARE ---

# Unauthenticated surface. Derived from ``@public_route`` (P1-S3), never a
# hand-maintained list of function names — renaming a view cannot silently
# expose it (audit S-04). Tests assert this equals EXPECTED_PUBLIC_ENDPOINTS.
class _PublicEndpoints:
    def __iter__(self):
        return iter(public_endpoint_names(app.view_functions))

    def __eq__(self, other: object) -> bool:
        return public_endpoint_names(app.view_functions) == frozenset(other)  # type: ignore[arg-type]

PUBLIC_ENDPOINTS = _PublicEndpoints()

# Media elements (Flutter's Image.network, <video>, <audio>, the PDF viewer)
# cannot attach custom headers, so the node accepts its own paired token in the
# query string for this small set of read-only streaming endpoints.
#
# This is a deliberate, narrow trade-off: query strings land in access logs and
# browser history. It is scoped to GET-only media routes and is retired entirely
# by the short-lived signed-URL scheme in
# docs/plans/security-hardening.md · Phase S2 (P2-S2).
MEDIA_TOKEN_ROUTES = frozenset({
    'files.preview_file', 'files.get_file_thumbnail',
    'transfer.download_file', 'transfer.download_chunked',
    'system.stream_screen',
})


@app.before_request
def verify_token_and_log():
    """Authenticate every request, then log it.

    ORDERING IS SECURITY-RELEVANT. Authentication must complete before the
    request body is touched. The previous implementation built its log entry —
    including `request.json.get('text')` — *before* checking the token, so a
    request with a non-JSON Content-Type died in Flask with 415 before it was
    ever authenticated, and an unauthenticated caller could make the node parse
    and log their body.

    Both are fixed here: authenticate first, parse never.
    """
    global last_screenshot_time

    # ── 0. Host header (DNS rebinding) ───────────────────────
    if not host_header_allowed(request.host):
        return jsonify({"success": False, "error": "invalid host"}), 400

    incoming_token = request.headers.get("X-Auth-Token")
    guest_token = request.args.get("token")

    # ── 1. Loopback shell ────────────────────────────────────
    if incoming_token == INTERNAL_TOKEN:
        return None

    # ── 2. Guest sessions ────────────────────────────────────
    # Guest tokens legitimately travel in the query string: the guest landing
    # page is opened in a plain browser that cannot set headers.
    if guest_token and request.path.startswith('/guest/'):
        if not guest_manager.validate_token(guest_token):
            return jsonify({"success": False, "error": "Invalid or expired guest token"}), 401
        return None

    # ── 3. Media streaming for a paired device ───────────────
    if (not incoming_token and guest_token
            and request.method == 'GET'
            and request.endpoint in MEDIA_TOKEN_ROUTES
            and guest_token in valid_tokens):
        incoming_token = guest_token

    # ── 4. Authentication ────────────────────────────────────
    authorized = (
        request.method == 'OPTIONS'                    # CORS preflight
        or is_public_view(app.view_functions.get(request.endpoint) if request.endpoint else None)
        or (incoming_token is not None and incoming_token in valid_tokens)
    )

    if not authorized:
        _record_command(success=False, details="unauthorized")
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    # ── 5. Rate limiting, AFTER authentication ───────────────
    # Previously the screenshot cooldown ran first, so an unauthenticated caller
    # could hold the cooldown open and deny screenshots to the legitimate user.
    if request.path == '/screenshot':
        now = time.time()
        if 'last_screenshot_time' in globals() and now - last_screenshot_time < 1.0:
            return jsonify({"success": False, "error": "Cooldown active"}), 429
        last_screenshot_time = now

    # ── 6. Audit log ─────────────────────────────────────────
    # Log the FACT of an action, never its content. The old entry recorded the
    # first 20 characters of everything sent to /type — i.e. passwords and 2FA
    # codes — to a log rendered in the desktop UI and persisted to disk
    # (audit S-15). Redaction by field class is P3-S1; this removes the leak now.
    details = ""
    if request.path == '/files/download':
        # Only the basename, and only of a path the caller already supplied.
        details = f"file:{os.path.basename(request.args.get('path', ''))}"
    elif request.path == '/type':
        body = request.get_json(silent=True) or {}
        details = f"keys:{len(str(body.get('text', '')))}"
    elif request.path == '/apps/launch':
        body = request.get_json(silent=True) or {}
        details = f"app:{os.path.basename(str(body.get('path', '')))}"

    _record_command(success=True, details=details)
    return None


def _record_command(success: bool, details: str = "") -> None:
    """Append to the bounded in-memory command history.

    Bounded so that spamming requests cannot exhaust node memory — the concern
    the old `[CHAOS FIX]` comment was reaching for.
    """
    command_history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": request.path,
        "method": request.method,
        "source_ip": request.remote_addr,
        "success": success,
        "details": details,
    })
    if len(command_history) > 500:
        del command_history[:len(command_history) - 500]

# --- HELPERS ---

def get_local_ip():
    """Returns IP from interface with active internet connectivity (default gateway). No hardcoded ranges."""
    try:
        all_addrs = psutil.net_if_addrs()
        all_stats = psutil.net_if_stats()

        # Helper: Check if IP is private (not loopback or link-local)
        def is_private_ip(ip):
            if ip.startswith('127.') or ip.startswith('169.254.'):
                return False
            # Private ranges: 10.x, 172.16-31.x, 192.168.x
            if ip.startswith('10.'):
                return True
            if ip.startswith('172.'):
                parts = ip.split('.')
                if len(parts) >= 2:
                    try:
                        second_octet = int(parts[1])
                        if 16 <= second_octet <= 31:
                            return True
                    except ValueError:
                        pass
            if ip.startswith('192.168.'):
                return True
            return False

        # STRATEGY: Active route detection - returns IP from interface with internet connectivity
        # This correctly identifies the real internet-connected adapter (USB tether, WiFi, LAN)
        # and ignores virtual adapters (VirtualBox, Hyper-V) that are UP but not connected
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.254.254.254', 1))
            ip = s.getsockname()[0]
            if is_private_ip(ip):
                return ip
        except Exception:
            pass
        finally:
            s.close()

        # Fallback: Return first UP interface with private IP if active route detection fails
        # Sorted order ensures consistent selection across restarts
        for iface_name in sorted(all_addrs.keys()):
            # Skip disconnected interfaces
            if iface_name not in all_stats or not all_stats[iface_name].isup:
                continue

            # Get IPv4 from this connected interface
            if iface_name in all_addrs:
                for addr in all_addrs[iface_name]:
                    if addr.family == socket.AF_INET and is_private_ip(addr.address):
                        return addr.address

        # Last resort: any private IP from any interface
        for iface_name in sorted(all_addrs.keys()):
            for addr in all_addrs[iface_name]:
                if addr.family == socket.AF_INET and is_private_ip(addr.address):
                    return addr.address

        return "127.0.0.1"
    except Exception:
        return "127.0.0.1"

def set_volume(change):
    if not WINDOWS or not AudioUtilities:
        return False
    try:
        # [FIX] Initialize COM for this thread
        ctypes.windll.ole32.CoInitialize(None)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        current_volume = volume.GetMasterVolumeLevelScalar()
        new_volume = max(0.0, min(1.0, current_volume + change))
        volume.SetMasterVolumeLevelScalar(new_volume, None)
        return True
    except Exception:
        return False
    finally:
        ctypes.windll.ole32.CoUninitialize()

def get_unique_path(target_path):
    path = Path(target_path)
    if not path.exists():
        return str(path)
    parent = path.parent
    name = path.stem
    ext = path.suffix
    counter = 1
    while (parent / f"{name} ({counter}){ext}").exists():
        counter += 1
    return str(parent / f"{name} ({counter}){ext}")

def get_human_readable_time(seconds: int) -> str:
    """Convert seconds to human readable format."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"




















# --- COMMUNICATION CHANNEL TO UI ---
ui_queue = queue.Queue()

def log_to_ui(action, device="Phone"):
    payload = {"action": action, "device": device, "time": datetime.now().strftime("%H:%M")}
    ui_queue.put(payload)
    # [LEVEL 3] Instant update via WebSockets
    socketio.emit('log_event', payload)































import shutil  # noqa: F401 — used by rewired route views














# --- SCREEN RECORDING ENGINE ---

def recording_worker():
    global recording_state
    _load_media_engine()
    try:
        with mss.mss() as sct:
            # Get screen dimensions
            monitor = sct.monitors[1] # Primary monitor
            width = monitor["width"]
            height = monitor["height"]

            # Define the codec and create VideoWriter object
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(recording_state["filepath"], fourcc, 10.0, (width, height))

            last_time = time.time()

            while recording_state["is_recording"]:
                if recording_state["is_paused"]:
                    time.sleep(0.5)
                    continue

                # Capture screen
                img = sct.grab(monitor)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                # Write frame
                out.write(frame)

                # Control FPS (Roughly 10 FPS)
                time.sleep(max(0, 0.1 - (time.time() - last_time)))
                last_time = time.time()

            out.release()
    except Exception as e:
        print(f"Recording Error: {e}")
        recording_state["is_recording"] = False























def build_startup_banner(local_ip: str) -> str:
    """Return the text the node prints when started directly.

    SECURITY: this must never contain INTERNAL_TOKEN or PAIRING_CODE.

    It used to print both:

        print(f"PAIRING KEY: {PAIRING_CODE}")
        print(f"INTERNAL BYPASS TOKEN: {INTERNAL_TOKEN}")

    Printing the token is a credential leak, because stdout is not private:
    `backend_manager.dart` pipes the child process's stdout, so the token lands in
    the Flutter shell's log buffer; on Windows a console window makes it visible to
    anyone who can see the screen; and if the node is run under a service manager
    or a CI job, stdout is captured to disk. A per-install token written to a
    0600 file is worthless if the same process then echoes it to a world-readable
    log.

    Printing the pairing code is worse in one specific way: it defeats the entire
    threat model of the six-digit code, which exists so that *physical or visual*
    proximity to the host is required to pair. Shoulder-surfing a terminal is
    exactly the attack it is meant to stop.

    Both values are already available where they are actually needed — the shell
    reads the token from `<appdata>/Cypher/internal_token`, and the pairing code is
    shown on the host's own screen by the desktop UI. Nothing is lost by removing
    them here.

    This is a function rather than inline `print()` calls so that
    tests/test_security.py can assert on the banner directly. Previously the test
    could only pass vacuously, because it never executed the `__main__` block.
    """
    token_path = get_config_path("internal_token")
    return "\n".join([
        "-" * 50,
        "CYPHER PC SERVER",
        f"IP: {local_ip}",
        f"Port: {SERVER_PORT}",
        "",
        "Pairing code: shown on this machine's screen (desktop UI / tray).",
        f"Auth token:   {token_path}  (mode 0600, read by the desktop shell)",
        "",
        "Secrets are deliberately not printed to stdout: this process's stdout",
        "is piped and logged by the desktop shell.",
        "-" * 50,
    ])


from .routes import register_blueprints
register_blueprints(app)

if __name__ == '__main__':
    print(build_startup_banner(get_local_ip()))
    # host="0.0.0.0" is the documented open finding S-07/P1-S4: the node must be
    # reachable from the phone on the LAN. Do not change this to loopback.
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # noqa: S104
