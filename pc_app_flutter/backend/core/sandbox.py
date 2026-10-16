"""Filesystem sandbox for the CYPHER node.

Owns exactly one question: may this session touch this path?

P1-S2. The implementation is the helper that already lived in core/server.py as
`is_path_in_folders` — Path.resolve() then relative_to() against an allowlist —
promoted so every filesystem route, not just /guest/*, has to go through it.

Nothing else in the codebase should resolve or validate a filesystem path. Adding
a new /files/* route without calling Sandbox.resolve is a bug; tests/test_sandbox.py
enumerates the routes and will fail the build.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

Access = Literal["read", "write", "delete", "execute"]


class SandboxViolation(Exception):
    """Raised when a path escapes every allowed root, or cannot be resolved."""


class Sandbox:
    """Allowlist of canonical roots. Containment is checked on the *resolved* path.

    resolve() collapses `..`, follows symlinks, and normalises separators / case
    the way the OS does. A symlink inside a shared folder that points at
    /etc/shadow therefore resolves outside the root and is refused — that is the
    whole point, and tests/test_sandbox.py pins it.
    """

    def __init__(self, roots: Iterable[str | Path], follow_symlinks: bool = True) -> None:
        # follow_symlinks defaults to True because Path.resolve() follows them;
        # refusing a resolved path that escaped is how we handle the escape, not
        # by walking lstat() ourselves. The flag is accepted so the signature
        # matches docs/plans/security-hardening.md §3.2.
        self._follow_symlinks = follow_symlinks
        self._roots: list[Path] = []
        for raw in roots:
            try:
                # strict=False: a configured folder that does not exist yet must
                # not crash the node at construction. Containment still works.
                self._roots.append(Path(raw).expanduser().resolve(strict=False))
            except (OSError, ValueError):
                continue

    def resolve(self, raw: str | Path, *, need: Access = "read") -> Path:
        """Return the canonical path if it is inside an allowed root.

        `need` is part of the public contract (read/write/delete/execute) so
        callers declare intent. The current policy does not distinguish them —
        if a path is inside a shared folder, every operation is permitted.
        Narrower scopes belong to guest sessions (their own Sandbox) and to
        P2-S5, not to a silent denylist here.

        Raises SandboxViolation otherwise. The exception message is deliberately
        generic: leaking the resolved path helps an attacker map the disk.
        """
        del need  # reserved; see docstring
        if raw is None or str(raw).strip() == "":
            raise SandboxViolation("empty path")
        try:
            candidate = Path(raw).expanduser().resolve(strict=False)
        except (OSError, ValueError) as exc:
            raise SandboxViolation("unresolvable path") from exc

        if not self._roots:
            raise SandboxViolation("path is outside the shared folders")

        for root in self._roots:
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            return candidate

        raise SandboxViolation("path is outside the shared folders")


def is_path_in_folders(file_path: str, allowed_folders: list[str]) -> bool:
    """Boolean wrapper kept for the guest routes and existing tests.

    True iff Sandbox(allowed_folders).resolve(file_path) succeeds. Never raises.
    """
    try:
        Sandbox(allowed_folders).resolve(file_path, need="read")
    except SandboxViolation:
        return False
    return True
