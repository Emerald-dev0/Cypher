"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from core.auth import public_route
from .bind import bind

bp = Blueprint('system', __name__)
bind(globals())

@bp.route('/settings', methods=['GET', 'POST'], endpoint='handle_settings')
def handle_settings():
    global battery_threshold
    if request.method == 'GET':
        try:
            # 1. Load basic settings
            settings = {}
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    settings = json.load(f)
            else:
                settings = DEFAULT_SETTINGS.copy()

            # 2. Add shared folders from the master config file
            settings["shared_folders"] = _get_shared_folders()

            return jsonify(settings)
        except Exception as e:
            print(f"SERVER ERROR: Getting settings: {e}")
            return jsonify(DEFAULT_SETTINGS)

    new_settings = request.json
    try:
        # Handle shared folders separately if they are in the request
        if "shared_folders" in new_settings:
            shared = new_settings.pop("shared_folders")
            # Load existing config or start fresh
            config_data = {}
            if SHARED_FOLDERS_FILE.exists():
                with open(SHARED_FOLDERS_FILE) as f:
                    config_data = json.load(f)

            config_data["shared_folders"] = shared

            with open(SHARED_FOLDERS_FILE, 'w') as f:
                json.dump(config_data, f, indent=4)

        if not new_settings:
            return jsonify({"success": True})

        with open(SETTINGS_FILE, 'r+') as f:
            current = json.load(f)

            old_name = current.get("device_name", socket.gethostname())
            new_name = new_settings.get("device_name")

            current.update(new_settings)
            battery_threshold = current.get("battery_alert_threshold", battery_threshold)

            f.seek(0)
            json.dump(current, f, indent=4)
            f.truncate()

        # Live discovery update if name changed
        if new_name and new_name != old_name:
            try:
                start_fn, get_inst_fn = get_discovery_node()
                disc = get_inst_fn()
                if disc:
                    disc.update_name(new_name)
                    log_to_ui(f"Discovery name updated to: {new_name}")
            except Exception as e:
                print(f"Discovery update failed: {e}")

        return jsonify({"success": True, "action": "settings_updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/events', methods=['GET'], endpoint='get_events')
def get_events():
    return jsonify(connection_events)

@bp.route('/events/connected', methods=['POST'], endpoint='log_connect')
def log_connect():
    device = request.json.get("device_name", "Unknown Device")
    event = {"event": "connected", "device": device, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    connection_events.append(event)
    if len(connection_events) > 50: connection_events.pop(0)
    return jsonify({"success": True})

@bp.route('/events/disconnected', methods=['POST'], endpoint='log_disconnect')
def log_disconnect():
    event = {"event": "disconnected", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    connection_events.append(event)
    if len(connection_events) > 50: connection_events.pop(0)
    return jsonify({"success": True})

@bp.route('/status', methods=['GET'], endpoint='get_status')
@public_route
def get_status():
    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
            display_name = settings.get("device_name", socket.gethostname())
    except:
        display_name = socket.gethostname()

    return jsonify({
        "pc_name": display_name,
        "status": "online",
        "platform": platform.system().lower()
    })

@bp.route('/connection-info', methods=['GET'], endpoint='get_connection_info')
def get_connection_info():
    """Diagnostic endpoint showing current connection type and IP."""
    try:
        local_ip = get_local_ip()
        all_addrs = psutil.net_if_addrs()
        all_stats = psutil.net_if_stats()

        # Detect connection type
        conn_type = "UNKNOWN"
        if local_ip:
            if local_ip.startswith('192.168.19.'):
                conn_type = "USB_TETHERING"
            elif local_ip.startswith('192.168.42.'):
                conn_type = "USB_TETHERING_ALT"
            elif local_ip.startswith('192.168.235.'):
                conn_type = "USB_TETHERING_VB"
            elif local_ip.startswith('192.168.43.'):
                conn_type = "ANDROID_HOTSPOT"
            elif local_ip.startswith('192.168.137.'):
                conn_type = "WINDOWS_HOTSPOT"
            elif local_ip.startswith('10.') or local_ip.startswith('172.') or (local_ip.startswith('192.168.') and not local_ip.startswith('192.168.1')):
                conn_type = "WIFI_OR_LAN"

        # Collect all UP interfaces
        up_interfaces = []
        for iface_name in sorted(all_addrs.keys()):
            if iface_name in all_stats and all_stats[iface_name].isup:
                for addr in all_addrs[iface_name]:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        up_interfaces.append({
                            "name": iface_name,
                            "ip": addr.address,
                            "is_active": addr.address == local_ip
                        })

        return jsonify({
            "ip": local_ip,
            "connection_type": conn_type,
            "up_interfaces": up_interfaces,
            "device_name": socket.gethostname()
        })
    except Exception as e:
        return jsonify({"error": str(e), "ip": get_local_ip()}), 500

@bp.route('/system-stats', methods=['GET'], endpoint='get_system_stats')
def get_system_stats():
    return jsonify(current_system_stats)

@bp.route('/system/optimize', methods=['POST'], endpoint='optimize_system')
def optimize_system():
    """Real system optimization: temp cleanup, RAM working set trim, DNS flush."""
    freed_bytes = 0
    actions = []

    try:
        if WINDOWS:
            # 1. Flush DNS cache
            subprocess.run("ipconfig /flushdns", shell=True, capture_output=True)
            actions.append("DNS cache flushed")

            # 2. Clear %TEMP% — files AND subdirectories
            temp_path = os.environ.get('TEMP') or os.environ.get('TMP')
            if temp_path and os.path.isdir(temp_path):
                for entry in os.listdir(temp_path):
                    entry_path = os.path.join(temp_path, entry)
                    try:
                        if os.path.isfile(entry_path):
                            size = os.path.getsize(entry_path)
                            os.remove(entry_path)
                            freed_bytes += size
                        elif os.path.isdir(entry_path):
                            import shutil
                            for root, dirs, files in os.walk(entry_path):
                                for f in files:
                                    try:
                                        fp = os.path.join(root, f)
                                        freed_bytes += os.path.getsize(fp)
                                    except: pass
                            shutil.rmtree(entry_path, ignore_errors=True)
                    except: pass
                actions.append(f"Temp files cleared ({freed_bytes // (1024*1024)} MB freed)")

            # 3. Clear Windows prefetch (speeds up older HDDs, harmless on SSDs)
            prefetch = r"C:\Windows\Prefetch"
            if os.path.isdir(prefetch):
                for f in os.listdir(prefetch):
                    try:
                        fp = os.path.join(prefetch, f)
                        if os.path.isfile(fp):
                            os.remove(fp)
                    except: pass
                actions.append("Prefetch cache cleared")

            # 4. Trim RAM working sets of all processes (the real "memory optimizer")
            # This releases unused RAM pages back to the OS — same as what RAM cleaner apps do
            try:
                import ctypes
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_QUERY_INFORMATION = 0x0400

                # NOTE: this block used to open the process token with
                # TOKEN_ADJUST_PRIVILEGES and declare `SE_DEBUG = 20`, but never
                # called AdjustTokenPrivileges — so SeDebugPrivilege was never
                # actually enabled and the dead constant was flagged by ruff
                # (F841). Removing it changes no behaviour.
                #
                # EmptyWorkingSet succeeds on processes the node's user already
                # owns. Protected and other-user processes fail the OpenProcess
                # call below and are skipped, which is the correct outcome:
                # silently failing is better than requesting debug privileges
                # over the whole system to trim RAM.

                trimmed = 0
                skipped = 0
                for proc in psutil.process_iter(['pid']):
                    handle = None
                    try:
                        handle = ctypes.windll.kernel32.OpenProcess(
                            PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, proc.info['pid']
                        )
                        if handle:
                            ctypes.windll.psapi.EmptyWorkingSet(handle)
                            trimmed += 1
                        else:
                            skipped += 1
                    except OSError:
                        skipped += 1
                    finally:
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                actions.append(
                    f"RAM working sets trimmed ({trimmed} processes, {skipped} inaccessible)"
                )
            except Exception as e:
                print(f"RAM trim failed: {e}")

        freed_mb = freed_bytes // (1024 * 1024)
        summary = " | ".join(actions) if actions else "Optimization complete"
        add_activity("System Optimized", summary, category="Commands")
        log_to_ui("System Optimization Complete")
        return jsonify({"success": True, "freed_mb": freed_mb, "actions": actions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/security/sessions', methods=['GET'], endpoint='get_security_sessions')
def get_security_sessions():
    """Returns active guest sessions."""
    sessions = get_guest_manager().get_all_active_sessions()
    return jsonify(sessions)

@bp.route('/system/resource-trends', methods=['GET'], endpoint='get_resource_trends')
def get_resource_trends():
    """Returns the last 30 sampled resource data points for charting."""
    return jsonify(resource_usage_history)

@bp.route('/uptime', methods=['GET'], endpoint='get_uptime')
def get_uptime():
    boot_time_timestamp = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_time_timestamp)
    uptime_seconds = int(time.time() - boot_time_timestamp)
    return jsonify({
        "uptime_seconds": uptime_seconds,
        "uptime_readable": str(timedelta(seconds=uptime_seconds)),
        "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S")
    })

@bp.route('/power/shutdown', methods=['POST'], endpoint='shutdown')
def shutdown():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    active = [t for t in active_transfers.values() if t.get("status") == "receiving"]
    if active:
        return jsonify({"success": False, "error": "Cannot shutdown while transfers are active"}), 409

    add_activity("System Shutdown", "A remote shutdown command was initiated.", category="Commands", is_urgent=True)
    log_to_ui("Shutdown Requested")
    os.system("shutdown /s /t 5")
    return jsonify({"success": True, "action": "shutdown"})

@bp.route('/power/restart', methods=['POST'], endpoint='restart')
def restart():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Restart Requested")
    os.system("shutdown /r /t 5")
    return jsonify({"success": True, "action": "restart"})

@bp.route('/power/sleep', methods=['POST'], endpoint='sleep')
def sleep():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Sleep Mode Activated")
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return jsonify({"success": True, "action": "sleep"})

@bp.route('/power/hibernate', methods=['POST'], endpoint='hibernate')
def hibernate():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Hibernation Requested")
    os.system("shutdown /h")
    return jsonify({"success": True, "action": "hibernate"})

@bp.route('/power/lock', methods=['POST'], endpoint='lock')
def lock():
    if not WINDOWS or not ctypes:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    log_to_ui("Locking Workstation")
    try:
        ctypes.windll.user32.LockWorkStation()
        return jsonify({"success": True, "action": "lock"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/processes', methods=['GET'], endpoint='get_processes')
def get_processes():
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            pinfo = proc.info
            procs.append({
                "pid": pinfo['pid'],
                "name": pinfo['name'],
                "cpu_percent": pinfo['cpu_percent'],
                "memory_mb": round(pinfo['memory_info'].rss / (1024 * 1024), 2),
                "status": pinfo['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
    return jsonify(procs)

@bp.route('/processes/kill', methods=['POST'], endpoint='kill_process')
def kill_process():
    pid = request.json.get("pid")
    try:
        proc = psutil.Process(pid)
        # Prevent killing self or system critical processes (simple check)
        if proc.pid == os.getpid():
            return jsonify({"success": False, "error": "Cannot kill CYPHER core process"}), 403

        proc.terminate()
        gone, alive = psutil.wait_procs([proc], timeout=2)
        if alive:
            proc.kill()
        return jsonify({"success": True, "pid": pid})
    except psutil.NoSuchProcess:
        return jsonify({"success": True, "note": "Process already gone"})
    except psutil.AccessDenied:
        return jsonify({"success": False, "error": "Access Denied: Try running CYPHER as Admin"}), 403
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@bp.route('/apps', methods=['GET'], endpoint='get_installed_apps')
def get_installed_apps():
    if not WINDOWS:
        return jsonify([]), 200
    apps = []
    search_paths = [
        Path(os.environ.get('ProgramData', '')) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get('AppData', '')) / "Microsoft/Windows/Start Menu/Programs"
    ]
    for path in search_paths:
        if path.exists():
            for file in path.rglob("*.lnk"):
                apps.append({"name": file.stem, "path": str(file)})
    return jsonify(apps)

@bp.route('/apps/launch', methods=['POST'], endpoint='launch_application')
def launch_application():
    if not WINDOWS:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400
    path = (request.json or {}).get("path")
    if not path:
        return jsonify({"success": False, "error": "No path provided"}), 400
    # Launch is a filesystem operation: only Start Menu shortcuts the node itself
    # enumerated, or a path inside a shared folder. os.startfile() on arbitrary
    # client input was arbitrary code execution (audit S-03).
    launch_roots = list(_get_shared_folders())
    launch_roots.append(str(Path(os.environ.get('ProgramData', '')) / "Microsoft/Windows/Start Menu/Programs"))
    launch_roots.append(str(Path(os.environ.get('AppData', '')) / "Microsoft/Windows/Start Menu/Programs"))
    try:
        resolved = Sandbox(launch_roots).resolve(path, need="execute")
    except SandboxViolation:
        return jsonify(_SANDBOX_DENIED), 403
    os.startfile(str(resolved))
    app_name = resolved.stem
    add_activity("App Launched", f"Successfully initialized {app_name}.", category="Commands")
    return jsonify({"success": True, "app": app_name})

@bp.route('/apps/close', methods=['POST'], endpoint='close_application')
def close_application():
    """Tries to find and close a window by ID or title."""
    _load_automation()
    if not WINDOWS or not gw:
        return jsonify({"success": False, "error": "Not available on this platform"}), 400

    app_name = request.json.get("name")
    window_id = request.json.get("id")

    try:
        if window_id:
            for win in gw.getAllWindows():
                if win._hWnd == window_id:
                    win.close()
                    add_activity("App Closed", f"Terminated process instance {window_id}.", category="Commands")
                    return jsonify({"success": True, "id": window_id})

        if app_name:
            found = False
            # 1. Try closing via Window Title
            for win in gw.getWindowsWithTitle(app_name):
                try:
                    win.close()
                    found = True
                except: pass

            # 2. Try closing via Process Name if window close failed
            if not found:
                for proc in psutil.process_iter(['name']):
                    try:
                        if app_name.lower() in proc.info['name'].lower():
                            proc.terminate()
                            found = True
                    except: pass

            if found:
                add_activity("App Closed", f"Terminated {app_name}.", category="Commands")
                return jsonify({"success": True, "name": app_name})
            return jsonify({"success": False, "error": "App not found"}), 404

        return jsonify({"success": False, "error": "No identifier provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/network', methods=['GET'], endpoint='get_network_info')
def get_network_info():
    net = psutil.net_io_counters()
    return jsonify({
        "bytes_sent_mb": round(net.bytes_sent / (1024 * 1024), 2),
        "bytes_received_mb": round(net.bytes_recv / (1024 * 1024), 2),
        "pc_ip": get_local_ip(),
        "hostname": socket.gethostname()
    })

@bp.route('/activewindow', methods=['GET'], endpoint='get_active_window')
def get_active_window():
    if not WINDOWS or not gw:
        return jsonify({"window_title": "N/A", "process_name": "N/A"})
    try:
        win = gw.getActiveWindow()
        return jsonify({
            "window_title": win.title if win else "None",
            "process_name": "N/A",
            "id": win._hWnd if win else None
        })
    except:
        return jsonify({"window_title": "Unknown"})

@bp.route('/system/stream', endpoint='stream_screen')
def stream_screen():
    """High-speed MJPEG screen stream for 'Remote View'."""
    # BUGFIX: this route relied on the background warm_up_engines() thread having
    # already finished. A client that opened Remote View within the first couple
    # of seconds of node start hit `mss is None` -> AttributeError raised outside
    # the inner try/except, which killed the stream with no error surfaced to the
    # user. Load synchronously and fail loudly instead.
    _load_media_engine()
    if mss is None or Image is None:
        return jsonify({
            "success": False,
            "error": "Screen streaming is unavailable: capture dependencies missing",
        }), 503

    def generate():
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while True:
                try:
                    img = sct.grab(monitor)
                    frame = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                    # Scale down for faster streaming over local network
                    frame.thumbnail((1280, 720))

                    output = io.BytesIO()
                    frame.save(output, format="JPEG", quality=50)

                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + output.getvalue() + b'\r\n')

                    # Performance: ~20 FPS limit to keep CPU sane
                    time.sleep(0.05)
                except:
                    break

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@bp.route('/system/active-windows', methods=['GET'], endpoint='get_active_windows')
def get_active_windows():
    """Returns a list of all visible application windows with process context."""
    _load_automation()
    if not WINDOWS or not win32gui:
        return jsonify({"windows": []})
    try:
        import win32process
        import win32con
        windows = []

        def enum_handler(hwnd, lparam):
            # 1. Must be visible
            if not win32gui.IsWindowVisible(hwnd):
                return

            # 2. Must have a title
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return

            # 3. Filter out common system tool windows/shells
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return

            # 4. Must have dimensions (ignore tray icons/cloaked windows)
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w <= 10 or h <= 10:
                return

            path = ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                path = proc.exe()
                # Filter out obvious system shells that aren't user apps
                if "System32" in path or "WindowsApps" in path:
                    if "ApplicationFrameHost" not in path: # Allow some WindowsApps
                        return
            except: pass

            windows.append({
                "title": title,
                "name": title,
                "id": hwnd,
                "path": path,
                "is_minimized": win32gui.IsIconic(hwnd),
                "is_maximized": win32gui.IsZoomed(hwnd)
            })

        win32gui.EnumWindows(enum_handler, None)

        # Sort by title for better UI experience
        windows.sort(key=lambda x: x['title'].lower())
        return jsonify({"windows": windows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/windows/focus', methods=['POST'], endpoint='focus_window')
def focus_window():
    """Brings a specific window to the foreground."""
    if not WINDOWS or not gw:
        return jsonify({"success": False, "error": "Platform not supported"}), 400

    hwnd = request.json.get("id")
    if not hwnd:
        return jsonify({"success": False, "error": "No window ID provided"}), 400

    try:
        # Use pygetwindow to find the specific window by handle
        all_wins = gw.getAllWindows()
        target = next((w for w in all_wins if str(w._hWnd) == str(hwnd)), None)

        if target:
            target.activate()
            if target.isMinimized:
                target.restore()
            log_to_ui(f"Focused Window: {target.title}")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Window not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/system/window-icon', methods=['GET'], endpoint='get_window_icon')
def get_window_icon():
    """Extracts the native icon from a window handle and returns it as an image."""
    _load_automation()
    if not WINDOWS or not win32gui:
        return jsonify({"error": "Not supported"}), 400

    hwnd = request.args.get('id', type=int)
    path = request.args.get('path')

    try:
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

        hicon = None
        if hwnd:
            # Try to get the window's own icon first
            res = win32gui.SendMessage(hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
            if not res:
                res = win32gui.GetClassLong(hwnd, win32con.GCL_HICON)
            hicon = res

        # If no hwnd or hwnd didn't have an icon, try the path
        if not hicon and path and os.path.exists(path):
            large, small = win32gui.ExtractIconEx(path, 0)
            if large:
                hicon = large[0]
                for h in small: win32gui.DestroyIcon(h)

        if not hicon:
            return jsonify({"error": "Icon not found"}), 404

        # Create device context and bitmap
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
        save_dc = hdc.CreateCompatibleDC()
        save_dc.SelectObject(hbmp)

        # Draw the icon
        win32gui.DrawIconEx(save_dc.GetSafeHdc(), 0, 0, hicon, ico_x, ico_y, 0, None, win32con.DI_NORMAL)

        # Convert to PIL
        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)

        # Final cleanup
        save_dc.DeleteDC()
        win32gui.DeleteObject(hbmp.GetHandle())

        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return Response(buffered.getvalue(), mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/system/displays', methods=['GET'], endpoint='get_display_info')
def get_display_info():
    """Detects primary and secondary monitor resolutions."""
    try:
        from screeninfo import get_monitors
        displays = []
        for m in get_monitors():
            displays.append({
                "name": m.name,
                "width": m.width,
                "height": m.height,
                "is_primary": m.is_primary
            })
        return jsonify(displays)
    except:
        return jsonify([{"name": "Default", "width": 1920, "height": 1080, "is_primary": True}])

@bp.route('/battery/status', methods=['GET'], endpoint='get_battery_status')
def get_battery_status():
    batt = psutil.sensors_battery()
    percent = batt.percent if batt else 0
    return jsonify({
        "percent": percent, "plugged": batt.power_plugged if batt else False,
        "alert_threshold": battery_threshold, "is_critical": percent <= battery_threshold
    })

@bp.route('/battery/threshold', methods=['POST'], endpoint='set_battery_threshold')
def set_battery_threshold():
    global battery_threshold
    battery_threshold = request.json.get("threshold", 20)
    return jsonify({"success": True})

@bp.route('/history', methods=['GET'], endpoint='get_history')
def get_history():
    return jsonify(command_history)

@bp.route('/notifications', methods=['GET'], endpoint='get_notifications')
def get_notifications():
    return jsonify(notifications_list)

@bp.route('/notifications/add', methods=['POST'], endpoint='add_notification')
def add_notification():
    data = request.json
    new_notif = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", "No Title"),
        "message": data.get("message", ""),
        "app_name": data.get("app_name", "System"),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    notifications_list.append(new_notif)
    if len(notifications_list) > 20: notifications_list.pop(0)
    return jsonify({"success": True})

@bp.route('/wol', methods=['POST'], endpoint='wake_on_lan')
def wake_on_lan():
    data = request.json or {}
    mac = data.get('mac', '').replace(':', '').replace('-', '').replace('.', '')
    if len(mac) != 12:
        return jsonify({"success": False, "error": "Invalid MAC address (expected xx:xx:xx:xx:xx:xx)"}), 400
    try:
        mac_bytes = bytes.fromhex(mac)
        magic = b'\xff' * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(magic, ('<broadcast>', 9))
        log_to_ui(f"WOL: Magic packet sent to {data.get('mac')}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/system/activity', methods=['GET'], endpoint='get_system_activity')
def get_system_activity():
    """Endpoint for the dynamic Activity Log tab."""
    return jsonify(system_activity_log)

