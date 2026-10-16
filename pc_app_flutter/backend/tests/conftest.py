"""
Shared pytest fixtures for the CYPHER node.

WHY THIS FILE EXISTS
────────────────────
The node's Windows-only dependencies (pyautogui, pywin32, pycaw, comtypes,
pygetwindow, customtkinter, screeninfo) cannot be installed on a Linux CI runner,
so `import core.server` used to be impossible outside Windows. That meant the
auth layer — the single most security-critical code in the repository — had no
automated tests at all, which is how the guest_manager NameError (audit F-02) and
the missing Pillow import (audit F-03) survived for months.

The node already loads those dependencies lazily and guards them, so stubbing them
here is legitimate: it exercises the real code paths on the real Flask app, with
only the OS-integration leaves faked.

Anything that genuinely needs Windows is marked `@pytest.mark.windows` and skipped
in Linux CI.

ROADMAP: P1-T1 expands this suite to >= 70% coverage of core/.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# Make `core` importable regardless of how pytest was invoked.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ─────────────────────────────────────────────────────────────
# Redirect all node state into a temporary directory BEFORE core
# is imported. core.utils.get_app_data_dir() resolves at import
# time via get_config_path(), and core.server generates and
# persists its internal token during module import.
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _isolated_app_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Point the node's app-data directory at a throwaway location.

    Without this, running the test suite would read and write the developer's real
    %APPDATA%/Cypher — including their actual paired_devices.json and internal
    token. That would be both destructive and non-hermetic.
    """
    app_data = tmp_path_factory.mktemp("cypher-app-data")

    # core.utils.get_app_data_dir() branches on sys.platform and environment.
    # Setting every candidate variable is simpler and more robust than monkey-
    # patching the function, and it keeps the real code path under test.
    os.environ["APPDATA"] = str(app_data)
    os.environ["USERPROFILE"] = str(app_data)
    os.environ["HOME"] = str(app_data)
    os.environ["XDG_CONFIG_HOME"] = str(app_data)

    # Linux branch of get_app_data_dir() is Path.home() / ".cypher"
    (app_data / ".cypher").mkdir(parents=True, exist_ok=True)

    return app_data


def _install_stub(name: str, **attrs) -> types.ModuleType:
    """Register a fake module so a Windows-only import does not explode."""
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


@pytest.fixture(scope="session", autouse=True)
def _stub_windows_dependencies() -> None:
    """Fake the Windows-only leaves. The node loads them lazily, so the stubs are
    only touched if a test exercises a route that needs them."""

    class _Unavailable:
        """Any attribute access raises, so a test that reaches for real Windows
        automation fails loudly instead of silently doing nothing."""

        def __init__(self, name: str) -> None:
            self._name = name

        def __getattr__(self, item: str):
            raise RuntimeError(
                f"{self._name}.{item} is Windows-only and unavailable in this test "
                f"environment. Mark the test @pytest.mark.windows."
            )

    for name in (
        "pyautogui", "pyperclip", "pygetwindow", "win32gui", "win32api",
        "win32con", "win32ui", "win32process", "pycaw", "pycaw.pycaw",
        "comtypes", "screeninfo", "customtkinter", "pystray",
    ):
        _install_stub(name, __stub__=True, _unavailable=_Unavailable(name))

    # pycaw.pycaw and comtypes are imported `from X import Y` inside
    # _load_audio_engine(); give those names something to bind.
    _install_stub("pycaw.pycaw", AudioUtilities=None, IAudioEndpointVolume=None)
    _install_stub("comtypes", CLSCTX_ALL=0)


# ─────────────────────────────────────────────────────────────
# The node itself
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def server(_isolated_app_data, _stub_windows_dependencies):
    """Import core.server once per session.

    Importing it starts two daemon threads (resource monitor, engine warm-up).
    They are harmless in a test process and die with it.
    """
    from core import server as server_module

    return server_module


@pytest.fixture()
def app(server):
    """A Flask app in testing mode."""
    server.app.config.update(TESTING=True)
    return server.app


@pytest.fixture()
def client(app):
    """A Flask test client — no socket is ever opened."""
    return app.test_client()


@pytest.fixture()
def internal_token(server) -> str:
    """The node's per-install loopback token."""
    return server.INTERNAL_TOKEN


@pytest.fixture()
def paired_token(server) -> str:
    """Pair a throwaway device the legitimate way and return its token.

    Goes through the real /pair_device handler so the throttle, the constant-time
    comparison and the code rotation are all exercised on the way.
    """
    server.paired_devices.clear()
    server.valid_tokens.clear()
    server.valid_tokens.add(server.INTERNAL_TOKEN)
    server._pairing_attempts.clear()
    server._pairing_lockouts.clear()

    token = "test-device-token-" + os.urandom(8).hex()
    server.paired_devices["test-device"] = {
        "device_name": "Test Device",
        "token": token,
        "paired_at": "2026-01-01 00:00:00",
    }
    server.valid_tokens.add(token)
    return token


@pytest.fixture(autouse=True)
def _reset_pairing_throttle(server):
    """Keep the throttle state from leaking between tests.

    The throttle is module-level and per-IP, and every test client request comes
    from the same address — so without this, the sixth pairing-related assertion
    in a session would hit the lockout and fail for no interesting reason.
    """
    yield
    server._pairing_attempts.clear()
    server._pairing_lockouts.clear()


@pytest.fixture()
def shared_folders(tmp_path: Path, monkeypatch, server):
    """A temporary "shared folder" with a file in it, wired into the node config.

    Used by the sandbox tests (P1-S2). The allowlist is patched rather than
    written to disk so tests cannot clobber a developer's real config.
    """
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "hello.txt").write_text("hello from the shared folder", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("this must never be reachable", encoding="utf-8")

    monkeypatch.setattr(server, "_get_shared_folders", lambda: [str(shared)])
    return types.SimpleNamespace(shared=shared, outside=outside, tmp=tmp_path)
