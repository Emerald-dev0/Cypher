# CYPHER Desktop

The Flutter desktop shell (Windows, and Linux from roadmap Phase 3) plus the
Python **node** it supervises.

> **Project documentation lives in [`../docs/`](../docs/).** Start with
> [`../AGENTS.md`](../AGENTS.md).

---

## Two things live here

### `lib/` — the shell

A Flutter app that spawns the node as a child process, health-checks it, and
talks to it over `http://127.0.0.1:5000`. It is the **only** desktop UI — an
older customtkinter UI was deleted during the 2026-10 audit
([`../docs/AUDIT.md`](../docs/AUDIT.md) A-01) because `service.py`, the real
entry point, never used it.

```
lib/
├── main.dart                  CypherPC → StartupScreen → health check → DashboardScreen
├── screens/dashboard_screen.dart   7-tab dashboard
├── screens/tabs/              home, files, transfers, activity, health, security, settings
├── services/
│   ├── backend_manager.dart   locates, spawns, pipes and supervises the node
│   ├── bridge_service.dart    loopback HTTP client + the per-install token
│   ├── theme_service.dart     light/dark
│   └── update_service.dart    GitHub releases check
└── widgets/glass_container.dart
```

### `backend/` — the node

A headless Python service doing the actual OS work: files, input injection,
screen capture, audio, power, processes, mDNS discovery, guest sessions.

```
backend/
├── service.py                 ENTRY POINT — single-instance mutex, elevation,
│                              firewall rule, then server + discovery + tray
├── core/
│   ├── server.py              ~3,000 lines: ~95 HTTP routes + the auth hook
│   ├── guest_manager.py       guest sessions, folder scoping, expiry
│   ├── discovery.py           mDNS (zeroconf) + UDP beacon
│   ├── tray.py                pystray tray icon
│   ├── recording_overlay.py   on-screen "RECORDING" privacy indicator
│   └── utils.py               paths, config, logging, OTA update check
├── tests/                     pytest — runs in CI on Linux and Windows
├── requirements.txt           runtime deps, platform-gated
├── requirements-dev.txt       ruff, pytest, mypy, pyinstaller
├── cypher_node.spec           PyInstaller → cypher_node binary
└── cypher_installer.iss       Inno Setup → Cypher-Setup-<ver>.exe
```

The node exposes **the same API the mobile app uses**. One protocol, two clients.

## Develop

```bash
# Node
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
ruff check .
python -m compileall -q core        # must pass on 3.11 AND 3.12
pytest tests -q
python service.py                   # listens on 0.0.0.0:5000

# Shell
cd ..
flutter pub get
flutter analyze --fatal-infos
flutter test
flutter run -d windows              # or -d linux
```

Runtime state lives **outside** the repo: `%APPDATA%\Cypher\` (Windows),
`~/.config/cypher/` (Linux — being unified, roadmap P3-L6),
`~/Library/Application Support/Cypher/` (macOS).

## Things that will bite you

Full list in [`../AGENTS.md`](../AGENTS.md) §6. The node-specific ones:

- **Python 3.11 must parse.** A backslash inside an f-string expression is a
  `SyntaxError` below 3.12 (PEP 701). One such line bricked the entire node.
  CI compiles on both versions.
- **Lazy loaders must be used everywhere.** `guest_manager` was referenced as a
  bare name in 14 routes but only imported inside an accessor — every guest
  request 500'd. `ruff check --select F821` is a CI gate for exactly this.
- **Never import a Windows-only module at top level.** Route it through
  `_load_automation()` / `_load_media_engine()` / `_load_audio_engine()` and check
  for `None`. The node must degrade, not crash (AGENTS.md §4 I6).
- **`server.py` is too big.** New route groups go in a new `core/` module as a
  Flask Blueprint (P1-B4), not appended here.
- **Every route is authenticated by default.** Adding to `PUBLIC_ENDPOINTS`
  creates an unauthenticated endpoint on a code-execution server and needs
  explicit maintainer approval. `tests/test_security.py` fails if the set drifts.
- **Filesystem access must go through the sandbox.** Today only the `/guest/*`
  routes do, via `is_path_in_folders()`; the `/files/*` routes do not, which is
  the top-priority open finding (P1-S2). Do not add new file routes until the
  helper is promoted into `core/sandbox.py`.
- **Do not reintroduce the customtkinter UI.** It was deleted deliberately.
  `recording_overlay.py` was kept because it is a privacy feature, not chrome.

## Rebuild in progress

[`../docs/plans/rebuild-desktop-ui.md`](../docs/plans/rebuild-desktop-ui.md):
a real process supervisor, capability-driven UI, seven tabs collapsed into six
purposeful regions, a persistent pairing surface, a security console, a shared
design-system package with the mobile app, and the Linux port.
