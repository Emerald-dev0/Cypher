# CYPHER - Complete Architecture Specification

## Project Overview

CYPHER is a local-network remote PC control application.

**What it does:**
- Phone controls entire PC over WiFi (no internet required)
- File transfer (both directions)
- Remote power control
- Media controls
- System monitoring
- Pairing with 6-digit code
- Logging all actions

**Target Users:**
- Power users who want instant PC control from phone
- Developers who need local network alternatives to cloud services
- Anyone who values privacy (100% local, no data leaves network)

**Platforms:**
- Mobile: Android (Flutter)
- PC: Windows (Python backend + Flutter UI)
- Connection: Phone WiFi hotspot

---

## Tech Stack

**Backend:**
- Python 3.12
- Flask (REST API)
- psutil (system monitoring)
- Running on localhost:5000

**Mobile:**
- Flutter (Dart)
- Android 11+
- SharedPreferences (for persistence)

**PC:**
- Flutter (Dart) for UI
- Python backend runs as service
- Windows 10+

---

## Core Flows

### Flow 1: Pairing (First Time)

PC Backend starts → Generates 6-digit pairing code
Mobile app starts → Shows onboarding
User enters pairing code → Mobile sends POST /pair_device
Backend validates code → Generates auth token
Mobile saves token to SharedPreferences
Mobile navigates to home screen
Mobile makes all future requests with X-Auth-Token header
Backend validates token on every request


### Flow 2: File Download (PC → Phone)

Mobile calls GET /files/browse?path=C:\Users\Downloads
Backend returns list of files with metadata
User taps file → Mobile calls GET /files/download?path=C:\Users...\file.zip
Backend streams file as binary data
Mobile receives stream → Saves to phone storage
Progress callback updates UI with percentage
On completion → Shows success message
Action logged in activity log


### Flow 3: File Upload (Phone → PC)

Mobile file picker selects file from phone
Mobile shows destination folder selector → Calls GET /files/list
User selects destination folder on PC
Mobile sends POST /files/upload with multipart/form-data
Backend receives file → Validates destination path
Backend saves file to destination
Success response returns filename
Mobile shows "Upload complete"
Action logged in activity log


### Flow 4: Remote Control (Power)

Mobile shows power options: Shutdown, Restart, Sleep, Lock
User taps "Shutdown"
Mobile shows confirmation dialog
User confirms → Mobile sends POST /power/shutdown
Backend executes: os.system("shutdown /s /t 5")
Backend returns: {success: true}
Mobile shows "PC shutting down in 5 seconds"
Action logged in activity log


### Flow 5: System Monitoring

Mobile home screen loads
Mobile starts timer to call GET /system-stats every 2 seconds
Backend returns: {cpu_percent, ram_percent, disk_percent, battery_percent, ...}
Mobile updates labels with live data
On disconnect → Shows "Disconnected" state
User taps reconnect → Attempts to call /ping endpoint
If /ping succeeds → Restores connection


---

## API Endpoints (Complete)

### Authentication & System

**GET /ping** - Health check
- Auth: None
- Returns: `{message: "pong"}`
- Used for: Connection verification

**GET /connect-code** - Get pairing code
- Auth: None
- Returns: `{code: "123456"}`
- Used for: First-time pairing

**POST /pair_device** - Pair new device
- Auth: None
- Body: `{pairing_code, device_id, device_name}`
- Returns: `{success: true, token: "abc123xyz"}`
- Stores in: paired_devices.json
- Used for: Initial pairing

**GET /status** - System status
- Auth: X-Auth-Token
- Returns: `{pc_name, status, platform}`

---

### File Operations

**GET /files** - List root files
- Auth: X-Auth-Token
- Returns: Array of shared folders + quick access folders
- Format:
```json
  [
    {
      "name": "Downloads",
      "path": "C:\\Users\\Downloads",
      "type": "folder"
    },
    {
      "name": "backup.zip",
      "path": "C:\\Users\\Downloads\\backup.zip",
      "type": "file",
      "size": 1024000,
      "modified": "2026-06-01 14:30:00"
    }
  ]
```

**GET /files/browse** - Browse folder
- Auth: X-Auth-Token
- Params: ?path=C:\Users\Downloads
- Returns: Same as /files for given path
- Path validation: Must be in shared_folders or quick access

**GET /files/download** - Download file
- Auth: X-Auth-Token
- Params: ?path=C:\full\path\to\file.zip
- Returns: Binary file stream
- Headers: Content-Type: application/octet-stream
- Used for: Streaming file to mobile

**POST /files/upload** - Upload file
- Auth: X-Auth-Token
- Body: multipart/form-data
    - file: binary data
    - destination: C:\Users\Downloads
- Returns: `{success: true, filename: "uploaded.zip"}`
- Validation: destination must be in shared_folders

**GET /files/list** - List folders for upload destination
- Auth: X-Auth-Token
- Returns: Array of selectable destinations
- Used for: Showing folder picker on mobile

---

### System Information

**GET /system-stats** - Live system stats
- Auth: X-Auth-Token
- Returns:
```json
  {
    "cpu_percent": 45.2,
    "ram_percent": 62.3,
    "ram_used": 8.5,
    "ram_total": 13.6,
    "disk_percent": 71.0,
    "battery_percent": 100,
    "battery_plugged": true
  }
```

**GET /network** - Network info
- Auth: X-Auth-Token
- Returns: `{pc_ip, hostname, bytes_sent, bytes_received}`

**GET /activewindow** - Currently active window
- Auth: X-Auth-Token
- Returns: `{window_title, process_name}`

---

### Remote Control

**POST /power/shutdown** - Shutdown PC
- Auth: X-Auth-Token
- Body: None
- Returns: `{success: true}`
- Executes: os.system("shutdown /s /t 5")

**POST /power/restart** - Restart PC
- Auth: X-Auth-Token
- Body: None
- Returns: `{success: true}`

**POST /power/sleep** - Sleep mode
- Auth: X-Auth-Token
- Body: None
- Returns: `{success: true}`

**POST /power/lock** - Lock workstation
- Auth: X-Auth-Token
- Body: None
- Returns: `{success: true}`

**POST /media/play** - Play media
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /media/pause** - Pause media
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /media/next** - Next track
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /media/prev** - Previous track
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /media/volumeup** - Volume up
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /media/volumedown** - Volume down
- Auth: X-Auth-Token
- Returns: `{success: true}`

**POST /type** - Remote typing
- Auth: X-Auth-Token
- Body: `{text: "hello"}`
- Returns: `{success: true}`
- Uses: pyautogui.write()

**POST /keyboard/hotkey** - Send hotkey
- Auth: X-Auth-Token
- Body: `{keys: ["ctrl", "alt", "delete"]}`
- Returns: `{success: true}`

**POST /screenshot** - Capture screenshot
- Auth: X-Auth-Token
- Returns: Binary image data (JPEG)
- Used for: Full screen capture

---

### Clipboard

**GET /clipboard** - Get PC clipboard
- Auth: X-Auth-Token
- Returns: `{type: "text", content: "clipboard text"}`
- OR `{type: "image", content: "base64_data"}`

**POST /clipboard** - Set PC clipboard
- Auth: X-Auth-Token
- Body: `{text: "new clipboard content"}`
- Returns: `{success: true}`

**POST /clipboard/phone** - Store phone clipboard
- Auth: X-Auth-Token
- Body: `{text: "content from phone"}`
- Returns: `{success: true}`
- Used for: Syncing phone clipboard to PC

**GET /clipboard/phone** - Get stored phone clipboard
- Auth: X-Auth-Token
- Returns: `{content: "...", timestamp: "..."}`

---

### Activity & Logging

**GET /history** - Get command history
- Auth: X-Auth-Token
- Returns: Array of commands executed with timestamps

**GET /notifications** - Get notifications list
- Auth: X-Auth-Token
- Returns: Array of system notifications

**POST /notifications/add** - Add notification
- Auth: X-Auth-Token
- Body: `{title, message, app_name}`
- Returns: `{success: true}`

---

### Settings

**GET /settings** - Get all settings
- Auth: X-Auth-Token
- Returns:
```json
  {
    "device_name": "My PC",
    "battery_alert_threshold": 20,
    "shared_folders": ["C:\\Users\\Downloads", ...],
    "notifications_enabled": true
  }
```

**POST /settings** - Update settings
- Auth: X-Auth-Token
- Body: `{device_name: "New Name"}`
- Returns: `{success: true}`
- Persists to: settings.json

---

## Data Persistence

### Backend Files
~/.cypher/
├── paired_devices.json
│   └── {device_id: {device_name, token, paired_at}}
├── settings.json
│   └── {device_name, battery_alert_threshold, shared_folders}
├── pairing_code.txt
│   └── "123456"
└── logs/
└── cypher_YYYY-MM-DD.log

### Mobile Storage (SharedPreferences)
auth_token = "abc123xyz"
device_id = "mobile_unique_id"
pc_ip_address = "192.168.137.100"
is_paired = true
device_name = "My Phone"

---

## Error Handling

All endpoints return error responses in this format:

```json
{
  "success": false,
  "error": "Human-readable error message"
}
```

**Common scenarios:**
- 401 Unauthorized: Invalid or missing X-Auth-Token
- 400 Bad Request: Invalid parameters
- 404 Not Found: File/resource not found
- 500 Server Error: Unexpected error

---

## Security

**Auth:**
- Pairing code is 6 random digits
- Generated fresh on every server start
- Used once, then token is used for auth
- Token stored in paired_devices.json

**Token:**
- 32-character hex string (16 bytes)
- Used in X-Auth-Token header
- Checked on every request

**File Access:**
- Only files in shared_folders can be accessed
- Path validation prevents directory traversal
- System folders (Windows, Program Files) blocked

**Data:**
- All communication over local network (no internet)
- No sensitive data logged
- Activity log records actions, not file contents

---

## Versioning

**Current:** 1.0.0
**Format:** MAJOR.MINOR.PATCH

Increment rules:
- PATCH: Bug fixes
- MINOR: New features
- MAJOR: Breaking changes

Update in:
- pubspec.yaml (both apps)
- server.py constant
- CHANGELOG.md

---

## Known Limitations (V1.0)

- ❌ No mDNS auto-discovery (manual IP or QR code required)
- ❌ No internet tunneling (local network only)
- ❌ No live screen streaming (screenshots only)
- ❌ No Wake-on-LAN
- ❌ No scheduled tasks

These are V1.1+ features.