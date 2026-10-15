# CYPHER — Codebase Audit

**Date:** 2026-10-15
**Scope:** Full repository at commit `8f52695` (branch `main`), plus all changes
made during this audit pass.
**Auditor method:** Static analysis (ruff/pyflakes, AST parse on Python 3.11 and
3.12 semantics, dependency and reference graph traversal, grep-based secret and
convention scanning), build/packaging config review, and manual read of every
security-relevant code path.

> ⚠️ **Testing limitation.** This audit is static. The sandbox has no Flutter
> SDK, no Windows host, and no Android device, so nothing was executed end to
> end. Findings marked **[runtime-confirmed]** were proven by the interpreter or
> a linter; everything else is proven by code inspection and must be re-verified
> on real hardware as part of Phase 1 (`ROADMAP.md` · P1-T1).

---

## 0. Executive summary

CYPHER is a genuinely ambitious product — ~95 HTTP routes, MJPEG screen
streaming, chunked file transfer, mDNS discovery, guest sandboxing, a Flutter
mobile client with ~25 screens, and a Flutter desktop shell — built fast, for a
hackathon, and then documented as if it were finished.

The gap between the documentation and the code is the central finding.
`SYSTEM_AUDIT.md` claimed *"COMPLETE & PRODUCTION-READY"* and
`FEATURE_VERIFICATION.md` claimed *"ALL CORE FEATURES VERIFIED ✅"*. In fact:

- **The backend did not parse** on Python 3.11 or below — a single f-string
  killed the entire node on any machine without exactly 3.12. **[runtime-confirmed]**
- **The whole guest-access feature returned HTTP 500** on every request, from a
  `NameError` on an unimported module referenced in 14 places. **[runtime-confirmed via ruff F821]**
- **Clipboard image capture and every thumbnail returned HTTP 500**, from Pillow
  being used in 8 places and never imported. **[runtime-confirmed via ruff F821]**
- **In-app file preview was unreachable**, because the mobile client sends the
  token in a query string and the auth hook only accepted a header.
- **A hardcoded authentication token was published to GitHub**, granting full
  remote control of every installed node to anyone who read the repo.
- **Release builds were signed with the debug keystore.**
- **The app sent install analytics to a third-party server**, while the README's
  headline promise was *"No cloud. No data tracking."*
- **78 MB of PyInstaller binary output was committed**, with no `.gitignore`
  anywhere in the repository.
- **There was no LICENSE file**, so the project was not open source at all —
  default copyright, all rights reserved.

None of this is unusual for a hackathon prototype. It is disqualifying for a
public security-sensitive release. The good news: the architecture underneath is
sound and worth keeping. The Flask node, the mDNS discovery, the Flutter
provider structure, and the design-token work are all reasonable foundations.
This is a **hardening and consolidation** problem, not a rewrite-from-scratch
problem — with one exception, the desktop UI, where two parallel
implementations must be collapsed into one.

### Severity counts

Counts below were recomputed mechanically from the finding headings after the
test-writing pass, because that pass added four findings (S-16, S-17, and the
three S-13 sub-bugs) and corrected one (S-03).

| Severity | Count | Definition |
| --- | --- | --- |
| 🔴 Critical | 13 | Blocks public release; security exposure or total feature failure |
| 🟠 High | 13 | Breaks a shipped feature, a platform, or the release pipeline |
| 🟡 Medium | 11 | Correctness, maintainability or professionalism defects |
| 🔵 Low | 1 | Hygiene, polish, documentation drift |
| **Total** | **38** | |

### Status after this pass

| | Found | Fixed | Partially fixed | Deferred to roadmap |
| --- | --- | --- | --- | --- |
| 🔴 Critical | 13 | **11** | 1 | 1 |
| 🟠 High | 13 | **4** | 2 | 7 |
| 🟡 Medium | 11 | **4** | 2 | 5 |
| 🔵 Low | 1 | **1** | 0 | 0 |
| **Total** | **38** | **20** | **5** | **13** |

**Exactly one critical finding remains open: S-03, the paired-device filesystem
sandbox (P1-S2).** Everything else critical is fixed or partially fixed. That is
the single highest-value change left in the project, and §3 of
[`security-hardening.md`](plans/security-hardening.md) explains why it is now a
much smaller change than it first appeared — the correct helper already exists
and just needs to be promoted and applied.

Deferred items are not ignored — every one has a numbered task in
[`ROADMAP.md`](../ROADMAP.md) and a cross-reference below.

### What the test suite found that this audit had missed

Writing `backend/tests/` was the single most productive step in this pass. It
found four defects that reading the code did not:

| Finding | Discovered by | Why review missed it |
| --- | --- | --- |
| **S-16** auth hook parsed bodies before authenticating | `test_anonymous_non_json_body_gets_401_not_415` | The hook *looked* correct — auth logic was present, just ordered after the body access |
| **S-13a** guest revocation was a no-op | `test_revocation_actually_revokes_access` | `end_session()` and `get_all_active_sessions()` both handled `is_active` correctly; only `validate_token()` forgot it, so the UI looked right |
| **S-13b** only the first allowed folder worked | `test_REGRESSION_every_folder_in_a_multi_folder_list_is_honoured` | `return True` inside a `for` loop reads as correct at a glance |
| **S-03 correction** guests *were* properly sandboxed | `TestExistingHelperIsCorrect`, `TestGuestRoutesAreSandboxed` | Review confirmed the *paired* routes were unsafe and generalised that to all filesystem access |

This is the argument for P1-T1. None of these would have been caught by review
alone, and each is now pinned by a regression test that fails if it comes back.

---

## 1. Security

CYPHER's threat model is brutal and should be stated plainly: **the node is an
unauthenticated-code-execution service listening on `0.0.0.0:5000` on a network
the user does not control.** Coffee shops, hotels, universities and conference
WiFi are the primary deployment environments. Every finding below should be read
against that.

### 🔴 S-01 — Hardcoded authentication token published to GitHub · **FIXED**

`INTERNAL_TOKEN = "cypher-internal-pc-app-token-2024"` in
`backend/core/server.py`, duplicated verbatim as `BridgeService.internalToken`
in `pc_app_flutter/lib/services/bridge_service.dart`.

This token bypassed **all** authorisation, on every route, for every install. It
was committed to a public repository. Any attacker who read the repo and could
reach port 5000 obtained: arbitrary file read/write/delete, keystroke injection,
process kill, app launch, and machine shutdown.

The auth hook honoured it before any other check:

```python
if incoming_token == INTERNAL_TOKEN:
    return None          # ← unconditional bypass
```

**Fix applied.** The node now generates a 48-byte `secrets.token_urlsafe` per
install, persists it to `<appData>/Cypher/internal_token` with mode `0600`, and
the Dart shell reads it from that path (`BridgeService._readInternalToken()`).
An empty token fails closed — every bridge call gets a 401 — which is the safe
degradation. CI greps for the old literal and fails the build if it returns.

**S-01b — the per-install token was then printed to stdout. · FIXED.** Making the
token per-install did not stop it leaking, because `server.py`'s `__main__` block
printed it:

```python
print(f"PAIRING KEY: {PAIRING_CODE}")
print(f"INTERNAL BYPASS TOKEN: {INTERNAL_TOKEN}")
```

stdout is not private in this architecture. `backend_manager.dart` pipes the child
process's stdout into the Flutter shell's log buffer; a Windows console window
shows it to anyone who can see the screen; a service manager or CI job captures it
to disk. A 48-byte token in a `0600` file is worthless if the same process then
echoes it somewhere world-readable.

Printing the **pairing code** is worse in one specific way: it defeats the entire
purpose of a six-digit code, which exists so that pairing requires *visual or
physical* proximity to the host. Shoulder-surfing a terminal is exactly the attack
the code is meant to stop.

Neither value needed printing — the shell reads the token from disk, and the
pairing code is rendered on the host's own screen by the desktop UI.

**Fix:** the banner is now `build_startup_banner(local_ip) -> str`, printing the
IP, the port, and *where to find* each secret rather than the secret. Extracting
it into a function is the point: the previous test asserted
`INTERNAL_TOKEN not in capsys.readouterr().out`, which passed **vacuously**
because pytest never executes `__main__` — the leak stayed in the code while the
suite reported it fixed. `test_the_startup_banner_contains_no_secrets` now
inspects the real string, includes a guard-the-guard assertion that neither secret
is empty, and was verified by mutation: re-injecting the two `print` lines makes
it fail.

⚠️ **Residual risk:** the literal remains in git history. Anyone who installed a
build from before this commit still has a guessable token until they upgrade.
`ROADMAP.md` · P1-S1 covers the history purge and the forced-upgrade notice.
Anyone who ran the node in a terminal or captured its stdout should rotate
`internal_token` by deleting the file and restarting.

### 🔴 S-02 — No brute-force protection on pairing · **FIXED**

`/pair_device` compared a 6-digit code (10⁶ keyspace) with no rate limit, no
lockout, and no attempt tracking. Over a LAN with parallel requests that is
minutes of work, not hours.

Compounding it: the code came from `random.randint`, whose Mersenne Twister state
is recoverable from a few observed outputs. `secrets` was imported in the same
file and unused.

**Fix applied.** `_pairing_throttle()` — 5 attempts per 5-minute window per
source IP, then a 15-minute lockout, tracked under a lock; the throttle runs
*before* the comparison so a correct guess from a locked-out address is still
refused; `hmac.compare_digest` for constant-time comparison; the code rotates on
every successful pairing so it is single-use; `secrets.randbelow` replaces
`random`. Blocked attempts are logged to the activity feed as urgent security
events.

### 🔴 S-03 — Paired-device filesystem access is not sandboxed · **DEFERRED → P1-S2** *(finding corrected)*

> **Correction, 2026-10-15.** The first draft of this audit reported "the
> filesystem is not sandboxed". Writing tests proved that half-wrong, and the
> distinction materially changes the fix — so it is recorded here rather than
> quietly edited.
>
> `is_path_in_folders()` **already exists and is correct**: `Path.resolve()` then
> `relative_to()`, which canonicalises `..`, follows symlinks and normalises
> separators. It is used consistently by **every `/guest/*` route**.
>
> It is used by **none** of the `/files/*` routes a paired device calls.
>
> So the exposure is inverted from what you would expect: a *temporary guest*
> holding a shared link is properly confined, while a *paired device* — including
> a lost or compromised phone — can read and write the whole filesystem.
>
> **Consequence for P1-S2:** the task is not "write a sandbox". It is "promote
> the correct helper into `core/sandbox.py` and call it from the paired-device
> routes too" — a much smaller and safer change. `tests/test_sandbox.py` proves
> the helper is sound (`TestExistingHelperIsCorrect`) and pins the gap with
> `strict=True` xfails that will fail the build until they are removed.

The advertised model is "shared folders" — the user picks which directories the
phone may see. The paired-device routes do not implement it.

- `/files/browse` takes `?path=` and calls `Path(path_str).iterdir()` with **no
  allowlist check at all**. Any paired device can enumerate the entire
  filesystem, including `Path.home()`.
- `/files/download`, `/files/download/chunked` and `/files/preview` read any path.
- `/files/upload` is worse than a read: it accepts an **absolute** `destination`,
  calls `os.makedirs(dest, exist_ok=True)` on it, and writes there — so a paired
  device can create directories and write files anywhere on the filesystem.
- `/files/delete` guards with a hardcoded Windows-only prefix list
  (`c:\windows`, `c:\program files`, …) applied to a lowercased *string*.

Three independent problems with that guard:

1. **It is a no-op on Linux and macOS** — no path starts with `c:\`.
2. **String prefix matching is bypassable.** `C:\Windows` is blocked;
   `C:\Users\..\Windows` and `c:/windows` (forward slashes) are not. Nothing
   calls `resolve()`.
3. **It is a denylist.** A denylist protects six directories and leaves
   `~/.ssh`, browser profile stores, password-manager vaults,
   `~/.aws/credentials` and every document on the machine wide open. The correct
   design is an allowlist of user-selected shared folders — which already exists
   for guests.

`/files/download/zip` has the same denylist inline, duplicated.

**Required fix** (P1-S2): promote `is_path_in_folders` into `core/sandbox.py` as
`Sandbox.resolve(path, need=…)`, apply it to every `/files/*` route, replace the
denylist entirely, and add the route-coverage test that asserts no filesystem
route can bypass it. `tests/test_sandbox.py` already contains the payload suite
(traversal, symlink, alternate separators, absolute upload destination).

### 🔴 S-04 — Unauthenticated-by-default is inverted for new routes · **PARTIALLY FIXED**

The `before_request` hook is a genuine global gate, which is the right shape.
But `public_endpoints` is a list of **function names**, and the comment above it
reads `# Audit Fix: Ensure these match the actual function names used in @app.route`
— evidence that a rename had already silently turned a protected route into a
public one, or vice versa. Name-based allowlists rot exactly like that.

**Fix applied:** the media-token path was scoped to an explicit route set
(`MEDIA_TOKEN_ROUTES`) rather than a path-prefix test.
**Deferred:** converting `public_endpoints` to decorator-based opt-in
(`@public_route`) so that adding a route cannot accidentally expose it — P1-S3.

### 🔴 S-05 — Debug-keystore release builds · **FIXED**

```kotlin
buildTypes { release { signingConfig = signingConfigs.getByName("debug") } }
```

Every "release" APK was signed with the public Android debug key — which is
identical on every developer machine on earth. Such a build cannot be uploaded
to the Play Store, cannot be updated by a properly signed build, and offers no
integrity guarantee to a user who sideloads it.

**Fix applied.** `build.gradle.kts` reads `android/key.properties` or
`ANDROID_SIGNING_*` env vars, warns loudly and falls back to debug *only* for
local development, and `release.yml` runs `apksigner verify` and **fails the
release** if the certificate says "Android Debug". Template committed at
`android/key.properties.example`; `.gitignore` excludes the real file.

### 🔴 S-06 — Committed credentials · **FIXED**

- `mobile_app/android/app/google-services.json` — live Firebase project
  `cypher-e7712`, project number `1096840086806`, and an embedded API key.
  **The key should be rotated**, not merely deleted: it is in git history.
- `pc_app_flutter/backend/metadata.json` — `"master_password": "emerald-admin"`.
  Unused by any code path, but a real credential published under a name that
  implies it unlocks something.

**Fix applied.** Both removed; `.gitignore` and a CI hygiene gate now block
`google-services.json`, `GoogleService-Info.plist`, `*.jks`, `*.keystore`,
`key.properties`, `.env`. Gitleaks runs against **full git history** in CI.

### 🟠 S-07 — Wildcard CORS on a code-execution service · **DEFERRED → P1-S4**

```python
CORS(app)                                             # allows every origin
socketio = SocketIO(app, cors_allowed_origins="*")
```

Combined with `Host` header not being validated, this is a **DNS rebinding**
surface: a malicious website the user visits can resolve `attacker.com` to
`127.0.0.1`, and the browser will then send same-origin-looking requests
straight to the local node. The token requirement blunts full compromise, but
simple requests (GET/POST with form encoding) can still be *sent* without
preflight, and any endpoint added to `public_endpoints` becomes drive-by
reachable from any website on the internet.

**Required fix:** restrict CORS to the loopback origin and the node's own
served origins; validate `Host` against an allowlist
(`127.0.0.1`, `localhost`, the node's own LAN IPs); reject requests whose `Host`
is a public hostname.

### 🟠 S-08 — All transport is cleartext · **DEFERRED → P2-S1**

HTTP on port 5000 for everything: pairing codes, auth tokens, clipboard content
(which routinely holds passwords), file bodies, and screen frames. Any passive
sniffer on the LAN captures the token in the first request and then owns the
node permanently — the token has no expiry.

This is the single largest architectural gap. Mitigations, in order:

1. TLS with a per-pairing self-signed node certificate, fingerprint shown to
   the user at pairing time (TOFU + pinning).
2. Short-lived derived session tokens instead of one permanent bearer token.
3. Noise Protocol (`Noise_XX_25519_ChaChaPoly_BLAKE2s`) for mutual
   authentication and forward secrecy, which also gives an authenticated channel
   that works through the relay unchanged.

Full design in [`security-hardening.md`](plans/security-hardening.md) · Phase S2/S3.

### 🟠 S-09 — Auth token in query strings · **PARTIALLY FIXED**

`api_service.dart` builds preview and thumbnail URLs as
`/files/preview?path=…&token=$token`. Query strings are logged by proxies, kept
in browser history, and leak through `Referer`.

The mobile code did this because `Image.network` cannot set headers — a real
constraint. But the node's auth hook **only** accepted `request.args["token"]`
for `/guest/` paths, so these requests were rejected with 401 anyway: the
compromise bought a leak and no functionality. Preview and thumbnails were
broken (see F-03).

**Fix applied:** the hook now accepts a query-string token for an explicit set of
GET-only streaming endpoints, so preview actually works, and the set is named and
documented rather than incidental.
**Deferred:** short-lived signed URLs (expiry + scope + HMAC), which remove the
token from the query string entirely — P2-S2.

### 🟠 S-10 — Tokens stored in plaintext, no local authentication · **DEFERRED → P2-S3**

`StorageService` keeps the paired auth token in `SharedPreferences`
(world-readable XML on rooted devices, backed up to Google Drive by default).
The node keeps device tokens in `paired_devices.json` with no filesystem
permissions set. Neither client has any local unlock — opening the app is
sufficient to control the PC.

**Required fix:** `flutter_secure_storage` (Keystore/Keychain) for the mobile
token; `0600` on `paired_devices.json`; an optional biometric/PIN gate on the
mobile app; and the backup exclusion now added to the manifest
(`data_extraction_rules.xml`) — that one **is** done, see F-07.

### 🟠 S-11 — Node elevates to Administrator by default · **DEFERRED → P2-S4**

`service.py::main()` calls `elevate()` — a UAC prompt via `ShellExecuteW` with
`runas` — whenever the `CYPHER_BRIDGE` firewall rule is missing. So the default
install path runs a network-exposed code-execution service **as Administrator**,
then opens inbound TCP 5000/5001 and UDP 5001/5002 for all profiles.

Every vulnerability above then yields a SYSTEM-level compromise rather than a
user-level one. Least privilege is not optional for this product category.

**Required fix:** run unprivileged by default; add the firewall rule scoped to
**private profiles only**, during install (where elevation is expected and
visible), not at every service start; make elevation opt-in for the specific
features that need it (hibernate, some process control) and degrade gracefully
otherwise.

### 🟡 S-12 — `/apps/launch` is arbitrary program execution · **DEFERRED → P2-S5**

```python
os.startfile(request.json.get("path"))
```

Any paired device can run any executable by absolute path, with no allowlist and
no confirmation on the node. Paired devices are meant to be trusted, but a
paired phone that is lost or compromised becomes an RCE client — and per S-01/S-02
pairing was not as hard to obtain as assumed.

**Required fix:** launch by resolved app identity from the enumerated app list,
not by raw path; an on-node confirmation for first launch of an unseen target;
and a per-device capability scope so a device paired for "files + media" cannot
invoke power or process control at all.

### 🟡 S-13 — Guest sandbox enforcement · **CORRECTED — model sound, three real bugs found and fixed**

`GuestSession` has a proper design — `secrets.token_urlsafe(32)`, expiry,
per-session `allowed_folders`, access logging, a cleanup thread, a lock — **and,
contrary to this audit's first draft, its path checks are also correct**: every
`/guest/files/*` route calls `is_path_in_folders()`, which uses `Path.resolve()`
+ `relative_to()`. Guests were properly confined even while paired devices were
not (see the corrected S-03).

Writing `tests/test_guest_manager.py` and `tests/test_sandbox.py` then found
three real defects in that otherwise-good implementation.

**S-13a — revoking a guest session did not revoke it. · FIXED.** `end_session()`
set `session.is_active = False`, but `validate_token()` only checked
`is_expired()`. So `/guest/end` returned `{"success": true}`, the desktop
Security tab dropped the session from its list (`get_all_active_sessions` *does*
filter on `is_active`), and the guest kept full file access until natural expiry
— potentially hours.

That is the worst possible failure shape: **the host believes a third party has
been cut off, the UI confirms it, and they have not been.** Regression test:
`test_revocation_actually_revokes_access`, plus three companions asserting a
revoked session cannot be extended back to life, cannot log access, and
disappears from the active list.

**S-13b — only the first folder in a multi-folder guest session worked. ·
FIXED.** In `is_path_in_folders`, `return True` sat *inside* the loop with a
single `try/except` around the whole body. The first folder that did not contain
the path raised `ValueError`, jumping straight to `return False` — so the loop
never reached folders 2…N. A host sharing "Documents + Pictures" with a guest
silently shared Documents only, and every Pictures request returned a bare 403
with no explanation. Regression test:
`test_REGRESSION_every_folder_in_a_multi_folder_list_is_honoured`.

**S-13c — the guest access log was unbounded in memory. · FIXED.** `to_dict()`
sliced `access_log[-5:]` for serialisation, but the underlying list grew forever.
A guest requesting files in a loop could grow node memory for the lifetime of the
session. Now capped at `GuestSession.MAX_LOG_ENTRIES` while `access_count` still
records the true total.

Remaining guest work (denylist replacement, rate limiting, no sibling-name
leakage, persistent on-node indicator) is folded into P1-S2 and P2-S5.


### 🟡 S-14 — No token expiry or revocation on node restart · **DEFERRED → P2-S6**

`paired_devices.json` is loaded at startup and every token in it is added to
`valid_tokens` forever. There is no expiry, no rotation, no last-seen tracking,
and `/paired-devices` returns **the raw tokens** of every paired device to any
authenticated caller — so a single compromised device can harvest the tokens of
all the others and impersonate them.

**Fix applied (partial):** `paired_at`, `last_seen` and `source_ip` are now
recorded at pairing time.
**Deferred:** token expiry + rotation, and stripping tokens from the
`/paired-devices` response — P2-S6.

### 🟡 S-15 — Activity log records typed text and file paths · **PARTIALLY FIXED → P3-S1**

```python
if request.path == '/type':
    log_entry["details"] = f"Typed: {request.json.get('text', '')[:20]}"
```

Keystroke content — which will include passwords — is written into an in-memory
log that `/history` and the desktop Activity tab render. `log_event()` persists
to disk. This is a plaintext credential store the user never agreed to.

**Fixed this pass:** `/type` no longer logs content. It records
`"keys": <len(request.json.get('text', ''))>` — the *fact* and *size* of an
injection, never the characters. The log-entry construction was also moved out of
the `before_request` hook into a post-auth `_record_command()` helper (S-16), so
an unauthenticated caller cannot make the node parse and log their body at all.
`tests/test_security.py::test_keystroke_content_is_not_logged` pins this, and
`test_keystroke_logging_records_length_not_content` asserts the length is still
recorded so the activity feed stays useful.

**Still open (P3-S1):** `/apps/launch` logs the full target path (which leaks
directory structure and usernames) and `/files/download` logs full basenames.
Both need the same field-class redaction, applied by a shared helper rather than
per-route.

### 🔴 S-16 — The auth hook parsed and logged request bodies *before* authenticating · **FIXED**

Found while writing the first tests — `POST /type` and `POST /apps/launch`
returned **415 Unsupported Media Type** to an anonymous caller instead of 401.
The cause was worse than a wrong status code:

```python
@app.before_request
def verify_token_and_log():
    ...
    log_entry = { "timestamp": ..., "endpoint": ..., "details": ... }
    if request.path == '/type':
        log_entry["details"] = f"Typed: {request.json.get('text','')[:20]}"  # ← parses body
    ...
    if not has_valid_token:                       # ← auth happened *after*
        return jsonify({...}), 401
```

`request.json` is evaluated eagerly and raises on a non-JSON content type, so the
hook aborted before the auth check ran. Three consequences:

1. **Unauthenticated callers could make the node parse their request body** and
   write an entry to the activity log — attacker-controlled strings entering a
   log the desktop UI renders.
2. **The wrong error was returned.** A legitimate client sending an empty or
   form-encoded body got 415 where the handler expected JSON, which is a
   confusing client-side failure mode.
3. **The screenshot cooldown ran before auth**, so an unauthenticated caller
   hitting `/system/screenshot` could exhaust the rate limit and deny screen
   capture to the real paired device — a trivial denial of service.

**Fix:** the hook now authenticates first and never touches the body. Public
endpoints and the media-token allowlist are module-level `frozenset`s
(`PUBLIC_ENDPOINTS`, `MEDIA_TOKEN_ROUTES`) so `tests/test_security.py` can assert
the exact set and fail if a name drifts. Logging moved to `_record_command()`,
called after a token is confirmed, with the entry list bounded to 500 and
`source_ip` attached. Regression tests: `test_anonymous_non_json_body_gets_401_not_415`
(parametrised over the sensitive routes), `test_screenshot_cooldown_does_not_run_before_auth`.

### 🟡 S-17 — Guest session revocation was a silent no-op · **FIXED**

See **S-13a** for the full analysis. Recorded here as well because it is a
security finding, not merely a functional one: the host UI confirmed a third
party had been cut off while they retained file access until natural expiry.
`validate_token()` now checks `is_active`, and four regression tests pin it.

---

## 2. Broken functionality

### 🔴 F-01 — Node fails to import on Python ≤ 3.11 · **FIXED** · **[runtime-confirmed]**

```
File "core/server.py", line 1355
    "name": f"Local Disk ({drive_name.strip('\\')})",
SyntaxError: f-string expression part cannot include a backslash
```

PEP 701 (Python 3.12) permits backslashes in f-string expressions; earlier
versions reject them at **parse** time. A single cosmetic label therefore made
`import core.server` fail outright, taking down every route, on any machine
without exactly Python 3.12. `README.md` said "Python 3.12" but nothing enforced
it, and every Linux distribution ships 3.11 or older.

**Fix applied:** the strip is computed on its own line. CI now runs
`compileall` on 3.11 **and** 3.12 in a matrix, so this class of bug cannot
recur silently.

### 🔴 F-02 — Entire guest feature returned HTTP 500 · **FIXED** · **[runtime-confirmed via ruff F821]**

`guest_manager` is used as a bare name in 14 route handlers and in the
`before_request` auth hook:

```
482, 1966, 1992, 2548, 2591, 2605, 2628, 2642, 2653, 2665, 2683, 2694,
2713, 2726, 2737, 2746, 2773
```

It was only ever imported *inside* `get_guest_manager()`. Every one of those
sites raised `NameError` → 500. Creating a guest link, browsing guest files,
downloading, uploading, extending and ending a session were all dead.

This is precisely what `MORE_CRITICAL_ISSUES.md` reported as
*"Security/Generate Link — Not working"* — a real diagnosis that was never
traced to its cause, because the module was never statically analysed.

Note the auth hook was affected too: any request to a `/guest/` path with a
token hit `guest_manager.validate_token(...)` and crashed, so guest access failed
**closed** (500, not bypass) — bad UX, but not a vulnerability.

**Fix applied:** module-level `from .guest_manager import guest_manager`. The
module only pulls in `secrets`/`threading`/`datetime`, so there is no startup
cost; the lazy accessor is retained for the call sites that use it. `ruff
--select F821` is now a CI gate.

### 🔴 F-03 — Clipboard images, thumbnails and window icons returned 500 · **FIXED** · **[runtime-confirmed via ruff F821]**

Pillow's `Image` and `ImageGrab` were referenced in 8 places and never imported:

| Site | Feature |
| --- | --- |
| `paste_from_phone` | Image clipboard phone → PC |
| `get_pc_clipboard` | Read PC clipboard (text **and** image) |
| `get_window_icon` | Window icons in the active-windows list |
| `get_file_thumbnail` | Image thumbnails in the file browser |
| `guest_file_preview` / thumbnail | Guest file preview |

The failure mode was especially perverse: the guard written to protect against a
missing Pillow (`if not WINDOWS or not ImageGrab:`) was itself the line that
raised `NameError`. **PC clipboard sync — an advertised headline feature — was
completely non-functional.**

**Fix applied:** tolerant module-level import (`Image = None`, `ImageGrab = None`
on failure) so the node still boots headless without Pillow and routes degrade to
a structured `503`. Verified: `ruff check --select F821` → *All checks passed*.

### 🔴 F-04 — In-app preview unreachable (401) · **FIXED**

`api_service.dart` sends preview/thumbnail requests with the token in the query
string because `Image.network` and the video/PDF viewers cannot set headers. The
auth hook only honoured a query token on `/guest/` paths. Result: **401 on every
image thumbnail, every in-app preview, every video and PDF.**

**Fix applied:** `MEDIA_TOKEN_ROUTES` — an explicit, documented set of GET-only
streaming endpoints that accept a query-string token. Retired by signed URLs in
P2-S2.

### 🔴 F-05 — Screen stream crashed on early connect · **FIXED**

`stream_screen()` used the lazily-loaded `mss` global without calling
`_load_media_engine()`, relying on the background `warm_up_engines()` thread
having finished its 2-second sleep. A client opening Remote View during node
startup hit `mss is None` → `AttributeError` raised **outside** the inner
`try/except`, killing the stream with nothing surfaced to the user.

**Fix applied:** synchronous `_load_media_engine()` plus an explicit
`503 {"success": false, "error": "…capture dependencies missing"}` when the
dependency is genuinely absent. This is the I6 pattern applied correctly.

### 🟠 F-06 — Share sheet dead on arrival · **DEFERRED → P2-M4**

`MainActivity.kt` fully implements the share bridge: `ACTION_SEND` and
`ACTION_SEND_MULTIPLE` intent filters, URI extraction, a `app/share`
MethodChannel with both `getSharedFiles` and a push-style `onSharedFiles`.

**Nothing on the Dart side references it.** `grep -rn "app/share\|getSharedFiles\|onSharedFiles\|MethodChannel" mobile_app/lib` returns zero matches. So "Share → CYPHER" appears in the Android share sheet, launches the app, and silently discards the file.

**Required fix:** a `ShareIntentService` that registers the channel handler,
buffers pending URIs across cold start, resolves `content://` URIs through the
platform resolver, and routes into the existing `SendToPCScreen`.

### 🟠 F-07 — Node dependencies missing from requirements.txt · **FIXED**

`backend/requirements.txt` omitted four modules the code imports:

| Module | Imported by | Effect of absence |
| --- | --- | --- |
| `pystray` | `core/tray.py` | Node crashes at startup |
| `mss` | `_load_media_engine()` | Screen streaming/recording dead |
| `numpy` | `_load_media_engine()` | Screen streaming/recording dead |
| `opencv-python` | `_load_media_engine()` | Screen streaming/recording dead |

They were only listed in the **root** `requirements.txt`, which was a stale
second file also carrying `pymongo[srv]` and `dnspython` — MongoDB drivers for a
cloud backend that does not exist in this repository. A contributor following
`README.md` got a node that would not start.

Conversely `eventlet`, `gunicorn` and `python-dotenv` were declared and never
imported anywhere (the server runs SocketIO in `threading` mode).

**Fix applied:** one authoritative, platform-gated `requirements.txt`
(Windows-only packages behind `; sys_platform == 'win32'`, so
`pip install -r requirements.txt` now works on Linux), a separate
`requirements-dev.txt`, and the stale root file deleted. Each removal and
addition is documented inline.

### 🟠 F-08 — Desktop shell cannot find its own backend · **DEFERRED → P1-D2**

`BackendManager.start()`:

```dart
final projectRoot = Directory.current.path;          // ← cwd, not the install dir
final backendDir = p.join(projectRoot, 'backend');
...
final List<String> pythonCommands = [
  r'C:\Users\hp\AppData\Local\Programs\Python\Python312\python.exe',  // ← one developer's machine
  'python', 'python3', 'py', 'python.exe'
];
```

Two defects. `Directory.current.path` is the *working directory*, which for a
double-clicked Windows shortcut is arbitrary — so the packaged app looks for
`backend/` in the wrong place. And the first Python candidate is an absolute path
into a specific user profile (`hp`) that exists on exactly one computer.

Also `BridgeService._appDataDir()` logic assumed `%APPDATA%` unconditionally,
with no Linux or macOS branch.

**Fix applied (partial):** `BridgeService` now resolves the app-data directory
per platform (Windows / macOS / XDG on Linux).
**Deferred:** `BackendManager` must resolve the node relative to
`Platform.resolvedExecutable`, not the cwd — P1-D2.

### 🟠 F-09 — Update checks pointed at the wrong GitHub account · **FIXED**

`mobile_app/lib/services/update_service.dart`,
`pc_app_flutter/lib/services/update_service.dart` and `backend/core/utils.py`
all referenced `Oluwadaredaniel/Cypher`; the actual repository is
`Emerald-dev0/Cypher`. Every user's "check for updates" queried a repo that does
not exist, so **no user would ever be told about the security fixes in this
audit**. `utils.py` also fetched `pc_app/metadata.json`, a path that has not
existed since the directory was renamed.

**Fix applied:** all references corrected to `Emerald-dev0/Cypher` and the
metadata path fixed.

### 🟠 F-10 — Install analytics sent to a third-party host · **FIXED**

`CentralService` posted to `https://cypher-3ctq.onrender.com/api/analytics/install`
on first run, and fetched a broadcast plus remote metadata from the same host.
`sync_metadata.py` did the same at build time.

This directly contradicts the README's headline — *"No cloud. No subscriptions.
No data tracking."* — and would have been a false statement on the Play Store
Data Safety form, which is a rejection and potentially a suspension risk.

Mitigating factor: `CentralService` had **zero references** anywhere in the Dart
code, so it was dead code that never actually fired. It was still committed,
still shipped in the binary, and one import away from being live.

**Fix applied:** `central_service.dart` and `sync_metadata.py` deleted; CI now
fails any PR adding a `firebase|analytics|sentry|mixpanel|amplitude|segment|posthog|onesignal|facebook`
dependency to either Flutter app. Firebase Analytics was also wired into the
Gradle build (`firebase-bom:33.1.1` + `firebase-analytics` + the
`com.google.gms.google-services` plugin) — all removed.

### 🟠 F-11 — Android release builds blocked from the LAN · **FIXED**

Android 9 (API 28)+ prohibits cleartext HTTP by default. The app's entire
purpose is HTTP to `192.168.x.x:5000`. There was no `networkSecurityConfig` and
no `usesCleartextTraffic` attribute. The Flutter tooling exempts debug and
profile builds automatically — **release builds get no exemption.** This is the
mechanism behind "works on my phone in debug, fails for everyone else."

**Fix applied:** `res/xml/network_security_config.xml` added and referenced from
the manifest. Note the documented limitation: Android matches hostnames only and
has **no CIDR syntax**, so the cleartext exception cannot be scoped to RFC1918
declaratively. The config comments say so explicitly and point at the client-side
`assertPrivateTarget` guard (P2-S1) and the TLS migration (Phase S2).

---

## 3. Architecture and maintainability

### 🔴 A-01 — Two complete desktop UIs, one of them dead · **FIXED**

The repository contained **two** full desktop front-ends:

1. **customtkinter** (Python) — `core/ui.py`, `dashboard_screen.py` (847 lines),
   `setup_screen.py`, `splash_screen.py`, `pairing_screen.py`, `files_panel.py`,
   `guest_panel.py` — roughly 2,400 lines.
2. **Flutter for Windows** — `pc_app_flutter/lib/`, ~2,400 lines across a
   7-tab dashboard.

Only the Flutter one is live. `BackendManager` spawns **`service.py`**, which
starts the server, discovery and tray and then loops — it never touches
customtkinter. `main.py` (the customtkinter entry point) was reachable only via
`CYPHER.spec`, and the packaged binary is built from `cypher_node.spec`, which
targets `service.py`.

So ~2,400 lines of parallel UI, a second PyInstaller spec, and a second icon
pipeline existed purely as maintenance drag and reviewer confusion — and any
feature added "to the desktop app" had a 50% chance of being added to the dead
one.

**Fix applied:** deleted `backend/main.py`, `CYPHER.spec`, and all seven dead
`core/` UI modules. **Kept** `recording_overlay.py` — it is the on-screen
"RECORDING" privacy indicator, a consent feature rather than chrome, and it is
live via `get_overlay_manager()`. It was rewritten to degrade to a no-op when
customtkinter is absent (headless Linux) and to expose `.available` so the UI can
warn the user.

### 🟠 A-02 — `server.py` is a 3,000-line god module · **DEFERRED → P1-B4**

~95 routes, the auth hook, the resource monitor, the recording state machine,
file transfer, guest sessions, and ~550 lines of embedded HTML/CSS/JS — all in
one file. Consequences observed during this audit: the `guest_manager` import
bug (F-02) survived because nobody could hold the file in their head; the
`public_endpoints` name list drifted (S-04); the guest landing page exists in
duplicate as `guest_html.txt`, a 29 KB copy-paste of the route body.

**Required fix:** Flask `Blueprint`s per domain (`files`, `system`, `guest`,
`media`, `recording`, `pairing`), the guest HTML extracted to a real template,
and a `sandbox` module owning all path resolution. Target: no file over ~500
lines.

### 🟠 A-03 — No test suite that CI could run · **PARTIALLY FIXED**

What existed: `test_suite.py`, `test_all_connections.py`,
`test_critical_endpoints.py`, `test_usb_tethering.py`, `diagnose_usb.py` —
ad-hoc scripts, several requiring a live Windows node and a paired phone, and
`test_suite.py` mocking away `flask.Flask` and `flask_cors.CORS` entirely, which
means it tested nothing about routing or auth.

Both Flutter apps had exactly one test, and **both were broken**:

- Desktop: the unmodified `flutter create` counter test, asserting
  `find.text('0')` against an app that has no counter.
- Mobile: a splash smoke test asserting `find.text('C')` and `find.text('Y')` as
  separate widgets — the splash renders `'CYPHER'` as **one** `Text`, so both
  assertions failed. It also awaited 1.8 s of `Future.delayed`, which makes
  `pumpAndSettle` time out.

Neither had ever passed. `flutter test` was red in both projects, or was simply
never run.

**Fix applied:**

- A real `pytest` suite under `backend/tests/` — **121 tests**: `test_security.py`
  (51), `test_guest_manager.py` (27), `test_sandbox.py` (43, of which 10 are
  `strict=True` xfails documenting P1-S2). `conftest.py` stubs the Windows-only
  modules (`pyautogui`, `win32*`, `pycaw`, `customtkinter`, `pystray`, …) and
  redirects `%APPDATA%`/`$HOME` into a tmpdir, so the node imports and its auth
  layer is fully testable on Linux CI without touching a developer's real config.
- `pc_app_flutter/test/widget_test.dart` **deleted** and replaced by
  `bridge_service_test.dart` (loopback-only URL, no hardcoded token, fail-closed
  behaviour) and `theme_service_test.dart`. Neither pumps `CypherPC`, because
  `StartupScreen.initState` spawns the real Python node — testing that needs a
  fake `BackendManager` (P1-T2).
- `mobile_app/test/widget_test.dart` replaced by `StorageService` tests, which
  cover the component that holds the paired-device token. Uses
  `SharedPreferences.setMockInitialValues({})` for isolation.
- The five ad-hoc backend scripts (`test_suite.py`, `test_all_connections.py`,
  `test_critical_endpoints.py`, `test_usb_tethering.py`, `diagnose_usb.py`,
  450 lines) **deleted**. They required a live Windows node and a paired phone,
  and `test_suite.py` mocked away `flask.Flask` and `flask_cors.CORS` entirely —
  it asserted nothing about routing or auth. They are recoverable from history if
  a USB-tethering diagnostic is wanted later (P2-M10).
- `ruff check pc_app_flutter/backend` now reports **zero** findings, down from
  58. Notable: all four `shell=True` `netsh` calls in `service.py` were replaced
  with argument lists and a `shutil.which()`-resolved executable; **eight bare
  `except:` clauses** were narrowed and logged — they ran in daemon threads, so
  they were also swallowing `KeyboardInterrupt` and `SystemExit` during shutdown;
  and the dead `SE_DEBUG` constant revealed that `OpenProcessToken` was called
  with `TOKEN_ADJUST_PRIVILEGES` but `AdjustTokenPrivileges` was never invoked,
  so the SeDebugPrivilege "escalation" in `/system/optimize` never happened.

Coverage gates (`fail_under = 70`) and integration tests are P1-T1/P1-T2 — the
gate is currently **not** met and CI will fail on it until the sandbox and the
route-level tests land.

### 🟡 A-04 — No `.gitignore` anywhere · **FIXED**

The repository root had no `.gitignore` at all (the sub-projects had Flutter's
defaults). Result: 78 MB `.git`, of which **69 MB was a single PyInstaller
`cypher_node.pkg`**, plus 8.8 MB `PYZ-00.pyz`, a 45,637-line `xref-*.html`,
`mobile_app/android/build/`, and the entire `.idea/` directory.

Every clone paid that cost forever — including CI, on every run.

**Fix applied:** comprehensive root `.gitignore` (Python, Flutter, Android,
iOS/macOS, native desktop build, IDEs, AI scratch space, secrets, logs) plus a CI
hygiene job that fails if any of these patterns reappear in `git ls-files`.
⚠️ The blobs are still in history; the purge is P1-B1 (`git filter-repo`), which
must be coordinated with all contributors because it rewrites SHAs.

### 🟡 A-05 — Version drift across five files · **PARTIALLY FIXED**

| Location | Claimed version |
| --- | --- |
| `mobile_app/pubspec.yaml` | `1.0.0` |
| `pc_app_flutter/pubspec.yaml` | `1.0.0` |
| `backend/metadata.json` | `1.0.0` |
| `cypher_installer.iss` | `1.0.0` |
| **`mobile_app/.../update_service.dart`** | **`2.0.0`** |
| **`central_service.dart`** | **`1.0.0`** |

The mobile app told users it was version 2.0.0 while every artefact said 1.0.0 —
so the update check compared `2.0.0` against GitHub tags and would **never**
offer an upgrade until 3.0.0 shipped. The tool meant to fix drift
(`sync_release.py`) was itself broken: it pointed at `pc_app/metadata.json` and
`pc_app/cypher_installer.iss`, paths that stopped existing when the directory was
renamed, and it silently no-ops on missing files.

**Fix applied:** `sync_release.py` deleted (CI does this now); `release.yml` has
a preflight job that extracts all four stamps and **fails the release** if any
disagrees with the tag.
**Deferred:** single source of truth — generate the stamps from one file, and
read the runtime version from `package_info_plus` rather than a Dart constant —
P1-B8.

### 🟡 A-06 — Placeholder application identity · **FIXED**

`applicationId = "com.example.mobile_app"` — the literal `flutter create` default.
Not publishable to the Play Store (the `com.example.*` namespace is reserved and
rejected), unprofessional, and permanently binding: changing an `applicationId`
after a Play upload breaks update continuity for every existing install.

**Fix applied:** `io.github.emerald_dev0.cypher`, with `namespace` matched,
`MainActivity.kt` moved to the corresponding package directory
(`kotlin/io/github/emerald_dev0/cypher/`), and a `.debug` `applicationIdSuffix`
so debug and release builds coexist on one device.
⚠️ **Decision needed:** if the project acquires a real domain, change this
*before* the first Play Store upload, not after.

### 🟡 A-07 — Light theme implemented but unreachable · **DEFERRED → P2-M2**

`theme/colors.dart` defines a complete light palette (`lightBgPrimary`,
`lightTextPrimary`, `lightBorder`, …). `app_theme.dart` exposes only
`static ThemeData get dark`. `main.dart` hardcodes `theme: AppTheme.dark` with no
`themeMode` or `darkTheme`. So the light tokens are dead weight, and the mobile
app ignores the OS appearance setting — unlike the desktop app, which does have a
working `ThemeService`.

### 🟡 A-08 — ~130 hardcoded color literals · **DEFERRED → P2-M2**

58 `Color(0x…)` literals in `mobile_app/lib` screens/widgets and 74 in
`pc_app_flutter/lib`, despite a complete token system existing in
`theme/colors.dart`. This is the concrete mechanism by which "the UI was ruined":
tokens drift from usage, dark/light can't be maintained, and contrast is
unauditable.

### 🟡 A-09 — Launch-time permission blast · **FIXED**

`main()` awaited six permission dialogs before the first frame:
`storage`, `manageExternalStorage`, `camera`, `locationWhenInUse`, `photos`,
`mediaLibrary`. The camera was justified in a comment as *"for potential future
features"* and precise location had no stated justification at all.

This is against Google Play policy (permissions must be requested in context,
with the requesting feature visible), guarantees a first-run wall of dialogs
before the user sees any UI, and `manageExternalStorage` in particular triggers
a Data Safety review that is frequently rejected.

**Fix applied:** replaced with `requestPermissionWhenNeeded(Permission)`, called
from the screen that needs it, with a permanent-denial path to `openAppSettings()`.
Manifest scoped with `maxSdkVersion` where appropriate, `NEARBY_WIFI_DEVICES`
(API 33+) added so mDNS discovery works **without** location on modern Android,
`location` capped at `maxSdkVersion=32`, camera marked
`android:required="false"`, and `MANAGE_EXTERNAL_STORAGE` retained with an inline
TODO pointing at the SAF migration (P2-M6).

### 🔵 A-10 — Miscellaneous hygiene · **FIXED**

- `mobile_app/lib/screens/home_screen_old.dart` — 468 lines, zero references.
- `backend/core/ui.py`, `core/pairing_screen.py`, `core/files_panel.py` — zero
  references even before the A-01 cleanup (`ui.py` also had broken relative
  imports: `from splash_screen import SplashScreen`).
- `backend/cypher_setup.iss` — a duplicate installer script with a **malformed
  `AppId`**: `{{C9PHER-BC12-4E8F-A9D1-789456123456}` is not a valid GUID, and it
  targeted `{autopf}` (Program Files, needs admin) while the other script used
  `{localappdata}`. Deleted; `cypher_installer.iss` kept.
- Installer `AppSupportURL` and `AppUpdatesURL` pointed at
  `https://tiktok.com/@emerald_dev1`. Repointed at the GitHub issues and
  releases pages.
- Both Flutter `README.md` files were the unmodified `flutter create` boilerplate
  ("A new Flutter project."). Replaced.
- `.idea/` committed, including `studiobot.xml`, `deviceManager.xml` and an
  88 KB `caches/deviceStreaming.xml`.
- 10 `*.artifact.md` AI scratch files across three `.artifacts/` directories.
- `print()` used in Dart instead of `debugPrint` (3 sites, in the deleted
  permission code).
- `bare except:` / `except: pass` used ~40 times in the node, swallowing errors
  that made F-02 and F-03 invisible for months.

---

## 4. Documentation

**Finding: 17 markdown files at the repo root, 12 of them point-in-time status
reports that contradicted each other.**

The most damaging pattern was confident false assurance:

| Document | Claim | Reality |
| --- | --- | --- |
| `SYSTEM_AUDIT.md` | "COMPLETE & PRODUCTION-READY" | Node did not parse on ≤3.11 (F-01) |
| `FEATURE_VERIFICATION.md` | "ALL CORE FEATURES VERIFIED ✅" | Guest feature 100% broken (F-02); clipboard 100% broken (F-03) |
| `FINAL_STATUS.md` | "ALL SYSTEMS GO!" | 9 critical defects open |
| `CRITICAL_BUGS_FOUND.md` | `/lock` endpoint missing | `/power/lock` exists — the doc was wrong about the bug |
| `README.md` | "No data tracking" | Firebase Analytics + install beacon (F-10) |
| `RELEASE_NOTES.md` | Documents v1.0.0 as shipped | No release had ever been cut |

`FEATURE_VERIFICATION.md` is worth dwelling on: it asserts, screen by screen,
that clipboard sync and screenshot features are "WORKING", citing line numbers.
The line numbers were real and the code paths were described accurately — but
two of them 500'd on an unimported module. **A document that records reading the
code is not verification.** That distinction is now encoded in the PR template
("what did you *run*, on what OS?") and in `AGENTS.md` §7.

### Actions taken

**Deleted (12):** `CRITICAL_BUGS_FOUND.md`, `DOCUMENTATION_INDEX.md`,
`FEATURE_VERIFICATION.md`, `FILE_TRANSFER_FIX_PLAN.md`, `FINAL_STATUS.md`,
`FUNCTIONALITY_AUDIT.md`, `HACKATHON_STATUS.md`, `MORE_CRITICAL_ISSUES.md`,
`SYSTEM_AUDIT.md`, `TEST_ALL_CONNECTIONS.md`,
`PERMISSIONS_CONFIGURATION.md`, `guest_html.txt`.

**Relocated into `docs/` (4):** `Architecture.md` → `docs/architecture/overview.md`;
`Pairing Specification.md` → `docs/architecture/pairing.md`;
`File transfer protocol.md` → `docs/architecture/file-transfer.md`;
`UI Design System.md` → `docs/architecture/design-system.md`.

**Renamed:** `RELEASE_NOTES.md` → `CHANGELOG.md` (Keep a Changelog format).
**Moved:** `index.html` → `website/index.html` (deployed by `pages.yml`).

**Created:** `docs/AUDIT.md` (this file), `ROADMAP.md`, `AGENTS.md`,
`docs/plans/{rebuild-desktop-ui,rebuild-mobile-ui,security-hardening,relay-cloud,cross-platform}.md`,
`docs/product/{features-and-applications,positioning,privacy,branding}.md`,
`docs/RELEASES.md`, `docs/README.md`, `SECURITY.md`, `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md`, `LICENSE`, `NOTICE`.

**Documentation rule going forward:** exactly one status document exists —
`ROADMAP.md`. Status reports are not committed; a closed issue is the record.
`AGENTS.md` §8 requires docs updates as part of the definition of done.

---

## 5. Cross-platform readiness

Assessed against the stated targets: mobile, Windows, Linux, and an optional
cloud tier.

| Target | State | Blockers |
| --- | --- | --- |
| **Android** | 🟡 Builds, ships | Debug signing (fixed), cleartext (fixed), placeholder id (fixed), dead share sheet (F-06), `MANAGE_EXTERNAL_STORAGE` (A-09), portrait-locked, no tablets |
| **iOS** | 🔴 Not shippable | `ios/` scaffold exists and nothing else: no local-network permission strings (`NSLocalNetworkUsageDescription`), no Bonjour services in `Info.plist`, untested, no signing pipeline. Also mDNS behaves differently on iOS. |
| **Windows** | 🟢 Primary platform | Works; but admin-by-default (S-11), no code signing, `Directory.current` bug (F-08) |
| **Linux** | 🔴 Does not run | See below |
| **macOS** | 🔴 Not attempted | `entitlements` lack local-network access; no platform code for input/capture |
| **Cloud relay** | 🔴 Does not exist | Only the (now-deleted) Render analytics host. Full design in `docs/plans/relay-cloud.md` |

### Linux blockers, concretely

- **`requirements.txt` failed to install** — pyautogui/pycaw/pywin32 have no
  Linux wheels (fixed by platform markers, F-07).
- **`os.startfile`** — Windows-only; `/apps/launch` returns 400 by design.
- **`win32gui`/`win32api`/`win32con`/`win32ui`** — window enumeration, focus,
  and icon extraction are all `if not WINDOWS: return`.
- **`pycaw`** — volume control is Windows-only.
- **`psutil.disk_usage('/')`** — hardcoded root; correct on Linux, wrong shape
  for Windows drives.
- **`netsh advfirewall`** — firewall configuration is Windows-only; Linux needs
  `firewalld`/`ufw`/`nftables` handling or documentation.
- **UAC elevation via `ShellExecuteW`** — no Linux analogue; needs a pkexec
  path or (better) no elevation at all per S-11.
- **`%APPDATA%`** — path resolution (fixed in Dart; `core/utils.py` already had
  an `~/.cypher` branch, but it disagrees with the Dart side's
  `~/.config/cypher` — **must be unified**).
- **Screen capture** — `mss` works on X11; on **Wayland** it does not, and Wayland
  is the default on Ubuntu 24.04 and Fedora. Needs PipeWire/xdg-desktop-portal
  ScreenShot. This is the hardest Linux problem and is scoped in
  `docs/plans/cross-platform.md` · L3.
- **Input injection** — `pyautogui` needs X11; Wayland requires
  `libei`/`ydotool`/uinput.
- **`customtkinter`** — needs a Tk stack; now optional (A-01 fix).
- **Flutter Linux desktop** — the `linux/` scaffold exists and builds, but the
  app has never been run there.

**Verdict:** Linux is a genuine port, not a config change. Estimated at
Phase 3 in `ROADMAP.md`, sequenced after security hardening — shipping a second
platform with the S-03 sandbox gap would double the exposure.

---

## 6. What is worth keeping

An audit that only lists defects is not useful for planning. These parts are
sound and should be preserved through the rebuild:

- **`GuestSession` model** — `secrets.token_urlsafe(32)`, expiry, per-session
  folder allowlist, access logging with a bounded tail, a cleanup thread, a lock.
  Correct design; only its path checks inherit S-03.
- **`CypherDiscovery`** — mDNS via zeroconf with a UDP beacon fallback,
  interface prioritisation (USB tethering → hotspot → LAN), exclusion of APIPA
  and loopback. Thoughtful about the real-world networks this runs on.
- **Design tokens** — `theme/colors.dart` is a complete, well-named dark+light
  palette with semantic roles. The problem is adoption (A-08), not the design.
- **Lazy capability loading** — `_load_automation()` / `_load_media_engine()` /
  `_load_audio_engine()` keep cold start fast and let the node boot without
  optional dependencies. The right pattern; applied inconsistently (F-05).
- **`before_request` global auth** — authenticated-by-default is the correct
  default, and the hook shape is right even though the allowlist mechanism is
  fragile (S-04).
- **Chunked transfer design** — `docs/architecture/file-transfer.md` describes
  resume and progress tracking; the protocol is reasonable for 100 GB+ files.
- **Provider architecture** on mobile — clean separation of connection/file/system
  state from screens.
- **Backend/shell process separation** — Flutter shell spawning a headless
  Python node over loopback is a legitimate architecture, and `service.py`
  already implements it correctly (single-instance mutex, health check, log
  piping). It just needs the path fix (F-08) and a Linux equivalent.

---

## 7. Audit → roadmap traceability

Every deferred finding maps to a numbered task in [`ROADMAP.md`](../ROADMAP.md).

| Finding | Task | Phase |
| --- | --- | --- |
| S-03 filesystem sandbox | P1-S2 | 1 |
| S-04 name-based public allowlist | P1-S3 | 1 |
| S-01 history purge + forced upgrade | P1-S1 | 1 |
| A-02 server.py decomposition | P1-B4 | 1 |
| A-03 test suite | P1-T1, P1-T2 | 1 |
| A-04 git history purge | P1-B1 | 1 |
| A-05 version single source | P1-B8 | 1 |
| F-08 backend path resolution | P1-D2 | 1 |
| S-07 CORS + DNS rebinding | P1-S4 | 1 |
| S-08 TLS transport | P2-S1 | 2 |
| S-09 signed URLs | P2-S2 | 2 |
| S-10 secure token storage | P2-S3 | 2 |
| S-11 least privilege | P2-S4 | 2 |
| S-12 app-launch allowlist + scopes | P2-S5 | 2 |
| S-14 token expiry/rotation | P2-S6 | 2 |
| F-06 share sheet | P2-M4 | 2 |
| A-07 / A-08 theming | P2-M2 | 2 |
| A-09 SAF migration | P2-M6 | 2 |
| AGP unlock | P2-M9 | 2 |
| S-15 log redaction (keystrokes done; paths pending) | P3-S1 | 3 |
| Linux port | P3-L1…L6 | 3 |

Fixed this pass and therefore absent from the table above: **S-16** (auth hook
parsed bodies before authenticating) and **S-17 / S-13a–c** (guest revocation
no-op, multi-folder allowlist bug, unbounded access log). Each has a regression
test in `backend/tests/`, so a reintroduction fails the build rather than
reappearing in a future audit.
| iOS / macOS | P4 | 4 |
| Cloud relay | P5 | 5 |

---

## 8. Method notes

Tools and checks used, so this audit can be repeated:

```bash
# Parse gate across supported interpreters
python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('pc_app_flutter/backend/**/*.py',recursive=True)]"

# Undefined names — found F-02 and F-03
ruff check --select F821 pc_app_flutter/backend/

# Unused imports, redefinitions, unused locals
ruff check --select F,E9 --statistics pc_app_flutter/backend/

# Repository bloat
git ls-files -z | xargs -0 du -h | sort -rh | head -20

# Secret scan
git grep -nI 'cypher-internal-pc-app-token\|master_password\|api_key'

# Reference graph — found A-01 and A-10 dead modules
grep -rn "^\s*\(from\|import\)\s" --include=*.py pc_app_flutter/backend

# Design-token drift — found A-08
grep -rn "Color(0x" --include=*.dart mobile_app/lib pc_app_flutter/lib | wc -l

# Dependency declaration vs. usage — found F-07
for m in pystray cv2 numpy mss; do
  echo "$m imports=$(grep -rl "import $m" --include=*.py . | wc -l) declared=$(grep -ci $m requirements.txt)"
done
```

`ruff` is pinned in `requirements-dev.txt` and wired into CI so the first three
checks run on every PR. The remaining checks are encoded as CI jobs
(`hygiene`, `docs`, `android-build`).
