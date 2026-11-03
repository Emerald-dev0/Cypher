# 🛡️ CYPHER — Local Network PC Remote Control

> **Control your PC from anywhere on the same WiFi. No internet. No servers. 100% local.**

CYPHER is a **full-featured remote control system** for Windows PCs, allowing you to:
- 📱 Control your PC from your Android phone
- 🎥 Record screen with custom quality & frame rates
- 📁 Transfer files seamlessly (upload/download)
- ⌨️ Type, hotkeys, click, and navigate remotely
- 🔒 Secure pairing system with guest access
- 🎮 Launch apps, manage processes, control power
- 📋 Sync clipboard, view screenshots, stream live desktop
- ⚡ Works on WiFi hotspots, USB tethering, and local LANs

**No cloud. No subscriptions. No data tracking. Pure local network magic.**

---

## ✨ Key Features

### 🎮 **Remote Control**
- ✅ Full screenshot capture
- ✅ Live desktop streaming (MJPEG)
- ✅ Remote keyboard (type text + hotkeys)
- ✅ Clipboard sync (bidirectional)
- ✅ Open URLs in browser
- ✅ Volume control + media playback

### 🎥 **Screen Recording**
- ✅ Full screen or window-specific recording
- ✅ Multiple quality presets (480p, 720p, 1080p)
- ✅ Adjustable frame rates (15, 24, 30, 60 FPS)
- ✅ Pause/resume mid-recording
- ✅ Auto-download after recording
- ✅ 3-second countdown before start

### 📁 **File Management**
- ✅ Browse shared folders from phone
- ✅ Upload files to PC
- ✅ Download single or batch (ZIP)
- ✅ Chunked transfers for large files (100GB+)
- ✅ Real-time progress tracking
- ✅ File preview (text, images, PDFs, video, audio)
- ✅ Rename/move files
- ✅ Delete with confirmation

### 💾 **System Control**
- ✅ Power commands: shutdown, restart, sleep, hibernate, lock
- ✅ Process manager: view, search, kill processes
- ✅ App launcher: install & launch applications
- ✅ System monitoring: CPU, RAM, disk usage (live)
- ✅ Battery status & network info
- ✅ Uptime tracking

### 🔐 **Security**
- ✅ 6-digit pairing code (fresh each session)
- ✅ Token-based authentication
- ✅ Guest access with folder sandboxing
- ✅ Session expiry & revocation
- ✅ Activity logging
- ✅ Path traversal protection
- ✅ Admin process protection

### 🌐 **Connectivity**
- ✅ WiFi hotspot (Android 192.168.43.x)
- ✅ Windows Mobile Hotspot (192.168.137.x)
- ✅ USB tethering (192.168.42.x)
- ✅ Local LAN/WiFi with mDNS discovery
- ✅ Manual IP entry fallback
- ✅ Smart auto-reconnect
- ✅ Wake-on-LAN support

### ⚙️ **Advanced Features**
- ✅ Clipboard history (last 50 items)
- ✅ Activity timeline view
- ✅ Activity log & notifications
- ✅ Screenshot save to phone
- ✅ Screen recording pause/resume
- ✅ Multi-window management
- ✅ Guest session management
- ✅ PC pairing code rotation

---

## 📦 Tech Stack

### **Frontend (Mobile)**
- **Framework:** Flutter (Dart)
- **State Management:** Provider
- **Networking:** HTTP + WebSocket
- **Storage:** Shared Preferences + Local JSON
- **Discovery:** mDNS (nsd package)
- **UI Components:** Custom Cypher Design System

### **Backend (PC)**
- **Server:** Python 3.12 + Flask + Flask-SocketIO
- **System API:** pyautogui, psutil, win32, pycaw
- **Media:** OpenCV (cv2), mss, ffmpeg
- **Discovery:** Zeroconf (mDNS) + UDP beacon
- **File Transfer:** Streaming + chunking
- **Recording:** Hardware-accelerated screen capture

### **PC Companion App**
- **Framework:** Flutter for Windows
- **Backend:** Python subprocess (auto-managed)
- **UI:** 7-tab dashboard (Home, Files, Transfers, Activity, Health, Security, Settings)

---

## 🚀 Quick Start

### **Prerequisites**
- **PC:** Windows 10+ with Python 3.12
- **Phone:** Android 10+ 
- **Network:** Both on same WiFi (or USB tethering)

### **Setup**

#### **1. PC Setup**
```bash
# Clone repo
git clone https://github.com/Emerald-dev0/Cypher.git
cd cypher

# Install Python dependencies
pip install -r pc_app_flutter/backend/requirements.txt

# Run the backend
python pc_app_flutter/backend/core/server.py

# Or run the Flutter PC app (uses backend subprocess)
cd pc_app_flutter
flutter run -d windows
```

The PC app will:
1. Start the Python backend automatically
2. Display the 6-digit pairing code
3. Show the dashboard after pairing

#### **2. Phone Setup**
```bash
# Install Flutter (if not installed)
# https://flutter.dev/docs/get-started/install

# Run the mobile app
cd mobile_app
flutter pub get
flutter run
```

#### **3. First Connection**
1. **Open CYPHER on phone** → "Find Your PC"
2. **Auto-discovery** finds your PC (mDNS or subnet scan)
3. **Tap your PC** → "Pairing screen"
4. **Enter 6-digit code** from PC dashboard
5. **Connected!** → Home screen appears

---

## 📋 Connection Methods

| Method | Protocol | Range | Auto-Discovery |
|--------|----------|-------|-----------------|
| **WiFi Hotspot (Android)** | Local network | 192.168.43.x | ✅ mDNS + Subnet |
| **WiFi Hotspot (Windows)** | Local network | 192.168.137.x | ✅ mDNS + Subnet |
| **USB Tethering** | Local network | 192.168.42.x | ✅ Subnet scan |
| **Local LAN/WiFi** | TCP/IP | Any subnet | ✅ mDNS + Subnet |
| **Manual IP** | TCP/IP | Any IP | ⚠️ User entry |

**Discovery Priority:**
1. **mDNS (fastest)** — Broadcast service discovery
2. **UDP Beacon** — Custom beacon broadcast (fallback)
3. **Subnet Scan** — Ping candidate IPs
4. **Manual Entry** — User types IP directly

---

## 🔒 Security

### **Pairing Mechanism**
- 6-digit code changes per session
- Code displayed only on PC
- One-time pairing per device
- Token-based auth after pairing

### **File Access**
- Admin-enforced shared folders only
- Path traversal protection on all endpoints
- System folder write protection (`C:\Windows`, `Program Files`, etc.)
- Guest sandboxing with folder limits

### **Guest Access**
- Temporary tokens with expiry
- Limited folder scope
- Read-only or upload toggles
- Session revocation anytime

### **Network**
- **No internet required** — 100% local
- **No cloud servers** — No external dependencies
- **No data tracking** — Activity logged locally only
- **Encrypted recommended** — Use WPA2+ WiFi

---

## 📁 Project Structure

```
cypher/
├── README.md                          # This file
├── Architecture.md                    # System design & components
├── Pairing Specification.md           # Pairing protocol details
├── File transfer protocol.md          # File transfer implementation
├── UI Design System.md                # Design tokens & components
├── SYSTEM_AUDIT.md                    # Network connectivity audit
├── FEATURE_VERIFICATION.md            # Feature checklist & status
│
├── mobile_app/                        # Flutter Android app
│   ├── lib/
│   │   ├── main.dart                 # App entry + routing
│   │   ├── providers/                # State management (Provider)
│   │   │   ├── connection_provider.dart
│   │   │   ├── file_provider.dart
│   │   │   ├── system_provider.dart
│   │   │   └── app_provider.dart
│   │   ├── services/                 # API & local services
│   │   │   ├── api_service.dart      # HTTP endpoints
│   │   │   ├── discovery_service.dart # mDNS + subnet scan
│   │   │   ├── storage_service.dart  # Local persistence
│   │   │   ├── clipboard_service.dart # Clipboard history
│   │   │   └── update_service.dart
│   │   ├── screens/                  # 22+ UI screens
│   │   │   ├── splash_screen.dart
│   │   │   ├── connection_screen.dart
│   │   │   ├── pairing_screen.dart
│   │   │   ├── home_screen.dart
│   │   │   ├── file_browser_screen.dart
│   │   │   ├── controls_screen.dart
│   │   │   ├── screen_recorder_screen.dart
│   │   │   ├── process_manager_screen.dart
│   │   │   ├── app_launcher_screen.dart
│   │   │   ├── clipboard_screen.dart
│   │   │   ├── clipboard_history_screen.dart
│   │   │   ├── wake_on_lan_screen.dart
│   │   │   └── ... (15+ more screens)
│   │   ├── widgets/                  # Reusable UI components
│   │   │   ├── cypher_button.dart
│   │   │   ├── cypher_card.dart
│   │   │   ├── stat_ring.dart
│   │   │   ├── file_icon.dart
│   │   │   └── ... (10+ more widgets)
│   │   └── theme/                    # Design system
│   │       ├── colors.dart
│   │       └── app_theme.dart
│   ├── pubspec.yaml                  # Dependencies
│   └── android/                       # Android config
│
├── pc_app_flutter/                    # Flutter Windows companion app
│   ├── lib/
│   │   ├── main.dart                 # Windows app entry
│   │   ├── screens/
│   │   │   ├── dashboard_screen.dart # 7-tab dashboard
│   │   │   └── tabs/                 # Individual tabs
│   │   │       ├── home_tab.dart
│   │   │       ├── files_tab.dart
│   │   │       ├── transfers_tab.dart
│   │   │       ├── activity_tab.dart
│   │   │       ├── health_tab.dart
│   │   │       ├── security_tab.dart
│   │   │       └── settings_tab.dart
│   │   ├── services/
│   │   │   ├── bridge_service.dart   # Local HTTP to backend
│   │   │   ├── backend_manager.dart  # Python subprocess mgmt
│   │   │   └── theme_service.dart
│   │   └── theme/
│   └── pubspec.yaml
│
├── pc_app_flutter/backend/
│   ├── core/
│   │   ├── server.py                 # 2800-line Flask server
│   │   │   # 60+ endpoints covering all features
│   │   │   # Power, files, processes, recording, etc.
│   │   ├── discovery.py              # mDNS + UDP beacon
│   │   ├── recording_overlay.py      # Screen recording
│   │   └── guest_manager.py          # Guest sessions
│   ├── requirements.txt               # Python deps
│   └── README.md                      # Backend docs
│
└── docs/                              # Additional documentation
    ├── SYSTEM_AUDIT.md
    ├── FEATURE_VERIFICATION.md
    └── Architecture.md
```

---

## 🛠️ Development

### **Install Dependencies**

**Mobile:**
```bash
cd mobile_app
flutter pub get
```

**Backend:**
```bash
pip install -r pc_app_flutter/backend/requirements.txt
```

### **Run in Development**

**Mobile:**
```bash
flutter run
# or specific device
flutter run -d emulator-5554
```

**Backend (standalone):**
```bash
python pc_app_flutter/backend/core/server.py
# Output:
# --------------------------------------------------
# CYPHER PC SERVER
# IP: 192.168.43.2
# PAIRING KEY: 123456
# --------------------------------------------------
```

**PC App (auto-manages backend):**
```bash
cd pc_app_flutter
flutter run -d windows
```

### **Testing**

**Quick test checklist:**
- [ ] WiFi hotspot connection (mDNS)
- [ ] USB tethering connection
- [ ] File upload (small + large)
- [ ] File download (small + large)
- [ ] Screenshot capture
- [ ] Screen recording (pause/resume)
- [ ] Power commands (lock, sleep)
- [ ] Process kill with confirmation
- [ ] App launcher
- [ ] Clipboard sync
- [ ] Guest access with expiry
- [ ] Pairing code rotation

---

## 🔧 Configuration

### **Shared Folders (PC)**
Edit in PC app Settings or `server.py`:
```python
SHARED_FOLDERS = [
    "C:\\Users\\YourName\\Downloads",
    "C:\\Users\\YourName\\Documents",
    "D:\\Media",
]
```

### **Recording Settings**
Change in Screen Recorder mobile screen:
- Quality: Low (480p), Medium (720p), High (1080p)
- FPS: 15, 24, 30, 60
- Audio: toggle on/off
- Source: Full screen or specific window

### **Auto-Connect**
Enable in Settings → "Smart Auto-Connect"
- Automatically reconnects on app launch
- Requires successful pairing first
- Skips manual connection screen

---

## 📊 Architecture Highlights

### **Discovery System** (3-layer fallback)
1. **mDNS** — Service broadcast (`_cypher._tcp`)
2. **UDP Beacon** — Custom broadcast every 3 seconds
3. **Subnet Scan** — Ping 192.168.43.x, 192.168.137.x, 192.168.42.x ranges

### **File Transfer** (Streaming + Chunking)
- **Small files (<100MB):** Direct stream
- **Large files (100MB+):** 1MB chunks with progress
- **Batch download:** Server ZIP → client streams

### **Recording System** (Hardware + Software)
- **Screen Capture:** `mss` (fast) or OpenCV (fallback)
- **Encoding:** ffmpeg with quality presets
- **Streaming:** Save to temp file, stream on request

### **Authentication** (Token-based)
1. User enters 6-digit code from PC
2. Backend validates, issues token
3. Phone saves token locally
4. All requests include `X-Auth-Token` header
5. Token revoked on unpair

### **Screen Streaming** (Live MJPEG)
- Continuous frame capture
- JPEG compression per frame
- HTTP chunked transfer
- Real-time latency ~100-200ms

---

## 📱 Mobile App Routes

```
/                     → Splash (auto-navigate)
/onboarding          → First-time setup
/setup               → Device pairing setup
/connection          → Discover & connect to PC
/pairing             → Enter pairing code
/home                → Main dashboard (2 tabs)
/browser             → File browser
/preview             → File preview
/controls            → Remote control panel
/clipboard           → Clipboard sync
/clipboard-history   → Clipboard history viewer
/guest               → Guest access management
/activity            → Activity log
/notifications       → System notifications
/settings            → User preferences
/processes           → Process manager
/apps_launcher       → App launcher & closer
/recorder            → Screen recording
/transfers           → Active transfers
/wol                 → Wake-on-LAN
/guide               → Setup & FAQ
/send                → Upload to PC
/phone_browser       → Browse phone files
/drop                → CypherDrop (local share)
```

---

## 🐛 Troubleshooting

### **PC Not Found During Discovery**
1. ✅ Both devices on same WiFi
2. ✅ PC firewall allows port 5000
3. ✅ Enable "file and printer sharing"
4. ✅ Try manual IP entry as fallback

### **Connection Drops**
1. ✅ Check WiFi signal strength
2. ✅ Verify PC still running CYPHER
3. ✅ Heartbeat auto-detects & reconnects (8 second interval)
4. ✅ Manual reconnect via "Scan again" button

### **Large File Transfer Stalls**
1. ✅ Check network bandwidth
2. ✅ Pause other downloads
3. ✅ Try chunked transfer endpoint
4. ✅ Increase timeout in settings

### **Recording Fails**
1. ✅ Verify PC has 2GB+ free space
2. ✅ Check ffmpeg installed (`ffmpeg -version`)
3. ✅ Try lower quality preset
4. ✅ Restart backend

### **Pairing Code Wrong**
1. ✅ Code changes on PC restart
2. ✅ Code is 6 digits only
3. ✅ Check for typos
4. ✅ Look at PC dashboard in Settings tab

---

## 🚀 Performance Tips

| Action | Optimization |
|--------|---------------|
| **Large files** | Use chunked download endpoint |
| **Slow WiFi** | Lower recording quality to 480p |
| **High latency** | Reduce FPS to 15, increase timeout |
| **Many processes** | Filter by name instead of full list |
| **Battery drain** | Disable clipboard history sync |

---

## 📈 Future Roadmap

### **Phase 2** (Medium Effort)
- [ ] Remote mouse control (trackpad)
- [ ] Scheduled power commands
- [ ] System notification mirroring
- [ ] Activity timeline UI
- [ ] Multi-monitor awareness
- [ ] System tray quick commands

### **Phase 3** (Advanced)
- [ ] Action macros ("Gaming Mode", etc.)
- [ ] Multi-device dashboard
- [ ] Custom hotkey bindings
- [ ] Real-time performance graphs
- [ ] Screen sharing for demos

---

## 🤝 Contributing

Pull requests welcome! Areas for contribution:
- Bug fixes & optimizations
- New screens & features
- Documentation improvements
- Platform support (macOS, Linux)
- Language translations

---

## 📄 License

MIT License — See LICENSE file

---

## 👨‍💻 About

**CYPHER** was built as a local-network alternative to TeamViewer/AnyDesk/Chrome Remote Desktop.

**Why CYPHER?**
- No internet required (security + speed)
- No subscriptions or data tracking
- Works everywhere (hotspot, USB tether, LAN)
- Full control with guest sandboxing
- Modern, fast, beautiful UI

---

## 🆘 Support

### **Getting Help**
1. Check [Troubleshooting](#-troubleshooting) section
2. Review [SYSTEM_AUDIT.md](./SYSTEM_AUDIT.md) for connectivity
3. Review [FEATURE_VERIFICATION.md](./FEATURE_VERIFICATION.md) for feature status
4. Check [Architecture.md](./Architecture.md) for implementation details

### **Reporting Bugs**
Include:
- Device info (PC OS, phone Android version)
- Connection type (WiFi/USB tether)
- Steps to reproduce
- Error message/logs

---

## 📚 Additional Documentation

- **[SYSTEM_AUDIT.md](./SYSTEM_AUDIT.md)** — Network connectivity audit, all connection modes tested
- **[FEATURE_VERIFICATION.md](./FEATURE_VERIFICATION.md)** — Complete feature checklist with status
- **[Architecture.md](./Architecture.md)** — System design, components, data flow
- **[Pairing Specification.md](./Pairing Specification.md)** — Pairing protocol details
- **[File transfer protocol.md](./File transfer protocol.md)** — File transfer implementation
- **[UI Design System.md](./UI Design System.md)** — Design tokens & component library

---

**Made with ❤️ for local network enthusiasts.**

*Last updated: 2026-06-17*
