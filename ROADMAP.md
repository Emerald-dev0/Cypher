# CYPHER Roadmap

**Last updated:** 2026-10-15
**Owner:** Emerald-dev0/maintainers
**Status source of truth:** this file. Point-in-time status reports are not
committed — a closed issue is the record. See [`AGENTS.md`](AGENTS.md) §4.

CYPHER is **pre-1.0 in substance and post-1.0 in marketing**. The version stamps
say `1.0.0`; the audit found the node would not start on Python 3.11, two whole
features returned HTTP 500 on every request, and a public authentication token
was committed to the repository. This roadmap sequences the work to make the
project genuinely releasable, then genuinely cross-platform, then genuinely
cloud-capable.

---

## How to read this

Every task has a stable ID (`P1-S2`) referenced from
[`docs/AUDIT.md`](docs/AUDIT.md) §7, [`AGENTS.md`](AGENTS.md), and the plan
documents. IDs never get reused; completed tasks keep their ID and move to the
bottom of their phase.

**Gate rule — each phase must close before the next opens.**

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
Freeze      Stabilise   Harden      Port        Apple       Cloud
            (v0.9)      (v1.0)      (v1.1+)     (v2.0)      (v2.1+)
```

The gate after Phase 1 is a **public-security gate**: CYPHER must not be
announced, listed, or promoted before Phase 1 closes. Publishing a
remote-control tool with no TLS (P2-S1
mitigations pending) would expose every early adopter's machine.

---

## Phase 0 — Freeze & foundations · ✅ COMPLETE (this pass)

Repo hygiene and the fixes that could be made safely without a test harness.

| ID | Task | Status |
| --- | --- | --- |
| P0-1 | Comprehensive root `.gitignore` | ✅ |
| P0-2 | Remove 78 MB of committed PyInstaller output, `.idea/`, AI scratch | ✅ |
| P0-3 | Delete 12 contradictory status docs; relocate 4 real specs into `docs/` | ✅ |
| P0-4 | Delete the dead customtkinter desktop UI (~2,400 lines, 8 modules) | ✅ |
| P0-5 | Purge committed secrets: `google-services.json`, `master_password` | ✅ |
| P0-6 | Replace hardcoded `INTERNAL_TOKEN` with a per-install generated token | ✅ |
| P0-7 | Pairing brute-force throttle + constant-time compare + code rotation | ✅ |
| P0-8 | Fix `SyntaxError` that bricked the node on Python ≤ 3.11 | ✅ |
| P0-9 | Fix `NameError` that broke all 14 guest routes | ✅ |
| P0-10 | Fix missing Pillow import (clipboard, thumbnails, window icons) | ✅ |
| P0-11 | Fix 401 on preview/thumbnail (media-token route set) | ✅ |
| P0-12 | Fix screen-stream crash on early connect | ✅ |
| P0-13 | Repair `requirements.txt`: add 4 missing, drop 3 unused, platform-gate | ✅ |
| P0-14 | Remove Firebase Analytics + third-party install beacon | ✅ |
| P0-15 | Fix debug-keystore release signing; add keystore template | ✅ |
| P0-16 | Add `network_security_config.xml` (Android release LAN access) | ✅ |
| P0-17 | Replace placeholder `com.example.mobile_app` application id | ✅ |
| P0-18 | Move permission requests from launch to point of use | ✅ |
| P0-19 | Correct update-check URLs to `Emerald-dev0/Cypher` | ✅ |
| P0-20 | Add `LICENSE` (Apache-2.0) + `NOTICE` with third-party attributions | ✅ |
| P0-21 | CI: `ci.yml`, `release.yml`, `codeql.yml`, `pages.yml`, Dependabot | ✅ |
| P0-22 | `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | ✅ |
| P0-23 | This roadmap + audit + five plan documents | ✅ |

---

## Phase 1 — Stabilise · target `v0.9.0-beta`

**Goal: the project is honestly testable, and nothing in it can be trivially
abused.** Estimated 3–4 weeks part-time.

### Security (must all close before any public announcement)

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P1-S2** ✅ | **Filesystem sandbox helper** — SHIPPED | `core/sandbox.py` (`Sandbox.resolve` + `SandboxViolation`). Applied to every `/files/*` route that takes a client path, `/apps/launch`, and the guest routes via the existing wrapper. Windows denylist removed. AST route-coverage test in `tests/test_sandbox.py`. | done |
| **P1-S3** | Decorator-based public routes | Replace the `public_endpoints` function-name list with an explicit `@public_route` decorator so a rename cannot silently expose a route. Assert in tests that the public set is exactly `{ping, get_status, pair_device}`. | 1d |
| **P1-S4** | CORS + DNS-rebinding defence | Restrict `CORS()` to known origins; validate the `Host` header against `{127.0.0.1, localhost, <own LAN IPs>}`; reject public hostnames; set `cors_allowed_origins` on SocketIO to match. | 2d |
| **P1-S1** | Purge secrets from git history | `git filter-repo` to remove `google-services.json`, the token literal and `master_password` from all history. Coordinate with every contributor (SHAs change). Rotate the Firebase key. Publish a forced-upgrade notice because pre-fix installs still carry the guessable token. | 2d |
| P1-S5 | Structured audit log with an explicit "sensitive" field class | Groundwork for P3-S1 redaction; make `log_event` schema-typed rather than free-text dicts. | 2d |

### Build & repo

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P1-B1** | Shrink `.git` from 78 MB | Executed alongside P1-S1 with the same `filter-repo` pass. Target < 15 MB. | 0d |
| **P1-B4** | Decompose `server.py` (3,000 lines → Blueprint modules) | `core/routes/{pairing,files,system,media,recording,guest,transfer}.py`, a `core/sandbox.py`, and a `core/auth.py`. Extract the ~550 lines of embedded guest HTML into `templates/guest.html`. Target: no file over ~500 lines. **Sequence after P1-S2** so the sandbox helper lands once, in its final home. | 5d |
| **P1-B8** | Single source of version truth | One `VERSION` file (or `version.py`) generates pubspec versions, `metadata.json`, the `.iss` stamp, and Dart's runtime version via `package_info_plus`. Delete every hardcoded version constant. `release.yml` preflight already enforces agreement; this removes the manual step. | 2d |
| **P1-B9** | **Remove `syncfusion_flutter_pdfviewer`** — release blocker | Its Community License is proprietary and **not Apache-2.0-compatible**, so binary distributions bundling it cannot be published under our license (see `NOTICE`). Replace with `pdfrx` or `pdfx` (BSD/Apache). | 2d |
| P1-B2 | Pyproject + ruff/mypy config for the node | `ruff` config with the F/E9 selection CI already runs; `mypy` in gradual mode on `core/sandbox.py` and `core/auth.py` first. | 1d |
| P1-B3 | `py.typed` and type hints on the security-critical modules | Sandbox, auth, guest manager. | 3d |
| P1-B5 | Pre-commit config | ruff, ruff-format, dart format, gitleaks, trailing whitespace, large-file block. | 1d |
| P1-B6 | Gradual mypy adoption | Expand from P1-B3 to `core/routes/`. | ongoing |
| P1-B7 | Renovate-or-Dependabot review cadence documented | Dependabot is configured; document the Monday triage routine in `CONTRIBUTING.md`. | 0.5d |
| P1-B10 | Rename directories to the target layout | `pc_app_flutter/` → `desktop/`, `pc_app_flutter/backend/` → `node/`, `mobile_app/` → `mobile/`. Do this **once**, early, in a single commit, before external contributors exist — every week of delay makes it more disruptive. Update specs, workflows, docs. | 1d |

### Tests

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P1-T1** ⏳ | Node test suite that CI can actually run | `backend/tests/conftest.py` stubs `win32*`, `pyautogui`, `pycaw`, `pygetwindow` so the node imports on Linux. Coverage: auth hook (401/403/429 paths), pairing throttle and rotation, sandbox helper, guest session lifecycle and expiry, transfer progress accounting, settings persistence. Target ≥ 70% on `core/`. | 5d |
| **P1-T2** ⏳ | Flutter widget + unit tests | ~~Replace the desktop app's leftover `flutter create` counter test~~ **done** — both broken widget tests are gone (desktop: `bridge_service_test.dart` + `theme_service_test.dart`; mobile: `StorageService` tests). Remaining: `ApiService` error mapping, provider state transitions, connection/reconnect logic, route table, and a fake `BackendManager` so `StartupScreen` can be pumped without spawning a real Python process. | 3d |
| P1-T3 | Contract tests between Dart and Python | Generate an OpenAPI spec from the Flask routes; validate `api_service.dart` against it in CI. Catches the endpoint-rename drift that produced S-04. | 3d |
| P1-T4 | Device test matrix | Encode `TEST_ALL_CONNECTIONS.md` (deleted) as a maintained manual matrix: 5 transports × Android 10/13/15 × Windows 10/11 × Ubuntu 22.04/24.04. Required before every release. | 1d |
| **P1-T5** | Make the Dart style gates blocking | `dart format` has never been run over this codebase and `flutter analyze --fatal-infos` fails on the ~130 hardcoded colour literals (A-08). Both steps currently run in CI as **non-blocking annotations** so the tree is not permanently red. This task: run `dart format lib test` in both apps as one dedicated commit, clear the info-level lint backlog, then flip both steps to blocking in the same PR. Must not be mixed with a feature change — a formatting-only commit is reviewable, a mixed one is not. | 2d |

### Desktop shell

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P1-D2** | Fix backend discovery | Resolve the node relative to `Platform.resolvedExecutable`, not `Directory.current`. Remove the hardcoded `C:\Users\hp\...\python.exe`. Search PATH properly; report which interpreter was used in the error screen. | 1d |
| P1-D1 | Node health protocol | `/ping` returns build version + protocol version; the shell refuses to talk to a mismatched node instead of failing mysteriously. | 1d |
| P1-D3 | Structured node logging | Replace `print()` with the `logging` module already configured in `service.py`; rotate to `<appData>/cypher/logs/node.log`; surface in the desktop Health tab. | 2d |

### Docs & community

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| P1-C1 | Rewrite `README.md` | Honest status, real quick start, security warning, screenshots, license. Remove every claim not currently true. | 1d |
| P1-C2 | `docs/product/privacy.md` | What is stored, where, what leaves the device (answer: nothing, and the one user-initiated GitHub version check). Feeds the Play Store Data Safety form. | 1d |
| P1-C3 | Troubleshooting guide | The five transports, firewall, mDNS failure modes, "works in debug not release". Absorbs the deleted `TEST_ALL_CONNECTIONS.md`. | 2d |
| P1-C4 | Issue triage labels + first-response SLA documented | | 0.5d |
| **P1-C5** | Audit every CI check for the fail-open shape | S-18 found a security gate that had *never run*: `git grep --exclude-dir=…` is GNU-grep syntax, so it exited non-zero inside an `if` condition, `set -e` did not fire, and the step printed "passed". Review all four workflows for `if <cmd>; then fail; fi` where `<cmd>` can error for unrelated reasons, and add a canary self-test to every gate whose failure mode is silence. Also add a CI step that validates the workflow YAML parses — `ci.yml` separately contained a plain scalar with `\|\| { … }` that PyYAML rejects outright. | 1d |
| P1-C5 | `docs/RELEASES.md` — how to cut a release | Secrets setup, tag procedure, keystore generation, draft review, Play Store upload. | 1d |

**Phase 1 exit criteria:** CI green on a clean clone; ≥ 70% node coverage; the
sandbox helper enforced on every filesystem route with a passing property test;
git history under 15 MB and free of secrets; a signed beta APK and a signed
Windows installer published as a draft release; README accurate.

---

## Phase 2 — Harden · target `v1.0.0`

**Goal: safe to announce publicly.** Estimated 4–6 weeks.

### Security

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P2-S1** | TLS transport | Per-pairing self-signed node certificate; fingerprint displayed at pairing and pinned by the client (TOFU). Client-side `assertPrivateTarget()` guard refusing HTTP to any non-RFC1918 destination — the compensating control for Android's inability to scope cleartext by CIDR. Then flip `network_security_config.xml` to `cleartextTrafficPermitted="false"`. | 8d |
| **P2-S2** | Signed URLs | Replace `MEDIA_TOKEN_ROUTES` query-string tokens with HMAC-signed, short-lived (60s), scope-limited URLs. Retires the S-09 compromise. | 3d |
| **P2-S3** | Secure token storage | `flutter_secure_storage` (Keystore/Keychain) on mobile; `0600` on `paired_devices.json`; optional biometric/PIN gate on app open. | 4d |
| **P2-S4** | Least privilege | Run the node unprivileged. Move the firewall rule into the installer, scoped to **private profiles only**. Make elevation opt-in per feature (hibernate, some process control) and degrade gracefully. Remove the automatic `runas` prompt. | 4d |
| **P2-S5** | Capability scopes + app-launch allowlist | Per-device scopes (`files`, `media`, `input`, `power`, `processes`) granted at pairing and visible/revocable in the Security tab. `/apps/launch` resolves app identity rather than executing an arbitrary path; on-node confirmation for first launch of an unseen target. | 5d |
| **P2-S6** | Token lifecycle | Expiry, rotation, `last_seen` enforcement, and **stop returning raw tokens from `/paired-devices`**. Add "revoke all devices". | 3d |
| P2-S7 | Threat model document | STRIDE across the three transports and the relay; publish at `docs/architecture/threat-model.md`. Prerequisite for the P5 relay design review. | 3d |
| P2-S8 | Dependency audit automation | `pip-audit` + `flutter pub deps` + OSV in CI; block releases on critical CVEs. | 1d |
| P2-S9 | Fuzz the HTTP surface | `atheris`/`hypothesis` against the transfer and guest routes. | 3d |

### Mobile

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P2-M2** | Design-system migration | Adopt `theme/colors.dart` everywhere; delete all ~130 `Color(0x…)` literals; wire `themeMode` + light theme (currently unreachable, A-07); add a `CypherTheme` extension so tokens are accessed via `Theme.of(context)`. Add a CI lint that fails on new color literals. Full plan: [`docs/plans/rebuild-mobile-ui.md`](docs/plans/rebuild-mobile-ui.md). | 6d |
| **P2-M4** | Share-sheet integration | Dart-side `ShareIntentService` for the already-implemented `app/share` MethodChannel: cold-start buffering, `content://` URI resolution, routing into `SendToPCScreen`. Fixes F-06. | 3d |
| **P2-M6** | SAF migration → drop `MANAGE_EXTERNAL_STORAGE` | Replace the raw phone browser with Storage Access Framework tree URIs. Removes the Play Store Data Safety review risk. | 5d |
| **P2-M9** | Unlock the AGP pin | Move off the 8.7.2 pin (which exists because 8.9.x hangs the Gradle daemon on Windows) and remove the `androidx.core`/`androidx.browser` resolution-strategy overrides. Verify on Windows CI. | 2d |
| P2-M1 | Navigation overhaul | Declarative `go_router` with typed routes, replacing the 25-case `onGenerateRoute` switch. Deep links for `cypher://pair` and `cypher://send`. | 4d |
| P2-M3 | Responsive layout | Unlock landscape and tablet breakpoints; the app is currently locked to portrait. | 3d |
| P2-M5 | Error-state design system | Every screen gets loading/empty/error/offline states from shared widgets; no more silent failures. | 3d |
| P2-M7 | Background transfer service | Foreground service with a notification so large transfers survive the app being backgrounded. Manifest permissions already added in Phase 0. | 4d |
| P2-M8 | Accessibility pass | Semantics labels, contrast audit against WCAG AA, dynamic text scaling, screen-reader order. | 3d |
| P2-M10 | Remove `print()` and add a logging facade | Level-filtered, redacting, exportable for bug reports. | 1d |
| P2-M11 | Delete unused permissions | `CAMERA` if QR pairing is dropped, `mediaLibrary`, and anything not backed by a shipped feature. Play policy requires each to be justified. | 1d |

### Desktop

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| P2-D1 | Desktop UI rebuild | Full plan: [`docs/plans/rebuild-desktop-ui.md`](docs/plans/rebuild-desktop-ui.md). Shared design-system package with mobile, adaptive layout, real Settings, security console. | 10d |
| P2-D2 | Shared `packages/cypher_ui` Dart package | One design system consumed by both apps — the structural fix for A-08 drift. | 4d |
| P2-D3 | Auto-update with signature verification | Replace the "open the releases page" flow with in-app download + Authenticode/minisign verification. | 4d |

**Phase 2 exit criteria:** TLS on by default for new pairings; no token appears
in a URL; the node runs unprivileged; capability scopes enforced and visible in
the UI; zero critical/high CVEs; CodeQL and Semgrep clean; both apps share one
design-system package; `v1.0.0` published with signed artefacts on all three
platforms and a completed Play Store Data Safety declaration.

---

## Phase 3 — Port · target `v1.1.0` (Linux), `v1.2.0` (CLI)

**Goal: Windows and Linux are equal first-class citizens.** Estimated 6–8 weeks.
Full detail: [`docs/plans/cross-platform.md`](docs/plans/cross-platform.md).

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| **P3-L1** | Platform abstraction layer | `core/platform/{base,windows,linux}.py` with a capability registry. Every `if not WINDOWS: return` becomes a declared capability the client can query, so the UI hides what the node cannot do instead of showing a button that 400s. | 5d |
| **P3-L2** | Linux input injection | X11 via `pyautogui`/`Xlib`; Wayland via `libei` or `ydotool`/uinput. Session-type detection at startup. | 8d |
| **P3-L3** | Linux screen capture | X11 via `mss`; **Wayland via PipeWire + xdg-desktop-portal ScreenShot** — the hard one, and the default on Ubuntu 24.04 and Fedora. Recording through the same portal. | 10d |
| **P3-L4** | Native recording overlay | Replace the Tk overlay with a Win32 layered window / X11 EWMH / Wayland layer-shell indicator, removing the customtkinter dependency. | 4d |
| **P3-L5** | Linux packaging | `.deb` + `.rpm` + AppImage; systemd **user** unit for the node; `firewalld`/`ufw` guidance instead of `netsh`. | 5d |
| **P3-L6** | Unify app-data path resolution | `core/utils.py` uses `~/.cypher`; `BridgeService` uses `~/.config/cypher`. They disagree — the shell cannot find the node's token file. Pick one (XDG: `~/.config/cypher`), add a migration for existing installs. | 1d |
| **P3-L7** | Explicit Windows DACL on the token file | `os.chmod(0o600)` is a no-op on Windows, so `internal_token` relies on the ACL inherited from `%APPDATA%` (audit S-19). Set an explicit DACL restricted to the current user via `pywin32` or `icacls`, Windows-only and behind a capability check from P3-L1. Low severity — `%APPDATA%` already denies other standard users — but it is the only credential-protection control that differs by platform, and it must not be attempted from a Linux workstation. | 1d |
| P3-S1 | Log redaction | Never log keystroke content; redact by field class using the P1-S5 schema. Fixes S-15. | 2d |
| P3-C1 | CLI client | `cypher` binary: `pair`, `ls`, `get`, `put`, `shot`, `lock`, `wol`. Same HTTP API, no UI. Unlocks scripting, CI and headless-server use. | 8d |
| P3-C2 | Headless node mode | No tray, no overlay, config-file-driven, `--no-discovery`. For servers and containers. | 2d |
| P3-C3 | Container image for the node | Dockerfile + compose; useful for the relay and for headless Linux nodes. | 2d |

**Phase 3 exit criteria:** an Ubuntu 24.04 (Wayland) user can pair, browse
shared folders, transfer files, capture the screen and inject input; `.deb` and
AppImage published by CI; the CLI can do everything the mobile app can do except
preview media.

---

## Phase 4 — Apple platforms · target `v2.0.0`

**Goal: iOS and macOS ship.** Estimated 8–12 weeks. Gated on Phase 2 (TLS)
because Apple's Local Network privacy model effectively requires it.

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| P4-1 | iOS local-network entitlements | `NSLocalNetworkUsageDescription`, `NSBonjourServices` in `Info.plist`, and the iOS 14+ local-network permission prompt flow. Currently absent — iOS cannot discover or reach a node at all. | 3d |
| P4-2 | iOS mDNS | `nw_browser`/`NetService` behaves differently from Android's NSD; validate discovery against a real node. | 5d |
| P4-3 | iOS background execution | Transfers cannot run backgrounded the way Android's do; design around `URLSession` background configuration. | 5d |
| P4-4 | iOS share extension | The equivalent of P2-M4, as a proper Share Extension target. | 5d |
| P4-5 | iOS signing & TestFlight pipeline | Certificates, provisioning profiles, Fastlane, a `release-ios.yml` workflow. Requires an Apple Developer account. | 4d |
| P4-6 | macOS node | Screen capture via `ScreenCaptureKit` (not `mss`), input via the Accessibility API with a TCC permission flow, audio via `CoreAudio`. Substantial: this is a second node implementation. | 15d |
| P4-7 | macOS entitlements & notarization | `com.apple.security.network.server`, App Sandbox considerations, notarization + stapling in CI. | 4d |
| P4-8 | Universal purchase / shared design language | iPad layout, menu-bar mode on macOS. | 5d |

**Phase 4 exit criteria:** TestFlight build discoverable and pairable on iOS 17+;
a notarized macOS node that can be controlled from an iPhone.

---

## Phase 5 — Cloud relay · target `v2.1.0`

**Goal: phone ↔ PC works when they are not on the same network — without
breaking the local-first contract.** Estimated 6–8 weeks.
Full design: [`docs/plans/relay-cloud.md`](docs/plans/relay-cloud.md).

**Architectural decision (locked):** the cloud component is a **self-hostable
relay**, not a storage or account backend. It forwards encrypted bytes between a
node and a client that cannot reach each other directly. It never sees plaintext,
never requires an account for LAN use, and ships as a Docker image anyone can
run. Emerald may operate a free public instance as a convenience.

| ID | Task | Detail | Est. |
| --- | --- | --- | --- |
| P5-1 | Noise Protocol handshake on the node | `Noise_XX_25519_ChaChaPoly_BLAKE2s`. Mutual authentication, forward secrecy, and one transport that works identically over LAN and relay — which makes P2-S1 and P5 the same code path rather than two. | 10d |
| P5-2 | Relay server | Rust or Go; WebSocket/TCP tunnel; no plaintext termination; per-pairing auth via node public keys; horizontal scale; hardening pass against P2-S7's threat model. | 12d |
| P5-3 | NAT traversal | STUN always, TURN as a paid/self-hosted fallback. Hole-punch where possible so the relay only carries what it must. | 6d |
| P5-4 | Relay client in node + mobile | Opt-in, off by default, with a visible indicator whenever traffic is relayed and a setting to pin a specific relay URL. | 5d |
| P5-5 | Docker image + compose + Helm | `ghcr.io/emerald-dev0/cypher-relay`. One-command self-host. | 3d |
| P5-6 | Public relay operations | Rate limiting, abuse handling, capacity planning, ToS, and an honest privacy statement. Decide whether this is free, metered, or paid. | 5d |
| P5-7 | E2EE verification UX | Show the Noise handshake fingerprint out-of-band (QR at pairing) so a user can confirm the relay is not MITMing. This is what makes the relay trustworthy. | 4d |

**Phase 5 exit criteria:** two devices on different continents transfer a file
through a self-hosted relay with the relay operator unable to read it; the LAN
path is bit-for-bit unchanged when the relay is disabled; a stranger can
self-host the relay from one `docker compose up`.

---

## Beyond the horizon

Ideas, not commitments. Scoped in
[`docs/product/features-and-applications.md`](docs/product/features-and-applications.md).

- **Multi-node** — one phone controlling several PCs, with a node switcher.
- **Presentation mode** — the phone becomes a clicker + slide remote + laser
  pointer over HDMI.
- **Kiosk / digital signage** — a locked-down node driven remotely.
- **Family/elder-care assist** — a trusted helper sees and guides a screen with
  explicit, revocable, time-boxed consent.
- **LAN file drop, no pairing** — an ephemeral AirDrop-style public drop zone.
- **Wake-on-LAN scheduler** and **remote boot profiles**.
- **Clipboard managers, snippet libraries, cross-device clipboard history** with
  opt-in end-to-end encryption.
- **Input remapping / macro recorder** with a shareable macro format.
- **Developer mode** — remote terminal, log tailing, port forwarding over the
  tunnel.
- **Home Assistant / MQTT integration** — the node as an automation actuator.
- **Plugin API** — a sandboxed manifest format so third parties can add node
  capability without forking. Must not arrive before P2-S5 capability scopes.

---

## Versioning & release policy

- **SemVer.** `vMAJOR.MINOR.PATCH`; a `-rc.N`/`-beta.N` suffix marks a
  pre-release, which `release.yml` publishes as a GitHub pre-release.
- **Protocol version** is separate from product version and travels in `/ping`.
  The shell refuses a mismatched node (P1-D1) rather than failing mysteriously.
- **Releases are cut by tag.** `git tag v1.2.0 && git push origin v1.2.0`.
  `release.yml` builds every target, checksums, and opens a **draft** release for
  human review. See [`docs/RELEASES.md`](docs/RELEASES.md).
- **`CHANGELOG.md`** follows Keep a Changelog and is written for users, not
  developers. Every user-visible PR updates it (AGENTS.md §8).
- **Support window:** the latest two minor versions get security fixes. Older
  versions get a forced-upgrade notice, because for a remote-control tool an
  unpatched install is an active liability.

---

## Contributing to the roadmap

Open an issue or a PR against this file. A roadmap entry needs:

1. A stable ID that is not already used.
2. A one-line outcome, not an activity ("the node refuses paths outside shared
   folders", not "look at path handling").
3. A pointer to the audit finding, plan section, or issue that motivates it.
4. An estimate in days.

Items are removed only when done or explicitly rejected — never silently. If you
invalidate a planned item, edit it in place and say why in the PR description.
