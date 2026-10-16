import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("cypher")

# ─────────────────────────────────────────────────────────────
# NETWORK CONSTANTS
# ─────────────────────────────────────────────────────────────
# The node's ports are a wire-protocol constant: the mobile app, the desktop
# shell, the mDNS advertisement and the Windows Firewall rules must all agree on
# them. They were previously hardcoded as bare `5000` / `5001` / `5002` literals
# in at least four files, so changing one silently broke the others.
#
# Changing these is a breaking protocol change — bump the mobile client's
# expected version at the same time (see docs/architecture/overview.md).
SERVER_PORT = 5000          # HTTP API + Socket.IO
DISCOVERY_PORT = 5001       # mDNS / zeroconf
BEACON_PORT = 5002          # UDP subnet broadcast fallback

# ----------------------------
# PYINSTALLER PATH RESOLUTION
# ----------------------------
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_app_data_dir():
    """Returns the persistent directory for application data."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        path = Path(base) / "Cypher"
    elif sys.platform == "darwin":
        path = Path.home() / "Library/Application Support/Cypher"
    else:
        path = Path.home() / ".cypher"

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path(filename):
    """
    Returns full path to a config file inside Cypher app data folder.
    """
    return get_app_data_dir() / filename

def get_metadata():
    """Reads project metadata from the local master file."""
    try:
        # Try to find metadata.json in the app root
        meta_path = get_resource_path("metadata.json")
        if os.path.exists(meta_path):
            # [FIX] Use utf-8-sig to handle Byte Order Mark (BOM) from Windows-saved files
            with open(meta_path, encoding="utf-8-sig") as f:
                return json.load(f)
    except (OSError, ValueError) as exc:
        # A missing or corrupt metadata.json must not stop the node starting —
        # the fallback below carries the real defaults.
        log.debug("metadata.json unreadable, using fallback: %s", exc)

    # Fallback
    return {
        "app_name": "CYPHER",
        "app_version": "1.0.0",
        "app_publisher": "Emerald Dev"
    }

# --- OTA UPDATE LOGIC ---
GITHUB_USER = "Emerald-dev0"
GITHUB_REPO = "Cypher"

def check_for_updates():
    """Checks GitHub for a newer version of metadata.json."""
    import requests
    try:
        current_version = get_metadata().get("app_version", "1.0.0")
        url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/pc_app_flutter/backend/metadata.json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            # [FIX] Manually decode with utf-8-sig to strip potential BOM from remote file
            raw_text = response.content.decode("utf-8-sig")
            remote_metadata = json.loads(raw_text)
            remote_version = remote_metadata.get("app_version", "1.0.0")

            if remote_version > current_version:
                return {
                    "update_available": True,
                    "version": remote_version,
                    "url": remote_metadata.get("app_updates_url", "")
                }
    except Exception as e:
        print(f"Update check failed: {e}")
    return {"update_available": False}

def log_event(event_type: str, details: object, *, sensitive: bool = False) -> None:
    """Local event log (P1-S5). Never send this file anywhere.

    ``sensitive=True`` means ``details`` must not be persisted as-is (keystrokes,
    clipboard, tokens). We record only the type and a placeholder.
    """
    from datetime import datetime

    log_file = get_config_path("analytics_log.json")

    event = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "sensitive": sensitive,
        "details": "<redacted>" if sensitive else details,
    }

    try:
        data = []

        if log_file.exists():
            with open(log_file) as f:
                data = json.load(f)

        data.append(event)

        # Keep only last 500 events
        if len(data) > 500:
            data = data[-500:]

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    except (OSError, TypeError, ValueError) as exc:
        # The activity log is a convenience, not a system of record. A full disk
        # or a non-serialisable field must not break the request that triggered it.
        log.warning("Could not persist activity log: %s", exc)
