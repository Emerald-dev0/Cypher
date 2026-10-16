# Cross-Platform Plan

**Roadmap phases:** P3-L1 … P3-L6 (Linux), P4-1 … P4-8 (Apple)
**Related:** [`rebuild-desktop-ui.md`](rebuild-desktop-ui.md) §5, [`security-hardening.md`](security-hardening.md)

---

## 1. Target support matrix

The honest current state, and where each cell needs to get to.

| Platform | Role | Today | v1.0 | v1.1 | v2.0 |
| --- | --- | --- | --- | --- | --- |
| **Windows 10/11** | Node + shell | 🟢 Works (primary) | 🟢 Hardened | 🟢 | 🟢 |
| **Ubuntu 22.04/24.04** | Node + shell | 🔴 Does not run | 🔴 | 🟡 Files/transfer/monitoring | 🟢 Full (X11) |
| **Fedora / Arch** | Node + shell | 🔴 | 🔴 | 🔵 Best effort | 🟡 |
| **Ubuntu 24.04 Wayland** | Node | 🔴 | 🔴 | 🔴 | 🟡 Portal-based |
| **macOS 13+** | Node + shell | 🔴 Scaffold only | 🔴 | 🔴 | 🟡 |
| **Android 10+** | Client | 🟡 Builds, ships | 🟢 | 🟢 | 🟢 |
| **Android tablets** | Client | 🔴 Portrait-locked | 🔴 | 🟡 | 🟢 |
| **iOS 16+** | Client | 🔴 No entitlements | 🔴 | 🔴 | 🟡 |
| **iPadOS** | Client | 🔴 | 🔴 | 🔴 | 🟡 |
| **Linux desktop (client)** | Client | 🔵 Flutter scaffold compiles | 🔵 | 🟡 | 🟡 |
| **Web client** | Client | 🔴 | 🔴 | 🔴 | 🔵 Explore |
| **CLI (any)** | Client | 🔴 | 🔴 | 🟢 v1.2 | 🟢 |

**Sequencing rationale:** Linux before Apple. Linux shares the Python node and
the Flutter shell with Windows, so it is a port. macOS needs a *second node
implementation* (ScreenCaptureKit, Accessibility API, TCC) and iOS needs Apple
signing infrastructure and a Local Network permission model that does not exist
in the codebase. Roughly 3× the effort for a smaller initial audience.

---

## 2. The blocker: platform assumptions are scattered

Today platform-specific behaviour is expressed as ad-hoc conditionals at the
point of use:

```python
WINDOWS = platform.system() == 'Windows'
...
if not WINDOWS or not pyautogui:
    return jsonify({"success": False, "error": "Not available on this platform"}), 400
```

This appears dozens of times, in three languages, with four different failure
shapes (`400`, empty list, silent no-op, `NameError`). Consequences:

- The UI cannot know what the node supports, so it renders buttons that fail.
- Adding Linux means editing every conditional — and missing some is silent.
- Windows-only modules (`win32gui`, `pycaw`, `os.startfile`, `%APPDATA%`,
  `netsh`, `ShellExecuteW`) are imported or referenced at module scope in places,
  which is why `requirements.txt` could not even install on Linux until P0-13.

**Fix first: a capability registry (P3-L1).** Everything else depends on it.

---

## 3. Platform abstraction layer (P3-L1)

### 3.1 Capabilities

```python
# core/platform/base.py

class Capability(str, Enum):
    FILES          = "files"
    SYSTEM_STATS   = "system.stats"
    PROCESS_LIST   = "process.list"
    PROCESS_KILL   = "process.kill"
    APP_LIST       = "app.list"
    APP_LAUNCH     = "app.launch"
    WINDOW_LIST    = "window.list"
    WINDOW_FOCUS   = "window.focus"
    WINDOW_ICON    = "window.icon"
    INPUT_KEYS     = "input.keys"
    INPUT_POINTER  = "input.pointer"
    CLIPBOARD_TEXT = "clipboard.text"
    CLIPBOARD_IMAGE= "clipboard.image"
    SCREENSHOT     = "screen.capture"
    SCREEN_STREAM  = "screen.stream"
    SCREEN_RECORD  = "screen.record"
    AUDIO_VOLUME   = "audio.volume"
    AUDIO_MEDIA    = "audio.media"
    POWER_SHUTDOWN = "power.shutdown"
    POWER_SLEEP    = "power.sleep"
    POWER_HIBERNATE= "power.hibernate"
    POWER_LOCK     = "power.lock"
    WOL            = "network.wol"
    BATTERY        = "system.battery"
    OVERLAY        = "ui.overlay"
    DISCOVERY_MDNS = "net.discovery.mdns"
```

### 3.2 Backend interface

```python
class PlatformBackend(Protocol):
    """One implementation per OS. Every method is optional at runtime."""

    name: str                                    # "windows" | "linux" | "macos"
    def capabilities(self) -> set[Capability]: …  # what THIS machine can do

    def screenshot(self) -> bytes | None: …
    def type_text(self, text: str) -> bool: …
    def hotkey(self, combo: list[str]) -> bool: …
    def move_pointer(self, dx: int, dy: int) -> bool: …
    def list_windows(self) -> list[WindowInfo]: …
    def list_processes(self) -> list[ProcessInfo]: …
    def kill_process(self, pid: int) -> bool: …
    def launch_app(self, identity: AppIdentity) -> bool: …
    def get_volume(self) -> float | None: …
    def set_volume(self, level: float) -> bool: …
    def power(self, action: PowerAction) -> bool: …
    ...

def get_backend() -> PlatformBackend:
    """Selected once at startup; never branched on again elsewhere."""
```

Two levels of granularity matter, because capability is not binary:

- **OS-level** — Windows has `WINDOW_ICON`; Linux/X11 partially; Wayland no.
- **Runtime-level** — Linux has `SCREEN_CAPTURE` under X11 but not under Wayland
  without a portal grant; a headless server has neither. Detect the session type
  (`XDG_SESSION_TYPE`) and any portal availability at startup.

`capabilities()` is therefore computed per machine, not per OS.

### 3.3 Exposure

`GET /ping` (and a dedicated `GET /capabilities`) returns:

```json
{
  "node_version": "1.1.0",
  "protocol_version": 3,
  "platform": "linux",
  "session": "wayland",
  "capabilities": ["files", "system.stats", "process.list", "screen.capture"],
  "missing": {
    "input.keys":   "Wayland requires a libei/uinput backend — not configured",
    "window.icon":  "not available on this session type",
    "power.hibernate": "requires logind inhibit privileges"
  }
}
```

`missing` carries a human-readable *reason*, which the UI can surface as a
tooltip rather than a dead button. This is the difference between "Linux support
is patchy" and "Linux support is honest".

### 3.4 Client behaviour

Both apps render from the capability set:

```dart
if (node.can(Capability.powerHibernate)) {
  PowerButton(action: PowerAction.hibernate);
}
```

Rules:

- A capability the node does not declare is **not rendered**. Never render and
  then error.
- Capabilities are re-read on reconnect — plugging in a display, switching
  session, or granting a portal permission changes the set.
- `protocol_version` mismatch ⇒ refuse to connect with an explicit upgrade
  message (P1-D1), rather than producing mysterious 404s.

### 3.5 Migration

Replace `if not WINDOWS: return 400` incrementally, one capability group at a
time. Order by value: `files` and `system.stats` (pure `psutil`, already
cross-platform) → `process.*` → `power.*` → `input.*` → `screen.*` → `audio.*` →
`window.*` (hardest on Wayland).

A CI job asserts that no new `platform.system() ==` comparison appears outside
`core/platform/`.

---

## 4. Linux specifics

Detailed per-area analysis lives in [`rebuild-desktop-ui.md`](rebuild-desktop-ui.md) §5.
The decisions that must be made now:

### 4.1 App-data path (P3-L6) — currently inconsistent

`core/utils.py::get_app_data_dir()` returns `~/.cypher`.
`BridgeService._appDataDir()` returns `~/.config/cypher`.

**They disagree, so the desktop shell cannot find the node's internal token file
on Linux.** Pick XDG: `~/.config/cypher` for config, `~/.local/state/cypher` for
logs and runtime state, `~/.local/share/cypher` for data. Add a one-time
migration from `~/.cypher` for existing installs. Do this before any Linux build
ships, or it becomes a support burden forever.

### 4.2 Wayland is the crux

Wayland is the default session on Ubuntu 24.04 and Fedora, and it deliberately
forbids global input injection and silent screen capture. This is not a bug to
route around — it is the platform's security model, and it aligns with CYPHER's
own (see [`security-hardening.md`](security-hardening.md) §1).

| Need | X11 | Wayland |
| --- | --- | --- |
| Input injection | `pyautogui` / `python-xlib` | **`libei`** (input emulation, the sanctioned path) or `ydotool`/uinput (needs a udev rule) |
| Screen capture | `mss` | **PipeWire + xdg-desktop-portal ScreenShot** — user consent dialog each session |
| Screen recording | `mss` + ffmpeg | **xdg-desktop-portal ScreenCast** — PipeWire stream |
| Window list | `wmctrl` / EWMH | Largely unavailable. Degrade honestly; do not fake it. |
| Overlay | Tk / X11 always-on-top | `wlr-layer-shell` (compositor-dependent) or none |
| Clipboard | `pyperclip` (xclip/wl-clip) | `wl-clipboard`; portal for image content |

**The portal consent dialog is a feature.** It means the OS itself tells the user
"an application is capturing your screen", which is exactly the consent guarantee
CYPHER's recording overlay is trying to provide by hand. Use the portal, show the
dialog, record the grant, and re-request when it expires.

### 4.3 Packaging (P3-L5)

| Format | Tooling | Notes |
| --- | --- | --- |
| `.deb` | `dpkg-deb` / `cpack` from the Flutter Linux build | Ubuntu, Debian, Mint — the primary target |
| `.rpm` | `rpmbuild` | Fedora, openSUSE |
| AppImage | `appimagetool` + `linuxdeploy` | Distro-agnostic; bundles the node binary |
| Flatpak | `flatpak-builder` | Sandboxed — **but** the sandbox blocks input injection and capture; needs careful permission set. Defer. |
| AUR | `PKGBUILD` | Community-maintained; do not own it |
| systemd | **user** unit, not system | `~/.config/systemd/user/cypher-node.service`; no root, consistent with P2-S4 |

Firewall: **do not touch it.** Document the port and let the user decide
(`firewall-cmd --add-port=5000/tcp --zone=home --permanent`). Automatic firewall
mutation is what P2-S4 removes on Windows; do not add it on Linux.

### 4.4 Distribution-specific traps

- **Python version:** Debian 12 ships 3.11, Ubuntu 24.04 ships 3.12. The F-01
  f-string bug was exactly this class. CI compiles on both.
- **`opencv-python` on Linux** pulls in `libGL.so.1`; headless servers need
  `opencv-python-headless`. Decide per build target.
- **`pystray`** needs an AppIndicator implementation;
  `libayatana-appindicator3` on modern Ubuntu, `libappindicator3` on older. CI
  already installs the ayatana package.
- **`psutil.disk_usage('/')`** — the node hardcodes `/`, which is right on Linux
  and wrong on Windows (which iterates drive letters). Move into the backend.
- **File paths in the API:** the protocol leaks Windows assumptions
  (`C:\Users\…` strings in JSON). Use POSIX-style relative paths within a shared
  folder, and let the node map them — which also strengthens the P1-S2 sandbox,
  since a relative path cannot escape by construction.

That last point is worth emphasising: **making the file API relative rather than
absolute is simultaneously a cross-platform fix and the cleanest possible
sandbox.** Prefer it in P1-S2's design.

---

## 5. Apple platforms (Phase 4)

### 5.1 iOS client

The `ios/` directory is a stock Flutter scaffold. Nothing iOS-specific has been
done. Required:

| Item | Detail |
| --- | --- |
| **Local Network permission** | `NSLocalNetworkUsageDescription` in `Info.plist` + `NSBonjourServices` listing `_cypher._tcp`. Without these, iOS 14+ **silently drops** all LAN traffic — the app appears to connect and never does. This is the single biggest iOS blocker and it is invisible in the current codebase. |
| Discovery | `nw_browser` / `NetService` behave differently from Android's NSD; multicast needs the entitlement. Validate against a real node. |
| Cleartext | `NSAppTransportSecurity` exception for local hosts; TLS (P2-S1) removes the need. |
| Background | No Android-style foreground service. Use `URLSession` background configuration for transfers; accept that long transfers pause when the app is suspended. Design the UX around it rather than fighting it. |
| Share extension | A separate extension target — not a MethodChannel like Android. |
| Permissions copy | Every `NS*UsageDescription` string must be honest and specific; generic strings are an App Review rejection. |
| Signing | Certificates, provisioning profiles, Fastlane, `release-ios.yml`. Needs an Apple Developer account (USD 99/yr) — a real project cost to budget. |
| Export compliance | Encryption declaration for TLS. Required for App Store submission. |

### 5.2 macOS node

A second node implementation, not a port:

| Area | macOS approach |
| --- | --- |
| Screen capture | **ScreenCaptureKit** (macOS 12.3+). `mss`/`CGWindowListCreateImage` are deprecated and gated by TCC. |
| Screen recording permission | TCC prompt; the user must grant it in System Settings → Privacy → Screen Recording. **The app cannot proceed without it**, and granting requires an app restart. Design onboarding around this. |
| Input injection | Accessibility API (`CGEventPost`) — requires TCC Accessibility permission, also manual, also restart-gated on some versions. |
| Audio | CoreAudio / `AudioDeviceSetProperty`. `pycaw` is Windows-only. |
| Window list | `CGWindowListCopyWindowInfo`; window *names* require Screen Recording permission (an Apple quirk worth documenting). |
| Power | `pmset` via a privileged helper, or IOKit. Sleep/lock are available; hibernate is not user-controllable on modern macOS. |
| Tray | `NSStatusItem`. |
| Sandbox | The Mac App Store requires App Sandbox, which **blocks** input injection and screen capture. Direct distribution (Developer ID + notarization) is the only viable path. This is a strategic decision: no Mac App Store. |
| Notarization | Developer ID signing + notarization + stapling in CI. Unnotarized apps trigger Gatekeeper warnings that look like malware. |
| entitlements | `com.apple.security.network.server`, `com.apple.security.device.audio-input` if recording mic, `com.apple.security.temporary-exception.apple-events` if scripting. |

**Recommendation:** ship macOS as a *client* first (the Flutter app runs there
today with modest work) and defer the macOS *node* until there is demonstrated
demand. A macOS user controlling a Windows/Linux PC is a real use case and is
~10% of the effort.

---

## 6. Mobile-specific compatibility

### 6.1 Android fragmentation

| Concern | Action |
| --- | --- |
| API 24 → 35+ | `minSdk = 24` set in P0-17. Verify `nsd`, `mobile_scanner` and `permission_handler` all support it. |
| Scoped storage (API 29+) | `requestLegacyExternalStorage` is set but ignored on API 30+. P2-M6 (SAF) is the real fix. |
| Photo picker (API 33+) | Prefer the system photo picker over `MANAGE_EXTERNAL_STORAGE` where the flow allows. |
| Foreground service types (API 34+) | `FOREGROUND_SERVICE_DATA_SYNC` permission added in P0-16; the service must declare `android:foregroundServiceType="dataSync"`. |
| mDNS without location (API 33+) | `NEARBY_WIFI_DEVICES` with `neverForLocation` added; location capped at `maxSdkVersion=32`. |
| OEM battery killers | Xiaomi/Samsung/Huawei aggressively kill background sockets. Need a "connection unreliable?" help sheet naming the OEM settings. This is the #1 real-world support issue for LAN apps. |
| Vendor WiFi isolation | Many routers enable "AP isolation", blocking client-to-client traffic entirely. Detect (mDNS sees nothing but the gateway is reachable) and explain. |
| AGP pin | 8.7.2 with `androidx.core`/`androidx.browser` overrides because 8.9.x hangs the Gradle daemon on Windows. Unlocking is P2-M9. |

### 6.2 Form factors

Currently `SystemChrome.setPreferredOrientations([portraitUp, portraitDown])` —
locked to portrait, which excludes tablets, foldables and Chromebooks. P2-M3
unlocks orientation and adds breakpoints:

| Width | Layout |
| --- | --- |
| < 600 dp | Phone: single column, bottom nav |
| 600–840 dp | Foldable / small tablet: single column, wider cards, side sheet |
| 840–1200 dp | Tablet: two-pane (list + detail) |
| > 1200 dp | Desktop / Chromebook: three-pane, sidebar nav, hover states, keyboard shortcuts |

The desktop app and the tablet layout should converge on the same components via
`packages/cypher_ui` (P2-D2) — one adaptive widget set, different densities.

### 6.3 A shared Dart package

`packages/cypher_ui` (tokens, components) and `packages/cypher_core`
(`NodeClient`, DTOs, `Result`/`Failure`, capability enum) consumed by mobile,
desktop, tablet and eventually a CLI-adjacent web client. This is the structural
answer to the "two divergent design systems" problem, and it makes the Apple and
Linux client work mostly configuration rather than reimplementation.

---

## 7. CI matrix

What `release.yml` builds, and what it should build once each phase lands.

| Target | Phase 0 (now) | Phase 3 | Phase 4 |
| --- | --- | --- | --- |
| Node · Windows x64 | ✅ PyInstaller zip | ✅ | ✅ |
| Node · Linux x64 | ✅ PyInstaller tar.gz | ✅ + `.deb`/`.rpm`/AppImage | ✅ |
| Node · macOS | — | — | ✅ universal (arm64 + x64) |
| Shell · Windows | ✅ zip + Inno Setup | ✅ + MSIX | ✅ |
| Shell · Linux | ✅ tar.gz | ✅ + `.deb`/AppImage | ✅ |
| Shell · macOS | — | — | ✅ notarized `.dmg` |
| Android | ✅ APK (split + universal) + AAB | ✅ | ✅ |
| iOS | — | — | ✅ IPA → TestFlight |
| CLI | — | ✅ v1.2 | ✅ |
| Relay image | — | — | ✅ (Phase 5) |

Add **Windows arm64** when Flutter's support stabilises, and **Android arm64 +
x86_64** splits (already produced). Drop `armeabi-v7a` only after Play Console
data shows it is negligible — it is still meaningful on low-end devices in the
project's likely core markets, including Nigeria.

---

## 8. Definition of done

**Linux (P3):**
- [ ] Capability registry in place; no `platform.system()` comparison outside
      `core/platform/`; CI enforces it.
- [ ] App-data path unified on XDG with a migration from `~/.cypher`.
- [ ] On Ubuntu 24.04: pair, browse shared folders, transfer both directions,
      read system stats, list and kill processes.
- [ ] On X11: additionally capture the screen, inject input, control volume.
- [ ] On Wayland: portal-based capture with a visible consent dialog; input via
      libei or a documented uinput setup; honest degradation elsewhere.
- [ ] `.deb`, `.rpm` and AppImage install from CI output and run.
- [ ] systemd **user** unit starts the node with no root.
- [ ] No firewall mutation, no elevation, no root requirement anywhere.

**Apple (P4):**
- [ ] iOS discovers and pairs with a node on a real device (proves the Bonjour
      entitlements are correct).
- [ ] iOS transfers a file both directions.
- [ ] TestFlight build produced by CI.
- [ ] macOS shell runs against a Windows node.
- [ ] (If the macOS node ships) notarized, with a TCC onboarding flow for Screen
      Recording and Accessibility.
