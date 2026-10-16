"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('files', __name__)
bind(globals())

@bp.route('/files/shared', methods=['GET'], endpoint='get_shared_folders_list')
def get_shared_folders_list():
    """Returns just the shared folders for the PC UI."""
    try:
        shared = _get_shared_folders()
        data = []
        home = Path.home()
        for path in shared:
            full_path = path
            # Expand standard folder names if they aren't absolute paths
            if path in ["Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures"]:
                full_path = str(home / path)

            if os.path.exists(full_path):
                data.append({
                    "name": os.path.basename(path) or path,
                    "path": full_path,
                    "full_access": True # Default for now
                })
        return jsonify(data)
    except:
        return jsonify([])

@bp.route('/files', methods=['GET'], endpoint='get_root_files')
def get_root_files():
    """Returns the user-configured shared folders. Nothing else.

    Used to also enumerate every logical drive and the user's Desktop/Documents/
    Downloads — which made the allowlist decorative. P1-S2: the filesystem API
    exposes only what the operator shared.
    """
    try:
        root_data = []
        home = Path.home()
        for path in _get_shared_folders():
            full_path = path
            if path in ["Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures"]:
                full_path = str(home / path)
            if os.path.exists(full_path):
                root_data.append({
                    "name": os.path.basename(path) or path,
                    "path": full_path,
                    "type": "folder",
                    "is_shared": True
                })
        return jsonify(root_data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/list', methods=['GET'], endpoint='list_files_for_app')
def list_files_for_app():
    """Returns both directories and files for destination selection."""
    try:
        p_str = request.args.get('path', "")
        if not p_str or p_str == "":
            root_data = []
            for folder in _get_shared_folders():
                p = Path(folder)
                if p.exists():
                    root_data.append({
                        "name": p.name or str(p),
                        "path": str(p),
                        "is_dir": True,
                        "selectable": True
                    })
            return jsonify({"contents": root_data})

        p, err = _require_shared_path(p_str, need="read")
        if err:
            return err
        if not p.exists():
            return jsonify({"success": False, "error": "Path not found"}), 404

        items = []
        try:
            for item in p.iterdir():
                try:
                    if item.name.startswith('.') or item.name.startswith('$'): continue
                    is_dir = item.is_dir()
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "is_dir": is_dir,
                        "selectable": is_dir,
                        "extension": item.suffix.lower() if not is_dir else ""
                    })
                except (PermissionError, OSError): continue
        except Exception:
            pass # Return empty list rather than erroring out

        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return jsonify({"contents": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/browse', methods=['GET'], endpoint='browse_files')
def browse_files():
    try:
        path_str = request.args.get('path')
        p, err = _require_shared_path(path_str, need="read")
        if err:
            return err
        if not p.exists():
             return jsonify({"success": False, "error": "Path does not exist"}), 404
        items = []
        try:
            for count, item in enumerate(p.iterdir()):
                if count >= 5000: break
                try:
                    if item.name.startswith('$') or item.name.startswith('.'): continue
                    stats = item.stat()
                    items.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "type": "file" if item.is_file() else "folder",
                        "size": stats.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "extension": item.suffix.lower() if item.is_file() else ""
                    })
                except (PermissionError, OSError): continue
        except Exception:
            pass

        return jsonify(items)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/browse-folders', methods=['GET'], endpoint='browse_folders')
def browse_folders():
    """Browse subfolders in a given path for upload destination selection."""
    try:
        path_str = request.args.get('path')
        if not path_str:
            folders = []
            for folder in _get_shared_folders():
                folder_path = Path(folder)
                if folder_path.exists() and folder_path.is_dir():
                    folders.append({
                        "name": folder_path.name or str(folder_path),
                        "path": str(folder_path),
                        "is_dir": True,
                    })
            current = str(Path(_get_shared_folders()[0])) if _get_shared_folders() else ""
            return jsonify({"success": True, "folders": folders, "current_path": current})

        path, err = _require_shared_path(path_str, need="read")
        if err:
            return err

        if not path.exists() or not path.is_dir():
            return jsonify({"success": False, "error": "Invalid path"}), 400

        folders = []
        try:
            for item in sorted(path.iterdir()):
                try:
                    if item.is_dir() and not item.name.startswith('.'):
                        folders.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                            "is_dir": True,
                        })
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass

        # Get parent folder if not at root
        parent_path = None
        if str(path.parent) != str(path):
            parent_path = str(path.parent)

        return jsonify({
            "success": True,
            "folders": folders,
            "current_path": str(path),
            "parent_path": parent_path,
            "display_name": path.name or str(path)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/files/preview', methods=['GET'], endpoint='preview_file')
def preview_file():
    """Streams file for in-app preview with Range support and correct MIME types."""
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    size = os.path.getsize(path)
    range_header = request.headers.get('Range', None)

    if not range_header:
        return send_file(path, mimetype=mime, as_attachment=False)

    try:
        byte1, byte2 = 0, None
        m = re.search(r'(\d+)-(\d*)', range_header)
        g = m.groups()
        if g[0]: byte1 = int(g[0])
        if g[1]: byte2 = int(g[1])
        length = size - byte1
        if byte2 is not None:
            length = byte2 - byte1 + 1

        def generate():
            with open(path, 'rb') as f:
                f.seek(byte1)
                remaining = length
                while remaining > 0:
                    chunk_size = min(remaining, 1024 * 128)
                    chunk = f.read(chunk_size)
                    if not chunk: break
                    yield chunk
                    remaining -= len(chunk)

        rv = Response(generate(), 206, mimetype=mime, direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        return rv
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/files/thumbnail', methods=['GET'], endpoint='get_file_thumbnail')
def get_file_thumbnail():
    """Generates a small preview for images."""
    resolved, err = _require_shared_path(request.args.get('path'), need="read")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path) or not Image:
        return jsonify({"error": "Not found"}), 404
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return jsonify({"error": "Unsupported"}), 400
        with Image.open(path) as img:
            img.thumbnail((128, 128))
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=70)
            buffered.seek(0)
            return send_file(buffered, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/files/delete', methods=['DELETE'], endpoint='delete_file')
def delete_file():
    resolved, err = _require_shared_path(request.args.get('path'), need="delete")
    if err:
        return err
    path = str(resolved)
    if not path or not os.path.exists(path):
        return jsonify({"success": False, "error": "Not found"}), 404

    try:
        if os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path)
        log_to_ui(f"Deleted: {os.path.basename(path)}")
        return jsonify({"success": True, "action": "deleted"})
    except PermissionError:
        return jsonify({"success": False, "error": "File is currently in use"}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

