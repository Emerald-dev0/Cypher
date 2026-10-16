# Manual Test Matrix

**Roadmap task:** P1-T4
**When:** before **every** release, and after any change to discovery, transport,
auth or file transfer.

CI cannot exercise any of this. There is no runner with a phone on a USB tether to
a Windows PC on a hotel WiFi network — which is precisely where CYPHER breaks.
This matrix is the compensating control, and [`RELEASES.md`](../RELEASES.md) §2
step 4 makes it a release blocker.

---

## Why this document exists

The repository previously contained `TEST_ALL_CONNECTIONS.md` (a plan, never
executed, every row marked `?`) alongside `SYSTEM_AUDIT.md` claiming the project
was *"COMPLETE & PRODUCTION-READY"* and `FEATURE_VERIFICATION.md` claiming
*"ALL CORE FEATURES VERIFIED ✅"*.

At that moment the backend would not parse on Python 3.11, and two entire
features returned HTTP 500 on every request. Both were deleted in the October
2026 cleanup — see [`../AUDIT.md`](../AUDIT.md) §4.

The lesson encoded here: **a test plan is not a test result, and reading code is
not verification.** Every row below has a place to write what actually happened,
on what hardware, by whom, when.

---

## How to run it

1. Copy this file to a scratch document (do **not** commit results — a closed
   issue or the release discussion is the record).
2. Fill in the environment block.
3. Work through the sections. Record ✅ / ❌ / ⚠️ and a note for anything that is
   not a clean pass.
4. Every ❌ becomes a GitHub issue before the release is published, labelled
   `release-blocker` if it affects a primary flow.
5. Attach the filled matrix to the release discussion.

You do not need every device. You need **at least one Android, one Windows and
one Linux**, and at least one row from each transport section. Record what you
could not test and why — an honest gap is far more useful than a false ✅.

---

## Environment

| | Value |
| --- | --- |
| Tester | |
| Date | |
| CYPHER version / tag | |
| Node commit SHA | |
| PC — OS and build | |
| PC — session type (Windows / X11 / Wayland) | |
| PC — node elevated? (should be **no**, see P2-S4) | |
| Phone — model, Android version | |
| Phone — OEM skin (Stock / One UI / MIUI / ColorOS / …) | |
| Router / AP model, and whether "AP isolation" is on | |

---

## 1. Transports

The five ways a phone and a PC actually end up on the same network. Each has a
different IP range, a different DHCP server, and a different set of failure
modes.

| # | Transport | Setup | Expect | Result |
| --- | --- | --- | --- | --- |
| T1 | **Same WiFi router** | Both join the home/office SSID | mDNS discovers the node; pairing succeeds | |
| T2 | **Android hotspot** (phone is AP) | Phone hotspot on, PC joins it | PC gets `192.168.43.x`; discovery finds the node | |
| T3 | **Windows Mobile Hotspot** (PC is AP) | PC hotspot on, phone joins it | Phone gets `192.168.137.x`; discovery finds the node | |
| T4 | **USB tethering** | USB cable, tethering enabled | PC gets `192.168.42.x`; works with WiFi off and airplane mode on | |
| T5 | **Wired LAN** | PC on Ethernet, phone on WiFi, same router | Discovery works across the wired/wireless boundary | |
| T6 | **Manual IP entry** | Discovery disabled; type the address | Connects and pairs without mDNS | |
| T7 | **Guest network / AP isolation ON** | Router with client isolation | Fails **clearly**, with an explanation — not a silent timeout | |

T7 matters as much as the rest. A user on a hotel or campus network with client
isolation cannot connect, and the difference between "connection timed out" and
"this network blocks device-to-device traffic — try a hotspot" is the difference
between a support ticket and a solved problem.

### Discovery checks

- [ ] mDNS finds the node within 5 s on T1/T5
- [ ] UDP beacon fallback works when mDNS is blocked
- [ ] The correct interface is chosen when the PC has several (Ethernet + WiFi +
      a VM adapter + a tethered phone)
- [ ] APIPA (`169.254.x.x`) and loopback are never advertised
- [ ] The advertised address is reachable from the phone (not a stale IP from a
      previous network)
- [ ] After the PC changes network, the phone re-discovers without a restart

---

## 2. Pairing and authentication

| # | Check | Expect | Result |
| --- | --- | --- | --- |
| P1 | Pair with the correct 6-digit code | Succeeds; a token is issued | |
| P2 | Pair with a wrong code | `401`; attempt is counted | |
| P3 | Six wrong codes in a row from one device | `429` + `Retry-After`; lockout appears in the Security console | |
| P4 | Correct code **during** the lockout | Still refused (throttle is checked first) | |
| P5 | Pair again after a successful pairing | The old code no longer works — codes are single-use | |
| P6 | Unauthenticated request to any protected route | `401`, and the attempt is logged | |
| P7 | Request with the old hardcoded token literal | `401` — it must not exist anywhere | |
| P8 | Revoke a device, then use its token | `401` immediately | |
| P9 | Restart the node; a previously paired device reconnects | Works without re-pairing | |
| P10 | Delete the app-data dir and restart | Everything is un-paired; a fresh code is generated | |
| P11 | Two devices paired simultaneously | Both work; both appear in the device list | |
| P12 | Guest link | Opens, is folder-scoped, and **expires** on time | |
| P13 | Guest link after expiry | Refused | |
| P14 | Guest tries to read a sibling folder | Refused, and the refusal does not reveal the sibling's name | |
| P15 | QR pairing (mobile) | Scans and pairs without typing the code | |

---

## 3. Files

Run each on **at least two transports** — T1 and T4 behave differently under load.

| # | Check | Expect | Result |
| --- | --- | --- | --- |
| F1 | Browse a shared folder | Lists correctly with sizes, dates and types | |
| F2 | Browse a **non-shared** folder by crafting the path | Refused (P1-S2 — 🔴 currently *not* enforced; record the actual behaviour) | |
| F3 | Path traversal `../../` in a browse/download/delete request | Refused | |
| F4 | Symlink inside a shared folder pointing outside it | Refused | |
| F5 | Upload a 1 KB file | Lands in the chosen destination | |
| F6 | Upload a 100 MB file | Completes; progress is accurate | |
| F7 | Upload a 5 GB file | Completes; no OOM on either side | |
| F8 | Download a single file | Arrives **byte-identical** (verify a checksum) | |
| F9 | Download a multi-file ZIP | Correct contents, correct names, no zip-slip on extraction | |
| F10 | Chunked download, then cancel mid-transfer | Cancels cleanly; no partial file left behind | |
| F11 | Resume an interrupted transfer | Resumes, does not restart (if implemented) | |
| F12 | Transfer while the screen is off (phone) | Continues | |
| F13 | Transfer while the app is backgrounded | Continues; notification shows progress | |
| F14 | A filename with spaces, unicode, emoji and `#&?%` | Transfers correctly | |
| F15 | A very long path (> 260 chars on Windows) | Works, or fails with a clear message | |
| F16 | Preview a text file, an image, a PDF, a video, an audio file | All render in-app | |
| F17 | Thumbnails for images | Render (F-03/F-04 regressions — must stay fixed) | |
| F18 | Delete a file | Deleted, with confirmation | |
| F19 | Delete inside a protected system directory | Refused on **every** OS, not just Windows | |
| F20 | Disk full on the destination | Clean error; no corruption, no crash | |
| F21 | Concurrent transfers (4+) | All progress; throughput is sane | |

**F8 is not optional.** A file transfer that silently corrupts is worse than one
that fails. `sha256sum` both ends.

---

## 4. Control

| # | Check | Expect | Result |
| --- | --- | --- | --- |
| C1 | Type text into a focused field | Appears correctly, including unicode | |
| C2 | Hotkeys: Ctrl+C, Ctrl+V, Alt+Tab, Win+L, Ctrl+Alt+Del | Each does what it says (note: Ctrl+Alt+Del needs special handling on Windows) | |
| C3 | Pointer move, click, right-click, double-click, scroll | Accurate at the phone's reported coordinates | |
| C4 | Multi-monitor: pointer maps to the right screen | Correct | |
| C5 | Screenshot | Matches the actual screen | |
| C6 | Live stream | ≥ 10 fps on LAN; no leak over 10 minutes | |
| C7 | Screen recording: start, pause, resume, stop | Produces a playable file of the right duration | |
| C8 | Recording overlay visible on the PC during capture | **Shows** — this is the anti-surveillance guarantee | |
| C9 | Clipboard: PC → phone, and phone → PC | Both directions, text | |
| C10 | Clipboard image | Transfers (F-03 regression) | |
| C11 | Volume get/set, mute, media next/prev/play/pause | Work | |
| C12 | Power: lock, sleep, restart, shutdown | Work — test shutdown **last** | |
| C13 | Process list, search, kill | Work; killing a system process is refused or warned | |
| C14 | App list and launch | Launches the right app | |
| C15 | Wake-on-LAN | Boots the target machine | |
| C16 | System stats match Task Manager / `htop` | Within a few percent | |

---

## 5. Platform-specific

### Windows

- [ ] Node starts from a double-clicked shortcut (not a terminal) — the
      `Directory.current` bug, F-08
- [ ] Installs to `%LOCALAPPDATA%` without a UAC prompt
- [ ] Runs as a standard user end to end (P2-S4)
- [ ] Firewall rule is scoped to **private** profiles only
- [ ] Tray icon appears; close-to-tray works; tray menu is correct
- [ ] Survives sleep/resume and a network switch mid-session
- [ ] Uninstall leaves no listener running on port 5000

### Linux (Phase 3+)

- [ ] `pip install -r requirements.txt` succeeds on a clean Ubuntu 24.04
- [ ] Node starts with no Windows-only import error
- [ ] App-data path matches what the shell expects (P3-L6 — currently divergent)
- [ ] Files, transfers and system stats work
- [ ] **X11:** screenshot, stream, input injection, volume
- [ ] **Wayland:** portal capture with a visible consent dialog; input via
      libei/uinput; window list degrades honestly
- [ ] `.deb` and AppImage install and run
- [ ] systemd **user** unit starts the node with no root
- [ ] Tray icon appears on GNOME and KDE

### Android

- [ ] minSdk device (API 24) installs and runs
- [ ] Android 13+ media permissions work
- [ ] Android 14+ foreground service type is accepted
- [ ] **Release** build (not debug) can reach the node — the cleartext trap, F-11
- [ ] Share sheet → CYPHER receives the file (P2-M4 — 🔴 currently dead)
- [ ] MIUI / One UI / ColorOS: connection survives aggressive battery management
- [ ] Tablet and landscape layout are usable (P2-M3)
- [ ] TalkBack navigates the primary flows (P2-M8)
- [ ] Backup/restore and device migration do **not** carry the token

### iOS (Phase 4+)

- [ ] Local Network permission prompt appears with honest copy
- [ ] Discovery finds a node (proves the Bonjour entitlements)
- [ ] Pairing, transfer, control

---

## 6. Resilience

| # | Scenario | Expect | Result |
| --- | --- | --- | --- |
| R1 | PC goes to sleep mid-session | Phone shows "unreachable" with recovery, not a spinner forever | |
| R2 | PC wakes up | Reconnects automatically | |
| R3 | WiFi drops mid-transfer | Transfer fails cleanly; retry works; no partial file | |
| R4 | Phone switches WiFi → mobile data | Clear state change; no silent failure | |
| R5 | Node process is killed | Shell detects it, shows the reason, offers restart | |
| R6 | Shell is killed | **The node does not stay listening** — no orphan | |
| R7 | Both are restarted | Reconnects without re-pairing | |
| R8 | Two phones paired at once | Both work independently | |
| R9 | One hour of continuous streaming | No memory creep on either side | |
| R10 | 100 sequential transfers | No handle or temp-file leak | |
| R11 | Node version and shell version mismatch | Refused with an explicit upgrade message (P1-D1) | |

R6 and R9 are the two most likely to fail and the two most likely to be skipped.
Do not skip them.

---

## 7. Performance targets

Measure, do not guess. Record the transport and the hardware.

| Metric | Target | Measured |
| --- | --- | --- |
| Pairing (code entered → home screen) | < 2 s | |
| Cold start: phone app → paired home | < 3 s | |
| Cold start: desktop shell → dashboard | < 6 s | |
| Screenshot request → rendered | < 800 ms | |
| Stream frame rate on LAN WiFi | ≥ 15 fps | |
| File transfer throughput on 5 GHz WiFi | ≥ 20 MB/s | |
| File transfer throughput on USB tethering | ≥ 25 MB/s | |
| Idle node RAM | < 150 MB | |
| Idle node CPU | < 1 % | |
| Idle shell RAM | < 250 MB | |
| Time to first byte on a 5 GB download | < 1 s | |

---

## 8. Sign-off

| | |
| --- | --- |
| Tested by | |
| Date | |
| Version | |
| Rows passed / attempted | |
| Open `release-blocker` issues | |
| Recommendation | ☐ Ship  ☐ Ship with known issues documented  ☐ Do not ship |

Attach this to the release discussion before publishing the draft
([`RELEASES.md`](../RELEASES.md) §2 step 6).
