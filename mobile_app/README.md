# CYPHER Mobile

The Flutter client that controls a CYPHER node. Android is the shipping target;
iOS is Phase 4 of the [roadmap](../ROADMAP.md).

> **Project documentation lives in [`../docs/`](../docs/).** Start with
> [`../AGENTS.md`](../AGENTS.md) — it is the technical contract for anyone (human
> or AI agent) changing code here.

---

## What this app is

A phone-side remote control for a PC on the same network. It pairs with a node
using a six-digit code shown on the PC's screen, then talks to it over HTTP +
Socket.IO — **the same API the desktop shell uses**. There is no mobile-specific
backend.

No account, no telemetry, no cloud. The only outbound request is the
user-initiated update check against `api.github.com`.

## Layout

```
lib/
├── main.dart          bootstrap + route table (onGenerateRoute, 25 routes)
├── providers/         ChangeNotifier state: connection, file, system, app
├── screens/           one file per route
├── services/
│   ├── api_service.dart      the only HTTP client — ~60 endpoint wrappers
│   ├── discovery_service.dart  mDNS (nsd) + subnet fallback
│   ├── storage_service.dart    SharedPreferences: token, IP, device identity
│   ├── clipboard_service.dart  clipboard history
│   ├── permission_service.dart runtime permission helpers
│   └── update_service.dart     GitHub releases check
├── theme/             colors.dart (tokens) + app_theme.dart
└── widgets/           CypherCard, StatRing, ConnectionBadge, EmptyState, ...
```

`android/app/src/main/kotlin/io/github/emerald_dev0/cypher/MainActivity.kt`
implements the share-sheet bridge (`app/share` MethodChannel). **The Dart side of
that channel is not implemented yet** — see roadmap P2-M4.

## Develop

```bash
flutter pub get
flutter analyze --fatal-infos
dart format --set-exit-if-changed lib test
flutter test
flutter run                       # with a device or emulator attached
```

Release build:

```bash
cp android/key.properties.example android/key.properties   # then fill it in
flutter build apk --release --split-per-abi
flutter build appbundle --release
```

Without `android/key.properties` the build falls back to the debug keystore with
a warning — fine for development, rejected by CI for release. See
[`../docs/RELEASES.md`](../docs/RELEASES.md).

## Things that will bite you

Read [`../AGENTS.md`](../AGENTS.md) §6 for the full list. The mobile-specific ones:

- **Cleartext HTTP.** Android 9+ blocks it by default, and debug/profile builds
  are silently exempted by the Flutter tooling while **release builds are not**.
  That is the "works in debug, fails in release" trap. See
  `android/app/src/main/res/xml/network_security_config.xml`.
- **Permissions are requested at the point of use**, via
  `requestPermissionWhenNeeded()` in `main.dart`. Never add a launch-time
  permission request — it is against Play policy and it used to fire six dialogs
  before the first frame.
- **Media elements cannot set headers.** `Image.network`, `<video>` and the PDF
  viewer cannot attach `X-Auth-Token`, so preview and thumbnail URLs carry the
  token in the query string and the node accepts it only on an explicit set of
  GET routes. Signed URLs (P2-S2) retire this.
- **No `Color(0x…)` literals.** Use `theme/colors.dart`. There are still ~58 to
  migrate; do not add more (P2-M2).
- **No telemetry.** Adding an analytics, crash-upload or tracking package fails
  CI. See [`../docs/product/privacy.md`](../docs/product/privacy.md).
- **`applicationId` is `io.github.emerald_dev0.cypher` and is permanent** once a
  Play Store upload exists. Change it before publishing, never after.
- **AGP is pinned to 8.7.2** because 8.9.x hangs the Gradle daemon on Windows.
  Dependabot is configured to ignore it. Unlocking is P2-M9.

## Rebuild in progress

The UI is being rebuilt against [`../docs/plans/rebuild-mobile-ui.md`](../docs/plans/rebuild-mobile-ui.md):
25 routes → 16, Provider → Riverpod, `go_router` with typed routes, full design
token adoption, light theme, responsive layout, and real error/empty/offline
states.
