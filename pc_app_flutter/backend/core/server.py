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
from flask import Flask, jsonify, request, send_file, Response, stream_with_context
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

app = Flask(__name__)
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
from .sandbox import Sandbox, SandboxViolation, is_path_in_folders
from .auth import is_public_view, public_endpoint_names, public_route

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
    return jsonify({"message": "pong", "status": "ok", "timestamp": datetime.now().strftime("%H:%M:%S")})

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
    'preview_file', 'get_file_thumbnail', 'download_file',
    'download_chunked', 'stream_screen',
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

# --- NEW PUBLIC ENDPOINT ---

@app.route('/connect-code', methods=['GET', 'POST'])
def get_connect_code():
    """Returns or rotates the current pairing code."""
    global PAIRING_CODE
    if request.method == 'POST':
        PAIRING_CODE = _generate_dynamic_code()
        add_activity("Security", "Pairing code was rotated for enhanced security.", category="Connections")
    return jsonify({"code": PAIRING_CODE})

# --- SETTINGS ENDPOINTS ---

@app.route('/settings', methods=['GET', 'POST'])
def handle_settings():
    global battery_threshold
    if request.method == 'GET':
        try:
            # 1. Load basic settings
            settings = {}
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    settings = json.load(f)
            else:
                settings = DEFAULT_SETTINGS.copy()

            # 2. Add shared folders from the master config file
            settings["shared_folders"] = _get_shared_folders()

            return jsonify(settings)
        except Exception as e:
            print(f"SERVER ERROR: Getting settings: {e}")
            return jsonify(DEFAULT_SETTINGS)

    new_settings = request.json
    try:
        # Handle shared folders separately if they are in the request
        if "shared_folders" in new_settings:
            shared = new_settings.pop("shared_folders")
            # Load existing config or start fresh
            config_data = {}
            if SHARED_FOLDERS_FILE.exists():
                with open(SHARED_FOLDERS_FILE) as f:
                    config_data = json.load(f)

            config_data["shared_folders"] = shared

            with open(SHARED_FOLDERS_FILE, 'w') as f:
                json.dump(config_data, f, indent=4)

        if not new_settings:
            return jsonify({"success": True})

        with open(SETTINGS_FILE, 'r+') as f:
            current = json.load(f)

            old_name = current.get("device_name", socket.gethostname())
            new_name = new_settings.get("device_name")

            current.update(new_settings)
            battery_threshold = current.get("battery_alert_threshold", battery_threshold)

            f.seek(0)
            json.dump(current, f, indent=4)
            f.truncate()

        # Live discovery update if name changed
        if new_name and new_name != old_name:
            try:
                start_fn, get_inst_fn = get_discovery_node()
                disc = get_inst_fn()
                if disc:
                    disc.update_name(new_name)
                    log_to_ui(f"Discovery name updated to: {new_name}")
            except Exception as e:
                print(f"Discovery update failed: {e}")

        return jsonify({"success": True, "action": "settings_updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- PHONE CLIPBOARD BUFFER ---

@app.route('/clipboard/phone', methods=['GET', 'POST'])
def handle_phone_clipboard():
    global phone_clipboard
    if request.method == 'POST':
        content = request.json.get("text", "")
        # Check if content is a base64 image
        if content.startswith("data:image"):
             phone_clipboard = {
                "content": content,
                "type": "image",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            phone_clipboard = {
                "content": content,
                "type": "text",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        return jsonify({"success": True, "action": "phone_clipboard_saved"})

    return jsonify({"success": True, **phone_clipboard})

@app.route('/clipboard/paste-from-phone', methods=['POST'])
def paste_from_phone():
    if not WINDOWS or not pyperclip:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    if phone_clipboard["content"]:
        log_to_ui(f"Pasted {phone_clipboard.get('type', 'text')} from Phone")
        if phone_clipboard.get("type") == "image":
            # Image setting logic can be complex via native API, saving temp for now
            try:
                 header, encoded = phone_clipboard["content"].split(",", 1)
                 data = base64.b64decode(encoded)
                 img = Image.open(io.BytesIO(data))
                 # [CHAOS FIX] Save to a proper path or use native clipboard
                 img.save(get_app_data_dir() / "temp_clip.png")
            except: pass

        pyperclip.copy(phone_clipboard["content"])
        return jsonify({"success": True, "action": "pasted_to_pc"})
    return jsonify({"success": False, "error": "Phone buffer is empty"}), 400

@app.route('/clipboard/pc', methods=['GET'])
def get_pc_clipboard():
    """Returns the current PC clipboard (Text or Image)."""
    if not WINDOWS or not ImageGrab:
        return jsonify({"type": "text", "content": ""})
    try:
        # Check for image first
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return jsonify({
                "type": "image",
                "content": f"data:image/png;base64,{img_str}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        # Fallback to text
        text = pyperclip.paste()
        return jsonify({
            "type": "text",
            "content": text or "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- CONNECTION EVENTS ---

@app.route('/events', methods=['GET'])
def get_events():
    return jsonify(connection_events)

@app.route('/events/connected', methods=['POST'])
def log_connect():
    device = request.json.get("device_name", "Unknown Device")
    event = {"event": "connected", "device": device, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    connection_events.append(event)
    if len(connection_events) > 50: connection_events.pop(0)
    return jsonify({"success": True})

@app.route('/events/disconnected', methods=['POST'])
def log_disconnect():
    event = {"event": "disconnected", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    connection_events.append(event)
    if len(connection_events) > 50: connection_events.pop(0)
    return jsonify({"success": True})

# --- PAIRING ENDPOINTS ---

@app.route('/pair_device', methods=['POST'])
@public_route
def pair_device():
    # `global` must precede the first use of the name in this function, otherwise
    # it is a SyntaxError ("used prior to global declaration") that takes down the
    # whole module at import time — the exact failure mode of audit finding F-01.
    global PAIRING_CODE

    data = request.get_json(silent=True) or {}
    client_code = str(data.get("pairing_code", ""))
    device_id = data.get("device_id")
    device_name = data.get("device_name", "Unknown Device")

    if not device_id:
        return jsonify({"success": False, "error": "device_id is required"}), 400

    client_ip = request.remote_addr or "unknown"

    # Throttle BEFORE comparing, otherwise a locked-out attacker can still
    # redeem a code they guessed while locked out.
    allowed, retry_after = _pairing_throttle(client_ip)
    if not allowed:
        add_activity(
            "Pairing Blocked",
            f"{client_ip} exceeded the attempt limit and was locked out.",
            category="Security",
            is_urgent=True,
        )
        response = jsonify({
            "success": False,
            "error": "Too many pairing attempts. Try again later.",
            "retry_after": retry_after,
        })
        response.headers["Retry-After"] = str(retry_after)
        return response, 429

    # Constant-time comparison: a plain `==` short-circuits on the first
    # differing character and leaks the code one digit at a time over a LAN.
    if not hmac.compare_digest(client_code, PAIRING_CODE):
        return jsonify({"success": False, "error": "Invalid pairing code"}), 401

    auth_token = secrets.token_hex(32)
    paired_devices[device_id] = {
        "device_name": device_name,
        "token": auth_token,
        "paired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_ip": client_ip,
    }
    valid_tokens.add(auth_token)
    save_paired_devices()

    # Rotate the code on every successful pairing so it is single-use, and
    # clear the throttle for this address now that it is authenticated.
    PAIRING_CODE = _generate_dynamic_code()
    _pairing_reset(client_ip)

    add_activity(
        "Device Paired",
        f"Successfully linked {device_name} via secure bridge.",
        category="Connections"
    )
    return jsonify({"success": True, "token": auth_token}), 200

@app.route('/paired-devices', methods=['GET'])
def get_paired_devices():
    devices = [{"device_id": k, "device_name": v["device_name"], "token": v["token"]} for k, v in paired_devices.items()]
    return jsonify(devices), 200

@app.route('/unpair', methods=['POST'])
def unpair_device():
    device_id = request.json.get("device_id")
    if device_id in paired_devices:
        valid_tokens.discard(paired_devices[device_id]["token"])
        del paired_devices[device_id]
        save_paired_devices()
        return jsonify({"success": True, "action": "unpaired"})
    return jsonify({"success": False, "error": "Device not found"}), 404

# --- SYSTEM, POWER & PROCESSES ---

@app.route('/status', methods=['GET'])
@public_route
def get_status():
    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
            display_name = settings.get("device_name", socket.gethostname())
    except:
        display_name = socket.gethostname()

    return jsonify({
        "pc_name": display_name,
        "status": "online",
        "platform": platform.system().lower()
    })

@app.route('/connection-info', methods=['GET'])
def get_connection_info():
    """Diagnostic endpoint showing current connection type and IP."""
    try:
        local_ip = get_local_ip()
        all_addrs = psutil.net_if_addrs()
        all_stats = psutil.net_if_stats()

        # Detect connection type
        conn_type = "UNKNOWN"
        if local_ip:
            if local_ip.startswith('192.168.19.'):
                conn_type = "USB_TETHERING"
            elif local_ip.startswith('192.168.42.'):
                conn_type = "USB_TETHERING_ALT"
            elif local_ip.startswith('192.168.235.'):
                conn_type = "USB_TETHERING_VB"
            elif local_ip.startswith('192.168.43.'):
                conn_type = "ANDROID_HOTSPOT"
            elif local_ip.startswith('192.168.137.'):
                conn_type = "WINDOWS_HOTSPOT"
            elif local_ip.startswith('10.') or local_ip.startswith('172.') or (local_ip.startswith('192.168.') and not local_ip.startswith('192.168.1')):
                conn_type = "WIFI_OR_LAN"

        # Collect all UP interfaces
        up_interfaces = []
        for iface_name in sorted(all_addrs.keys()):
            if iface_name in all_stats and all_stats[iface_name].isup:
                for addr in all_addrs[iface_name]:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        up_interfaces.append({
                            "name": iface_name,
                            "ip": addr.address,
                            "is_active": addr.address == local_ip
                        })

        return jsonify({
            "ip": local_ip,
            "connection_type": conn_type,
            "up_interfaces": up_interfaces,
            "device_name": socket.gethostname()
        })
    except Exception as e:
        return jsonify({"error": str(e), "ip": get_local_ip()}), 500

@app.route('/system-stats', methods=['GET'])
def get_system_stats():
    return jsonify(current_system_stats)

@app.route('/system/optimize', methods=['POST'])
def optimize_system():
    """Real system optimization: temp cleanup, RAM working set trim, DNS flush."""
    freed_bytes = 0
    actions = []

    try:
        if WINDOWS:
            # 1. Flush DNS cache
            subprocess.run("ipconfig /flushdns", shell=True, capture_output=True)
            actions.append("DNS cache flushed")

            # 2. Clear %TEMP% — files AND subdirectories
            temp_path = os.environ.get('TEMP') or os.environ.get('TMP')
            if temp_path and os.path.isdir(temp_path):
                for entry in os.listdir(temp_path):
                    entry_path = os.path.join(temp_path, entry)
                    try:
                        if os.path.isfile(entry_path):
                            size = os.path.getsize(entry_path)
                            os.remove(entry_path)
                            freed_bytes += size
                        elif os.path.isdir(entry_path):
                            import shutil
                            for root, dirs, files in os.walk(entry_path):
                                for f in files:
                                    try:
                                        fp = os.path.join(root, f)
                                        freed_bytes += os.path.getsize(fp)
                                    except: pass
                            shutil.rmtree(entry_path, ignore_errors=True)
                    except: pass
                actions.append(f"Temp files cleared ({freed_bytes // (1024*1024)} MB freed)")

            # 3. Clear Windows prefetch (speeds up older HDDs, harmless on SSDs)
            prefetch = r"C:\Windows\Prefetch"
            if os.path.isdir(prefetch):
                for f in os.listdir(prefetch):
                    try:
                        fp = os.path.join(prefetch, f)
                        if os.path.isfile(fp):
                            os.remove(fp)
                    except: pass
                actions.append("Prefetch cache cleared")

            # 4. Trim RAM working sets of all processes (the real "memory optimizer")
            # This releases unused RAM pages back to the OS — same as what RAM cleaner apps do
            try:
                import ctypes
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_QUERY_INFORMATION = 0x0400

                # NOTE: this block used to open the process token with
                # TOKEN_ADJUST_PRIVILEGES and declare `SE_DEBUG = 20`, but never
                # called AdjustTokenPrivileges — so SeDebugPrivilege was never
                # actually enabled and the dead constant was flagged by ruff
                # (F841). Removing it changes no behaviour.
                #
                # EmptyWorkingSet succeeds on processes the node's user already
                # owns. Protected and other-user processes fail the OpenProcess
                # call below and are skipped, which is the correct outcome:
                # silently failing is better than requesting debug privileges
                # over the whole system to trim RAM.

                trimmed = 0
                skipped = 0
                for proc in psutil.process_iter(['pid']):
                    handle = None
                    try:
                        handle = ctypes.windll.kernel32.OpenProcess(
                            PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, proc.info['pid']
                        )
                        if handle:
                            ctypes.windll.psapi.EmptyWorkingSet(handle)
                            trimmed += 1
                        else:
                            skipped += 1
                    except OSError:
                        skipped += 1
                    finally:
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                actions.append(
                    f"RAM working sets trimmed ({trimmed} processes, {skipped} inaccessible)"
                )
            except Exception as e:
                print(f"RAM trim failed: {e}")

        freed_mb = freed_bytes // (1024 * 1024)
        summary = " | ".join(actions) if actions else "Optimization complete"
        add_activity("System Optimized", summary, category="Commands")
        log_to_ui("System Optimization Complete")
        return jsonify({"success": True, "freed_mb": freed_mb, "actions": actions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/shared', methods=['GET'])
def get_shared_folders_list():
    """Returns just the shared folders for the PC UI."""
    try:
        shared = _get_shared_folders()
        data = []
        home = Path.home()
        for path in shared:
            full_path = path
            # Expand standard folder names if they aren't absolute paths
            if path in ["Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures"]:
                full_path = str(home / path)

            if os.path.exists(full_path):
                data.append({
                    "name": os.path.basename(path) or path,
                    "path": full_path,
                    "full_access": True # Default for now
                })
        return jsonify(data)
    except:
        return jsonify([])

@app.route('/security/sessions', methods=['GET'])
def get_security_sessions():
    """Returns active guest sessions."""
    sessions = get_guest_manager().get_all_active_sessions()
    return jsonify(sessions)

# --- [UPDATE] RESOURCE TRENDS ---
@app.route('/system/resource-trends', methods=['GET'])
def get_resource_trends():
    """Returns the last 30 sampled resource data points for charting."""
    return jsonify(resource_usage_history)

@app.route('/uptime', methods=['GET'])
def get_uptime():
    boot_time_timestamp = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_time_timestamp)
    uptime_seconds = int(time.time() - boot_time_timestamp)
    return jsonify({
        "uptime_seconds": uptime_seconds,
        "uptime_readable": str(timedelta(seconds=uptime_seconds)),
        "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S")
    })

# --- COMMUNICATION CHANNEL TO UI ---
ui_queue = queue.Queue()

def log_to_ui(action, device="Phone"):
    payload = {"action": action, "device": device, "time": datetime.now().strftime("%H:%M")}
    ui_queue.put(payload)
    # [LEVEL 3] Instant update via WebSockets
    socketio.emit('log_event', payload)

@app.route('/power/shutdown', methods=['POST'])
def shutdown():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    active = [t for t in active_transfers.values() if t.get("status") == "receiving"]
    if active:
        return jsonify({"success": False, "error": "Cannot shutdown while transfers are active"}), 409

    add_activity("System Shutdown", "A remote shutdown command was initiated.", category="Commands", is_urgent=True)
    log_to_ui("Shutdown Requested")
    os.system("shutdown /s /t 5")
    return jsonify({"success": True, "action": "shutdown"})

@app.route('/power/restart', methods=['POST'])
def restart():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Restart Requested")
    os.system("shutdown /r /t 5")
    return jsonify({"success": True, "action": "restart"})

@app.route('/power/sleep', methods=['POST'])
def sleep():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Sleep Mode Activated")
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return jsonify({"success": True, "action": "sleep"})

@app.route('/power/hibernate', methods=['POST'])
def hibernate():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Hibernation Requested")
    os.system("shutdown /h")
    return jsonify({"success": True, "action": "hibernate"})

@app.route('/power/lock', methods=['POST'])
def lock():
    if not WINDOWS or not ctypes:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Locking Workstation")
    try:
        ctypes.windll.user32.LockWorkStation()
        return jsonify({"success": True, "action": "lock"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/processes', methods=['GET'])
def get_processes():
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            pinfo = proc.info
            procs.append({
                "pid": pinfo['pid'],
                "name": pinfo['name'],
                "cpu_percent": pinfo['cpu_percent'],
                "memory_mb": round(pinfo['memory_info'].rss / (1024 * 1024), 2),
                "status": pinfo['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    return jsonify(procs)

@app.route('/processes/kill', methods=['POST'])
def kill_process():
    pid = request.json.get("pid")
    try:
        proc = psutil.Process(pid)
        # Prevent killing self or system critical processes (simple check)
        if proc.pid == os.getpid():
            return jsonify({"success": False, "error": "Cannot kill CYPHER core process"}), 403

        proc.terminate()
        gone, alive = psutil.wait_procs([proc], timeout=2)
        if alive:
            proc.kill()
        return jsonify({"success": True, "pid": pid})
    except psutil.NoSuchProcess:
        return jsonify({"success": True, "note": "Process already gone"})
    except psutil.AccessDenied:
        return jsonify({"success": False, "error": "Access Denied: Try running CYPHER as Admin"}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# --- APP LAUNCHER ---

@app.route('/apps', methods=['GET'])
def get_installed_apps():
    if not WINDOWS:
        return jsonify([]), 200
    apps = []
    search_paths = [
        Path(os.environ.get('ProgramData', '')) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get('AppData', '')) / "Microsoft/Windows/Start Menu/Programs"
    ]
    for path in search_paths:
        if path.exists():
            for file in path.rglob("*.lnk"):
                apps.append({"name": file.stem, "path": str(file)})
    return jsonify(apps)

@app.route('/apps/launch', methods=['POST'])
def launch_application():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    path = (request.json or {}).get("path")
    if not path:
        return jsonify({"success": False, "error": "No path provided"}), 400
    # Launch is a filesystem operation: only Start Menu shortcuts the node itself
    # enumerated, or a path inside a shared folder. os.startfile() on arbitrary
    # client input was arbitrary code execution (audit S-03).
    launch_roots = list(_get_shared_folders())
    launch_roots.append(str(Path(os.environ.get('ProgramData', '')) / "Microsoft/Windows/Start Menu/Programs"))
    launch_roots.append(str(Path(os.environ.get('AppData', '')) / "Microsoft/Windows/Start Menu/Programs"))
    try:
        resolved = Sandbox(launch_roots).resolve(path, need="execute")
    except SandboxViolation:
        return jsonify(_SANDBOX_DENIED), 403
    os.startfile(str(resolved))
    app_name = resolved.stem
    add_activity("App Launched", f"Successfully initialized {app_name}.", category="Commands")
    return jsonify({"success": True, "app": app_name})

@app.route('/apps/close', methods=['POST'])
def close_application():
    """Tries to find and close a window by ID or title."""
    _load_automation()
    if not WINDOWS or not gw:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400

    app_name = request.json.get("name")
    window_id = request.json.get("id")

    try:
        if window_id:
            for win in gw.getAllWindows():
                if win._hWnd == window_id:
                    win.close()
                    add_activity("App Closed", f"Terminated process instance {window_id}.", category="Commands")
                    return jsonify({"success": True, "id": window_id})

        if app_name:
            found = False
            # 1. Try closing via Window Title
            for win in gw.getWindowsWithTitle(app_name):
                try:
                    win.close()
                    found = True
                except: pass

            # 2. Try closing via Process Name if window close failed
            if not found:
                for proc in psutil.process_iter(['name']):
                    try:
                        if app_name.lower() in proc.info['name'].lower():
                            proc.terminate()
                            found = True
                    except: pass

            if found:
                add_activity("App Closed", f"Terminated {app_name}.", category="Commands")
                return jsonify({"success": True, "name": app_name})
            return jsonify({"success": False, "error": "App not found"}), 404

        return jsonify({"success": False, "error": "No identifier provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- NETWORK & WINDOW INFO ---

@app.route('/network', methods=['GET'])
def get_network_info():
    net = psutil.net_io_counters()
    return jsonify({
        "bytes_sent_mb": round(net.bytes_sent / (1024 * 1024), 2),
        "bytes_received_mb": round(net.bytes_recv / (1024 * 1024), 2),
        "pc_ip": get_local_ip(),
        "hostname": socket.gethostname()
    })

@app.route('/activewindow', methods=['GET'])
def get_active_window():
    if not WINDOWS or not gw:
        return jsonify({"window_title": "N/A", "process_name": "N/A"})
    try:
        win = gw.getActiveWindow()
        return jsonify({
            "window_title": win.title if win else "None",
            "process_name": "N/A",
            "id": win._hWnd if win else None
        })
    except:
        return jsonify({"window_title": "Unknown"})

@app.route('/system/stream')
def stream_screen():
    """High-speed MJPEG screen stream for 'Remote View'."""
    # BUGFIX: this route relied on the background warm_up_engines() thread having
    # already finished. A client that opened Remote View within the first couple
    # of seconds of node start hit `mss is None` -> AttributeError raised outside
    # the inner try/except, which killed the stream with no error surfaced to the
    # user. Load synchronously and fail loudly instead.
    _load_media_engine()
    if mss is None or Image is None:
        return jsonify({
            "success": False,
            "error": "Screen streaming is unavailable: capture dependencies missing",
        }), 503

    def generate():
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while True:
                try:
                    img = sct.grab(monitor)
                    frame = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                    # Scale down for faster streaming over local network
                    frame.thumbnail((1280, 720))

                    output = io.BytesIO()
                    frame.save(output, format="JPEG", quality=50)

                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + output.getvalue() + b'\r\n')

                    # Performance: ~20 FPS limit to keep CPU sane
                    time.sleep(0.05)
                except:
                    break

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/system/active-windows', methods=['GET'])
def get_active_windows():
    """Returns a list of all visible application windows with process context."""
    _load_automation()
    if not WINDOWS or not win32gui:
        return jsonify({"windows": []})
    try:
        import win32process
        import win32con
        windows = []

        def enum_handler(hwnd, lparam):
            # 1. Must be visible
            if not win32gui.IsWindowVisible(hwnd):
                return

            # 2. Must have a title
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return

            # 3. Filter out common system tool windows/shells
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return

            # 4. Must have dimensions (ignore tray icons/cloaked windows)
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w <= 10 or h <= 10:
                return

            path = ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                path = proc.exe()
                # Filter out obvious system shells that aren't user apps
                if "System32" in path or "WindowsApps" in path:
                    if "ApplicationFrameHost" not in path: # Allow some WindowsApps
                        return
            except: pass

            windows.append({
                "title": title,
                "name": title,
                "id": hwnd,
                "path": path,
                "is_minimized": win32gui.IsIconic(hwnd),
                "is_maximized": win32gui.IsZoomed(hwnd)
            })

        win32gui.EnumWindows(enum_handler, None)

        # Sort by title for better UI experience
        windows.sort(key=lambda x: x['title'].lower())
        return jsonify({"windows": windows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/windows/focus', methods=['POST'])
def focus_window():
    """Brings a specific window to the foreground."""
    if not WINDOWS or not gw:
        return jsonify({"success": False, "error": "Platform not supported"}), 400

    hwnd = request.json.get("id")
    if not hwnd:
        return jsonify({"success": False, "error": "No window ID provided"}), 400

    try:
        # Use pygetwindow to find the specific window by handle
        all_wins = gw.getAllWindows()
        target = next((w for w in all_wins if str(w._hWnd) == str(hwnd)), None)

        if target:
            target.activate()
            if target.isMinimized:
                target.restore()
            log_to_ui(f"Focused Window: {target.title}")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Window not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/system/window-icon', methods=['GET'])
def get_window_icon():
    """Extracts the native icon from a window handle and returns it as an image."""
    _load_automation()
    if not WINDOWS or not win32gui:
        return jsonify({"error": "Not supported"}), 400

    hwnd = request.args.get('id', type=int)
    path = request.args.get('path')

    try:
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

        hicon = None
        if hwnd:
            # Try to get the window's own icon first
            res = win32gui.SendMessage(hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
            if not res:
                res = win32gui.GetClassLong(hwnd, win32con.GCL_HICON)
            hicon = res

        # If no hwnd or hwnd didn't have an icon, try the path
        if not hicon and path and os.path.exists(path):
            large, small = win32gui.ExtractIconEx(path, 0)
            if large:
                hicon = large[0]
                for h in small: win32gui.DestroyIcon(h)

        if not hicon:
            return jsonify({"error": "Icon not found"}), 404

        # Create device context and bitmap
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
        save_dc = hdc.CreateCompatibleDC()
        save_dc.SelectObject(hbmp)

        # Draw the icon
        win32gui.DrawIconEx(save_dc.GetSafeHdc(), 0, 0, hicon, ico_x, ico_y, 0, None, win32con.DI_NORMAL)

        # Convert to PIL
        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)

        # Final cleanup
        save_dc.DeleteDC()
        win32gui.DeleteObject(hbmp.GetHandle())

        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return Response(buffered.getvalue(), mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- [UPDATE] DISPLAY INFO ---
@app.route('/system/displays', methods=['GET'])
def get_display_info():
    """Detects primary and secondary monitor resolutions."""
    try:
        from screeninfo import get_monitors
        displays = []
        for m in get_monitors():
            displays.append({
                "name": m.name,
                "width": m.width,
                "height": m.height,
                "is_primary": m.is_primary
            })
        return jsonify(displays)
    except:
        return jsonify([{"name": "Default", "width": 1920, "height": 1080, "is_primary": True}])

# --- FILE SYSTEM ---

@app.route('/files', methods=['GET'])
def get_root_files():
    """Returns the user-configured shared folders. Nothing else.

    Used to also enumerate every logical drive and the user's Desktop/Documents/
    Downloads — which made the allowlist decorative. P1-S2: the filesystem API
    exposes only what the operator shared.
    """
    try:
        root_data = []
        home = Path.home()
        for path in _get_shared_folders():
            full_path = path
            if path in ["Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures"]:
                full_path = str(home / path)
            if os.path.exists(full_path):
                root_data.append({
                    "name": os.path.basename(path) or path,
                    "path": full_path,
                    "type": "folder",
                    "is_shared": True
                })
        return jsonify(root_data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/list', methods=['GET'])
def list_files_for_app():
    """Returns both directories and files for destination selection."""
    try:
        p_str = request.args.get('path', "")
        if not p_str or p_str == "":
            root_data = []
            for folder in _get_shared_folders():
                p = Path(folder)
                if p.exists():
                    root_data.append({
                        "name": p.name or str(p),
                        "path": str(p),
                        "is_dir": True,
                        "selectable": True
                    })
            return jsonify({"contents": root_data})

        p, err = _require_shared_path(p_str, need="read")
        if err:
            return err
        if not p.exists():
            return jsonify({"success": False, "error": "Path not found"}), 404

        items = []
        try:
            for item in p.iterdir():
                try:
                    if item.name.startswith('.') or item.name.startswith('$'): continue
                    is_dir = item.is_dir()
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "is_dir": is_dir,
                        "selectable": is_dir,
                        "extension": item.suffix.lower() if not is_dir else ""
                    })
                except (PermissionError, OSError): continue
        except Exception:
            pass # Return empty list rather than erroring out

        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return jsonify({"contents": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/browse', methods=['GET'])
def browse_files():
    try:
        path_str = request.args.get('path')
        p, err = _require_shared_path(path_str, need="read")
        if err:
            return err
        if not p.exists():
             return jsonify({"success": False, "error": "Path does not exist"}), 404
        items = []
        try:
            for count, item in enumerate(p.iterdir()):
                if count >= 5000: break
                try:
                    if item.name.startswith('$') or item.name.startswith('.'): continue
                    stats = item.stat()
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "type": "file" if item.is_file() else "folder",
                        "size": stats.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "extension": item.suffix.lower() if item.is_file() else ""
                    })
                except (PermissionError, OSError): continue
        except Exception:
            pass

        return jsonify(items)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/download/zip', methods=['POST'])
def download_files_zip():
    """Download multiple selected files as a single ZIP archive."""
    incoming_token = request.headers.get("X-Auth-Token")
    if not incoming_token or incoming_token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    paths = data.get('paths', [])

    if not paths:
        return jsonify({"success": False, "error": "No files selected"}), 400

    try:
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                try:
                    p = _paired_sandbox().resolve(path, need="read")
                except SandboxViolation:
                    return jsonify(_SANDBOX_DENIED), 403
                if p.exists() and p.is_file():
                    zf.write(str(p), arcname=p.name)

        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'cypher_batch_{timestamp}.zip'
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/upload-destinations', methods=['GET'])
def get_upload_destinations():
    """Get list of folders where files can be uploaded."""
    try:
        destinations = []
        for folder in _get_shared_folders():
            folder_path = Path(folder)
            if folder_path.exists():
                destinations.append({
                    "name": folder_path.name or str(folder_path),
                    "path": str(folder_path),
                    "icon": folder_path.name.lower()
                })

        return jsonify({"success": True, "destinations": destinations})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/browse-folders', methods=['GET'])
def browse_folders():
    """Browse subfolders in a given path for upload destination selection."""
    try:
        path_str = request.args.get('path')
        if not path_str:
            folders = []
            for folder in _get_shared_folders():
                folder_path = Path(folder)
                if folder_path.exists() and folder_path.is_dir():
                    folders.append({
                        "name": folder_path.name or str(folder_path),
                        "path": str(folder_path),
                        "is_dir": True,
                    })
            current = str(Path(_get_shared_folders()[0])) if _get_shared_folders() else ""
            return jsonify({"success": True, "folders": folders, "current_path": current})

        path, err = _require_shared_path(path_str, need="read")
        if err:
            return err

        if not path.exists() or not path.is_dir():
            return jsonify({"success": False, "error": "Invalid path"}), 400

        folders = []
        try:
            for item in sorted(path.iterdir()):
                try:
                    if item.is_dir() and not item.name.startswith('.'):
                        folders.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                            "is_dir": True,
                        })
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass

        # Get parent folder if not at root
        parent_path = None
        if str(path.parent) != str(path):
            parent_path = str(path.parent)

        return jsonify({
            "success": True,
            "folders": folders,
            "current_path": str(path),
            "parent_path": parent_path,
            "display_name": path.name or str(path)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/files/upload', methods=['POST'])
def upload_file_stream():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    files = request.files.getlist('file')
    destination = request.form.get('destination', '')

    # Resolve the destination against the allowlist BEFORE creating anything.
    # The previous code accepted an absolute path, called os.makedirs, then
    # checked a Windows denylist — so a paired device could create directories
    # anywhere on the disk (audit S-03 / F-13's sibling).
    if not destination:
        shared = _get_shared_folders()
        if not shared:
            return jsonify(_SANDBOX_DENIED), 403
        destination = shared[0]
    dest_path, err = _require_shared_path(destination, need="write")
    if err:
        return err
    dest = str(dest_path)
    os.makedirs(dest, exist_ok=True)

    from werkzeug.utils import secure_filename

    results = []
    for file in files:
        safe_name = secure_filename(file.filename or "")
        if not safe_name:
            results.append({"name": file.filename, "status": "error", "message": "invalid filename"})
            continue
        final_path = get_unique_path(os.path.join(dest, safe_name))
        temp_path = final_path + ".part" # Atomic upload pattern
        transfer_id = str(uuid.uuid4())
        active_transfers[transfer_id] = {
            "name": file.filename,
            "progress": 0,
            "status": "receiving",
            "start_time": time.time(),
            "speed": "0 KB/s"
        }

        try:
            # Atomic Save
            file.save(temp_path)
            if os.path.exists(temp_path):
                os.rename(temp_path, final_path)

            active_transfers[transfer_id]["progress"] = 100
            active_transfers[transfer_id]["status"] = "completed"

            add_activity(
                "File Received",
                f"Sync complete. Saved to {os.path.basename(dest)}.",
                category="Transfers",
                attachment=file.filename
            )

            log_to_ui(f"Received: {file.filename}")
            results.append({"name": file.filename, "status": "success"})
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path) # Cleanup broken file
            active_transfers[transfer_id]["status"] = "failed"
            results.append({"name": file.filename, "status": "error", "message": str(e)})

    return jsonify({"success": True, "files": results})

@app.route('/files/transfers', methods=['GET'])
def get_transfers():
    return jsonify(active_transfers)

@app.route('/files/download', methods=['GET'])
def download_file():
    path, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(path)
    if path and os.path.isfile(path):
        try:
            add_activity(
                "File Downloaded",
                f"A remote device accessed: {os.path.basename(path)}",
                category="Transfers"
            )
            return send_file(path, as_attachment=True)
        except Exception as e:
            log_event("DOWNLOAD_ERROR", {"path": path, "error": str(e)})
            return jsonify({"error": "Failed to stream file", "details": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@app.route('/files/download/chunked', methods=['GET'])
def download_chunked():
    global cancel_all_transfers
    cancel_all_transfers = False
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    try:
        f_test = open(path, "rb")
        f_test.close()
    except Exception as e:
        return jsonify({"error": "File is locked or inaccessible", "details": str(e)}), 403

    def generate():
        try:
            with open(path, "rb") as f:
                while not cancel_all_transfers:
                    chunk = f.read(1024 * 64)
                    if not chunk: break
                    yield chunk
        except Exception as e:
            log_event("STREAM_INTERRUPTED", {"path": path, "error": str(e)})
    return Response(stream_with_context(generate()), mimetype="application/octet-stream")

@app.route('/files/download/cancel', methods=['POST'])
def cancel_downloads():
    global cancel_all_transfers
    cancel_all_transfers = True
    log_to_ui("Downloads Cancelled")
    return jsonify({"success": True, "action": "cancelled"})

@app.route('/files/preview', methods=['GET'])
def preview_file():
    """Streams file for in-app preview with Range support and correct MIME types."""
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    size = os.path.getsize(path)
    range_header = request.headers.get('Range', None)

    if not range_header:
        return send_file(path, mimetype=mime, as_attachment=False)

    try:
        byte1, byte2 = 0, None
        m = re.search(r'(\d+)-(\d*)', range_header)
        g = m.groups()
        if g[0]: byte1 = int(g[0])
        if g[1]: byte2 = int(g[1])
        length = size - byte1
        if byte2 is not None:
            length = byte2 - byte1 + 1

        def generate():
            with open(path, 'rb') as f:
                f.seek(byte1)
                remaining = length
                while remaining > 0:
                    chunk_size = min(remaining, 1024 * 128)
                    chunk = f.read(chunk_size)
                    if not chunk: break
                    yield chunk
                    remaining -= len(chunk)

        rv = Response(generate(), 206, mimetype=mime, direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        return rv
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/files/thumbnail', methods=['GET'])
def get_file_thumbnail():
    """Generates a small preview for images."""
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path) or not Image:
        return jsonify({"error": "Not found"}), 404
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return jsonify({"error": "Unsupported"}), 400
        with Image.open(path) as img:
            img.thumbnail((128, 128))
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            buffered.seek(0)
            return send_file(buffered, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import shutil

@app.route('/files/delete', methods=['DELETE'])
def delete_file():
    resolved, err = _require_shared_path(request.args.get('path'), need="delete")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path):
        return jsonify({"success": False, "error": "Not found"}), 404

    try:
        if os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path)
        log_to_ui(f"Deleted: {os.path.basename(path)}")
        return jsonify({"success": True, "action": "deleted"})
    except PermissionError:
        return jsonify({"success": False, "error": "File is currently in use"}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- GUEST ACCESS ENDPOINTS (TIER 1, 2, 3) ---

@app.route('/guest/create', methods=['POST'])
def guest_create_session():
    """TIER 1: Create a guest session from authenticated device."""
    token = request.headers.get("X-Auth-Token")
    if not token or (token not in valid_tokens and token != INTERNAL_TOKEN):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    raw_folders = data.get("folders", [])
    duration = data.get("duration_minutes", 15)
    
    # [NEW] Normalize and Validate Folders
    valid_folders = []
    for f in raw_folders:
        p = Path(f)
        if not p.is_absolute():
            # Try to resolve common names to user home
            p = Path.home() / f

        if p.exists() and p.is_dir():
            valid_folders.append(str(p.resolve()))

    if not valid_folders:
        return jsonify({"success": False, "error": "No valid folders provided"}), 400

    guest_token = guest_manager.create_session(valid_folders, duration, token)
    local_ip = get_local_ip()
    guest_url = f"http://{local_ip}:5000/guest/access?token={guest_token}"

    add_activity(
        "Guest Link Created",
        f"A temporary access link was generated for {len(valid_folders)} folders.",
        category="Connections"
    )

    # Universal Link for the scanner
    qr_link = f"cypher://{local_ip}:5000/guest?token={guest_token}"
    
    return jsonify({
        "success": True,
        "token": guest_token,
        "url": guest_url,
        "qr_link": qr_link,
        "accepted_folders": valid_folders,
        "expires_at": (datetime.now() + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
    }), 200

@app.route('/guest/access', methods=['GET'])
def guest_landing():
    """TIER 2: Guest landing page - HTML file browser."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)
    
    if not session:
        return jsonify({"error": "Invalid or expired token"}), 401
    
    mode = request.args.get('mode', '')
    is_drop = mode == 'drop'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">
  <title>CYPHER{'Drop' if is_drop else ' — Shared Files'}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    :root {{
      --accent:      #7C3AED;
      --accent-light:#A78BFA;
      --accent-glow: rgba(124,58,237,0.25);
      --bg:          #0F0F11;
      --surface:     #18181B;
      --surface2:    #1F1F23;
      --surface3:    #27272B;
      --text:        #F4F4F5;
      --text2:       #A1A1AA;
      --text3:       #71717A;
      --border:      rgba(255,255,255,0.07);
      --border2:     rgba(124,58,237,0.3);
      --success:     #22C55E;
      --error:       #EF4444;
      --warning:     #F59E0B;
      --radius-sm:   10px;
      --radius:      16px;
      --radius-lg:   22px;
    }}

    *, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}

    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100dvh;
      padding: max(env(safe-area-inset-top),20px) 0 max(env(safe-area-inset-bottom),40px);
    }}

    .wrap {{ max-width: 680px; margin: 0 auto; padding: 0 16px; }}

    /* ── Top bar ── */
    .topbar {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 20px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      position: sticky; top: 0; z-index: 50;
      backdrop-filter: blur(20px);
    }}
    .logo {{
      display: flex; align-items: center; gap: 10px;
    }}
    .logo-mark {{
      width: 34px; height: 34px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), #4F46E5);
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 0 20px var(--accent-glow);
    }}
    .logo-mark svg {{ width:18px; height:18px; fill:white; }}
    .logo-name {{ font-size:15px; font-weight:800; color:var(--text); letter-spacing:-0.5px; }}
    .logo-name span {{ color:var(--accent-light); }}

    .timer-badge {{
      font-size: 12px; font-weight: 700; letter-spacing: 0.5px;
      padding: 7px 14px; border-radius: 20px;
      background: var(--surface2); border: 1px solid var(--border);
      color: var(--text2); transition: all 0.4s;
    }}
    .timer-badge.warn  {{ color: var(--warning); border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.08); }}
    .timer-badge.crit  {{ color: var(--error);   border-color: rgba(239,68,68,0.3);  background: rgba(239,68,68,0.08);  }}

    /* ── Install banner ── */
    .install-banner {{
      margin: 16px 0 0;
      padding: 14px 16px;
      background: linear-gradient(135deg, rgba(124,58,237,0.12), rgba(79,70,229,0.08));
      border: 1px solid var(--border2);
      border-radius: var(--radius);
      display: flex; align-items: center; gap: 12px;
    }}
    .install-icon {{
      width: 44px; height: 44px; flex-shrink: 0;
      background: linear-gradient(135deg, var(--accent), #4F46E5);
      border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 4px 16px var(--accent-glow);
    }}
    .install-icon svg {{ width:22px; height:22px; fill:white; }}
    .install-text {{ flex:1; min-width:0; }}
    .install-text strong {{ font-size:13px; font-weight:700; color:var(--text); display:block; }}
    .install-text span {{ font-size:11px; color:var(--text2); }}
    .install-btn {{
      padding: 8px 14px; border-radius: 8px; font-size:12px; font-weight:700;
      background: var(--accent); color: white; border: none; cursor: pointer;
      white-space: nowrap; flex-shrink: 0; transition: 0.2s;
    }}
    .install-btn:active {{ opacity:0.8; transform:scale(0.96); }}
    #installBanner {{ display:none; }}

    /* ── Drop hero ── */
    .drop-hero {{
      margin: 20px 0 0;
      text-align: center;
      padding: 28px 20px;
      background: var(--surface);
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
    }}
    .drop-hero h2 {{ font-size:20px; font-weight:800; color:var(--text); margin-bottom:6px; }}
    .drop-hero p  {{ font-size:13px; color:var(--text2); line-height:1.6; }}

    /* ── Section header ── */
    .section-head {{
      display: flex; align-items: center; justify-content: space-between;
      margin: 24px 0 10px;
    }}
    .section-title {{
      font-size: 11px; font-weight: 700;
      letter-spacing: 1.5px; color: var(--text3); text-transform: uppercase;
    }}
    .section-count {{
      font-size: 11px; font-weight: 600; color: var(--text3);
    }}

    /* ── Upload zone ── */
    .upload-zone {{
      border: 2px dashed rgba(124,58,237,0.25);
      border-radius: var(--radius-lg);
      padding: 36px 20px;
      text-align: center;
      cursor: pointer;
      transition: all 0.25s;
      background: rgba(124,58,237,0.03);
      position: relative;
    }}
    .upload-zone:hover, .upload-zone.drag {{ border-color:var(--accent); background:rgba(124,58,237,0.07); }}
    .upload-zone-icon {{
      width: 56px; height: 56px; margin: 0 auto 14px;
      background: rgba(124,58,237,0.1);
      border-radius: 14px;
      display: flex; align-items: center; justify-content: center;
    }}
    .upload-zone-icon svg {{ width:26px; height:26px; stroke:var(--accent-light); fill:none; stroke-width:2; }}
    .upload-zone h3 {{ font-size:15px; font-weight:700; color:var(--text); margin-bottom:4px; }}
    .upload-zone p  {{ font-size:12px; color:var(--text2); }}
    .upload-zone input {{ position:absolute; inset:0; opacity:0; cursor:pointer; }}

    /* ── Upload progress ── */
    #uploadProgress {{ display:none; margin-top:16px; }}
    .upload-item {{
      display: flex; align-items: center; gap: 12px;
      padding: 12px 14px;
      background: var(--surface2); border-radius: var(--radius-sm);
      margin-bottom: 8px;
    }}
    .upload-item-icon {{
      width: 36px; height: 36px; flex-shrink:0;
      background: rgba(124,58,237,0.1); border-radius: 9px;
      display: flex; align-items: center; justify-content: center;
    }}
    .upload-item-icon svg {{ width:18px; height:18px; stroke:var(--accent-light); fill:none; stroke-width:2; }}
    .upload-item-info {{ flex:1; min-width:0; }}
    .upload-item-name {{ font-size:12px; font-weight:600; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .upload-item-bar {{ height:3px; border-radius:2px; background:var(--surface3); margin-top:6px; overflow:hidden; }}
    .upload-item-fill {{ height:100%; background:var(--accent); border-radius:2px; transition:width 0.2s; }}
    .upload-item-pct {{ font-size:11px; color:var(--text3); flex-shrink:0; width:34px; text-align:right; }}

    /* ── Breadcrumb ── */
    .breadcrumb {{
      display: flex; gap: 6px; margin-bottom: 12px;
      overflow-x: auto; scrollbar-width: none; padding: 2px;
    }}
    .breadcrumb::-webkit-scrollbar {{ display:none; }}
    .crumb {{
      padding: 7px 14px; border-radius: 20px; font-size:12px; font-weight:600;
      background: var(--surface2); border: 1px solid var(--border);
      color: var(--accent-light); cursor: pointer; white-space: nowrap; transition: 0.2s;
    }}
    .crumb:last-child {{ color:var(--text3); cursor:default; background:transparent; border-color:transparent; }}
    .crumb:not(:last-child):hover {{ background:var(--surface3); border-color:var(--border2); }}

    /* ── File list ── */
    .file-list {{ display:flex; flex-direction:column; gap:8px; }}

    .file-item {{
      display: flex; align-items: center; gap: 12px;
      padding: 13px 14px;
      background: var(--surface); border-radius: var(--radius);
      border: 1px solid var(--border);
      transition: all 0.18s; cursor: default;
    }}
    .file-item.is-folder {{ cursor:pointer; }}
    .file-item.is-folder:hover {{ background:var(--surface2); border-color:var(--border2); transform:translateX(2px); }}
    .file-item:not(.is-folder):hover {{ background:var(--surface2); }}

    .file-icon {{
      width: 40px; height: 40px; flex-shrink:0; border-radius: 11px;
      display: flex; align-items: center; justify-content: center;
    }}
    .file-icon svg {{ width:20px; height:20px; }}

    .file-info {{ flex:1; min-width:0; }}
    .file-name {{ font-size:13px; font-weight:600; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .file-meta {{ font-size:11px; color:var(--text3); margin-top:2px; }}

    .btn-dl {{
      padding: 8px 14px; border-radius: 8px; font-size:12px; font-weight:700;
      background: rgba(124,58,237,0.12); color:var(--accent-light);
      border: 1px solid rgba(124,58,237,0.2);
      cursor: pointer; white-space:nowrap; transition: 0.2s;
      display: flex; align-items: center; gap: 5px;
    }}
    .btn-dl:hover {{ background:rgba(124,58,237,0.22); border-color:var(--accent); }}
    .btn-dl:active {{ transform:scale(0.95); opacity:0.8; }}
    .btn-dl svg {{ width:13px; height:13px; stroke:currentColor; fill:none; stroke-width:2.5; }}

    .folder-chevron {{ width:16px; height:16px; stroke:var(--text3); fill:none; stroke-width:2; }}

    /* ── Empty state ── */
    .empty {{
      text-align: center; padding: 52px 20px;
    }}
    .empty-icon {{
      width: 64px; height: 64px; margin: 0 auto 16px;
      background: var(--surface2); border-radius: 18px;
      display: flex; align-items: center; justify-content: center;
    }}
    .empty-icon svg {{ width:30px; height:30px; stroke:var(--text3); fill:none; stroke-width:1.5; }}
    .empty h3 {{ font-size:15px; font-weight:700; color:var(--text); margin-bottom:6px; }}
    .empty p  {{ font-size:13px; color:var(--text2); }}

    /* ── Toast ── */
    #toastBox {{
      position: fixed; bottom: max(env(safe-area-inset-bottom),24px); left:50%;
      transform: translateX(-50%); z-index:999; display:flex;
      flex-direction:column; align-items:center; gap:8px;
    }}
    .toast {{
      padding: 11px 20px; border-radius: 12px;
      font-size: 13px; font-weight: 600; color: #fff;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      animation: slideUp 0.2s ease;
      white-space: nowrap;
    }}
    .toast.ok    {{ background: #16a34a; }}
    .toast.err   {{ background: var(--error); }}
    .toast.info  {{ background: var(--accent); }}
    @keyframes slideUp {{ from {{ transform:translateY(12px); opacity:0; }} to {{ transform:translateY(0); opacity:1; }} }}

    /* ── Loading skeleton ── */
    .skeleton {{
      height: 64px; border-radius: var(--radius);
      background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
      background-size: 200% 100%;
      animation: shimmer 1.4s infinite;
    }}
    @keyframes shimmer {{ 0% {{ background-position:200% 0; }} 100% {{ background-position:-200% 0; }} }}

    @media (max-width: 480px) {{
      .btn-dl span {{ display:none; }}
      .btn-dl {{ padding:8px; }}
      .install-banner {{ flex-wrap:nowrap; }}
    }}
  </style>
</head>
<body>

  <!-- Top bar -->
  <div class="topbar">
    <div class="logo">
      <div class="logo-mark">
        <svg viewBox="0 0 24 24"><path d="M12 2L4 6v6c0 5.5 3.8 10.7 8 12 4.2-1.3 8-6.5 8-12V6l-8-4z"/></svg>
      </div>
      <div class="logo-name">CYPHER<span>{'Drop' if is_drop else ''}</span></div>
    </div>
    <div class="timer-badge" id="timerEl">--:--</div>
  </div>

  <div class="wrap">

    <!-- Install banner -->
    <div class="install-banner" id="installBanner">
      <div class="install-icon">
        <svg viewBox="0 0 24 24"><path d="M12 2L4 6v6c0 5.5 3.8 10.7 8 12 4.2-1.3 8-6.5 8-12V6l-8-4z"/></svg>
      </div>
      <div class="install-text">
        <strong>Get CYPHER on your phone</strong>
        <span>Control your PC from anywhere on your WiFi — free forever</span>
      </div>
      <button class="install-btn" onclick="showToast('Search \\'CYPHER Remote\\' on your app store', 'info')">Get App</button>
    </div>

    {'<div class="drop-hero"><h2>Files dropped for you</h2><p>Everything below was shared by the sender. Download to your device or send files back.</p></div>' if is_drop else ''}

    <!-- Upload section -->
    <div class="section-head" style="margin-top:20px">
      <span class="section-title">{'Send to Them' if is_drop else 'Upload Files'}</span>
    </div>

    <div class="upload-zone" id="dropZone">
      <div class="upload-zone-icon">
        <svg viewBox="0 0 24 24"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/></svg>
      </div>
      <h3>{'Drop files to send back' if is_drop else 'Drop files here'}</h3>
      <p>Tap to browse or drag and drop · No size limit</p>
      <input type="file" id="uploadInput" multiple>
    </div>

    <div id="uploadProgress"></div>

    <!-- File list section -->
    <div class="section-head">
      <span class="section-title">{'Shared Files' if is_drop else 'Files'}</span>
      <span class="section-count" id="fileCount"></span>
    </div>

    <div class="breadcrumb" id="breadcrumb"></div>
    <div class="file-list" id="fileList">
      <div class="skeleton"></div>
      <div class="skeleton"></div>
      <div class="skeleton" style="opacity:.6"></div>
    </div>

  </div>

  <div id="toastBox"></div>

  <script>
    const TOKEN = "{token}";
    const BASE = window.location.origin;
    const IS_DROP = {'true' if is_drop else 'false'};
    let path = "";

    // ── Timer ──
    async function updateTimer() {{
      try {{
        const r = await fetch(`${{BASE}}/guest/session?token=${{TOKEN}}`);
        const d = await r.json();
        if (!d.success) return;
        const s = d.time_remaining_seconds || 0;
        const m = Math.floor(s/60), sc = s%60;
        const el = document.getElementById('timerEl');
        el.textContent = `${{String(m).padStart(2,'0')}}:${{String(sc).padStart(2,'0')}}`;
        el.className = s < 60 ? 'timer-badge crit' : s < 300 ? 'timer-badge warn' : 'timer-badge';
      }} catch(_) {{}}
    }}

    // ── Load files ──
    async function loadFiles() {{
      const list = document.getElementById('fileList');
      list.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
      try {{
        const r = await fetch(`${{BASE}}/guest/files?token=${{TOKEN}}&path=${{encodeURIComponent(path)}}`);
        const d = await r.json();
        const files = d.files || [];
        document.getElementById('fileCount').textContent = files.length ? `${{files.length}} item${{files.length===1?'':'s'}}` : '';
        updateBreadcrumb();
        if (!files.length) {{
          list.innerHTML = `<div class="empty">
            <div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg></div>
            <h3>No files here</h3><p>This folder is empty</p></div>`;
          return;
        }}
        list.innerHTML = files.map(f => fileCard(f)).join('');
      }} catch(e) {{
        list.innerHTML = '<div class="empty"><h3>Could not load files</h3><p>Check your connection</p></div>';
      }}
    }}

    function fileCard(f) {{
      const isDir = f.type === 'folder';
      const icon = isDir ? folderIcon() : fileIconFor(f.extension);
      const meta = isDir ? `${{f.item_count || 0}} items` : formatSize(f.size);
      const safe = f.path.replace(/\\\\/g,'/').replace(/'/g, "\\'");
      const action = isDir
        ? `onclick="nav('${{safe}}')" `
        : ``;
      const dlBtn = !isDir ? `<button class="btn-dl" onclick="dl(event,'${{safe}}')">
          <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>Download</span></button>` : '';
      const chevron = isDir ? `<svg class="folder-chevron" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>` : '';
      return `<div class="file-item ${{isDir?'is-folder':''}}" ${{action}}>
        <div class="file-icon" style="background:${{isDir ? 'rgba(245,158,11,0.1)' : 'rgba(124,58,237,0.08)'}}">${{icon}}</div>
        <div class="file-info">
          <div class="file-name">${{esc(f.name)}}</div>
          <div class="file-meta">${{meta}}</div>
        </div>
        ${{dlBtn}}${{chevron}}
      </div>`;
    }}

    function nav(p) {{ path = p; loadFiles(); }}

    function dl(e, p) {{
      e.stopPropagation();
      showToast('Download starting…', 'info');
      window.location.href = `${{BASE}}/guest/files/download?token=${{TOKEN}}&path=${{encodeURIComponent(p)}}`;
    }}

    // ── Breadcrumb ──
    function updateBreadcrumb() {{
      const bc = document.getElementById('breadcrumb');
      const parts = path.split(/[\\/]/).filter(Boolean);
      const crumbs = [{{label:'Root', p:''}}];
      parts.forEach((part, i) => crumbs.push({{label:part, p:parts.slice(0,i+1).join('/')}}));
      bc.innerHTML = crumbs.map((c,i) =>
        `<div class="crumb" onclick="if(${{i<crumbs.length-1}})nav('${{c.p}}')">${{esc(c.label)}}</div>`
      ).join('');
    }}

    // ── Upload ──
    const dropZone = document.getElementById('dropZone');
    const uploadInput = document.getElementById('uploadInput');

    dropZone.addEventListener('dragover', e => {{ e.preventDefault(); dropZone.classList.add('drag'); }});
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
    dropZone.addEventListener('drop', e => {{
      e.preventDefault(); dropZone.classList.remove('drag');
      handleUpload(e.dataTransfer.files);
    }});
    uploadInput.addEventListener('change', () => handleUpload(uploadInput.files));

    async function handleUpload(files) {{
      if (!files.length) return;
      const prog = document.getElementById('uploadProgress');
      prog.style.display = 'block';
      prog.innerHTML = '';

      const items = Array.from(files);
      const rows = {{}};

      items.forEach(f => {{
        const id = 'up_' + Math.random().toString(36).slice(2);
        rows[f.name] = id;
        prog.innerHTML += `<div class="upload-item">
          <div class="upload-item-icon">${{fileIconFor(f.name.split('.').pop())}}</div>
          <div class="upload-item-info">
            <div class="upload-item-name">${{esc(f.name)}}</div>
            <div class="upload-item-bar"><div class="upload-item-fill" id="${{id}}" style="width:0%"></div></div>
          </div>
          <div class="upload-item-pct" id="${{id}}_pct">0%</div>
        </div>`;
      }});

      for (const f of items) {{
        const id = rows[f.name];
        const xhr = new XMLHttpRequest();
        const fd = new FormData();
        fd.append('file', f);
        fd.append('destination', path || 'CypherDrop');

        xhr.upload.onprogress = e => {{
          if (!e.lengthComputable) return;
          const pct = Math.round(e.loaded/e.total*100);
          const el = document.getElementById(id);
          const pelEl = document.getElementById(id+'_pct');
          if (el) el.style.width = pct+'%';
          if (pelEl) pelEl.textContent = pct+'%';
        }};

        await new Promise(resolve => {{
          xhr.onload = () => {{
            const el = document.getElementById(id);
            if (el) el.style.background = xhr.status===200 ? 'var(--success)' : 'var(--error)';
            resolve();
          }};
          xhr.onerror = resolve;
          xhr.open('POST', `${{BASE}}/guest/files/upload?token=${{TOKEN}}`);
          xhr.send(fd);
        }});
      }}

      showToast('Upload complete!', 'ok');
      setTimeout(() => {{ prog.style.display='none'; prog.innerHTML=''; }}, 2500);
      loadFiles();
    }}

    // ── Icon helpers ──
    function folderIcon() {{
      return `<svg viewBox="0 0 24 24" style="width:20px;height:20px;stroke:#F59E0B;fill:none;stroke-width:2">
        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`;
    }}

    function fileIconFor(ext) {{
      ext = (ext||'').toLowerCase().replace('.','');
      const imgs = ['jpg','jpeg','png','gif','webp','bmp','svg','heic'];
      const vids = ['mp4','mkv','mov','avi','webm','m4v'];
      const auds = ['mp3','wav','aac','flac','m4a','ogg'];
      const docs = ['pdf','doc','docx','xls','xlsx','ppt','pptx'];
      const code = ['js','ts','py','dart','html','css','json','xml','sh'];
      const arch = ['zip','rar','7z','tar','gz'];
      const txts = ['txt','md','csv','log'];

      let stroke = '#A78BFA', d = 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z';
      if (imgs.includes(ext)) {{ stroke='#06B6D4'; d='M21 9v10a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h10'; }}
      if (vids.includes(ext)) {{ stroke='#EC4899'; d='M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.899L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z'; }}
      if (auds.includes(ext)) {{ stroke='#8B5CF6'; d='M9 18V5l12-2v13'; }}
      if (docs.includes(ext)) {{ stroke='#3B82F6'; }}
      if (code.includes(ext)) {{ stroke='#22C55E'; d='M16 18l6-6-6-6M8 6l-6 6 6 6'; }}
      if (arch.includes(ext)) {{ stroke='#F59E0B'; d='M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z'; }}
      if (txts.includes(ext)) {{ stroke='#94A3B8'; }}
      return `<svg viewBox="0 0 24 24" style="width:20px;height:20px;stroke:${{stroke}};fill:none;stroke-width:2"><path d="${{d}}"/></svg>`;
    }}

    // ── Utilities ──
    function formatSize(b) {{
      if (!b) return '0 B';
      const u = ['B','KB','MB','GB','TB'];
      const i = Math.min(Math.floor(Math.log(b)/Math.log(1024)), u.length-1);
      return (b/Math.pow(1024,i)).toFixed(i>0?1:0)+' '+u[i];
    }}

    function esc(s) {{
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }}

    function showToast(msg, type='info') {{
      const box = document.getElementById('toastBox');
      const el = document.createElement('div');
      el.className = 'toast '+type;
      el.textContent = msg;
      box.appendChild(el);
      setTimeout(() => el.remove(), 3000);
    }}

    // ── Install banner: show on mobile ──
    if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {{
      document.getElementById('installBanner').style.display = 'flex';
    }}

    // ── Boot ──
    setInterval(updateTimer, 1000);
    updateTimer();
    loadFiles();
    updateBreadcrumb();
  </script>
</body>
</html>"""
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/guest/files', methods=['GET'])
def guest_get_files():
    """TIER 1: List files in allowed folders for guest."""
    token = request.args.get('token')
    path = request.args.get('path', '')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    try:
        if not path:
            # Return allowed folders
            files = []
            for folder in session.allowed_folders:
                if Path(folder).exists():
                    files.append({
                        "name": Path(folder).name,
                        "path": str(Path(folder)),
                        "type": "folder",
                        "size": 0,
                        "item_count": len(list(Path(folder).iterdir())),
                        "modified": datetime.fromtimestamp(Path(folder).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "extension": ""
                    })
            return jsonify({"success": True, "files": files})

        # Validate path is in allowed folders
        if not is_path_in_folders(path, session.allowed_folders):
            return jsonify({"success": False, "error": "Access denied"}), 403

        p = Path(path)
        if not p.exists():
            return jsonify({"success": False, "error": "Path not found"}), 404

        items = []
        for item in sorted(p.iterdir()):
            try:
                stats = item.stat()
                item_count = len(list(item.iterdir())) if item.is_dir() else 0
                items.append({
                    "name": item.name,
                    "path": str(item.absolute()),
                    "type": "folder" if item.is_dir() else "file",
                    "size": stats.st_size if item.is_file() else 0,
                    "item_count": item_count,
                    "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "extension": item.suffix if item.is_file() else ""
                })
                guest_manager.log_guest_access(token, str(item), "browse")
            except:
                continue

        return jsonify({"success": True, "files": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/guest/files/search', methods=['GET'])
def guest_search_files():
    """TIER 2: Search files in allowed folders."""
    token = request.args.get('token')
    query = request.args.get('q', '').lower()

    session = guest_manager.validate_token(token)
    if not session or not query:
        return jsonify({"success": False, "error": "Invalid request"}), 400

    try:
        results = []
        for folder in session.allowed_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                continue

            for item in folder_path.rglob('*'):
                if not is_path_in_folders(str(item), session.allowed_folders):
                    continue
                if query in item.name.lower() and len(results) < 50:
                    try:
                        stats = item.stat()
                        results.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                            "type": "folder" if item.is_dir() else "file",
                            "size": stats.st_size if item.is_file() else 0,
                            "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "extension": item.suffix if item.is_file() else ""
                        })
                        guest_manager.log_guest_access(token, str(item), "search")
                    except:
                        continue

        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/guest/files/download', methods=['GET'])
def guest_download_file():
    """TIER 1: Download a file as guest."""
    token = request.args.get('token')
    path = request.args.get('path')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not path or not is_path_in_folders(path, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        guest_manager.log_guest_access(token, path, "download")
        return send_file(path, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/guest/files/download/zip', methods=['POST'])
def guest_download_zip():
    """TIER 1: Download multiple files as ZIP."""
    token = request.args.get('token')
    data = request.json or {}
    paths = data.get('paths', [])

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not paths:
        return jsonify({"success": False, "error": "No files selected"}), 400

    # Validate all paths
    for path in paths:
        if not is_path_in_folders(path, session.allowed_folders):
            return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                if os.path.isfile(path):
                    zf.write(path, arcname=os.path.basename(path))
                    guest_manager.log_guest_access(token, path, "zip-download")

        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='files.zip')
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/guest/files/upload', methods=['POST'])
def guest_upload_files():
    """TIER 1: Upload files as guest."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)

    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    files = request.files.getlist('file')
    dest = request.form.get('destination') or (session.allowed_folders[0] if session.allowed_folders else "")

    if not is_path_in_folders(dest, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    results = []
    for file in files:
        try:
            target_path = get_unique_path(os.path.join(dest, file.filename))
            file.save(target_path)
            guest_manager.log_guest_access(token, target_path, "upload")
            results.append({"name": file.filename, "status": "success"})
        except Exception as e:
            results.append({"name": file.filename, "status": "error", "message": str(e)})

    return jsonify({"success": True, "files": results}), 200

@app.route('/guest/files/preview', methods=['GET'])
def guest_preview_file():
    """TIER 2: Preview file without downloading."""
    token = request.args.get('token')
    path = request.args.get('path')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not path or not is_path_in_folders(path, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    if not os.path.exists(path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        guest_manager.log_guest_access(token, path, "preview")
        return send_file(path, as_attachment=False)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/guest/session', methods=['GET'])
def guest_get_session():
    """TIER 2: Get session info including timer."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)

    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    return jsonify({
        "success": True,
        "token": token,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": session.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "time_remaining_seconds": max(0, int((session.expires_at - datetime.now()).total_seconds())),
        "access_count": session.access_count,
        "allowed_folders": session.allowed_folders,
        "is_active": session.is_active
    }), 200

@app.route('/guest/extend', methods=['POST'])
def guest_extend_session():
    """TIER 3: Extend guest session from host."""
    token = request.headers.get("X-Auth-Token")
    if not token or token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    guest_token = data.get("guest_token")
    additional_minutes = data.get("additional_minutes", 30)

    if guest_manager.extend_session(guest_token, additional_minutes):
        return jsonify({"success": True, "action": "extended"}), 200

    return jsonify({"success": False, "error": "Session not found"}), 404

@app.route('/guest/end', methods=['POST'])
def guest_end_session():
    """TIER 3: End guest session immediately."""
    token = request.headers.get("X-Auth-Token")
    if not token or token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    guest_token = data.get("guest_token")

    if get_guest_manager().end_session(guest_token):
        add_activity("Access Revoked", f"Guest session {(guest_token or '')[:8]} terminated.", category="Connections", is_urgent=True)
        return jsonify({"success": True, "action": "ended"}), 200

    return jsonify({"success": False, "error": "Session not found"}), 404

@app.route('/guest/sessions', methods=['GET'])
def guest_list_sessions():
    """TIER 3: List active guest sessions. PC UI sees all sessions."""
    token = request.headers.get("X-Auth-Token")
    if not token or (token not in valid_tokens and token != INTERNAL_TOKEN):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    # If it's the PC UI, show EVERYTHING. If it's a phone, show only what it created.
    filter_id = token if token != INTERNAL_TOKEN else None
    sessions = get_guest_manager().get_all_active_sessions(host_device_id=filter_id)
    return jsonify({"success": True, "sessions": sessions}), 200

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

# --- SCREEN RECORDING ---

@app.route('/recording/start', methods=['POST'])
def start_recording():
    global recording_state
    if recording_state["is_recording"]:
        return jsonify({"success": False, "error": "Recording already in progress"}), 400

    data = request.json or {}
    source = data.get("source", "fullscreen")

    record_dir = Path.home() / "Videos" / "CYPHER"
    record_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    filepath = record_dir / filename

    recording_state.update({
        "is_recording": True,
        "is_paused": False,
        "start_time": time.time(),
        "filename": filename,
        "filepath": str(filepath),
        "source": source
    })

    # Start the background recording thread
    threading.Thread(target=recording_worker, daemon=True).start()

    add_activity("Screen Recording", f"Started session ({source}).", category="Commands")
    log_to_ui(f"Recording Started: {source}")
    get_overlay_manager().start()
    return jsonify({"success": True, "filename": filename})

@app.route('/recording/status', methods=['GET'])
def get_recording_status():
    return jsonify({
        "is_recording": recording_state["is_recording"],
        "is_paused": recording_state["is_paused"],
        "duration": int(time.time() - recording_state["start_time"]) if recording_state["is_recording"] else 0,
        "filename": recording_state["filename"]
    })

@app.route('/recording/pause', methods=['POST'])
def pause_recording():
    global recording_state
    if not recording_state["is_recording"]:
        return jsonify({"success": False, "error": "No recording in progress"}), 400
    recording_state["is_paused"] = not recording_state["is_paused"]
    action = "Paused" if recording_state["is_paused"] else "Resumed"
    log_to_ui(f"Recording {action}")
    return jsonify({"success": True, "is_paused": recording_state["is_paused"]})

@app.route('/recording/stop', methods=['POST'])
def stop_recording():
    global recording_state
    if not recording_state["is_recording"]:
        return jsonify({"success": False, "error": "No recording in progress"}), 400
    filepath = recording_state["filepath"]
    recording_state.update({"is_recording": False, "is_paused": False, "start_time": None})
    add_activity("Recording Saved", "Session stored in Videos/CYPHER.", category="Commands", attachment=os.path.basename(filepath))
    log_to_ui("Recording Stopped & Saved")
    get_overlay_manager().stop()
    return jsonify({"success": True, "path": filepath})

# --- PERIPHERALS & MEDIA ---

@app.route('/screenshot', methods=['GET'])
def get_screenshot():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    try:
        add_activity("Screenshot Taken", "A remote screen capture was initiated.", category="Commands")
        log_to_ui("Screenshot Captured")
        screenshot = pyautogui.screenshot()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=60)
        buffered.seek(0)
        return send_file(buffered, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/clipboard', methods=['GET', 'POST'])
def handle_pc_clipboard():
    _load_automation()
    if request.method == 'GET':
        if not WINDOWS or not pyperclip:
            return jsonify({"success": True, "content": ""})
        return jsonify({"success": True, "content": pyperclip.paste()})
    if not WINDOWS or not pyperclip:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400

    # Handle both 'content' (Mobile) and 'text' (Legacy) keys
    data = request.json
    text = data.get("content") or data.get("text", "")

    if len(text) > 1024 * 1024:
        return jsonify({"success": False, "error": "Clipboard content too large"}), 413
    log_to_ui("Clipboard Updated")
    pyperclip.copy(text)
    return jsonify({"success": True, "action": "clipboard_set"})

@app.route('/open-link', methods=['POST'])
def open_remote_link():
    """Support for 'Open Link' feature from mobile clipboard."""
    url = request.json.get("url", "")
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400
    try:
        import webbrowser
        webbrowser.open(url)
        log_to_ui(f"Opened: {url[:30]}...")
        return jsonify({"success": True, "action": "link_opened"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/type', methods=['POST'])
def remote_type():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    text = request.json.get("text", "")
    log_to_ui(f"Typed: {text[:15]}...")
    # Give system a tiny moment to stabilize focus if needed
    time.sleep(0.1)
    pyautogui.write(text, interval=0.01)
    return jsonify({"success": True, "text": text})

@app.route('/keyboard/hotkey', methods=['POST'])
def remote_hotkey():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    keys = request.json.get("keys", [])
    if keys:
        log_to_ui(f"Hotkey: {'+'.join(keys)}")
        time.sleep(0.1)
        pyautogui.hotkey(*keys)
        return jsonify({"success": True, "keys": keys})
    return jsonify({"success": False, "error": "No keys provided"}), 400


@app.route('/media/volume/get', methods=['GET'])
def get_volume():
    _load_audio_engine()
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available"}), 400
    try:
        ctypes.windll.ole32.CoInitialize(None)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        current_volume = volume.GetMasterVolumeLevelScalar()
        return jsonify({"success": True, "level": int(current_volume * 100)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        ctypes.windll.ole32.CoUninitialize()

@app.route('/media/volume/set', methods=['POST'])
def volume_set_exact():
    _load_audio_engine()
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    level = request.json.get("level", 50)
    log_to_ui(f"Volume Set: {level}%")
    try:
        ctypes.windll.ole32.CoInitialize(None)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return jsonify({"success": True, "level": level})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        ctypes.windll.ole32.CoUninitialize()

@app.route('/media/<action>', methods=['POST'])
def media_generic_control(action):
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    map = {"playpause": "playpause", "next": "nexttrack", "prev": "prevtrack", "stop": "stop", "mute": "volumemute"}
    if action in map:
        log_to_ui(f"Media: {action}")
        pyautogui.press(map[action])
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid media action"}), 400

@app.route('/media/volumeup', methods=['POST'])
def volume_up():
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    set_volume(0.05)
    return jsonify({"success": True})

@app.route('/media/volumedown', methods=['POST'])
def volume_down():
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    set_volume(-0.05)
    return jsonify({"success": True})

@app.route('/battery/status', methods=['GET'])
def get_battery_status():
    batt = psutil.sensors_battery()
    percent = batt.percent if batt else 0
    return jsonify({
        "percent": percent, "plugged": batt.power_plugged if batt else False,
        "alert_threshold": battery_threshold, "is_critical": percent <= battery_threshold
    })

@app.route('/battery/threshold', methods=['POST'])
def set_battery_threshold():
    global battery_threshold
    battery_threshold = request.json.get("threshold", 20)
    return jsonify({"success": True})

@app.route('/history', methods=['GET'])
def get_history():
    return jsonify(command_history)

# --- NOTIFICATIONS & MACROS ---

@app.route('/notifications', methods=['GET'])
def get_notifications():
    return jsonify(notifications_list)

@app.route('/notifications/add', methods=['POST'])
def add_notification():
    data = request.json
    new_notif = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", "No Title"),
        "message": data.get("message", ""),
        "app_name": data.get("app_name", "System"),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    notifications_list.append(new_notif)
    if len(notifications_list) > 20: notifications_list.pop(0)
    return jsonify({"success": True})

@app.route('/wol', methods=['POST'])
def wake_on_lan():
    data = request.json or {}
    mac = data.get('mac', '').replace(':', '').replace('-', '').replace('.', '')
    if len(mac) != 12:
        return jsonify({"success": False, "error": "Invalid MAC address (expected xx:xx:xx:xx:xx:xx)"}), 400
    try:
        mac_bytes = bytes.fromhex(mac)
        magic = b'\xff' * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(magic, ('<broadcast>', 9))
        log_to_ui(f"WOL: Magic packet sent to {data.get('mac')}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/system/activity', methods=['GET'])
def get_system_activity():
    """Endpoint for the dynamic Activity Log tab."""
    return jsonify(system_activity_log)

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


if __name__ == '__main__':
    print(build_startup_banner(get_local_ip()))
    # host="0.0.0.0" is the documented open finding S-07/P1-S4: the node must be
    # reachable from the phone on the LAN. Do not change this to loopback.
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # noqa: S104
