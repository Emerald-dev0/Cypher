"""P1-S3: @public_route is the only way a view becomes unauthenticated."""

from __future__ import annotations

from core.auth import (
    PUBLIC_ATTR,
    is_public_view,
    public_endpoint_names,
    public_route,
)


def test_undecorated_callable_is_not_public():
    def ping():  # name is the S-04 trap
        return "pong"

    assert is_public_view(ping) is False
    assert public_endpoint_names({"ping": ping}) == frozenset()


def test_decorated_callable_is_public():
    @public_route
    def ping():
        return "pong"

    assert getattr(ping, PUBLIC_ATTR) is True
    assert is_public_view(ping) is True
    assert public_endpoint_names({"ping": ping, "other": lambda: None}) == frozenset({"ping"})


def test_none_is_not_public():
    assert is_public_view(None) is False
