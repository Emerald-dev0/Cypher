# AGENTS.md — Working on CYPHER

Guidance for AI coding agents (and humans) making changes in this repository.

Read this before editing anything. CYPHER is a **remote-control system**: a bug
here is not a visual glitch, it is an attacker on a coffee-shop WiFi shutting
someone's PC down or reading their files. Correctness and security review
outweigh velocity in every trade-off below.

> **Human maintainers:** this file is the agent-facing contract. The
> human-facing equivalents are [CONTRIBUTING.md](CONTRIBUTING.md) and
> [docs/](docs/). Keep them consistent when you change one.

---

## 1. What CYPHER is

Local-first remote control: a **phone** (or any client) pairs with a **PC node**
over the LAN and controls it — files, input, power, media, screen capture.

The product contract, which every change is measured against:

1. **Local-first.** All core functionality works with no internet, no account,
   and no data leaving the local network.
2. **No telemetry.** Nothing phones home. No analytics SDK, no crash reporter
   that uploads, no install beacon. Enforced by a CI gate
   (`.github/workflows/ci.yml` → `flutter` job → "Check for banned dependencies").
3. **Explicit consent.** Anything that captures the screen, injects input, or
   exposes files requires a visible, revocable authorisation on the node.
4. **Optional cloud.** The relay (`docs/plans/relay-cloud.md`) is an add-on that
   is self-hostable and off by default. It must never become a dependency of the
   LAN path.

If a change conflicts with 1–3, stop and raise it rather than implementing it.

---

## 2. Repository map

Monorepo, three shippable components plus site and docs.

```
Cypher/
├── mobile_app/            Flutter client — Android (primary), iOS (not yet shipped)
│   ├── lib/
│   │   ├── main.dart           route table (onGenerateRoute) + app bootstrap
│   │   ├── providers/          ChangeNotifier state: connection, file, system, app
│   │   ├── screens/            one file per route, ~25 screens
│   │   ├── services/           api_service (HTTP client), discovery, storage,
│   │   │                       clipboard, permission, update
│   │   ├── theme/              app_theme.dart, colors.dart  ← design tokens
│   │   └── widgets/            shared primitives (CypherCard, StatRing, ...)
│   └── android/           Gradle build, manifest, MainActivity.kt share bridge
│
├── pc_app_flutter/        Desktop shell + Python node
│   ├── lib/               Flutter for Windows/Linux — the ONLY desktop UI
│   │   ├── main.dart           StartupScreen → health-check → DashboardScreen
│   │   ├── screens/tabs/       home, files, transfers, activity, health,
│   │   │                       security, settings
│   │   ├── services/           backend_manager (spawns the node),
│   │   │                       bridge_service (loopback HTTP to the node),
│   │   │                       theme_service, update_service
│   │   └── widgets/
│   └── backend/           Python node — headless Flask + Socket.IO server
│       ├── service.py          ENTRY POINT. single-instance lock, elevation,
│       │                       firewall rule, starts server+discovery+tray
│       ├── core/
│       │   ├── server.py       ~3000 lines: all ~95 HTTP routes + auth hook
│       │   ├── guest_manager.py  guest sessions, folder sandboxing, expiry
│       │   ├── discovery.py      mDNS (zeroconf) + UDP beacon advertisement
│       │   ├── tray.py           pystray system tray icon
│       │   ├── recording_overlay.py  on-screen "RECORDING" privacy indicator
│       │   └── utils.py          paths, config, logging, OTA update check
│       ├── tests/                pytest suite (runs in CI)
│       ├── requirements.txt      runtime deps, platform-gated
│       ├── requirements-dev.txt  lint/test/package deps
│       ├── cypher_node.spec      PyInstaller spec → cypher_node binary
│       └── cypher_installer.iss  Inno Setup → Cypher-Setup-<ver>.exe
│
├── website/               Static landing page → GitHub Pages
├── docs/                  All documentation (see docs/README.md for the index)
│   ├── architecture/      overview, pairing, file-transfer, design-system
│   ├── plans/             audit, roadmap detail, rebuild plans, security
│   └── product/           positioning, feature ideas, branding
├── .github/workflows/     ci.yml, release.yml, codeql.yml, pages.yml
├── AGENTS.md              ← you are here
├── ROADMAP.md             phased plan; the source of truth for "what's next"
├── CHANGELOG.md           user-facing release history
├── LICENSE / NOTICE       Apache-2.0 + third-party attributions
└── README.md              user-facing entry point
```

### What is gone, and why

Removed during the 2026-10 audit (see [`docs/AUDIT.md`](docs/AUDIT.md)). Do not
reintroduce these:

- **The customtkinter desktop UI** (`backend/main.py`, `core/ui.py`,
  `dashboard_screen.py`, `setup_screen.py`, `splash_screen.py`,
  `pairing_screen.py`, `files_panel.py`, `guest_panel.py`). It was a second,
  parallel desktop UI competing with the Flutter shell. `service.py` — the
  actual production entry point — never used it. The Flutter shell is the only
  desktop UI now. `recording_overlay.py` was kept because it is a privacy
  feature, not chrome.
- **`CentralService`** (`mobile_app/lib/services/central_service.dart`) posted
  install analytics to a third-party Render host. Direct violation of contract
  item 2.
- **Committed secrets**: `google-services.json` (Firebase API key),
  `master_password` in `metadata.json`, the hardcoded internal token.
- **78 MB of PyInstaller output** committed under `backend/build/`.
- **~12 stale status docs** (`HACKATHON_STATUS.md`, `FINAL_STATUS.md`,
  `SYSTEM_AUDIT.md`, ...) that contradicted each other.

---

## 3. Commands

Everything runs from the repo root unless noted.

### Python node

```bash
cd pc_app_flutter/backend
python -m venv .venv && source .venv/bin/activate    # .venv/ is git-ignored
pip install -r requirements-dev.txt

ruff check .                       # lint (CI: fail)
ruff format --diff --check .       # format (CI: warn)
python -m compileall -q core       # syntax gate — see §6, Python version trap
pytest tests -q                    # tests (CI: fail)

python service.py                  # run the node (starts on 0.0.0.0:5000)
pyinstaller --clean cypher_node.spec   # build the binary
```

Node config/state lives outside the repo: `%APPDATA%\Cypher\` (Windows),
`~/.config/cypher/` (Linux), `~/Library/Application Support/Cypher/` (macOS).
Never write runtime state into the repo tree.

### Flutter clients

```bash
cd mobile_app        # or cd pc_app_flutter
flutter pub get
flutter analyze --fatal-infos      # CI fails on infos
dart format --set-exit-if-changed lib test
flutter test

flutter run                        # mobile_app: attach a device
flutter build apk --release --split-per-abi
flutter build windows --release    # pc_app_flutter, on Windows
flutter build linux --release      # pc_app_flutter, on Linux
```

### Full local verification (what CI runs)

```bash
ruff check pc_app_flutter/backend
(cd pc_app_flutter/backend && pytest tests -q)
(cd mobile_app && flutter analyze --fatal-infos && flutter test)
(cd pc_app_flutter && flutter analyze --fatal-infos && flutter test)
```

---

## 4. Invariants — do not break these

These are the rules that, if violated, produce a security incident or a broken
release. CI checks some; **you must check all of them.**

### I1 — Every route is authenticated by default

`core/server.py::verify_token_and_log` is a `@app.before_request` hook that
rejects anything not in `public_endpoints` or `MEDIA_TOKEN_ROUTES`.

- Adding a route ⇒ it is authenticated automatically. Good.
- Adding to `public_endpoints` ⇒ you have created an **unauthenticated endpoint
  on a server that can execute code**. Require a written justification in the PR
  description and a maintainer's explicit approval.
- Adding to `MEDIA_TOKEN_ROUTES` ⇒ the token may arrive in a query string. Only
  for GET-only, read-only, streaming endpoints that a media element must load
  without custom headers. This is a documented compromise retired by
  `docs/plans/security-hardening.md` · Phase S3.

### I2 — No hardcoded secrets, ever

Tokens are generated per install (`_get_internal_token()`), pairing codes come
from `secrets` (`_generate_dynamic_code()`), device tokens are
`secrets.token_hex(32)`. The Dart side reads the loopback token from disk
(`BridgeService.internalToken`).

A CI job greps for the old literal `cypher-internal-pc-app-token` and fails.
Never compare secrets with `==` — use `hmac.compare_digest`.

### I3 — File access is sandboxed to shared folders

Any route that touches the filesystem must resolve the requested path and prove
it is inside an allowlisted shared folder **before** opening it. Use
`Path.resolve()` and check containment with `is_relative_to()`; never
string-prefix match. String prefix checks are defeated by `C:\Users\..\Windows`,
by symlinks, and by case/slash differences.

Current state: `/files/browse`, `/files/download` and `/files/delete` do **not**
enforce this — that is the top item in
[`docs/plans/security-hardening.md`](docs/plans/security-hardening.md) (S1).
Do not add new filesystem routes until the shared helper lands; extend the
helper instead of hand-rolling a check.

### I4 — Nothing phones home

No analytics, no crash upload, no install beacon, no telemetry endpoint. Update
checks against `api.github.com/repos/Emerald-dev0/Cypher/releases/latest` are
permitted because they are user-initiated, version-only, and disclosed in
`docs/product/privacy.md`. CI enforces this for Dart deps; apply the same
standard to Python.

### I5 — Version stamps stay in sync

`release.yml` fails if these disagree with the tag:

| File | Field |
| --- | --- |
| `mobile_app/pubspec.yaml` | `version:` |
| `pc_app_flutter/pubspec.yaml` | `version:` |
| `pc_app_flutter/backend/metadata.json` | `app_version` |
| `pc_app_flutter/backend/cypher_installer.iss` | `AppVersion=` |

Never hardcode a version in Dart source. Read it at runtime
(`package_info_plus`) — the old `UpdateService.currentVersion = '2.0.0'` while
pubspec said `1.0.0` is exactly the drift this rule prevents.

### I6 — The node must degrade, not crash

Platform-specific capability is loaded lazily and guarded: `_load_automation()`,
`_load_media_engine()`, `_load_audio_engine()`, and the optional
`customtkinter`/Pillow imports. On Linux or a minimal install the node boots and
routes return a structured `503 {"success": false, "error": ...}` rather than
raising.

Never import a Windows-only module at module top level. Always route through a
loader and check for `None` before use.

### I7 — Apache-2.0 compatibility

Do not add a dependency whose license is not Apache-2.0-compatible without
updating `NOTICE` and getting maintainer sign-off.
`syncfusion_flutter_pdfviewer` is already flagged for removal (see NOTICE).

---

## 5. Conventions

### Python (node)

- **Ruff** is the linter and formatter. Config: `pyproject.toml`.
- Target **Python 3.11 as the floor**, 3.12 in packaged builds. CI runs both.
- Return shape is uniform: `{"success": bool, ...}` for actions,
  `{"error": str}` + an appropriate status for failures. Clients branch on
  `success`; do not invent new shapes.
- Errors returned to clients must not leak paths, tokens, or stack traces.
  `str(e)` is acceptable only when `e` is known to be user-safe (e.g. "file is
  in use"). Log the detail server-side with `log_to_ui()` / `log_event()`.
- Long work runs on a `threading.Thread(daemon=True)`. The server is
  `async_mode='threading'`; do not introduce eventlet/gevent.
- New capability goes in a new module under `core/` with an explicit accessor,
  not appended to `server.py`. That file is already too large — see §6.

### Dart (Flutter)

- **`flutter analyze --fatal-infos`** and **`dart format`** are CI gates.
- State lives in `ChangeNotifier` providers under `providers/`. Screens read
  state; they do not own networking.
- All HTTP goes through `services/api_service.dart`. It owns base-URL
  construction, the auth header, timeouts and error mapping. Do not call
  `http.get` from a widget.
- Design tokens come from `theme/colors.dart` and `theme/app_theme.dart`.
  **No `Color(0xFF...)` literals in screens or widgets.** There are still ~130
  of these to migrate — see `docs/plans/rebuild-mobile-ui.md` · P2-M2. Do not
  add more.
- No `print()`. Use `debugPrint` or the logging facade.
- Permissions are requested **at the point of use** via
  `requestPermissionWhenNeeded()` in `main.dart`, never at launch.

### Git

- Branch from `main`; name branches `type/short-description`
  (`fix/pairing-throttle`, `feat/relay-handshake`).
- Conventional Commits: `fix(node):`, `feat(mobile):`, `docs:`, `ci:`,
  `refactor(desktop):`, `chore(deps):`. Scope in parentheses = component.
- One logical change per PR. Squash-merge.
- Releases are cut by pushing a semver tag — never by hand-editing a release.

---

## 6. Known traps

Learned the hard way during the audit. Each of these broke something real.

**Python version trap.** An f-string whose expression contains a backslash is a
`SyntaxError` before Python 3.12 (PEP 701 relaxed it). One such line silently
bricked the entire node on 3.11. Compute the value on its own line first. CI
runs `compileall` on 3.11 **and** 3.12 to catch this class.

**Lazy-loader shadowing.** `guest_manager` was referenced as a bare module-level
name in 14 route handlers, but only imported *inside* `get_guest_manager()`.
Every guest route raised `NameError` → HTTP 500, and the feature was reported as
"not working" for months. When you use a lazy accessor, use it *everywhere*.
`ruff check --select F821` catches this; it is a CI gate.

**Same for Pillow.** `Image` / `ImageGrab` were used in 8 places and never
imported. The guard `if not ImageGrab` itself raised `NameError`. Ruff F821
again.

**Media elements cannot send headers.** Flutter's `Image.network`, `<video>`,
`<audio>` and the PDF viewer cannot attach `X-Auth-Token`. If you add a route
that a media element must load, either register it in `MEDIA_TOKEN_ROUTES` or
implement signed URLs (S3). Forgetting this produces a silent 401 and a blank
thumbnail.

**Cleartext on Android.** Android 9+ blocks plaintext HTTP by default. Debug and
profile builds are exempted by the Flutter tooling; **release builds are not.**
That is why things "work in debug but not in release". See
`android/app/src/main/res/xml/network_security_config.xml`. Android's config
matches hostnames only — it has **no CIDR syntax**, so you cannot scope the
exception to RFC1918 declaratively; the client enforces that instead.

**Release signing fallback.** `mobile_app/android/app/build.gradle.kts` falls
back to the debug keystore when no `key.properties` is present, so contributors
can still `flutter run --release`. `release.yml` explicitly verifies the
artefact is *not* debug-signed and fails otherwise. Do not remove either half.

**Windows-only assumptions.** `os.startfile`, `%APPDATA%`, `netsh`, UAC
elevation via `ShellExecuteW`, `pyautogui.FAILSAFE`, and the hardcoded
`C:\Users\hp\...\python.exe` in `backend_manager.dart` all break Linux and other
people's machines. When touching process spawn or paths, use the platform
helpers in `core/utils.py` and `BridgeService._appDataDir()`.

**`server.py` is 3000 lines.** Adding to it makes review harder and merge
conflicts likelier. New route groups belong in a new `core/` module registered
through a Flask `Blueprint`. The decomposition plan is
`docs/plans/security-hardening.md` · S1 and `ROADMAP.md` · P1-B4.

**Do not "fix" the AGP pin.** `com.android.application` is pinned to 8.7.2
because 8.9.x hangs the Gradle daemon on Windows. Dependabot is configured to
ignore it. Unlocking it is a tracked task (P2-M9), not a drive-by upgrade.

**Never link a document that does not exist yet.** The CI `docs` job fails on any
relative Markdown link whose target is missing, so a planned document must be
named as a code span — `` `product/troubleshooting.md` (P1-C3) `` — and only
turned into a real link in the commit that creates it. Note the relative depth:
files under `docs/product/` reach the repo root with `../../`, not `../`. Run the
checker before pushing:

```bash
git ls-files '*.md' | while read -r f; do d=$(dirname "$f")
  grep -oE '\]\(([^)]+)\)' "$f" | sed -E 's/^\]\(//; s/\)$//' \
    | grep -vE '^(https?:|mailto:|#|/)' | sed -E 's/#.*$//' | grep -v '^$' \
    | while read -r l; do [ -e "$d/$l" ] || echo "BROKEN $f -> $l"; done
done
```

It only inspects **tracked** files. A brand-new doc is invisible to it until
`git add`, which is how four broken links reached a commit in this very
repository before being caught.

**An xfail that starts passing fails the build.** That is deliberate. The ten
`strict=True` xfails in `backend/tests/test_sandbox.py` document the P1-S2
sandbox gap; when the sandbox lands they XPASS, `xfail_strict` turns that into a
failure, and you must delete the markers in the same PR. Do not "fix" this by
removing `strict` — the whole point is that a closed gap cannot be left
undocumented.

**Run a CI step locally before you commit it.** Extract the `run:` body from the
YAML and execute it verbatim:

```bash
python -c "import yaml,pathlib; d=yaml.safe_load(open('.github/workflows/ci.yml')); \
  pathlib.Path('/tmp/step.sh').write_text(next(s['run'] for s in d['jobs']['docs']['steps'] if 'run' in s))"
bash /tmp/step.sh
```

Four CI defects shipped in one pass because the configuration was written and
never executed: a `git grep` guard using a GNU-grep-only flag (it errored inside an
`if`, so it silently never ran — audit S-18); `python-engineio==4.9.5`, a version
that does not exist on PyPI (S-18b); a docs link-checker that failed **without
printing anything** because `set -euo pipefail` turned "this document has no
links" into a job failure (S-18c); and `FLUTTER_VERSION: 3.27.1` against
lockfiles requiring `flutter >= 3.38.4`, which killed both Flutter jobs before a
line of Dart was compiled (S-18d). Related: verify dependency pins exist rather
than trusting recall, and note that mypy's `ignore_missing_imports` does **not**
cover installed-but-untyped packages — those need `types-*` stubs.

**A check that passes must say what it checked.** Silent success and silent
failure are indistinguishable, and only one of them is safe. The docs job now
prints `Checked 171 relative links across 27 markdown files.`; the hygiene job
runs a canary against its own pattern. If you cannot tell from the output whether
a gate did anything, it is not a gate.

Job **logs** are served from `results-receiver.actions.githubusercontent.com`, a
different host from `api.github.com`, and may be unreachable. Job **annotations**
are reachable, and naming the failing step is usually enough to act on:

```bash
gh api repos/OWNER/REPO/actions/jobs/JOB_ID \
  --jq '.steps[] | select(.conclusion=="failure") | .name'
gh api repos/OWNER/REPO/check-runs/JOB_ID/annotations --jq '.[].message'
```

**Step summaries (`$GITHUB_STEP_SUMMARY`) are NOT readable through the API.** That
was assumed, tried, and `.output.summary` on the check-run came back empty — so
this paragraph replaces a claim in an earlier revision of this file that said they
were reachable. Do not rely on them for anything you need to debug from. Emit
diagnostics as `::error::` / `::warning::` annotations instead, which is why the
`flutter analyze` step re-emits one annotation per finding (capped at 40, with the
total reported separately) rather than writing a summary.

**Set `shell: bash` explicitly on any job whose steps use bash syntax.** Windows
runners default to PowerShell, so `|| { … }`, `tee`, `grep -q` and `[ "$x" -ne 0 ]`
fail there while passing on Linux from *identical source* — that is audit S-18e,
and it cost a CI cycle to find. The node job sets it once in `defaults.run.shell`;
do the same for any new job rather than repeating it per step.

**Start any step that inspects a failure with `set +e`.** The runner invokes
`bash -e {0}` — on Windows, `bash --noprofile --norc -e -o pipefail {0}` — so
`errexit` is already on before your first line runs. Writing `set -uo pipefail` in
order to capture `${PIPESTATUS[0]}` then makes the failing pipeline abort the
script *at that line*, and every diagnostic after it is unreachable: the step
fails while explaining nothing. That is audit S-18f, and it defeated three
successive attempts to report analyzer output. End such a step with
`exit "$status"` so it still fails.

**Prove a diagnostic fires before you trust it.** A diagnostic that has never been
observed producing output is a hypothesis, not a safety net. Extract the step body
from the YAML and run it under `bash -e`, against a synthetic failing command, in
each failure mode you intend to distinguish. For the pytest step that means two
runs: tests failing with coverage passing, and coverage failing too — because the
first version conflated them and sent the next reader to edit `fail_under` for a
problem that was not coverage.

**Distinguish failure modes by a string only the failure produces.** Grepping for
`Required test coverage` matched pytest's success line as well. Anchor on
`^FAIL Required test coverage`. The same reasoning is why the annotation emitter
deliberately does no pattern matching at all: it emits every non-empty line,
because a filter that only recognises output shaped the way its author expected is
how the analyzer findings went unreported twice.

**A permanently red gate teaches people to ignore CI.** Two gates are therefore
deliberately non-blocking and both are ratchets, not aspirations: coverage
(`fail_under = 35` against a measured 35.73, target 70 at P1-T1) and the Dart
style checks (`dart format`, `analyze --fatal-infos`, P1-T5). Raise a ratchet in
the same PR that earns it; never lower one. `flutter analyze --fatal-warnings`
*is* blocking, because errors and warnings mean broken code — only style is
deferred.

---

## 7. Testing expectations

| Layer | Tool | Where | CI gate |
| --- | --- | --- | --- |
| Node unit | pytest | `pc_app_flutter/backend/tests/` | fail |
| Node security | pytest (auth, throttle, sandbox) | `backend/tests/test_security.py` | fail |
| Mobile widgets | `flutter_test` | `mobile_app/test/` | fail |
| Desktop widgets | `flutter_test` | `pc_app_flutter/test/widget_test.dart` | fail |
| Static security | CodeQL + Semgrep | `.github/workflows/codeql.yml` | fail |
| Secrets | Gitleaks (full history) | `ci.yml` → hygiene | fail |
| Integration (real devices) | manual | `docs/plans/test-matrix.md` | release blocker |

A PR that changes an auth decision, a filesystem path check, or a network
listener **must** add or update a test in `backend/tests/test_security.py`.
No exceptions — this is the code that keeps a stranger off someone's PC.

Device-level behaviour (pairing over USB tethering, transfer throughput, screen
recording) cannot be exercised in CI. If your change touches it, say so in the
PR and note what needs manual verification.

---

## 8. Definition of done

Before marking work complete:

- [ ] `ruff check` and `ruff format --check` clean on the node.
- [ ] `python -m compileall -q core` passes on 3.11 **and** 3.12.
- [ ] `pytest tests -q` passes; new behaviour has a test.
- [ ] `flutter analyze --fatal-infos` clean in every app you touched.
- [ ] `dart format --set-exit-if-changed` clean.
- [ ] `flutter test` passes.
- [ ] No new `Color(0x...)` literal, no `print()`, no top-level Windows import.
- [ ] No new secret, no new telemetry, no new unauthenticated route.
- [ ] Filesystem-touching code uses the sandbox helper (I3).
- [ ] Version stamps updated **iff** this is a release PR (I5).
- [ ] `NOTICE` updated if a dependency was added or removed (I7).
- [ ] Docs updated: `CHANGELOG.md` for user-visible change, `docs/` for
      architecture or protocol change, `ROADMAP.md` if you completed or
      invalidated a planned item.
- [ ] PR description states what was **manually** verified, and on which OS.

---

## 9. Where to go next

| You want to… | Read |
| --- | --- |
| Understand what was broken and why | [`docs/AUDIT.md`](docs/AUDIT.md) |
| See what's planned and in what order | [`ROADMAP.md`](ROADMAP.md) |
| Rebuild the desktop UI | [`docs/plans/rebuild-desktop-ui.md`](docs/plans/rebuild-desktop-ui.md) |
| Rebuild the mobile UI | [`docs/plans/rebuild-mobile-ui.md`](docs/plans/rebuild-mobile-ui.md) |
| Touch auth, crypto or the file sandbox | [`docs/plans/security-hardening.md`](docs/plans/security-hardening.md) |
| Work on the relay / cloud tier | [`docs/plans/relay-cloud.md`](docs/plans/relay-cloud.md) |
| Add Linux or macOS support | [`docs/plans/cross-platform.md`](docs/plans/cross-platform.md) |
| Propose or scope a new feature | [`docs/product/features-and-applications.md`](docs/product/features-and-applications.md) |
| Understand the protocol | [`docs/architecture/`](docs/architecture/) |
| Cut or debug a release | [`docs/RELEASES.md`](docs/RELEASES.md) |
| Report a vulnerability | [`SECURITY.md`](SECURITY.md) |
