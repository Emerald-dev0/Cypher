"""Single place the node reports who it is (P1-D1; P1-B8 will drive this from VERSION)."""

from __future__ import annotations

# Bump when the HTTP/Socket.IO contract changes in a way old clients cannot ignore.
PROTOCOL_VERSION = 1

# Product version until P1-B8 (one VERSION file) lands.
NODE_VERSION = "0.9.0-beta"
