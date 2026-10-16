"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('media', __name__)
bind(globals())

@bp.route('/clipboard/phone', methods=['GET', 'POST'], endpoint='handle_phone_clipboard')
def handle_phone_clipboard():
    global phone_clipboard
    if request.method == 'POST':
        content = request.json.get("text", "")
        # Check if content is a base64 image
        if content.startswith("data:image"):
             phone_clipboard = {
                "content": content,
                "type": "image",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            phone_clipboard = {
                "content": content,
                "type": "text",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        return jsonify({"success": True, "action": "phone_clipboard_saved"})

    return jsonify({"success": True, **phone_clipboard})

@bp.route('/clipboard/paste-from-phone', methods=['POST'], endpoint='paste_from_phone')
def paste_from_phone():
    if not WINDOWS or not pyperclip:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    if phone_clipboard["content"]:
        log_to_ui(f"Pasted {phone_clipboard.get('type', 'text')} from Phone")
        if phone_clipboard.get("type") == "image":
            # Image setting logic can be complex via native API, saving temp for now
            try:
                 header, encoded = phone_clipboard["content"].split(",", 1)
                 data = base64.b64decode(encoded)
                 img = Image.open(io.BytesIO(data))
                 # [CHAOS FIX] Save to a proper path or use native clipboard
                 img.save(get_app_data_dir() / "temp_clip.png")
            except: pass

        pyperclip.copy(phone_clipboard["content"])
        return jsonify({"success": True, "action": "pasted_to_pc"})
    return jsonify({"success": False, "error": "Phone buffer is empty"}), 400

@bp.route('/clipboard/pc', methods=['GET'], endpoint='get_pc_clipboard')
def get_pc_clipboard():
    """Returns the current PC clipboard (Text or Image)."""
    if not WINDOWS or not ImageGrab:
        return jsonify({"type": "text", "content": ""})
    try:
        # Check for image first
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            return jsonify({
                "type": "image",
                "content": f"data:image/png;base64,{img_str}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        # Fallback to text
        text = pyperclip.paste()
        return jsonify({
            "type": "text",
            "content": text or "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/screenshot', methods=['GET'], endpoint='get_screenshot')
def get_screenshot():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    try:
        add_activity("Screenshot Taken", "A remote screen capture was initiated.", category="Commands")
        log_to_ui("Screenshot Captured")
        screenshot = pyautogui.screenshot()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="JPEG", quality=60)
        buffered.seek(0)
        return send_file(buffered, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/clipboard', methods=['GET', 'POST'], endpoint='handle_pc_clipboard')
def handle_pc_clipboard():
    _load_automation()
    if request.method == 'GET':
        if not WINDOWS or not pyperclip:
            return jsonify({"success": True, "content": ""})
        return jsonify({"success": True, "content": pyperclip.paste()})
    if not WINDOWS or not pyperclip:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400

    # Handle both 'content' (Mobile) and 'text' (Legacy) keys
    data = request.json
    text = data.get("content") or data.get("text", "")

    if len(text) > 1024 * 1024:
        return jsonify({"success": False, "error": "Clipboard content too large"}), 413
    log_to_ui("Clipboard Updated")
    pyperclip.copy(text)
    return jsonify({"success": True, "action": "clipboard_set"})

@bp.route('/open-link', methods=['POST'], endpoint='open_remote_link')
def open_remote_link():
    """Support for 'Open Link' feature from mobile clipboard."""
    url = request.json.get("url", "")
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400
    try:
        import webbrowser
        webbrowser.open(url)
        log_to_ui(f"Opened: {url[:30]}...")
        return jsonify({"success": True, "action": "link_opened"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/type', methods=['POST'], endpoint='remote_type')
def remote_type():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    text = request.json.get("text", "")
    log_to_ui(f"Typed: {text[:15]}...")
    # Give system a tiny moment to stabilize focus if needed
    time.sleep(0.1)
    pyautogui.write(text, interval=0.01)
    return jsonify({"success": True, "text": text})

@bp.route('/keyboard/hotkey', methods=['POST'], endpoint='remote_hotkey')
def remote_hotkey():
    _load_automation()
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    keys = request.json.get("keys", [])
    if keys:
        log_to_ui(f"Hotkey: {'+'.join(keys)}")
        time.sleep(0.1)
        pyautogui.hotkey(*keys)
        return jsonify({"success": True, "keys": keys})
    return jsonify({"success": False, "error": "No keys provided"}), 400

@bp.route('/media/volume/get', methods=['GET'], endpoint='get_volume')
def get_volume():
    _load_audio_engine()
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available"}), 400
    try:
        ctypes.windll.ole32.CoInitialize(None)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        current_volume = volume.GetMasterVolumeLevelScalar()
        return jsonify({"success": True, "level": int(current_volume * 100)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        ctypes.windll.ole32.CoUninitialize()

@bp.route('/media/volume/set', methods=['POST'], endpoint='volume_set_exact')
def volume_set_exact():
    _load_audio_engine()
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    level = request.json.get("level", 50)
    log_to_ui(f"Volume Set: {level}%")
    try:
        ctypes.windll.ole32.CoInitialize(None)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return jsonify({"success": True, "level": level})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        ctypes.windll.ole32.CoUninitialize()

@bp.route('/media/<action>', methods=['POST'], endpoint='media_generic_control')
def media_generic_control(action):
    if not WINDOWS or not pyautogui:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    map = {"playpause": "playpause", "next": "nexttrack", "prev": "prevtrack", "stop": "stop", "mute": "volumemute"}
    if action in map:
        log_to_ui(f"Media: {action}")
        pyautogui.press(map[action])
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid media action"}), 400

@bp.route('/media/volumeup', methods=['POST'], endpoint='volume_up')
def volume_up():
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    set_volume(0.05)
    return jsonify({"success": True})

@bp.route('/media/volumedown', methods=['POST'], endpoint='volume_down')
def volume_down():
    if not WINDOWS or not AudioUtilities:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    set_volume(-0.05)
    return jsonify({"success": True})

