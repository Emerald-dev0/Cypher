"""Run blueprint view functions in ``core.server``'s namespace.

See register_blueprints: Flask captures the original view in a deferred
lambda, so we rewrite ``app.view_functions`` *after* register_blueprint.
"""

from __future__ import annotations

import types
from typing import Any


def bind(module_globals: dict[str, Any]) -> None:
    return None


def rewire_app_views(app: Any) -> None:
    import core.server as server

    ns = server.__dict__
    for endpoint, fn in list(app.view_functions.items()):
        if not isinstance(fn, types.FunctionType):
            continue
        if not getattr(fn, "__module__", "").startswith("core.routes"):
            continue
        new = types.FunctionType(
            fn.__code__,
            ns,
            fn.__name__,
            fn.__defaults__,
            fn.__closure__,
        )
        new.__kwdefaults__ = fn.__kwdefaults__
        new.__dict__.update(fn.__dict__)
        new.__annotations__ = getattr(fn, "__annotations__", {})
        app.view_functions[endpoint] = new
