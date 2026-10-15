# Mobile UI Rebuild Plan

**Target:** `mobile_app/` · Android first, iOS in Phase 4
**Roadmap phase:** P2-M1 … P2-M11
**Estimated effort:** ~6 weeks
**Prerequisite:** Phase 1 security work (P1-S2 sandbox) — the UI must not be
rebuilt on top of an API whose file semantics are about to change.

---

## 1. Diagnosis: what is actually wrong

The mobile app has ~25 screens, ~6,700 lines of Dart, and a genuinely good
foundation: a complete design-token palette, a provider architecture, and a
reusable widget set. It reads as *ruined* for four specific, fixable reasons.

### 1.1 The design system exists but is not used

`theme/colors.dart` defines a complete dark **and** light palette with semantic
roles (`bgCard`, `textSecondary`, `borderFocus`, `successDim`, `cpu`, `ram`,
`storage`, `battery`). Then:

- **58 `Color(0x…)` literals** are scattered through `mobile_app/lib` screens
  and widgets, plus **74 more** in the desktop app.
- `app_theme.dart` exposes only `static ThemeData get dark`. There is no `light`
  getter even though the light tokens exist.
- `main.dart` hardcodes `theme: AppTheme.dark` with no `themeMode` and no
  `darkTheme`, so **the app ignores the OS appearance setting** and the entire
  light palette is dead code.
- `colors.dart` mixes `static const` and non-const `static` members
  (`accentDim`, `border`, `lightBorder` are mutable statics computed with
  `withOpacity`) — so tokens cannot be used in `const` widget constructors, which
  pushes authors toward inline literals. That is the mechanical cause of the
  drift, not carelessness.

### 1.2 Navigation does not scale

A single `_generateRoute` switch in `main.dart` with 25 `case` arms, string
route names, untyped `s.arguments as Map<String, dynamic>?` casts at every call
site, and a `default:` that silently falls back to `SplashScreen`. Consequences:

- No deep links (`cypher://pair`, `cypher://send`) — which blocks the QR pairing
  flow and the share sheet.
- Argument mismatches are runtime crashes, not compile errors.
- A global `navigatorKey` is used for cross-screen navigation, which fights
  nested navigators and makes the tablet layout (P2-M3) hard.
- `default: SplashScreen` means a typo'd route silently restarts the app.

### 1.3 No error, empty, or offline states

The app's whole job is talking to a machine that may be asleep, on another
network, or mid-transfer. Most screens have a happy path and nothing else.
`empty_state.dart` and `shimmer_box.dart` exist in `widgets/` but are used
inconsistently. There is a `disconnected_screen.dart` as a full-screen dead end
rather than a recoverable inline state.

### 1.4 Permission UX was inverted

`main()` awaited six permission dialogs **before the first frame** — storage,
all-files access, camera, precise location, photos, media library — with the
camera justified in a comment as *"for potential future features"*.
**Fixed in Phase 0** (P0-18): now `requestPermissionWhenNeeded()` at the point of
use. The remaining work is P2-M6 (drop `MANAGE_EXTERNAL_STORAGE` for SAF) and
P2-M11 (delete permissions with no shipped feature).

### 1.5 Dead and duplicated code

`home_screen_old.dart` (468 lines, zero references) — deleted in Phase 0.
`central_service.dart` (telemetry beacon, zero references) — deleted in Phase 0.
Both `home_screen.dart` (583 lines) and `master_control_screen.dart` overlap
heavily in what they offer.

---

## 2. Target architecture

### 2.1 Layering

```
lib/
├── app/
│   ├── app.dart              MaterialApp.router, theme wiring, locale
│   ├── router.dart           GoRouter config + typed route definitions
│   └── bootstrap.dart        init sequence: storage → session → discovery
├── core/
│   ├── result.dart           sealed Result<T> = Ok<T> | Err<Failure>
│   ├── failure.dart          typed failures: network, auth, timeout, sandbox, …
│   ├── logging.dart          level-filtered, REDACTING logger (P2-M10)
│   └── validators.dart       IP, path, MAC, port
├── design/                   ← thin re-export of packages/cypher_ui (P2-D2)
│   ├── theme.dart            ThemeData for light + dark, built from tokens
│   ├── tokens.dart           re-export of the shared token set
│   └── motion.dart           durations + curves, one place
├── data/
│   ├── node_client.dart      the ONLY HTTP client; owns auth header, retries,
│   │                         timeouts, error → Failure mapping
│   ├── dto/                  JSON ⇄ model, one file per resource
│   └── local/                secure storage, preferences, transfer cache
├── domain/
│   ├── model/                immutable entities: Node, Device, FileEntry,
│   │                         Transfer, GuestSession, SystemStats
│   └── repository/           interfaces only; no Flutter imports
├── state/                    providers (Riverpod) — one per feature slice
├── features/
│   ├── pairing/              screens + widgets, self-contained
│   ├── files/
│   ├── transfer/
│   ├── control/              input, media, power
│   ├── capture/              screenshot, stream, recorder
│   ├── clipboard/
│   ├── guest/
│   ├── system/               processes, apps, health
│   └── settings/
└── shared/widgets/           cross-feature primitives only
```

Rules enforced by an `import_lint` config in CI:

- `features/*` may not import another `features/*` — go through `state/` or
  `domain/`.
- `domain/` may not import Flutter.
- Only `data/node_client.dart` may import `package:http`.
- No `Color(0x…)`, no `print()`, no `EdgeInsets.all(16)` magic numbers
  (use `tokens.space`).

### 2.2 State management: Provider → Riverpod

The current `ChangeNotifier` + `Provider` setup works but has three structural
problems this rebuild needs solved:

1. `ConnectionProvider`, `FileProvider` and `SystemProvider` all fetch
   independently with their own timers, so the same endpoint is polled several
   times per second and they disagree about connection state.
2. There is no way to express "this data is stale" vs "this data is loading" vs
   "this failed" — hence the missing error states.
3. Lifecycle is hand-rolled with `WidgetsBindingObserver` in
   `connection_provider.dart`.

Riverpod's `AsyncNotifier` gives loading/error/data as a first-class state,
`ref.keepAlive()` / auto-dispose solves the polling duplication, and
`StreamProvider` maps cleanly onto the SocketIO feed the node already emits
(`system_stats`). This is a migration, not a rewrite: convert one feature slice
at a time behind the existing screens.

### 2.3 One HTTP client

`api_service.dart` (672 lines) is a bag of ~60 static methods that each rebuild
headers and re-implement timeouts (values ranging from 5s to 30s inconsistently)
and error handling. Replace with:

```dart
/// The only place that talks to a node.
class NodeClient {
  Future<Result<T>> get<T>(String path, {Map<String, String>? query, JsonCodec<T>? codec});
  Future<Result<T>> post<T>(String path, {Object? body, JsonCodec<T>? codec});
  Stream<Uint8List> download(String path, {void Function(TransferProgress)? onProgress});
  Future<Result<Unit>> upload(MultipartFile file, String destination, {…});
  Uri signedMediaUrl(String path);   // P2-S2 — no token in the query string
}
```

`Result<T>` means no screen ever needs a `try/catch`, and every failure carries a
typed `Failure` the UI can render meaningfully (`Failure.nodeUnreachable` →
"Is your PC awake and on the same WiFi?", not "Error").

---

## 3. Design system

### 3.1 Fix the tokens so they are usable

Make every token `const` by precomputing alpha variants instead of calling
`withOpacity` on a non-const field:

```dart
// BEFORE — mutable static, cannot be used in a const constructor
static Color accentDim = const Color(0xFF7C3AED).withOpacity(0.15);

// AFTER — const, tree-shakeable, usable anywhere
static const accentDim = Color(0x267C3AED);   // 0x26 ≈ 15% alpha
```

This single change is what makes the literal-free goal (P2-M2) achievable: right
now authors are *pushed* to inline colors because the tokens are not `const`.

### 3.2 Token layers

```
Primitive   violet.500 = #7C3AED        ← never referenced by a widget
Semantic    accent, surface, onSurface, border, danger   ← what widgets use
Component   cardBackground, statRingTrack, controlPressed
```

Expose via a `ThemeExtension<CypherTokens>` so a widget reads
`Theme.of(context).extension<CypherTokens>()!.accent` and light/dark falls out
for free. This is also the mechanism that makes P2-D2 (one shared package for
mobile + desktop) possible — the desktop app currently has its own
`theme_service.dart` with a second, divergent palette.

### 3.3 Type scale

Replace ad-hoc `fontSize:` values with a scale: `display`, `title`, `body`,
`label`, `caption`, `mono`. `google_fonts` is already a dependency; pin the
family and preload it so first paint does not fall back to Roboto.

### 3.4 Spacing, radius, elevation

A 4-pt spacing scale (`space.xs` 4 → `space.xxl` 32), a radius scale matching the
existing `--radius-sm/--radius/--radius-lg` from the design-system doc, and
**elevation by border + background rather than shadow** — the current aesthetic
is a dark glassmorphic surface, where Material shadows are invisible anyway.

### 3.5 Motion

One `motion.dart` with `fast` (120 ms), `normal` (260 ms — matching the existing
route transition), `slow` (400 ms) and the `Curves.easeOutCubic` already used in
`_generateRoute`. `animate_do` is a dependency; confine it to `shared/widgets` so
animation style stays consistent and it can be swapped without touching features.

### 3.6 CI enforcement

```yaml
# fails the build on a new hardcoded color, spacing literal, or print()
- name: Design-system lint
  run: |
    if grep -rnE "Color\(0x[0-9A-Fa-f]{6,8}\)" lib --include='*.dart' \
       | grep -v 'lib/design/'; then
      echo "::error::Hardcoded color outside lib/design/. Use a token."
      exit 1
    fi
```

---

## 4. Screen inventory

Legend: **Keep** · **Rework** · **Merge** · **Cut**

| Route | Screen | Lines | Decision |
| --- | --- | --- | --- |
| `/` | `splash_screen` | 130 | **Rework** — becomes a bootstrap state machine, not a timed animation |
| `/onboarding` | `onboarding_screen` | 222 | **Rework** — 3 pages: what it is, permissions *in context*, pair now |
| `/setup` | `setup_screen` | 193 | **Merge** into onboarding |
| `/connection` | `connection_screen` | 239 | **Rework** — auto-discovery list first, manual IP as a fallback affordance |
| `/pairing` | `pairing_screen` | 168 | **Rework** — QR scan + code entry as peers; deep link `cypher://pair` |
| `/home` | `home_screen` | 583 | **Rework** — the primary surface; see §5.1 |
| `/master_control` | `master_control_screen` | — | **Merge** into home's control sheet; overlaps heavily |
| `/browser` | `file_browser_screen` | 272 | **Rework** — needs the P1-S2 sandbox semantics |
| `/preview` | `file_preview_screen` | 256 | **Rework** — depends on P1-B9 (PDF viewer license) and P2-S2 (signed URLs) |
| `/send` | `send_to_pc_screen` | 386 | **Rework** — destination picker + progress inline |
| `/drop` | `drop_zone_screen` | 705 | **Rework** — largest screen; becomes the share-sheet target (P2-M4) |
| `/transfers` | `transfer_progress_screen` | 168 | **Rework** — merge with `active_tasks_screen` (288) |
| `/active_tasks` | `active_tasks_screen` | 288 | **Merge** into transfers |
| `/controls` | `controls_screen` | 293 | **Rework** — trackpad + keyboard + hotkeys; see §5.2 |
| `/recorder` | `screen_recorder_screen` | 786 | **Rework** — largest file; extract the state machine |
| `/clipboard` | `clipboard_screen` | 228 | **Keep**, restyle |
| `/clipboard-history` | `clipboard_history_screen` | 291 | **Merge** into clipboard as a tab |
| `/phone_browser` | `phone_browser_screen` | 254 | **Rework** — SAF-based (P2-M6) |
| `/processes` | `process_manager_screen` | 186 | **Keep**, restyle |
| `/apps_launcher` | `app_launcher_screen` | 182 | **Rework** — capability-scoped (P2-S5) |
| `/wol` | `wake_on_lan_screen` | 274 | **Merge** into settings → power |
| `/guest` | `guest_screen` | 336 | **Rework** — the only working guest UI; backend was broken until P0-9 |
| `/activity` | `activity_screen` | 174 | **Keep**, restyle |
| `/notifications` | `notification_screen` | 216 | **Cut** — fold into activity with a filter |
| `/settings` | `settings_screen` | 327 | **Rework** — real settings, including relay opt-in (P5-4) |
| `/disconnected` | `disconnected_screen` | 192 | **Cut** as a route — becomes an inline recoverable state (§3.3 of the audit) |
| `/guide` | `guide_screen` | 136 | **Cut** — move to docs + a contextual help sheet |

**25 routes → 16.** Net effect: less to maintain, no duplicated control surfaces,
and every remaining screen owns one job.

---

## 5. Key screens

### 5.1 Home

Current: a 2×2 grid of animated stat rings (CPU/RAM/storage/battery) plus quick
controls. The stat rings are the strongest visual idea in the app and stay.

Rebuild as three zones:

1. **Node header** — PC name, connection transport badge (WiFi / USB / hotspot /
   relay), latency, and a *tap-to-diagnose* affordance. When the node is
   unreachable this header carries the recovery UI inline; there is no
   disconnected dead end.
2. **Vitals** — the existing `StatRing` grid, driven by one `StreamProvider` over
   the SocketIO `system_stats` event the node already broadcasts every 2 s
   (instead of the current duplicated HTTP polling).
3. **Actions** — the six things people actually do: Send file, Get file,
   Screenshot, Remote view, Clipboard, Power. Everything else lives behind
   "More". Ordering is data-driven so the most-used actions surface first.

### 5.2 Controls (input)

The current `controls_screen` mixes a trackpad, a keyboard, hotkey buttons and
media controls in one scroll view. Rebuild as a bottom sheet with three tabs —
**Pointer**, **Keys**, **Media** — so the trackpad gets the full width in
landscape (P2-M3) and the keyboard can be a proper system IME overlay rather
than a text field.

Haptic feedback on trackpad edges and keypresses; this is the difference between
a toy and a usable remote.

### 5.3 Transfers

Merge `transfer_progress_screen` + `active_tasks_screen` into one list with
per-item progress, speed, ETA, cancel, and retry. Backed by the P2-M7 foreground
service so a transfer survives backgrounding, with the notification as the
progress surface.

### 5.4 Pairing

QR and manual code as equal options, not a fallback chain. Scanning a QR that
encodes `cypher://pair?host=…&fp=…` gives both the address and the certificate
fingerprint (P2-S1) — which is what makes TOFU pinning trustworthy rather than
hopeful. Camera permission requested here, on tap, never at launch.

---

## 6. Migration sequence

Each step lands independently, keeps CI green, and is shippable.

| # | Step | Tasks | Risk |
| --- | --- | --- | --- |
| 1 | `core/` scaffolding: `Result`, `Failure`, logging facade | P2-M10 | Low |
| 2 | Token constification + `ThemeExtension` + light theme wired to `themeMode` | P2-M2a | Low |
| 3 | `NodeClient` extracted from `api_service.dart`; old methods delegate to it | — | Medium |
| 4 | Delete the literal colors screen by screen (58 in mobile); CI lint turned on at 0 remaining | P2-M2b | Medium |
| 5 | `go_router` + typed routes; `onGenerateRoute` switch deleted | P2-M1 | Medium |
| 6 | Shared `packages/cypher_ui` extracted; desktop app consumes it | P2-D2 | Medium |
| 7 | Riverpod migration, one feature slice at a time (start: `system` vitals) | — | High |
| 8 | Error/empty/offline state widgets applied to every screen | P2-M5 | Low |
| 9 | Responsive: landscape + tablet breakpoints, portrait lock removed | P2-M3 | Medium |
| 10 | Share intent service (Dart side of the existing MethodChannel) | P2-M4 | Low |
| 11 | SAF phone browser; drop `MANAGE_EXTERNAL_STORAGE` | P2-M6 | High |
| 12 | Accessibility pass | P2-M8 | Medium |
| 13 | Screen merges and route deletions | — | Medium |
| 14 | AGP unlock + remove resolution-strategy pins | P2-M9 | Low |

**Do not** big-bang the Riverpod migration (step 7). Convert `system` first —
it is the most self-contained and immediately removes the duplicate polling.

---

## 7. Definition of done for the mobile rebuild

- [ ] Zero `Color(0x…)` literals outside `lib/design/`; CI lint enforces it.
- [ ] Light and dark themes both ship; `themeMode` follows the system.
- [ ] All 16 remaining screens render loading, empty, error and offline states.
- [ ] No `print()`; the logging facade redacts tokens and file paths.
- [ ] `go_router` with typed routes; `cypher://pair` and `cypher://send` work.
- [ ] Share sheet receives a file and lands on the send screen (P2-M4).
- [ ] Landscape and a 10" tablet layout are usable.
- [ ] `MANAGE_EXTERNAL_STORAGE` removed; SAF covers the phone browser.
- [ ] TalkBack navigates every primary flow; WCAG AA contrast verified.
- [ ] No permission is requested at launch; each has a shipped feature behind it.
- [ ] `flutter analyze --fatal-infos` clean; widget coverage on every feature slice.
- [ ] Cold start to interactive under 1.5 s on a mid-range Android device.
