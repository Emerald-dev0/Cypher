"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('pairing', __name__)
bind(globals())

@bp.route('/connect-code', methods=['GET', 'POST'], endpoint='get_connect_code')
def get_connect_code():
    """Returns or rotates the current pairing code."""
    global PAIRING_CODE
    if request.method == 'POST':
        PAIRING_CODE = _generate_dynamic_code()
        add_activity("Security", "Pairing code was rotated for enhanced security.", category="Connections")
    return jsonify({"code": PAIRING_CODE})

@bp.route('/pair_device', methods=['POST'], endpoint='pair_device')
@public_route
def pair_device():
    # `global` must precede the first use of the name in this function, otherwise
    # it is a SyntaxError ("used prior to global declaration") that takes down the
    # whole module at import time — the exact failure mode of audit finding F-01.
    global PAIRING_CODE

    data = request.get_json(silent=True) or {}
    client_code = str(data.get("pairing_code", ""))
    device_id = data.get("device_id")
    device_name = data.get("device_name", "Unknown Device")

    if not device_id:
        return jsonify({"success": False, "error": "device_id is required"}), 400

    client_ip = request.remote_addr or "unknown"

    # Throttle BEFORE comparing, otherwise a locked-out attacker can still
    # redeem a code they guessed while locked out.
    allowed, retry_after = _pairing_throttle(client_ip)
    if not allowed:
        add_activity(
            "Pairing Blocked",
            f"{client_ip} exceeded the attempt limit and was locked out.",
            category="Security",
            is_urgent=True,
        )
        response = jsonify({
            "success": False,
            "error": "Too many pairing attempts. Try again later.",
            "retry_after": retry_after,
        })
        response.headers["Retry-After"] = str(retry_after)
        return response, 429

    # Constant-time comparison: a plain `==` short-circuits on the first
    # differing character and leaks the code one digit at a time over a LAN.
    if not hmac.compare_digest(client_code, PAIRING_CODE):
        return jsonify({"success": False, "error": "Invalid pairing code"}), 401

    auth_token = secrets.token_hex(32)
    paired_devices[device_id] = {
        "device_name": device_name,
        "token": auth_token,
        "paired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_ip": client_ip,
    }
    valid_tokens.add(auth_token)
    save_paired_devices()

    # Rotate the code on every successful pairing so it is single-use, and
    # clear the throttle for this address now that it is authenticated.
    PAIRING_CODE = _generate_dynamic_code()
    _pairing_reset(client_ip)

    add_activity(
        "Device Paired",
        f"Successfully linked {device_name} via secure bridge.",
        category="Connections"
    )
    return jsonify({"success": True, "token": auth_token}), 200

@bp.route('/paired-devices', methods=['GET'], endpoint='get_paired_devices')
def get_paired_devices():
    devices = [{"device_id": k, "device_name": v["device_name"], "token": v["token"]} for k, v in paired_devices.items()]
    return jsonify(devices), 200

@bp.route('/unpair', methods=['POST'], endpoint='unpair_device')
def unpair_device():
    device_id = request.json.get("device_id")
    if device_id in paired_devices:
        valid_tokens.discard(paired_devices[device_id]["token"])
        del paired_devices[device_id]
        save_paired_devices()
        return jsonify({"success": True, "action": "unpaired"})
    return jsonify({"success": False, "error": "Device not found"}), 404

