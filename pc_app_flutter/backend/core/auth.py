"""Authentication helpers for the CYPHER node.

P1-S3. Public routes are opted *in* with ``@public_route``. The unauthenticated
surface is therefore the set of functions that carry the mark — renaming a
handler cannot silently expose it, which is how audit S-04 happened when the
allowlist was a list of function-name strings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Attribute set on every view that is reachable without a token.
PUBLIC_ATTR = "_cypher_public"


def public_route(fn: F) -> F:
    """Mark a Flask view as reachable without an auth token.

    Apply *under* ``@app.route`` so Flask registers the same object that carries
    the mark::

        @app.route("/ping")
        @public_route
        def ping(): ...
    """
    setattr(fn, PUBLIC_ATTR, True)
    return fn


def is_public_view(view: object | None) -> bool:
    return bool(view is not None and getattr(view, PUBLIC_ATTR, False))


def public_endpoint_names(view_functions: Mapping[str, object]) -> frozenset[str]:
    """Names of views marked ``@public_route``. Used by tests as the source of truth."""
    return frozenset(name for name, fn in view_functions.items() if is_public_view(fn))
