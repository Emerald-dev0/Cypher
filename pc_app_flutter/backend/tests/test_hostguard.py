"""P1-S4 / S-07: Host header allowlist."""

from __future__ import annotations

from core.hostguard import host_header_allowed, parse_host_header


def test_loopback_hosts_are_allowed():
    for h in ("127.0.0.1", "127.0.0.1:5000", "localhost", "localhost:5000", "[::1]", "[::1]:5000"):
        assert host_header_allowed(h), h


def test_public_hostname_is_rejected():
    assert host_header_allowed("evil.example") is False
    assert host_header_allowed("evil.example:5000") is False


def test_empty_is_rejected():
    assert host_header_allowed(None) is False
    assert host_header_allowed("") is False


def test_parse_strips_port():
    assert parse_host_header("127.0.0.1:5000") == "127.0.0.1"
    assert parse_host_header("[::1]:5000") == "[::1]"


def test_flask_rejects_foreign_host(client):
    r = client.get("/ping", headers={"Host": "evil.example"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid host"


def test_flask_accepts_localhost(client):
    r = client.get("/ping", headers={"Host": "127.0.0.1:5000"})
    assert r.status_code == 200
