"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('recording', __name__)
bind(globals())

@bp.route('/recording/start', methods=['POST'], endpoint='start_recording')
def start_recording():
    global recording_state
    if recording_state["is_recording"]:
        return jsonify({"success": False, "error": "Recording already in progress"}), 400

    data = request.json or {}
    source = data.get("source", "fullscreen")

    record_dir = Path.home() / "Videos" / "CYPHER"
    record_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    filepath = record_dir / filename

    recording_state.update({
        "is_recording": True,
        "is_paused": False,
        "start_time": time.time(),
        "filename": filename,
        "filepath": str(filepath),
        "source": source
    })

    # Start the background recording thread
    threading.Thread(target=recording_worker, daemon=True).start()

    add_activity("Screen Recording", f"Started session ({source}).", category="Commands")
    log_to_ui(f"Recording Started: {source}")
    get_overlay_manager().start()
    return jsonify({"success": True, "filename": filename})

@bp.route('/recording/status', methods=['GET'], endpoint='get_recording_status')
def get_recording_status():
    return jsonify({
        "is_recording": recording_state["is_recording"],
        "is_paused": recording_state["is_paused"],
        "duration": int(time.time() - recording_state["start_time"]) if recording_state["is_recording"] else 0,
        "filename": recording_state["filename"]
    })

@bp.route('/recording/pause', methods=['POST'], endpoint='pause_recording')
def pause_recording():
    global recording_state
    if not recording_state["is_recording"]:
        return jsonify({"success": False, "error": "No recording in progress"}), 400
    recording_state["is_paused"] = not recording_state["is_paused"]
    action = "Paused" if recording_state["is_paused"] else "Resumed"
    log_to_ui(f"Recording {action}")
    return jsonify({"success": True, "is_paused": recording_state["is_paused"]})

@bp.route('/recording/stop', methods=['POST'], endpoint='stop_recording')
def stop_recording():
    global recording_state
    if not recording_state["is_recording"]:
        return jsonify({"success": False, "error": "No recording in progress"}), 400
    filepath = recording_state["filepath"]
    recording_state.update({"is_recording": False, "is_paused": False, "start_time": None})
    add_activity("Recording Saved", "Session stored in Videos/CYPHER.", category="Commands", attachment=os.path.basename(filepath))
    log_to_ui("Recording Stopped & Saved")
    get_overlay_manager().stop()
    return jsonify({"success": True, "path": filepath})

