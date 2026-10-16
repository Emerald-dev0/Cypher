"""Host-header and CORS origin allowlists (P1-S4 / S-07).

The node is a code-execution service on the LAN. A website the user visits
must not be able to talk to it via DNS rebinding (Host: attacker.com → 127.0.0.1)
or via wildcard CORS. Allowed Host values are loopback and this machine's own
addresses only — not "any private IP".
"""

from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


@lru_cache(maxsize=1)
def own_addresses() -> frozenset[str]:
    names: set[str] = set(LOOPBACK_HOSTS)
    try:
        hostname = socket.gethostname()
        names.add(hostname.lower())
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if addr:
                names.add(addr.lower())
                if ":" in addr:
                    names.add(f"[{addr.lower()}]")
    except OSError:
        pass
    return frozenset(names)


def parse_host_header(host_header: str) -> str:
    """Return the hostname (no port) from a Host header."""
    host = host_header.strip().lower()
    if not host:
        return ""
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return ""
        return host[: end + 1]
    # IPv4 or name with optional :port. IPv6 without brackets has >1 colon.
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def host_header_allowed(
    host_header: str | None,
    extra: frozenset[str] | None = None,
) -> bool:
    if not host_header:
        return False
    name = parse_host_header(host_header)
    if not name:
        return False
    allowed = {a.lower() for a in own_addresses()}
    if extra:
        allowed |= {a.lower() for a in extra}
    if name in allowed or name in LOOPBACK_HOSTS:
        return True
    bare = name[1:-1] if name.startswith("[") and name.endswith("]") else name
    try:
        ip = ipaddress.ip_address(bare)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    return bare in allowed or name in allowed


def cors_origin_list() -> list[str]:
    origins: list[str] = []
    for h in sorted(own_addresses()):
        if h.startswith("["):
            origins.append(f"http://{h}")
            origins.append(f"http://{h}:5000")
            continue
        if ":" in h:
            origins.append(f"http://[{h}]")
            origins.append(f"http://[{h}]:5000")
            continue
        origins.append(f"http://{h}")
        origins.append(f"http://{h}:5000")
    return origins
