"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, render_template, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('guest', __name__)
bind(globals())

@bp.route('/guest/create', methods=['POST'], endpoint='guest_create_session')
def guest_create_session():
    """TIER 1: Create a guest session from authenticated device."""
    token = request.headers.get("X-Auth-Token")
    if not token or (token not in valid_tokens and token != INTERNAL_TOKEN):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    raw_folders = data.get("folders", [])
    duration = data.get("duration_minutes", 15)
    
    # [NEW] Normalize and Validate Folders
    valid_folders = []
    for f in raw_folders:
        p = Path(f)
        if not p.is_absolute():
            # Try to resolve common names to user home
            p = Path.home() / f

        if p.exists() and p.is_dir():
            valid_folders.append(str(p.resolve()))

    if not valid_folders:
        return jsonify({"success": False, "error": "No valid folders provided"}), 400

    guest_token = guest_manager.create_session(valid_folders, duration, token)
    local_ip = get_local_ip()
    guest_url = f"http://{local_ip}:5000/guest/access?token={guest_token}"

    add_activity(
        "Guest Link Created",
        f"A temporary access link was generated for {len(valid_folders)} folders.",
        category="Connections"
    )

    # Universal Link for the scanner
    qr_link = f"cypher://{local_ip}:5000/guest?token={guest_token}"
    
    return jsonify({
        "success": True,
        "token": guest_token,
        "url": guest_url,
        "qr_link": qr_link,
        "accepted_folders": valid_folders,
        "expires_at": (datetime.now() + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
    }), 200

@bp.route('/guest/access', methods=['GET'], endpoint='guest_landing')
def guest_landing():
    """TIER 2: Guest landing page - HTML file browser."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)
    
    if not session:
        return jsonify({"error": "Invalid or expired token"}), 401
    
    mode = request.args.get('mode', '')
    is_drop = mode == 'drop'

    html_content = render_template('guest.html', is_drop=is_drop, token=token)
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

@bp.route('/guest/files', methods=['GET'], endpoint='guest_get_files')
def guest_get_files():
    """TIER 1: List files in allowed folders for guest."""
    token = request.args.get('token')
    path = request.args.get('path', '')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    try:
        if not path:
            # Return allowed folders
            files = []
            for folder in session.allowed_folders:
                if Path(folder).exists():
                    files.append({
                        "name": Path(folder).name,
                        "path": str(Path(folder)),
                        "type": "folder",
                        "size": 0,
                        "item_count": len(list(Path(folder).iterdir())),
                        "modified": datetime.fromtimestamp(Path(folder).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "extension": ""
                    })
            return jsonify({"success": True, "files": files})

        # Validate path is in allowed folders
        if not is_path_in_folders(path, session.allowed_folders):
            return jsonify({"success": False, "error": "Access denied"}), 403

        p = Path(path)
        if not p.exists():
            return jsonify({"success": False, "error": "Path not found"}), 404

        items = []
        for item in sorted(p.iterdir()):
            try:
                stats = item.stat()
                item_count = len(list(item.iterdir())) if item.is_dir() else 0
                items.append({
                    "name": item.name,
                    "path": str(item.absolute()),
                    "type": "folder" if item.is_dir() else "file",
                    "size": stats.st_size if item.is_file() else 0,
                    "item_count": item_count,
                    "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "extension": item.suffix if item.is_file() else ""
                })
                guest_manager.log_guest_access(token, str(item), "browse")
            except:
                continue

        return jsonify({"success": True, "files": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/guest/files/search', methods=['GET'], endpoint='guest_search_files')
def guest_search_files():
    """TIER 2: Search files in allowed folders."""
    token = request.args.get('token')
    query = request.args.get('q', '').lower()

    session = guest_manager.validate_token(token)
    if not session or not query:
        return jsonify({"success": False, "error": "Invalid request"}), 400

    try:
        results = []
        for folder in session.allowed_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                continue

            for item in folder_path.rglob('*'):
                if not is_path_in_folders(str(item), session.allowed_folders):
                    continue
                if query in item.name.lower() and len(results) < 50:
                    try:
                        stats = item.stat()
                        results.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                            "type": "folder" if item.is_dir() else "file",
                            "size": stats.st_size if item.is_file() else 0,
                            "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                            "extension": item.suffix if item.is_file() else ""
                        })
                        guest_manager.log_guest_access(token, str(item), "search")
                    except:
                        continue

        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/guest/files/download', methods=['GET'], endpoint='guest_download_file')
def guest_download_file():
    """TIER 1: Download a file as guest."""
    token = request.args.get('token')
    path = request.args.get('path')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not path or not is_path_in_folders(path, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    if not os.path.isfile(path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        guest_manager.log_guest_access(token, path, "download")
        return send_file(path, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/guest/files/download/zip', methods=['POST'], endpoint='guest_download_zip')
def guest_download_zip():
    """TIER 1: Download multiple files as ZIP."""
    token = request.args.get('token')
    data = request.json or {}
    paths = data.get('paths', [])

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not paths:
        return jsonify({"success": False, "error": "No files selected"}), 400

    # Validate all paths
    for path in paths:
        if not is_path_in_folders(path, session.allowed_folders):
            return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                if os.path.isfile(path):
                    zf.write(path, arcname=os.path.basename(path))
                    guest_manager.log_guest_access(token, path, "zip-download")

        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='files.zip')
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/guest/files/upload', methods=['POST'], endpoint='guest_upload_files')
def guest_upload_files():
    """TIER 1: Upload files as guest."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)

    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    files = request.files.getlist('file')
    dest = request.form.get('destination') or (session.allowed_folders[0] if session.allowed_folders else "")

    if not is_path_in_folders(dest, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    results = []
    for file in files:
        try:
            target_path = get_unique_path(os.path.join(dest, file.filename))
            file.save(target_path)
            guest_manager.log_guest_access(token, target_path, "upload")
            results.append({"name": file.filename, "status": "success"})
        except Exception as e:
            results.append({"name": file.filename, "status": "error", "message": str(e)})

    return jsonify({"success": True, "files": results}), 200

@bp.route('/guest/files/preview', methods=['GET'], endpoint='guest_preview_file')
def guest_preview_file():
    """TIER 2: Preview file without downloading."""
    token = request.args.get('token')
    path = request.args.get('path')

    session = guest_manager.validate_token(token)
    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    if not path or not is_path_in_folders(path, session.allowed_folders):
        return jsonify({"success": False, "error": "Access denied"}), 403

    if not os.path.exists(path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        guest_manager.log_guest_access(token, path, "preview")
        return send_file(path, as_attachment=False)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/guest/session', methods=['GET'], endpoint='guest_get_session')
def guest_get_session():
    """TIER 2: Get session info including timer."""
    token = request.args.get('token')
    session = guest_manager.validate_token(token)

    if not session:
        return jsonify({"success": False, "error": "Invalid or expired token"}), 401

    return jsonify({
        "success": True,
        "token": token,
        "created_at": session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": session.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "time_remaining_seconds": max(0, int((session.expires_at - datetime.now()).total_seconds())),
        "access_count": session.access_count,
        "allowed_folders": session.allowed_folders,
        "is_active": session.is_active
    }), 200

@bp.route('/guest/extend', methods=['POST'], endpoint='guest_extend_session')
def guest_extend_session():
    """TIER 3: Extend guest session from host."""
    token = request.headers.get("X-Auth-Token")
    if not token or token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    guest_token = data.get("guest_token")
    additional_minutes = data.get("additional_minutes", 30)

    if guest_manager.extend_session(guest_token, additional_minutes):
        return jsonify({"success": True, "action": "extended"}), 200

    return jsonify({"success": False, "error": "Session not found"}), 404

@bp.route('/guest/end', methods=['POST'], endpoint='guest_end_session')
def guest_end_session():
    """TIER 3: End guest session immediately."""
    token = request.headers.get("X-Auth-Token")
    if not token or token not in valid_tokens:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    guest_token = data.get("guest_token")

    if get_guest_manager().end_session(guest_token):
        add_activity("Access Revoked", f"Guest session {(guest_token or '')[:8]} terminated.", category="Connections", is_urgent=True)
        return jsonify({"success": True, "action": "ended"}), 200

    return jsonify({"success": False, "error": "Session not found"}), 404

@bp.route('/guest/sessions', methods=['GET'], endpoint='guest_list_sessions')
def guest_list_sessions():
    """TIER 3: List active guest sessions. PC UI sees all sessions."""
    token = request.headers.get("X-Auth-Token")
    if not token or (token not in valid_tokens and token != INTERNAL_TOKEN):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    # If it's the PC UI, show EVERYTHING. If it's a phone, show only what it created.
    filter_id = token if token != INTERNAL_TOKEN else None
    sessions = get_guest_manager().get_all_active_sessions(host_device_id=filter_id)
    return jsonify({"success": True, "sessions": sessions}), 200

