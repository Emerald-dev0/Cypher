"""Exercise authenticated routes so coverage is not just the auth hook.

These are behavioural smoke tests on Linux CI: Windows-only leaves (input,
capture, volume COM) may 400/500; we still require the handler to *run*
authenticated and never 401.
"""

from __future__ import annotations

import pytest


def _h(token: str) -> dict[str, str]:
    return {"X-Auth-Token": token}


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/settings"),
        ("GET", "/events"),
        ("GET", "/uptime"),
        ("GET", "/connection-info"),
        ("GET", "/files/shared"),
        ("GET", "/files"),
        ("GET", "/files/list"),
        ("GET", "/files/transfers"),
        ("GET", "/files/upload-destinations"),
        ("GET", "/history"),
        ("GET", "/notifications"),
        ("GET", "/recording/status"),
        ("GET", "/battery/status"),
        ("GET", "/network"),
        ("GET", "/connect-code"),
        ("GET", "/paired-devices"),
        ("GET", "/security/sessions"),
        ("GET", "/system/activity"),
        ("GET", "/system/resource-trends"),
        ("GET", "/guest/sessions"),
        ("GET", "/apps"),
        ("GET", "/processes"),
        ("GET", "/system/displays"),
        ("GET", "/system/active-windows"),
        ("GET", "/activewindow"),
        ("GET", "/clipboard/phone"),
        ("GET", "/media/volume/get"),
        ("GET", "/status"),
    ],
)
def test_authenticated_gets_are_not_401(client, paired_token, method, path):
    r = client.open(path, method=method, headers=_h(paired_token))
    assert r.status_code != 401, f"{method} {path} still 401 with a valid token"
    assert r.status_code != 400 or r.get_json() is None or r.get_json().get("error") != "invalid host"


def test_connect_code_returns_six_digits(client, paired_token):
    r = client.get("/connect-code", headers=_h(paired_token))
    assert r.status_code == 200
    code = r.get_json()["code"]
    assert isinstance(code, str) and len(code) == 6 and code.isdigit()


def test_settings_get_and_post_roundtrip(client, paired_token, tmp_path, server, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    r = client.get("/settings", headers=_h(paired_token))
    assert r.status_code == 200
    r = client.post(
        "/settings",
        headers=_h(paired_token),
        json={"device_name": "test-node"},
    )
    assert r.status_code in (200, 500)


def test_events_connected_and_disconnected(client, paired_token):
    assert client.post("/events/connected", headers=_h(paired_token), json={"name": "phone"}).status_code != 401
    assert client.post("/events/disconnected", headers=_h(paired_token), json={"name": "phone"}).status_code != 401
    body = client.get("/events", headers=_h(paired_token)).get_json()
    assert body is not None


def test_phone_clipboard_roundtrip(client, paired_token):
    r = client.post("/clipboard/phone", headers=_h(paired_token), json={"text": "hello"})
    assert r.status_code != 401
    r = client.get("/clipboard/phone", headers=_h(paired_token))
    assert r.status_code == 200


def test_notifications_add(client, paired_token):
    r = client.post(
        "/notifications/add",
        headers=_h(paired_token),
        json={"title": "t", "body": "b"},
    )
    assert r.status_code != 401
    listed = client.get("/notifications", headers=_h(paired_token))
    assert listed.status_code == 200


def test_guest_create_with_real_folder(client, paired_token, shared_folders):
    r = client.post(
        "/guest/create",
        headers=_h(paired_token),
        json={"folders": [str(shared_folders.shared)], "duration_minutes": 5},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["success"] is True
    token = body["token"]
    landing = client.get("/guest/access", query_string={"token": token})
    assert landing.status_code == 200
    files = client.get("/guest/files", query_string={"token": token})
    assert files.status_code == 200


def test_guest_access_without_token_is_401(client):
    r = client.get("/guest/access")
    assert r.status_code in (401, 400)


def test_guest_files_without_token_is_401(client):
    r = client.get("/guest/files")
    assert r.status_code in (401, 400)


def test_recording_status_shape(client, paired_token):
    r = client.get("/recording/status", headers=_h(paired_token))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)


def test_files_browse_shared(client, paired_token, shared_folders):
    r = client.get(
        "/files/browse",
        headers=_h(paired_token),
        query_string={"path": str(shared_folders.shared)},
    )
    assert r.status_code == 200


def test_files_list_for_app(client, paired_token, shared_folders):
    r = client.get("/files/list", headers=_h(paired_token))
    assert r.status_code in (200, 400)


def test_history_is_a_list(client, paired_token):
    r = client.get("/history", headers=_h(paired_token))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_system_activity_is_a_list(client, paired_token):
    r = client.get("/system/activity", headers=_h(paired_token))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_unpair_unknown_is_not_500(client, paired_token):
    r = client.post("/unpair", headers=_h(paired_token), json={"device_id": "no-such"})
    assert r.status_code in (200, 400, 404)


def test_media_volume_get_does_not_401(client, paired_token):
    r = client.post("/media/volumeup", headers=_h(paired_token))
    assert r.status_code != 401
    r = client.post("/media/volumedown", headers=_h(paired_token))
    assert r.status_code != 401


def test_open_link_requires_auth(client, paired_token):
    r = client.post("/open-link", headers=_h(paired_token), json={"url": "https://example.com"})
    assert r.status_code != 401


def test_type_requires_auth(client, paired_token):
    r = client.post("/type", headers=_h(paired_token), json={"text": "hi"})
    assert r.status_code != 401


def test_hotkey_requires_auth(client, paired_token):
    r = client.post("/keyboard/hotkey", headers=_h(paired_token), json={"keys": "ctrl+c"})
    assert r.status_code != 401


def test_screenshot_requires_auth(client, paired_token):
    r = client.get("/screenshot", headers=_h(paired_token))
    assert r.status_code != 401


def test_wol_requires_auth(client, paired_token):
    r = client.post("/wol", headers=_h(paired_token), json={"mac": "00:11:22:33:44:55"})
    assert r.status_code != 401


def test_power_lock_requires_auth(client, paired_token):
    r = client.post("/power/lock", headers=_h(paired_token))
    assert r.status_code != 401


def test_apps_launch_missing_path(client, paired_token):
    r = client.post("/apps/launch", headers=_h(paired_token), json={})
    assert r.status_code in (400, 403, 500)


def test_files_thumbnail_outside_still_denied(client, paired_token, shared_folders):
    r = client.get(
        "/files/thumbnail",
        headers=_h(paired_token),
        query_string={"path": str(shared_folders.outside / "secret.txt")},
    )
    assert r.status_code in (403, 400)


def test_cors_origin_list_includes_loopback():
    from core.hostguard import cors_origin_list

    origins = cors_origin_list()
    assert any("127.0.0.1" in o or "localhost" in o for o in origins)


def test_version_file_is_readable():
    from core.version import NODE_VERSION, PROTOCOL_VERSION

    assert PROTOCOL_VERSION == 1
    assert NODE_VERSION
    assert "\n" not in NODE_VERSION


def test_log_event_redacts_sensitive(tmp_path, monkeypatch):
    from core import utils

    monkeypatch.setattr(utils, "get_config_path", lambda name: tmp_path / name)
    utils.log_event("clipboard", {"text": "secret"}, sensitive=True)
    import json

    data = json.loads((tmp_path / "analytics_log.json").read_text(encoding="utf-8"))
    assert data[-1]["sensitive"] is True
    assert data[-1]["details"] == "<redacted>"
