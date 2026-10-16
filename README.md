<div align="center">

# CYPHER

**Your phone. Your PC. Same room, same network, no cloud.**

Move files, control playback, grab a screenshot, lock the machine — without a
cable, an account, or a vendor sitting between you and your own computer.

[![CI](https://github.com/Emerald-dev0/Cypher/actions/workflows/ci.yml/badge.svg)](https://github.com/Emerald-dev0/Cypher/actions/workflows/ci.yml)
[![Release](https://github.com/Emerald-dev0/Cypher/actions/workflows/release.yml/badge.svg)](https://github.com/Emerald-dev0/Cypher/actions/workflows/release.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android-informational.svg)](#platform-support)

</div>

---

## ⚠️ Read this before installing

CYPHER is **pre-release software under active hardening**. An audit in October
2026 ([`docs/AUDIT.md`](docs/AUDIT.md)) found 43 defects, including a published
authentication token and a file API that did not enforce the shared-folder
boundary. The filesystem sandbox, public-route decorator, CORS/Host allowlist,
and Syncfusion removal have shipped; remaining work is in
[`ROADMAP.md`](ROADMAP.md).

**What that means for you today:**

- 🟠 **Do not run the node on a network you do not trust** — hotel, café,
  conference or campus WiFi. Traffic is still **unencrypted HTTP** on the LAN
  (TLS is [P2-S1](docs/plans/security-hardening.md)). A paired device can only
  read **shared folders** (sandbox, P1-S2).
- 🟠 **Traffic is unencrypted.** LAN HTTP means anyone on the same network can
  sniff the auth token. TLS is [P2-S1](docs/plans/security-hardening.md).
- 🟠 **Builds from before October 2026 must be uninstalled**, not updated. They
  shipped a hardcoded token that was public in this repository. Delete
  `%APPDATA%\Cypher\paired_devices.json` too. See [`SECURITY.md`](SECURITY.md).
- 🟢 **On your own home WiFi, with devices you own, it works** — and it works
  without touching the internet.

We would rather you know this than discover it. The project is not being publicly
promoted until Phase 1 closes.

---

## What it does

Pair your phone to your PC with a six-digit code shown on the PC's screen. Then:

| | |
| --- | --- |
| 📁 **Files** | Browse shared folders, upload, download, batch-ZIP, preview text/images/PDF/video/audio, chunked transfers for very large files |
| ⌨️ **Control** | Remote keyboard, hotkeys, trackpad, clicks, scroll — across monitors |
| 🖥️ **Screen** | Screenshot on demand, live MJPEG streaming, screen recording with quality and frame-rate control, pause/resume |
| 📋 **Clipboard** | Bidirectional text and image sync, with history |
| 🎵 **Media** | Volume, mute, play/pause, next/previous |
| ⚡ **Power** | Lock, sleep, hibernate, restart, shutdown |
| 📊 **System** | Live CPU/RAM/disk/battery, process list and kill, app launcher, uptime, network info |
| 🔗 **Guest links** | Share one folder with someone for a set time, without giving them your PC |
| 🌐 **Wake-on-LAN** | Boot a machine from your phone |

**No account. No subscription. No telemetry. No internet required.**

The only outbound request the app ever makes is the update check *you* trigger,
to `api.github.com`. Everything else stays on your network. The full accounting
is in [`docs/product/privacy.md`](docs/product/privacy.md).

---

## Platform support

| | Node (the PC being controlled) | Client (the controller) |
| --- | --- | --- |
| **Windows 10/11** | ✅ Works — primary platform | ✅ Desktop shell |
| **Android 10+** | — | ✅ Works — primary client |
| **Linux** | 🚧 Files, transfers and monitoring land in [Phase 3](ROADMAP.md); input and capture follow | 🔵 Compiles, untested |
| **macOS** | ❌ Not implemented | 🚧 [Phase 4](ROADMAP.md) |
| **iOS / iPadOS** | — | 🚧 [Phase 4](ROADMAP.md) — needs Local Network entitlements |
| **CLI** | — | 🚧 [Phase 3](ROADMAP.md) |

Honest detail per platform, including the Wayland capture problem and the iOS
Bonjour requirement: [`docs/plans/cross-platform.md`](docs/plans/cross-platform.md).

---

## Install

> **No signed release has been published yet.** The pipeline that produces them
> is [`release.yml`](.github/workflows/release.yml); the first artefacts land when
> Phase 1 closes. Until then, build from source.

### Requirements

- **PC:** Windows 10 or 11, Python 3.11+ (3.12 recommended)
- **Phone:** Android 10+ (API 24+)
- **Network:** both on the same WiFi, a hotspot, or a USB tether

### 1. Start the node on your PC

```bash
git clone https://github.com/Emerald-dev0/Cypher.git
cd Cypher/pc_app_flutter/backend

python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

python service.py
```

The node listens on port 5000 and advertises itself via mDNS. Pairing code is
shown in the **desktop shell** (sidebar), not printed to stdout (that was a
credential leak). Troubleshooting: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

Or run the desktop shell, which manages the node for you:

```bash
cd ../            # pc_app_flutter/
flutter pub get
flutter run -d windows
```

### 2. Install the app on your phone

```bash
cd mobile_app
flutter pub get
flutter build apk --release
# → build/app/outputs/flutter-apk/app-release.apk
```

Sideload the APK. For development, `flutter run` with a device attached.

> Release builds need a signing key. Copy
> `android/key.properties.example` to `android/key.properties` — without it the
> build falls back to the debug keystore, which is fine for development and
> rejected by CI for release. See [`docs/RELEASES.md`](docs/RELEASES.md).

### 3. Pair

1. Phone → **Find your PC**. Discovery lists the node; tap it.
2. Enter the six-digit code from the PC screen (or scan its QR code).
3. Done. The phone keeps a token and reconnects automatically.

If discovery finds nothing, type the address manually — it is printed by the
node. Troubleshooting is in [`docs/RELEASES.md`](docs/RELEASES.md) and the
connection matrix in [`docs/plans/test-matrix.md`](docs/plans/test-matrix.md) §1.

---

## How it connects

| Transport | Typical range | Discovery |
| --- | --- | --- |
| Same WiFi router | Any private subnet | mDNS → UDP beacon → manual |
| Android hotspot (phone is AP) | `192.168.43.x` | mDNS + subnet |
| Windows Mobile Hotspot (PC is AP) | `192.168.137.x` | mDNS + subnet |
| USB tethering | `192.168.42.x` | Subnet — works with WiFi off |
| Manual entry | Anything | — |

Discovery tries mDNS first, falls back to a UDP beacon, then to a subnet scan,
then asks you. Interface selection prioritises tethering over hotspots over LAN,
and excludes loopback and APIPA addresses.

**Not over the internet.** That is deliberate. Off-LAN access arrives in
[Phase 5](ROADMAP.md) as a **self-hostable relay** that forwards end-to-end
encrypted bytes and never requires an account —
[`docs/plans/relay-cloud.md`](docs/plans/relay-cloud.md).

---

## Architecture

```
┌──────────────────────┐         ┌──────────────────────────┐
│  Mobile client       │         │  Desktop shell (Flutter)  │
│  Flutter / Android   │         │  spawns and supervises    │
│                      │         │  the node over loopback   │
└──────────┬───────────┘         └────────────┬─────────────┘
           │                                  │
           │   one HTTP + Socket.IO API       │
           │   X-Auth-Token per device        │
           ▼                                  ▼
┌────────────────────────────────────────────────────────────┐
│  Node (Python) — headless                                   │
│  Flask + Flask-SocketIO · psutil · mss/OpenCV · zeroconf    │
│  files · input · capture · audio · power · processes        │
└────────────────────────────────────────────────────────────┘
```

One protocol, two clients. The desktop shell is not privileged — it
authenticates with a per-install loopback token and is subject to the same rules
as a paired phone.

| Component | Path | Stack |
| --- | --- | --- |
| Node | `pc_app_flutter/backend/` | Python 3.11+, Flask, Flask-SocketIO, psutil, Pillow, mss, OpenCV, zeroconf |
| Desktop shell | `pc_app_flutter/lib/` | Flutter for Windows/Linux, `window_manager`, Provider |
| Mobile client | `mobile_app/lib/` | Flutter, Provider, `nsd`, `mobile_scanner`, `file_picker` |
| Website | `website/` | Static HTML → GitHub Pages |

Detail: [`docs/architecture/overview.md`](docs/architecture/overview.md),
[`pairing.md`](docs/architecture/pairing.md),
[`file-transfer.md`](docs/architecture/file-transfer.md),
[`design-system.md`](docs/architecture/design-system.md).

---

## Security

The controls that exist **today**:

- ✅ Six-digit pairing code from `secrets`, regenerated every session, **rotated
  on every successful pairing** so it is single-use
- ✅ Brute-force throttle: 5 attempts per 5 minutes per source IP, then a 15-minute
  lockout — checked *before* the comparison
- ✅ Constant-time code comparison (`hmac.compare_digest`)
- ✅ Per-install generated loopback token at `0600` — no published secret
- ✅ 32-byte device tokens
- ✅ Global authentication: every route is protected unless explicitly public
- ✅ Guest sessions with `secrets.token_urlsafe(32)`, expiry, folder scoping and
  an access log
- ✅ An on-screen recording indicator, so anyone in the room knows when capture is
  active
- ✅ No telemetry, no analytics, no crash upload, enforced by a CI gate
- ✅ Android backup and device migration disabled, so a token cannot be restored
  onto a new handset

The controls that are **not yet done**, in priority order:

| | Gap | Task |
| --- | --- | --- |
| 🔴 | Shared-folder boundary is not enforced on the file routes | [P1-S2](docs/plans/security-hardening.md#3-the-filesystem-sandbox-p1-s2--highest-priority) |
| 🔴 | CORS is a wildcard and the `Host` header is not validated (DNS rebinding) | P1-S4 |
| 🟠 | Transport is cleartext HTTP; no node authentication | P2-S1 |
| 🟠 | No capability scopes — a paired device can do everything | P2-S5 |
| 🟠 | Device tokens never expire; `/paired-devices` returns raw tokens | P2-S6 |
| 🟠 | The node auto-elevates to Administrator on first run | P2-S4 |
| 🟠 | Keystroke text is written to the activity log | P3-S1 |

The full threat model, the target authentication design and the verification
tests for each control are in
[`docs/plans/security-hardening.md`](docs/plans/security-hardening.md).

**Found a vulnerability?** Please use the private channel in
[`SECURITY.md`](SECURITY.md) — not a public issue.

### A position on surveillance

CYPHER is a remote-control tool, which makes it dual-use by nature. We have chosen
a side:

- A **persistent, non-dismissable on-screen indicator** whenever the screen is
  captured, streamed or recorded.
- **No stealth mode.** Not as a setting, not as a flag, not for "kiosk use".
- Pairing requires **physical presence** at the PC to read the code. There is no
  remote approval, and there will not be one.
- CYPHER is not designed, licensed or supported for covert monitoring of another
  person's device.

The reasoning is in
[`docs/product/features-and-applications.md`](docs/product/features-and-applications.md#42-anti-surveillance-as-a-feature).

---

## Documentation

| | |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | The technical contract — repo map, commands, invariants, known traps. **Read this before contributing.** |
| [`ROADMAP.md`](ROADMAP.md) | What is planned, in what order, with stable task IDs |
| [`docs/AUDIT.md`](docs/AUDIT.md) | The October 2026 audit: 43 findings with evidence |
| [`docs/`](docs/README.md) | Everything else — architecture, plans, product |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Setup, conventions, PR expectations |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting and supported versions |
| [`docs/RELEASES.md`](docs/RELEASES.md) | How releases are cut and verified |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

---

## Development

```bash
# Node
cd pc_app_flutter/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && pytest tests -q
python service.py

# Clients
cd mobile_app && flutter pub get && flutter analyze --fatal-infos && flutter test
cd ../pc_app_flutter && flutter pub get && flutter analyze --fatal-infos && flutter test
```

CI runs all of the above on every PR, plus CodeQL, Semgrep, Gitleaks over full
git history, a repository-hygiene gate and an Android release assemble. See
[`.github/workflows/`](.github/workflows/).

Runtime state lives outside the repo: `%APPDATA%\Cypher\` on Windows,
`~/.config/cypher/` on Linux, `~/Library/Application Support/Cypher/` on macOS.

---

## Contributing

Issues and PRs welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and look
for `good first issue`.

The highest-leverage places to help right now:

- **Node test suite** ([P1-T1](ROADMAP.md)) — the best way to learn the codebase
- **Design-token migration** ([P2-M2](docs/plans/rebuild-mobile-ui.md)) — mechanical,
  reviewable in small chunks, high visible impact
- **Linux: files, transfers, monitoring** ([P3-L1](docs/plans/cross-platform.md)) —
  pure `psutil`, no platform-specific code
- **CLI client** ([P3-C1](ROADMAP.md)) — well-bounded, and it doubles as an API
  test harness
- **Troubleshooting docs** ([P1-C3](ROADMAP.md)) — especially if you just went
  through setup yourself

Please read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). Third-party attributions in
[`NOTICE`](NOTICE).

The Apache-2.0 grant covers copyright only. It does **not** grant any right to
the CYPHER name or marks; forks must rebrand. See
[`docs/product/branding.md`](docs/product/branding.md).

---

## Acknowledgements

Built by [Emerald Dev](https://github.com/Emerald-dev0) and contributors.

CYPHER stands on Flask, Socket.IO, psutil, Pillow, mss, OpenCV, zeroconf, Flutter
and a long tail of open-source work — all credited in [`NOTICE`](NOTICE).
