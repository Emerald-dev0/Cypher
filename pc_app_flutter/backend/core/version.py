"""Single place the node reports who it is (P1-D1 / P1-B8).

``VERSION`` at the repository root is the source of truth. This module reads it
at import; if the file is missing (PyInstaller one-file, odd cwd) we fall back
to the last known string so the node still boots.
"""

from __future__ import annotations

from pathlib import Path

# Bump when the HTTP/Socket.IO contract changes in a way old clients cannot ignore.
PROTOCOL_VERSION = 1

_FALLBACK = "0.9.0-beta"


def _read_node_version() -> str:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "VERSION",  # repo root: Cypher/VERSION
        here.parents[2] / "VERSION",  # pc_app_flutter/VERSION
        Path.cwd() / "VERSION",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip()
    return _FALLBACK


NODE_VERSION = _read_node_version()
