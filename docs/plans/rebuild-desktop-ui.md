# Desktop UI Rebuild Plan

**Target:** `pc_app_flutter/` · Windows and Linux
**Roadmap phase:** P2-D1 … P2-D3 (with P1-D1 … P1-D3 as prerequisites)
**Estimated effort:** ~4 weeks
**Decision:** Flutter desktop is the single desktop UI. The customtkinter
Python UI was deleted in Phase 0 (audit finding A-01).

---

## 1. Where the desktop app stands

### 1.1 What it is

A Flutter shell that spawns a headless Python node as a child process and talks
to it over `http://127.0.0.1:5000`. Seven tabs — Home, Files, Transfers,
Activity, Health, Security, Settings — in a ~750-line `dashboard_screen.dart`
with a custom hidden title bar via `window_manager`.

### 1.2 What is right about it

- **The process architecture is correct.** A Flutter shell over a headless
  language-runtime service is a legitimate design: Python owns OS integration
  (input, capture, audio, psutil), Flutter owns the UI, and the boundary is a
  loopback HTTP API that is *the same API the phone uses*. That is a real
  advantage — one protocol, two clients — and it should be preserved
  deliberately rather than by accident.
- `service.py` is a proper service entry point: single-instance mutex, health
  readiness, stdout/stderr piping into the shell's error screen.
- `ThemeService` already implements working light/dark switching — something the
  mobile app does not (P2-M2).
- `glass_container.dart` is a genuine shared primitive rather than a one-off.

### 1.3 What is wrong

**It cannot find its own backend.** `BackendManager.start()` resolves the node
via `Directory.current.path` — the *working directory*, which for a
double-clicked shortcut is arbitrary — and then tries
`C:\Users\hp\AppData\Local\Programs\Python\Python312\python.exe` as its first
Python candidate. One developer's machine, hardcoded. (Audit F-08 → **P1-D2**.)

**It hardcodes the loopback token.** `BridgeService.internalToken` was the
published literal; now reads from disk, but `_appDataDir()` and
`core/utils.py::get_app_data_dir()` **disagree on Linux** (`~/.config/cypher`
vs `~/.cypher`), so the shell cannot find the node's token file there.
(**P3-L6**, but it must be decided now or Linux will never work.)

**It is Windows-only in practice.** `APPDATA`, `netsh`, UAC elevation,
`os.startfile`, and win32 window management are all assumed. The `linux/`
scaffold exists and compiles; the app has never been run on it.

**Seven tabs is a filing cabinet, not a UI.** Home, Health and Activity overlap;
Security is a read-only list; Settings is thin. The node exposes ~95 routes and
the tab structure reflects the order the endpoints were written, not what a
person at a desk needs.

**Two divergent design systems.** `theme_service.dart` (desktop) and
`theme/colors.dart` (mobile) define different palettes with different names for
the same roles. 74 hardcoded `Color(0x…)` literals in the desktop app on top of
that. This is the structural reason the two apps do not look related.

**The startup screen is a 15-second timeout.** The documented sequence is:
launch shell → spawn Python → sleep 1 s → poll `/ping` for up to 15 s → show
dashboard or an error screen. On a cold start with PyInstaller unpacking, that
budget is tight; on a machine without Python it burns all 15 s before saying
anything. There is no progress signal, no distinction between "node is starting"
and "node failed", and no version check — so a shell/node mismatch surfaces as a
mysterious 404 rather than a clear message.

---

## 2. Target architecture

### 2.1 Three processes, one protocol

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop shell (Flutter)                                     │
│  ─ window chrome, tray, settings, security console           │
│  ─ spawns and supervises the node                            │
└───────────────┬─────────────────────────────────────────────┘
                │ loopback HTTP + Socket.IO
                │ X-Auth-Token: <per-install internal token>
┌───────────────▼─────────────────────────────────────────────┐
│  Node (Python) — headless                                    │
│  ─ OS integration: input, capture, audio, files, power       │
│  ─ LAN listener: the SAME API the phone uses                 │
│  ─ mDNS/UDP advertisement, optional relay client             │
└───────────────▲─────────────────────────────────────────────┘
                │ LAN HTTPS (P2-S1) or relay tunnel (P5)
        ┌───────┴────────┐
        │  Mobile client │   ← identical API surface
        └────────────────┘
```

The shell is **not** a privileged client. It authenticates with the loopback
token and is otherwise subject to the same capability scopes as a paired phone
(P2-S5). That keeps one authorization path to test instead of two, and it means
the shell cannot become the bypass that `INTERNAL_TOKEN` used to be.

### 2.2 Supervision contract

`BackendManager` becomes a real supervisor:

| Concern | Behaviour |
| --- | --- |
| **Locate** | Resolve the node next to `Platform.resolvedExecutable` (`…/backend/dist/cypher_node[.exe]`). Fall back to a bundled-asset path, then to a Python on `PATH` — never to a hardcoded absolute path. |
| **Handshake** | `GET /ping` must return `{version, protocol_version, capabilities}`. Refuse to proceed on a protocol mismatch with an explicit message (P1-D1). |
| **Progress** | Emit discrete states — `locating → spawning → waiting → ready / failed(reason)` — each rendered in the startup screen. No silent 15-second spinner. |
| **Supervise** | Watch the child; on unexpected exit, capture the tail of stderr, surface it, and offer restart with exponential backoff (max 3 attempts). |
| **Shut down** | SIGTERM/`GenerateConsoleCtrlEvent`, wait 5 s, then kill. Never orphan the node — an orphaned listener on `0.0.0.0:5000` is a security incident, not a leak. |
| **Single instance** | Respect the node's existing mutex; if another shell owns it, focus that window instead of failing. |

### 2.3 Capabilities drive the UI

The node's `/ping` returns a capability list (`input`, `capture`, `audio`,
`power`, `processes`, `files`, `recording`, `overlay`). The shell and the mobile
app both render **only what the node declares**.

This is the fix for the current pattern of `if not WINDOWS: return 400` — where
the UI happily shows a "Hibernate" button on Linux and the user gets an error
toast. Capability-gated UI degrades honestly (P3-L1).

### 2.4 One design system, two apps

Extract `packages/cypher_ui` (P2-D2): tokens, `ThemeExtension`, typography,
spacing, motion, and the shared primitives (`CypherCard`, `StatRing`,
`GlassContainer`, `ConnectionBadge`, `EmptyState`, `ShimmerBox`). Both apps
consume it. Desktop adds *adaptive density* — the same components at a
pointer-friendly scale with keyboard focus rings.

This is the single highest-leverage change in the plan: it removes the 74 + 58
hardcoded literals as a side effect of making tokens the only available API.

---

## 3. Information architecture

### 3.1 Tabs → three regions

Seven peer tabs is too many to scan and hides the two things that matter most
for this product: **what is connected**, and **what is permitted**.

```
┌────────────────────────────────────────────────────────────────────┐
│ ◈ CYPHER    ● Node ready · Windows 11 · 192.168.1.24:5000    ⚙  ─ □ ✕│  title bar = status
├──────────────┬─────────────────────────────────────────────────────┤
│              │                                                     │
│  Overview    │   primary surface                                   │
│  Files       │                                                     │
│  Transfers   │                                                     │
│  Devices     │                                                     │
│  Security    │                                                     │
│  Settings    │                                                     │
│              │                                                     │
│──────────────│                                                     │
│  Pairing     │   ← persistent: QR + code, because this is the      │
│  ▣ ▣ ▣ ▣ ▣ ▣ │     single most common first-run action             │
│              │                                                     │
└──────────────┴─────────────────────────────────────────────────────┘
```

| Region | Replaces | Why |
| --- | --- | --- |
| **Overview** | Home + Health | One screen: vitals, paired devices summary, active transfers, recent activity. Health *is* the overview at a glance; a separate tab made people look in two places. |
| **Files** | Files | Shared-folder management front and centre — this is the allowlist the P1-S2 sandbox enforces, so it must be obvious and easy to edit. |
| **Transfers** | Transfers + Activity (transfer part) | Live and historical transfers together, with per-item throughput and resume state. |
| **Devices** | *(new)* | Paired devices, their scopes, last seen, source IP, revoke. Today this is buried in Security and only shows a token list. |
| **Security** | Security + Activity (events part) | The audit log, pairing history, blocked attempts (now that P0-7 logs lockouts), TLS fingerprint, relay status. This becomes a *console*, not a list. |
| **Settings** | Settings | Node config, network, power behaviour, updates, about, diagnostics export. |

**Activity is split, not deleted.** Transfer events belong with Transfers;
security events belong with Security. A single chronological firehose of
everything was the reason the tab felt useless.

### 3.2 The pairing surface is persistent

The current design puts the pairing code behind a Home tab card and a
`refreshConnectCode()` call. But pairing is the first thing every new user must
do, and the code rotates on every successful pairing (P0-7), so a stale display
is actively misleading.

Make it a permanent sidebar element: QR code + 6-digit code + "regenerate",
with a countdown showing time-to-rotation. It is the desktop equivalent of the
mobile pairing screen and it should be equally effortless.

### 3.3 Title bar carries node status

`titleBarStyle: TitleBarStyle.hidden` is already set. Use the reclaimed space:
node state dot, machine name, listening address, transport, and a
click-through-to-diagnostics affordance. When the node is down, the title bar is
red and says so — no modal, no dead end.

### 3.4 Window management

- `window_manager` keeps: min size 900×600, remember geometry, snap layouts.
- **Add:** minimise-to-tray on close (the tray already exists in `core/tray.py`),
  single-instance focus, and a tray menu that mirrors the sidebar.
- **Add:** a compact "menubar mode" — a small always-on-top window with just the
  vitals and a Power button. This is the desktop analogue of the mobile home
  screen and it is what most people will actually live in.
- **Linux:** the tray needs `libayatana-appindicator3` (already added to the CI
  apt step in `release.yml`). Verify on both GNOME and KDE; Wayland tray
  behaviour differs.

---

## 4. Key screens

### 4.1 Overview

Three columns on a wide window, collapsing to a single scroll on a narrow one:

- **Vitals** — CPU / RAM / disk / battery, sparkline from the node's
  `resource_usage_history` (it already keeps 30 samples), plus uptime and
  network. Driven by the SocketIO `system_stats` stream, not HTTP polling.
- **Right now** — active transfers, recording state (with the overlay status
  from `RecordingOverlay.available`), connected devices.
- **Recent** — the last 10 activity items with a filter, linking into Security.

### 4.2 Files

- Left: the shared-folder allowlist with add/remove and a per-folder scope
  selector (read-only vs read-write). This is the P1-S2 enforcement surface, so
  it must be unambiguous.
- Right: a real file browser — grid/list toggle, sort, breadcrumb, thumbnail
  preview (now that F-03/F-04 are fixed), multi-select, drag-and-drop **onto**
  the window to upload and **out** to download.
- Drag-and-drop is the desktop affordance the mobile app cannot have and the
  biggest single usability win in this rebuild.

### 4.3 Devices

One row per paired device: name, platform icon, granted scopes as chips,
`last_seen`, source IP, and a revoke action. A scope editor lets you downgrade a
device from `power + input + files` to `files` only — the P2-S5 capability model
made visible. "Revoke all" with a confirmation that explains the consequence.

**Never display a raw token.** `/paired-devices` currently returns them
(S-14/P2-S6); the UI should show a fingerprint instead.

### 4.4 Security console

- **Live:** is the node listening, on which interfaces, is TLS on, is the relay
  connected, how many paired devices.
- **Pairing history:** successes and *blocked attempts* — P0-7 now logs lockouts
  as urgent events, and that log is worthless if nobody can see it.
- **Audit log:** filterable by category, device and time, exportable, with
  sensitive fields redacted (P3-S1).
- **Certificate:** the node's TLS fingerprint, with a "show QR so my phone can
  pin it" action (P2-S1/P5-7).

### 4.5 Settings

Grouped: **Node** (name, port, launch at login, run as service), **Network**
(interfaces to bind, discovery on/off, firewall help, relay opt-in with a custom
relay URL), **Privacy** (what is logged, clipboard sync direction, redaction),
**Power** (battery threshold alerts, sleep behaviour), **Updates** (channel,
check now, signature verification per P2-D3), **About** (versions, licenses,
diagnostics export).

A **diagnostics export** button that produces a redacted zip — node log, config
sans secrets, versions, capability list — turns most bug reports from
"it doesn't work" into something actionable.

---

## 5. Linux port (the hard part)

Windows works today. Linux is a port, not a config change. Sequenced in
`ROADMAP.md` Phase 3, but the **decisions must be made now** so the rebuild does
not bake in Windows assumptions.

| Area | Windows | Linux | Task |
| --- | --- | --- | --- |
| App-data path | `%APPDATA%\Cypher` | **decide: `~/.config/cypher` (XDG)** — `core/utils.py` currently says `~/.cypher` and the Dart side says `~/.config/cypher`. They must agree or the shell cannot find the token file. | P3-L6 |
| Input injection | `pyautogui` + win32 | X11: `pyautogui`/`Xlib`. **Wayland: `libei` or `ydotool`/uinput.** | P3-L2 |
| Screen capture | `mss` | X11: `mss`. **Wayland: PipeWire + xdg-desktop-portal ScreenShot.** | P3-L3 |
| Audio | `pycaw`/COM | PipeWire/PulseAudio via `pulsectl` or `wpctl` | P3-L2 |
| Window list | `win32gui` | X11: `wmctrl`/EWMH. Wayland: largely unavailable — degrade honestly via the capability registry. | P3-L1 |
| App launch | `os.startfile` | `gio open` / `xdg-open`, `.desktop` file resolution | P3-L1 |
| Firewall | `netsh advfirewall` | `firewalld` / `ufw` / `nftables` — **or don't touch it and document the port** (preferred; see P2-S4 least privilege) | P3-L5 |
| Elevation | UAC `ShellExecuteW` | `pkexec` — **or don't elevate at all** | P2-S4 |
| Recording overlay | Tk (works) | Tk needs X11; on Wayland use a layer-shell surface | P3-L4 |
| Tray | `pystray` + win32 | `pystray` + AppIndicator (needs `libayatana-appindicator3`) | P3-L5 |
| Packaging | Inno Setup `.exe` | `.deb`, `.rpm`, AppImage + a systemd **user** unit | P3-L5 |
| Shell window | `window_manager` | Works; verify hidden title bar on GNOME/CSD and KDE | P3-L5 |

**Wayland is the crux.** It is the default session on Ubuntu 24.04 and Fedora,
and it deliberately does not permit global input injection or screen capture
without a portal round-trip and explicit user consent each time. That is not a
bug to route around — it is the platform's security model, and CYPHER should
adopt it: use the portal, show the consent dialog, and record the grant. Detect
the session type at startup (`XDG_SESSION_TYPE`) and populate the capability
registry accordingly.

**Build order for Linux:** files + transfers + system monitoring work with
`psutil` alone and need no platform-specific code. Ship those first as a
`v1.1.0-beta` Linux build — it is genuinely useful and it de-risks the harder
capture/input work.

---

## 6. Migration sequence

| # | Step | Tasks | Risk |
| --- | --- | --- | --- |
| 1 | Fix node discovery + handshake protocol; remove the hardcoded Python path | P1-D2, P1-D1 | Low — unblocks everything |
| 2 | Unify the app-data path across Python and Dart | P3-L6 (early) | Low |
| 3 | Structured node logging + log viewer in Settings | P1-D3 | Low |
| 4 | Extract `packages/cypher_ui`; desktop adopts it | P2-D2 | Medium |
| 5 | Rebuild the startup screen around discrete supervisor states | P1-D2 | Low |
| 6 | Split Activity into Transfers + Security; introduce the Devices screen | — | Medium |
| 7 | Overview = Home + Health merge | — | Medium |
| 8 | Files: allowlist editor + drag-and-drop | depends on P1-S2 | Medium |
| 9 | Capability-gated UI everywhere | P3-L1 | Medium |
| 10 | Security console (blocked attempts, fingerprint, audit log) | depends on P0-7, P2-S1 | Medium |
| 11 | Menubar/compact mode + tray parity | — | Low |
| 12 | Linux build: files/transfers/monitoring only | P3-L5 | High |
| 13 | Auto-update with signature verification | P2-D3 | Medium |
| 14 | Linux capture + input | P3-L2, P3-L3 | High |

---

## 7. Definition of done for the desktop rebuild

- [ ] The shell finds and starts the node from a double-clicked shortcut, an
      installed path, and a dev checkout — on Windows **and** Linux.
- [ ] No hardcoded absolute path or machine-specific interpreter anywhere.
- [ ] Startup shows discrete progress states and fails with an actionable
      message in under 3 s when Python/node is genuinely missing.
- [ ] `/ping` version + protocol check; a mismatched node is refused explicitly.
- [ ] Killing the shell never orphans a listener on `0.0.0.0:5000`.
- [ ] Seven tabs collapsed to six purposeful regions; Activity split correctly.
- [ ] Pairing QR + code persistently visible, with a rotation countdown.
- [ ] Zero `Color(0x…)` literals; both apps consume `packages/cypher_ui`.
- [ ] Light and dark themes, following the OS, with a manual override.
- [ ] UI renders only capabilities the node declares; no button 400s.
- [ ] No raw token is ever displayed.
- [ ] Devices screen shows scopes, last seen, source IP; revoke works.
- [ ] Security console shows blocked pairing attempts.
- [ ] Diagnostics export produces a redacted zip.
- [ ] A `.deb` and an AppImage install and run on Ubuntu 24.04 (files,
      transfers, monitoring).
- [ ] `flutter analyze --fatal-infos` and `flutter test` clean on Windows and
      Linux runners.
