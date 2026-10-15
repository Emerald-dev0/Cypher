# Changelog

All notable changes to CYPHER are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries before **[Unreleased]** describe what shipped. Entries under
**[Unreleased]** describe the 2026-10 hardening and open-sourcing pass, which has
not been tagged or released yet.

> **A note on the historical entries below.** The v2.1 release notes claimed
> *"Path traversal prevention on all endpoints"*, *"Session expiry & revocation"*
> and *"Guest access with folder sandboxing"*. The October 2026 audit
> ([`docs/AUDIT.md`](docs/AUDIT.md)) found all three were **not true as written**:
> paired-device file routes had no path checks at all (S-03), and revoking a
> guest session silently did nothing (S-13a). The claims are struck through below
> rather than deleted, because knowing what the project believed about itself is
> part of its history. Nothing in the historical sections should be read as a
> current security statement — see [`SECURITY.md`](SECURITY.md) for that.

---

## [Unreleased]

The project's first pass at being a professional open-source codebase. There was
previously **no LICENSE file**, so despite being public on GitHub it was not open
source at all — default copyright, all rights reserved.

### Added

- **`LICENSE`** — Apache-2.0, plus a `NOTICE` file. Chosen over MIT because the
  patent grant matters for a remote-control product, and over GPL because the
  Flutter clients should remain linkable.
- **`AGENTS.md`** — the technical contract for anyone changing this code, human or
  AI agent: the product contract, repo map, commands, seven invariants (I1–I7),
  conventions, known traps, testing expectations, definition of done, doc index.
- **`ROADMAP.md`** — five phases with numbered tasks (P1-S*/B*/T*/D*/C*, P2-*,
  P3-*, P4-*, P5-*), each traceable to an audit finding.
- **`SECURITY.md`** — threat model, supported versions, disclosure policy with a
  90-day clock, and an explicit list of what CYPHER will never do.
- **`CONTRIBUTING.md`** and **`CODE_OF_CONDUCT.md`** (Contributor Covenant 2.1,
  extended with anti-surveillance and anti-zero-day clauses).
- **`docs/AUDIT.md`** — 38 findings across security, functionality, architecture,
  mobile, desktop and release engineering, each with a severity, a status, and a
  roadmap task ID. 20 fixed, 5 partially fixed, 13 deferred.
- **`docs/RELEASES.md`** — the secrets table, `keytool` recipe, seven-step release
  process, artefact and pipeline tables, rollback procedure, Play Store notes.
- **`docs/plans/`** — `rebuild-desktop-ui.md`, `rebuild-mobile-ui.md`,
  `security-hardening.md`, `relay-cloud.md`, `cross-platform.md`, `test-matrix.md`.
- **`docs/architecture/`** — `overview.md`, `pairing.md`, `file-transfer.md`,
  `design-system.md`.
- **`docs/product/`** — `features-and-applications.md`, `privacy.md`,
  `positioning.md`, `branding.md`.
- **GitHub Actions CI/CD** — `ci.yml` (hygiene, docs links, banned-dependency
  gate, Python lint/type/test on Linux *and* Windows, Flutter analyze/test on both
  apps), `release.yml` (signed Android + Windows installer + Linux artefacts),
  `codeql.yml`, `pages.yml`. Plus `dependabot.yml`, issue templates, and a PR
  template with a mandatory "what did you actually run" table and an eight-box
  security checklist.
- **A real test suite** — `pc_app_flutter/backend/tests/`, **121 tests**:
  `test_security.py` (51), `test_guest_manager.py` (27), `test_sandbox.py` (43).
  `conftest.py` stubs the Windows-only modules and redirects `%APPDATA%`/`$HOME`
  into a tmpdir, so the node is testable on Linux CI without touching a
  developer's real configuration. Ten tests are `strict=True` xfails that document
  the open sandbox gap and will fail the build the moment it is fixed, forcing the
  markers to be removed deliberately.
- **Flutter tests** — `bridge_service_test.dart` and `theme_service_test.dart`
  (desktop), `StorageService` tests (mobile).
- **Root `.gitignore`** — Python, Flutter, Android, iOS/macOS, native desktop
  build output, IDEs, AI scratch space, secrets, logs. Enforced by a CI hygiene
  job that fails if any of these patterns reappear in `git ls-files`.
- **Keystore support for Android release builds**, with `key.properties.example`
  and a CI assertion that release artefacts are not debug-signed.
- **Android network security config** (`allowBackup="false"`, data-extraction
  rules) plus the client-side private-network guard that makes its global
  cleartext permission safe — see F-11b under Security below.

### Changed

- **Authentication.** The hardcoded `INTERNAL_TOKEN` (`cypher-internal-pc-app-token-2024`,
  committed to a public repo, granting full remote control of every installed
  node) is replaced by a per-install `secrets.token_urlsafe(48)` written to
  `<appdata>/Cypher/internal_token` with mode `0600`, read by the Flutter shell
  from the same file. The node's startup banner no longer prints it.
- **Port constants.** `SERVER_PORT` (5000), `DISCOVERY_PORT` (5001) and
  `BEACON_PORT` (5002) are now defined once in `core/utils.py` and used by the
  HTTP bind, the Socket.IO bind and the Windows Firewall rules. They were
  previously bare literals in at least four files, so changing one silently left a
  stale firewall rule opening a port nothing listened on.
- **Pairing.** Codes are generated with `secrets.randbelow` and compared with
  `hmac.compare_digest`; a per-IP throttle allows 5 attempts per 300 s with a
  900 s lockout, checked *before* the comparison; codes are single-use and rotate
  after success; `pairing_code.txt` is written mode `0600`.
- **Request hook ordering.** `before_request` now authenticates *first* and never
  parses the body (see Security below).
- **`is_path_in_folders()`** now honours every folder in the allowlist, not just
  the first.
- **Guest sessions** are actually revoked by `end_session()`, and their access log
  is bounded.
- **Dependencies.** `requirements.txt` and `requirements-dev.txt` rebuilt with
  platform markers; `pyproject.toml` added with ruff/pytest/mypy/coverage config.
- **Application identity** — `io.github.emerald_dev0.cypher` (was a placeholder).
- **Permissions** are requested at the point of use instead of six dialogs at
  launch.
- **`customtkinter` is now optional** — the node imports without it, and
  `recording_overlay.py` degrades instead of crashing.
- **README.md rewritten** — the previous 572 lines of emoji marketing made
  security claims the code did not support.
- **`service.py`** — `netsh` calls no longer use `shell=True`, resolve the
  executable with `shutil.which()`, and share one helper between `main()` and
  `register_firewall()`. Eight bare `except:` clauses across `core/` were narrowed
  and logged; they ran in daemon threads and were swallowing `KeyboardInterrupt`
  and `SystemExit` during shutdown.
- **Ruff is clean** — `ruff check pc_app_flutter/backend` reports zero findings,
  down from 58.

### Removed

- **Committed credentials** — `google-services.json` (API key
  `AIzaSyCmdZYTYwrSB34q7gSI2yA8F6KGf_kH8Mk`, project `cypher-e7712`) deleted and
  Firebase stripped from both Gradle files. The key must still be treated as
  compromised and rotated: it remains in git history until P1-B1.
- **Install analytics** to a third-party host, which contradicted the README's
  headline *"No cloud. No data tracking."* A CI job now fails the build if any
  `firebase|analytics|sentry|mixpanel|amplitude|segment|posthog|onesignal|facebook`
  dependency appears.
- **The dead customtkinter desktop UI** — ~2,400 lines across eight modules
  (`core/ui.py`, `pairing_screen.py`, `files_panel.py`, `guest_panel.py`,
  `dashboard_screen.py`, `setup_screen.py`, `splash_screen.py`,
  `sync_metadata.py`). `service.py`, the actual entry point, never imported any of
  them. Flutter desktop is now the single desktop UI.
- **78 MB of committed build output** — a 69 MB PyInstaller `cypher_node.pkg`, an
  8.8 MB `PYZ-00.pyz`, a 45,637-line `xref-*.html`, `mobile_app/android/build/`,
  and `.idea/`. ⚠️ The blobs remain in git history; the purge is P1-B1
  (`git filter-repo`), which rewrites SHAs and must be coordinated with
  contributors.
- **Eleven stale root documents** (`CRITICAL_BUGS_FOUND`, `DOCUMENTATION_INDEX`,
  `FEATURE_VERIFICATION`, `FILE_TRANSFER_FIX_PLAN`, `FINAL_STATUS`,
  `FUNCTIONALITY_AUDIT`, `HACKATHON_STATUS`, `MORE_CRITICAL_ISSUES`,
  `SYSTEM_AUDIT`, `TEST_ALL_CONNECTIONS`, `PERMISSIONS_CONFIGURATION`), plus
  `guest_html.txt`, both `*.artifact.md`, `.artifacts/`, `sync_release.py`, the
  root `requirements.txt`, `backend/main.py`, `backend/CYPHER.spec`,
  `backend/cypher_setup.iss`, a duplicate `.iss`, `home_screen_old.dart`,
  `central_service.dart`, and both broken Flutter widget tests.
- **Five ad-hoc backend scripts** (`test_suite.py`, `test_all_connections.py`,
  `test_critical_endpoints.py`, `test_usb_tethering.py`, `diagnose_usb.py`,
  450 lines) — Windows-only, needed a live node and a paired phone, and
  `test_suite.py` mocked away `flask.Flask` and `flask_cors.CORS` entirely so it
  asserted nothing about routing or auth.
- **`master_password`** — an unused second credential path.
- **Dead `SE_DEBUG` privilege code** in `/system/optimize`: `OpenProcessToken` was
  called with `TOKEN_ADJUST_PRIVILEGES` but `AdjustTokenPrivileges` was never
  invoked, so the escalation never happened. Removing it changes no behaviour.

### Fixed

- **Node failed to import on Python ≤ 3.11** — a backslash inside an f-string
  expression is a `SyntaxError` before PEP 701. This bricked the entire node for
  anyone not on 3.12+. CI now compiles on both versions.
- **The whole guest feature returned HTTP 500** — `guest_manager` was referenced
  as a bare name in 14 routes but only imported inside an accessor. Fixed by a
  module-level import; `ruff --select F821` is now a CI gate so this class of bug
  cannot return.
- **Clipboard images, thumbnails and window icons returned 500** — `Image` and
  `ImageGrab` were `NameError` in 8 routes for the same reason.
- **In-app preview was unreachable (401)** — `<img>`/`<video>` cannot send an
  `X-Auth-Token` header. `?token=` is now honoured on an explicit allowlist of
  five GET-only media routes (`MEDIA_TOKEN_ROUTES`), and rejected everywhere else.
- **Screen stream crashed on early connect** — `mss` and `Image` are lazily
  initialised by a background warm-up thread, so a connect in the first ~2 s hit
  `None`. Added `_load_media_engine()` and a 503 guard.
- **A security test asserted POSIX semantics on every platform** —
  `test_internal_token_is_persisted_with_restrictive_permissions` gated its
  `0o600` check on `hasattr(os, "chmod")`, but `os.chmod` *exists* on Windows,
  where it only toggles the read-only bit and leaves `st_mode` at `0o666`. The
  guard was always true, so the test failed on `windows-latest` while the product
  code behaved exactly as documented. Now keyed on `os.name`, matching the idiom
  `test_sandbox.py` already used. The underlying Windows gap is recorded as audit
  S-19 and tracked as P3-L7.
- **The mobile app did not compile.** Four analyzer *errors*, found only when the
  blocking `flutter analyze` gate ran for the first time:
  `screens/home_screen.dart` used `SliverSizedBox` in three places and that class
  has never existed anywhere in the project — confirmed against the base commit,
  where the same three call sites appear with no definition — and
  `screens/controls_screen.dart` passed a `style:` parameter that `CypherButton`
  does not accept. `HomeScreen` is routed from `main.dart`, so `flutter build apk`
  could not have succeeded. Added `widgets/sliver_sized_box.dart` and a
  `CypherButtonVariant.success` that uses the existing colour tokens. (Audit F-12)
- **Upload progress could never move.** `ApiService.uploadFile` and `uploadToDrop`
  both accepted an `onProgress` callback and never invoked it, using
  `MultipartFile.fromPath`, which exposes no byte count — while `downloadFile`
  reported progress correctly. Two callers wired up progress UI that was
  guaranteed to sit at zero. Both now stream through a counting
  `http.ByteStream`. Reported bytes are those handed to the HTTP layer rather than
  acknowledged on the wire, so the bar runs slightly ahead; that is documented at
  the call site. (Audit F-13)
- **Eleven more `flutter analyze` findings in `mobile_app`** — four further unused
  `app_theme.dart` imports, three write-only state fields, and two locals computed
  for the progress reporting above. `_loadingFolders` and `_browsingFolders` were
  assigned in four places and read in none, so folder fetches gave no feedback;
  they now drive a `LinearProgressIndicator`. `_savedPath` was dead and is removed.
  `pc_app_flutter` produced zero findings from the same gate.
- **Android release builds were blocked from the LAN** — Android 9+ rejects
  cleartext HTTP, and debug/profile builds are silently exempted by the Flutter
  tooling while release builds are not. This is the classic "works in debug, fails
  in release" trap.
- **Update checks pointed at the wrong GitHub account.**
- **Desktop shell could not reliably find its own backend** — partially addressed;
  the hardcoded `C:\Users\hp\...\python.exe` and `Directory.current.path` in
  `backend_manager.dart` remain (P1-D2).
- **`is_path_in_folders()` only honoured the first allowed folder.** `return True`
  sat inside the loop with one `try/except` around the whole body, so the first
  non-containing folder raised `ValueError` and jumped to `return False` — the loop
  never reached folders 2…N. Sharing "Documents + Pictures" with a guest silently
  shared Documents only, and every Pictures request was a bare 403.
- **`/system/optimize` requested a privilege it never enabled.** `OpenProcessToken`
  was called with `TOKEN_ADJUST_PRIVILEGES` and `SE_DEBUG = 20` was declared, but
  `AdjustTokenPrivileges` was never invoked — so the SeDebugPrivilege escalation
  never happened and protected processes were silently skipped. The dead code is
  removed; `EmptyWorkingSet` succeeds on processes the node's user owns, and the
  response now reports how many were inaccessible rather than implying success.

### Security

- **The private-network guard refused a valid link-local range.**
  `ApiService.isPermittedTarget` classified loopback and link-local by delegating
  to `InternetAddress.isLoopback` / `isLinkLocal`, and the SDK helper disagreed
  with RFC 4291: `febf::1` was refused even though `fe80::/10` spans `fe80::`
  through `febf::`. Classification is now done on the raw bytes for both address
  families, with every permitted prefix written out against its RFC. This is the
  dangerous direction to fail — refusing a legitimate link-local peer surfaces as
  "the PC will not pair", which nobody would trace to a two-bit prefix. Verified by
  reimplementing the byte logic in Python and comparing it against the `ipaddress`
  module, exhaustively across all 256 second bytes of `fe??::1`. (Audit F-11c)

Five findings in this category were discovered *by writing the tests or by
chasing a comment to the code it described*, not by reading the code top to
bottom — which is the strongest argument for P1-T1.

- **S-01b — the new per-install token was printed to stdout.** `__main__` did
  `print(f"INTERNAL BYPASS TOKEN: {INTERNAL_TOKEN}")` and
  `print(f"PAIRING KEY: {PAIRING_CODE}")`. stdout is not private here:
  `backend_manager.dart` pipes the child's stdout into the shell's log buffer, a
  Windows console shows it to anyone who can see the screen, and a service manager
  or CI job captures it to disk. Printing the *pairing code* also defeats the
  entire purpose of a six-digit code, which exists so pairing requires visual or
  physical proximity to the host — shoulder-surfing a terminal is exactly what it
  is meant to stop. Neither value needed printing. The banner is now
  `build_startup_banner()`, which prints where to find each secret instead of the
  secret. **The previous test for this passed vacuously** — it asserted the token
  was absent from `capsys` output, but pytest never runs `__main__`, so the leak
  stayed in the code while the suite reported it fixed. The replacement inspects
  the real string, guards against empty secrets, and was verified by mutation.
  Anyone who ran the node in a terminal should rotate `internal_token` by deleting
  the file and restarting.

- **S-16 — the auth hook parsed and logged request bodies before authenticating.**
  `request.json` is evaluated eagerly and raises on a non-JSON content type, so
  `POST /type` and `POST /apps/launch` returned **415** to anonymous callers
  instead of 401. Unauthenticated callers could make the node parse their body and
  write an attacker-controlled string into an activity log the desktop UI renders.
  The screenshot cooldown also ran *before* auth, so an anonymous caller could
  exhaust the rate limit and deny screen capture to the real paired device. Fixed:
  authenticate first, never touch the body in the hook, cooldown after auth,
  logging moved to a post-auth `_record_command()` bounded to 500 entries with
  `source_ip`.
- **S-17 / S-13a — revoking a guest session was a silent no-op.** `end_session()`
  set `is_active = False`; `validate_token()` only checked `is_expired()`. So
  `/guest/end` returned `{"success": true}`, the desktop Security tab dropped the
  session from its list, and the guest kept full file access until natural expiry.
  The worst possible failure shape: **the host believes a third party has been cut
  off, the UI confirms it, and they have not been.**
- **F-11b — the private-network guard the Android config relied on did not
  exist.** `network_security_config.xml` permits cleartext HTTP *globally*,
  because Android's network security config matches hostnames only and has no
  CIDR syntax to scope it to RFC1918. Its comment named `assertPrivateTarget` in
  `api_service.dart` as the compensating control — **that function did not
  exist**, so the app would send a paired token in plaintext to any host on the
  internet if the stored address were ever replaced. A documented-but-absent
  control is worse than an undocumented gap: it stops the next reader looking.
  Now implemented as `isPermittedTarget` / `assertPrivateTarget` /
  `assertPrivateUri`, enforced through `_baseUrl(ip)` — the single choke point
  for all ~60 endpoint wrappers. Policy: **cleartext only to a private host, TLS
  to anywhere**, which is why the GitHub release check keeps working. CGNAT
  (`100.64.0.0/10`) and routable hostnames are refused, the latter without
  resolving them because the DNS query would itself leak the destination. Two
  call sites bypassed `_baseUrl` and are now covered: `drop_zone_screen.dart`
  builds a guest share URL directly (that link goes to a third party carrying a
  guest token in cleartext) and `file_preview_screen.dart` fetches a URL the
  *node* returned. 39 assertions in `mobile_app/test/api_service_test.dart`.
- **S-15 (partial) — keystroke content is no longer logged.** `/type` recorded
  `f"Typed: {request.json.get('text','')[:20]}"` into a log persisted to disk and
  rendered in the Activity tab — a plaintext credential store the user never
  agreed to. It now records `"keys": <length>`: the fact and size of an injection,
  never the characters. `/apps/launch` paths and `/files/download` basenames are
  still logged verbatim (P3-S1).

### CI gate policy

Two gates are deliberately **not** blocking yet, and the reasoning is recorded
here because "make CI green" and "make CI meaningful" pull in opposite directions:

- **Coverage** is `fail_under = 35` (measured 35.73%), not the Phase 1 target of
  70. A gate that is red on every run from day one teaches contributors to ignore
  CI entirely, which is worse than no gate. It is configured as a **ratchet**: any
  PR that adds tests must raise the floor to the new measurement, no PR may lower
  it, and P1-T1 takes it to 70 permanently.
- **`dart format` and `flutter analyze --fatal-infos`** run as non-blocking
  annotations (P1-T5). Neither has ever been run over this codebase — 27 mobile
  screens and 7 desktop tabs, plus ~130 hardcoded colour literals that A-08
  already tracks. `flutter analyze --fatal-warnings` **is** blocking, because
  errors and warnings mean broken code; only *style* is deferred.

What **is** blocking: required files present, no banned telemetry dependencies,
no build output or secrets in the index, relative Markdown links resolve, ruff
clean, mypy clean on the typed modules, `compileall` on Python 3.11 *and* 3.12,
the full pytest suite, and Flutter analyze/test on both apps.

Also fixed while wiring this up: `ci.yml` contained a `run:` value written as a
plain YAML scalar with `|| { … }` in it. PyYAML reads the brace as the start of a
flow mapping and **fails to parse the file**; GitHub's parser happens to tolerate
it. Converted to a block scalar, and all four workflows are now validated as
parseable YAML.

### Known issues

Tracked in [`docs/AUDIT.md`](docs/AUDIT.md) with roadmap task IDs. The headline:

- **Exactly one critical finding remains open: S-03**, the paired-device
  filesystem sandbox (P1-S2). The correct helper `is_path_in_folders()` already
  exists and is proven by tests, but only the `/guest/*` routes call it — none of
  the `/files/*` routes a paired device uses do. The exposure is inverted from
  what you would expect: a temporary guest with a shared link is properly
  confined, while a paired device (including a lost or compromised phone) can read
  the whole filesystem, and via `/files/upload`'s absolute `destination` argument
  can **create directories and write files anywhere**. The fix is to promote the
  existing helper into `core/sandbox.py` and call it everywhere.
- **No TLS**; wildcard CORS; the node binds `0.0.0.0:5000`; no `Host` validation
  (DNS rebinding) — P1-S4 / P2-S1.
- **Mobile token stored in plaintext `SharedPreferences`** — P2-S3.
- **Windows-only node** — P3-L1…L6.
- **Test coverage is 35.73% against a Phase 1 target of 70%.** The enforced floor
  is currently 35 as a ratchet (see "CI gate policy" above); P1-T1 raises it.
  The bulk of the uncovered 1,250 statements is `server.py`, which is why
  decomposing it (P1-B4) is what makes covering it tractable.
- **Version drift** — `update_service.dart` hardcodes `currentVersion = '2.0.0'`
  while the app ships 2.1.0 — P1-B8.
- **`syncfusion_flutter_pdfviewer` is Apache-2.0-incompatible** — P1-B9.
- **Git history still contains the committed secrets and the 78 MB of build
  output** — P1-B1.
- **The Dart changes in this pass are uncompiled.** This sandbox has no
  Flutter/Dart toolchain, so `assertPrivateTarget`, the three new Dart test files
  and the `backend_manager.dart`/`update_service.dart` fixes could not be built
  or run. They are pure Dart with no new dependencies and were checked
  structurally (bracket balance, single definitions, no unresolved doc
  references), but CI's `flutter analyze --fatal-warnings` and `flutter test` are
  the real gate. Deliberately **not** attempted: adding `package_info_plus` to fix
  the version drift (A-05), because that requires regenerating `pubspec.lock`,
  which CI verifies is committed and current and which cannot be produced without
  `flutter pub get`.

---

## [2.1.0] — 2026-06-17

### Added

- **Close App from the mobile UI** — long-press any app in App Launcher, with a
  confirmation modal. Backed by a new `/apps/close` endpoint.
- **Wake-on-LAN** — `wake_on_lan_screen.dart` at route `/wol`, with saved MAC
  addresses, one-tap magic-packet broadcast, and built-in setup instructions.
- **Clipboard history sync** — last 50 items stored locally, searchable, copyable
  to phone or pasteable to PC, with timestamp and source tracking.
  `clipboard_history_screen.dart` + `clipboard_service.dart`.
- **Smart Auto-Connect** — Settings toggle; reconnects on launch if paired, skips
  the manual connection screen, and switches itself off when the network is
  unavailable.
- Confirmation modals for destructive actions: process kill, file deletion, power
  commands.

### Changed

- Removed deprecated cloud services and unused screens/widgets.
- Consistent Provider pattern throughout the mobile app.
- Haptic feedback on all actions.
- Expanded documentation: README, network audit, architecture, security model.

### Security *(claims as made at the time — see the note at the top of this file)*

- ~~Path traversal prevention on all endpoints~~ — **not true.** True only for
  `/guest/*` routes; see S-03.
- ~~Session expiry & revocation~~ — **not true.** Expiry worked; revocation was a
  no-op. Fixed in [Unreleased]; see S-17.
- ~~Guest access with folder sandboxing~~ — **partly true.** The model was sound
  and correctly implemented, but only the first folder in a multi-folder session
  was ever honoured. Fixed in [Unreleased]; see S-13b.
- System-folder write protection — a Windows-only string-prefix denylist that is
  a no-op on Linux/macOS and bypassable. Superseded by P1-S2.
- Admin process protection; input validation on endpoints. These held up.

## [2.0.0] — 2026-05

Initial working release: Python/Flask node on Windows, Flutter mobile client,
six-digit pairing, file browse/transfer/preview, screen mirroring, clipboard
sync, input injection, power and process control, mDNS discovery.

### Known limitations at the time

- Windows 10+ only for the node (no macOS/Linux backend).
- Android 10+ only (no iOS app).
- mDNS depends on router support; a subnet-broadcast fallback exists.
- Large file transfers degrade on 2.4 GHz.
- Screen recording needs ~2 GB free.

---

## Versioning

`MAJOR.MINOR.PATCH` across the node, the desktop shell and the mobile client,
released together. The single source of truth is
`pc_app_flutter/backend/metadata.json`; the Flutter apps and the installer read
from it. Consolidating the remaining hardcoded versions is **P1-B8**.

Releases are produced by `.github/workflows/release.yml` on a `v*` tag. See
[`docs/RELEASES.md`](docs/RELEASES.md).

[Unreleased]: https://github.com/Emerald-dev0/Cypher/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/Emerald-dev0/Cypher/releases/tag/v2.1.0
[2.0.0]: https://github.com/Emerald-dev0/Cypher/releases/tag/v2.0.0
