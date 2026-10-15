import os
import sys

# Eventlet monkey patching is unnecessary for 'threading' mode on Windows
# and often causes issues in packaged executables on Python 3.12
import threading
import time
import json
import logging
import ctypes
import shutil
import subprocess
import warnings

# --- SUPPRESS DEPRECATIONS ---
warnings.filterwarnings("ignore", category=DeprecationWarning)

# --- SINGLE INSTANCE LOCK ---
def ensure_single_instance():
    """Uses a named mutex to prevent multiple instances of the backend service."""
    if sys.platform == 'win32':
        mutex_name = "Global\\CypherBackendServiceMutex"
        # CreateMutexW returns a handle to the mutex
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()

        # ERROR_ALREADY_EXISTS = 183
        if last_error == 183:
            print("CYPHER Backend is already running. Exiting.")
            sys.exit(0)
        # We must keep the mutex handle alive for the duration of the process
        return mutex
    return None

# Keep reference to mutex so it's not garbage collected
_instance_mutex = None

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("cypher")

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        # AttributeError on non-Windows (no ctypes.windll), OSError if the call
        # itself fails. Either way: not admin.
        return False

def elevate():
    """Triggers the Windows UAC prompt to run this script as Administrator."""
    if not is_admin():
        log.info("Requesting Administrator privileges...")
        # Get absolute path to the script to ensure it can be found after elevation
        script = os.path.abspath(sys.argv[0])
        # Prepare parameters, ensuring the script path is quoted if it contains spaces
        params = f'"{script}"'
        if len(sys.argv) > 1:
            params += " " + " ".join(sys.argv[1:])

        # 'runas' is the verb that triggers UAC
        # We also pass the directory explicitly to maintain the working environment
        directory = os.path.dirname(script)

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, directory, 1
        )
        sys.exit(0)

# Firewall rule names are module-level constants so the check, the add, and the
# duplicate check in main() cannot drift apart.
FW_RULE_API = "CYPHER_BRIDGE"
FW_RULE_DISCOVERY = "CYPHER_DISCOVERY"

# Derived from the shared protocol constants in core.utils rather than hardcoded,
# so a port change cannot leave a stale firewall rule that opens a port nothing
# listens on (or worse, fails to open the port that does).
from core.utils import BEACON_PORT, DISCOVERY_PORT, SERVER_PORT  # noqa: E402

FW_TCP_PORTS = f"{SERVER_PORT},{DISCOVERY_PORT}"
FW_UDP_PORTS = f"{DISCOVERY_PORT},{BEACON_PORT}"


def _netsh(*args: str) -> subprocess.CompletedProcess:
    """Run a netsh command WITHOUT a shell.

    Every one of these previously used `shell=True` with an interpolated command
    string. The arguments are all module-level constants, so there was no live
    injection — but `shell=True` is still the wrong default: it hands the string
    to cmd.exe, which applies its own quoting and globbing rules, and it is what
    ruff's S602 exists to stop people reaching for reflexively.

    Note the quoting change: under a shell, `name="CYPHER_BRIDGE"` has its quotes
    consumed by cmd.exe before netsh sees it. With an argument list the quotes
    would be passed through literally and the rule would never match, so the
    argument is written `name=CYPHER_BRIDGE`.
    """
    # Resolve netsh to an absolute path. A bare executable name makes the
    # process inherit PATH, which on a multi-user Windows box is attacker-
    # influenceable; shutil.which pins it to the system copy.
    netsh = shutil.which("netsh")
    if netsh is None:
        raise OSError("netsh not found on PATH")
    return subprocess.run(  # noqa: S603 -- args are module-level constants, never user input
        [netsh, "advfirewall", "firewall", *args],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


def firewall_rule_missing(name: str) -> bool:
    """True when no rule called `name` is registered."""
    try:
        result = _netsh("show", "rule", f"name={name}")
    except OSError as exc:
        # netsh is absent on non-Windows platforms and on stripped Windows images.
        # Treat that as "not configured" so the caller can decide, rather than
        # crashing the service on a platform check.
        log.debug("netsh unavailable, assuming rule %s is missing: %s", name, exc)
        return True
    return result.returncode != 0 or "no rules match" in result.stdout.lower()


def register_firewall():
    """Ensures the PC allows connections from the mobile app through the Windows Firewall."""
    if not is_admin():
        return

    log.info("Checking System Firewall rules...")
    try:
        if not firewall_rule_missing(FW_RULE_API):
            log.info("Firewall rules already present.")
            return

        log.info("Registering CYPHER in Windows Firewall...")
        # Inbound TCP for the API, inbound UDP for mDNS/beacon discovery.
        _netsh(
            "add", "rule", f"name={FW_RULE_API}",
            "dir=in", "action=allow", "protocol=TCP", f"localport={FW_TCP_PORTS}",
        )
        _netsh(
            "add", "rule", f"name={FW_RULE_DISCOVERY}",
            "dir=in", "action=allow", "protocol=UDP", f"localport={FW_UDP_PORTS}",
        )
        log.info("Firewall configured successfully.")
    except Exception as e:
        log.error("Failed to configure firewall: %s", e)

DEFAULT_PC_NAME = "Cypher PC"


def get_pc_name():
    """Best-effort device name from settings.json, with a safe fallback.

    The node name is advertised over mDNS and shown in the phone's device list,
    so a failure here must degrade to a generic name rather than crash the
    service. That is why the exception is caught — but it is caught narrowly and
    logged, because a bare `except: pass` also swallows KeyboardInterrupt and
    SystemExit and hides real configuration errors.
    """
    try:
        # Avoid circular import by importing here
        from core.utils import get_config_path
        settings_path = get_config_path("settings.json")
        if settings_path.exists():
            with open(settings_path, encoding="utf-8") as f:
                return json.load(f).get("device_name") or DEFAULT_PC_NAME
    except (OSError, ValueError) as exc:
        log.debug("Could not read device name from settings: %s", exc)
    return DEFAULT_PC_NAME

def start_server(flask_app, socketio):
    def run():
        log.info("Starting High-Performance Node on port 5000...")
        # host="0.0.0.0" is deliberate and is the single largest open security
        # finding: the node must be reachable from the phone on the LAN, so it
        # cannot bind loopback. What is missing is the compensating controls —
        # TLS, a Host-header allowlist, and interface selection. Tracked as
        # P1-S4 / P2-S1 in ../../ROADMAP.md and ../../docs/AUDIT.md S-07/S-08.
        # Do not "fix" this by binding 127.0.0.1; it breaks the product.
        socketio.run(
            flask_app,
            host="0.0.0.0",  # noqa: S104 -- see the comment above
            port=SERVER_PORT,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    threading.Thread(target=run, daemon=True).start()

def main():
    # 🚀 Step -1: Single Instance Check
    global _instance_mutex
    _instance_mutex = ensure_single_instance()

    # 🚀 Step 0: Elevation Strategy
    if not is_admin() and firewall_rule_missing(FW_RULE_API):
        log.info("System configuration missing. Requesting one-time elevation...")
        elevate()

    log.info("CYPHER Background Service initializing...")

    # Lazy Load Core Services
    try:
        from core.server import app as flask_app, socketio
        from core import discovery
        from core import tray
    except ImportError as e:
        log.critical(f"Failed to import core modules: {e}")
        sys.exit(1)

    # 2. Start the 'Brain' (Server)
    start_server(flask_app, socketio)

    # 3. Start the 'Lighthouse' (Discovery)
    pc_name = get_pc_name()
    discovery.start_discovery_thread(pc_name)

    # 4. Start the 'Control' (Tray Icon)
    tray.start_tray()

    log.info("CYPHER System is now persistent in the background.")

    # Keep the main thread alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
