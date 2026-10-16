"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('transfer', __name__)
bind(globals())

@bp.route('/files/download/zip', methods=['POST'], endpoint='download_files_zip')
def download_files_zip():
    """Download multiple selected files as a single ZIP archive."""
    incoming_token = request.headers.get("X-Auth-Token")
    if not incoming_token or incoming_token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    paths = data.get('paths', [])

    if not paths:
        return jsonify({"success": False, "error": "No files selected"}), 400

    try:
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                try:
                    p = _paired_sandbox().resolve(path, need="read")
                except SandboxViolation:
                    return jsonify(_SANDBOX_DENIED), 403
                if p.exists() and p.is_file():
                    zf.write(str(p), arcname=p.name)

        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'cypher_batch_{timestamp}.zip'
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/upload-destinations', methods=['GET'], endpoint='get_upload_destinations')
def get_upload_destinations():
    """Get list of folders where files can be uploaded."""
    try:
        destinations = []
        for folder in _get_shared_folders():
            folder_path = Path(folder)
            if folder_path.exists():
                destinations.append({
                    "name": folder_path.name or str(folder_path),
                    "path": str(folder_path),
                    "icon": folder_path.name.lower()
                })

        return jsonify({"success": True, "destinations": destinations})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/upload', methods=['POST'], endpoint='upload_file_stream')
def upload_file_stream():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    files = request.files.getlist('file')
    destination = request.form.get('destination', '')

    # Resolve the destination against the allowlist BEFORE creating anything.
    # The previous code accepted an absolute path, called os.makedirs, then
    # checked a Windows denylist — so a paired device could create directories
    # anywhere on the disk (audit S-03 / F-13's sibling).
    if not destination:
        shared = _get_shared_folders()
        if not shared:
            return jsonify(_SANDBOX_DENIED), 403
        destination = shared[0]
    dest_path, err = _require_shared_path(destination, need="write")
    if err:
        return err
    dest = str(dest_path)
    os.makedirs(dest, exist_ok=True)

    from werkzeug.utils import secure_filename

    results = []
    for file in files:
        safe_name = secure_filename(file.filename or "")
        if not safe_name:
            results.append({"name": file.filename, "status": "error", "message": "invalid filename"})
            continue
        final_path = get_unique_path(os.path.join(dest, safe_name))
        temp_path = final_path + ".part" # Atomic upload pattern
        transfer_id = str(uuid.uuid4())
        active_transfers[transfer_id] = {
            "name": file.filename,
            "progress": 0,
            "status": "receiving",
            "start_time": time.time(),
            "speed": "0 KB/s"
        }

        try:
            # Atomic Save
            file.save(temp_path)
            if os.path.exists(temp_path):
                os.rename(temp_path, final_path)

            active_transfers[transfer_id]["progress"] = 100
            active_transfers[transfer_id]["status"] = "completed"

            add_activity(
                "File Received",
                f"Sync complete. Saved to {os.path.basename(dest)}.",
                category="Transfers",
                attachment=file.filename
            )

            log_to_ui(f"Received: {file.filename}")
            results.append({"name": file.filename, "status": "success"})
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path) # Cleanup broken file
            active_transfers[transfer_id]["status"] = "failed"
            results.append({"name": file.filename, "status": "error", "message": str(e)})

    return jsonify({"success": True, "files": results})

@bp.route('/files/transfers', methods=['GET'], endpoint='get_transfers')
def get_transfers():
    return jsonify(active_transfers)

@bp.route('/files/download', methods=['GET'], endpoint='download_file')
def download_file():
    path, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(path)
    if path and os.path.isfile(path):
        try:
            add_activity(
                "File Downloaded",
                f"A remote device accessed: {os.path.basename(path)}",
                category="Transfers"
            )
            return send_file(path, as_attachment=True)
        except Exception as e:
            log_event("DOWNLOAD_ERROR", {"path": path, "error": str(e)})
            return jsonify({"error": "Failed to stream file", "details": str(e)}), 500
    return jsonify({"error": "File not found"}), 404

@bp.route('/files/download/chunked', methods=['GET'], endpoint='download_chunked')
def download_chunked():
    global cancel_all_transfers
    cancel_all_transfers = False
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    try:
        f_test = open(path, "rb")
        f_test.close()
    except Exception as e:
        return jsonify({"error": "File is locked or inaccessible", "details": str(e)}), 403

    def generate():
        try:
            with open(path, "rb") as f:
                while not cancel_all_transfers:
                    chunk = f.read(1024 * 64)
                    if not chunk: break
                    yield chunk
        except Exception as e:
            log_event("STREAM_INTERRUPTED", {"path": path, "error": str(e)})
    return Response(stream_with_context(generate()), mimetype="application/octet-stream")

@bp.route('/files/download/cancel', methods=['POST'], endpoint='cancel_downloads')
def cancel_downloads():
    global cancel_all_transfers
    cancel_all_transfers = True
    log_to_ui("Downloads Cancelled")
    return jsonify({"success": True, "action": "cancelled"})

