# Security Hardening Plan

**Scope:** node backend, both clients, the relay
**Roadmap phases:** P1-S1…S5, P2-S1…S9, P3-S1
**Prerequisite reading:** [`docs/AUDIT.md`](../AUDIT.md) §1

---

## 0. Read this first

CYPHER is a **remote code execution service that the user installs on purpose**.
It reads and writes arbitrary files, injects keystrokes, kills processes,
captures the screen, and shuts the machine down — and it listens on
`0.0.0.0:5000`.

That is the product. The security work is not about removing capability; it is
about making sure that **only the person who paired a device can use it, that
they can see when it is being used, and that they can take it away.**

The deployment environment is hostile by default: hotel WiFi, coffee shops,
university networks, conference halls, and shared home networks where the router
admin password is `admin`. Assume the LAN is attacker-controlled. Assume the
phone gets lost. Assume the PC gets stolen.

Every design decision below follows from one rule:

> **A compromised peer device must not become a compromised PC, and a
> compromised PC must not silently become a compromised peer.**

---

## 1. Threat model

### 1.1 Assets

| Asset | Why it matters |
| --- | --- |
| Files on the node | Documents, credentials, `~/.ssh`, browser profiles, password vaults, source code |
| Keystrokes and clipboard | Passwords, 2FA codes, private messages — the clipboard is a credential channel |
| Screen content | Everything above, plus whatever is currently displayed |
| Node control | Power, processes, installed apps — a foothold for persistent compromise |
| Pairing credentials | The token *is* the account; stealing it is total compromise |
| Guest session | Deliberately exposes files to a **third party** — the least-trusted actor in the system |
| Availability | A node that can be shut down by a stranger is a denial-of-service vector against the user's work |

### 1.2 Actors

| Actor | Capability | Motive |
| --- | --- | --- |
| **A1 LAN attacker** | On the same WiFi/hotspot; can sniff, ARP-spoof, scan, and reach port 5000 | Opportunistic theft, ransomware, botnet recruitment |
| **A2 Remote web attacker** | Runs a website the user visits; can attempt DNS rebinding against `127.0.0.1:5000` | Drive-by control of local services |
| **A3 Lost/stolen phone** | Physical access to a paired client, possibly unlocked | Full node control with today's design |
| **A4 Malicious guest** | Holds a legitimately issued guest link | Exceed the folder scope, extend the session, enumerate the host |
| **A5 Compromised node** | Code execution on the PC | Steal every paired device's token; pivot to phones |
| **A6 Relay operator** | Runs the cloud relay (including a hostile one) | Read or modify traffic between node and client |
| **A7 Supply chain** | A malicious dependency or CI runner | Backdoor into every install |

### 1.3 STRIDE summary

| Threat | Vector | Current state | Target | Task |
| --- | --- | --- | --- | --- |
| **Spoofing** | Guess the 6-digit pairing code | 🔴 No throttle, non-crypto RNG | 🟢 Throttled, `secrets`, single-use, constant-time compare | **P0-7 ✅** |
| **Spoofing** | Use the published internal token | 🔴 Hardcoded, public | 🟢 Per-install, 0600, read from disk | **P0-6 ✅** |
| **Spoofing** | Impersonate a node (MITM on LAN) | 🔴 No authentication of the node at all | 🟢 TLS + fingerprint pinning at pairing | P2-S1 |
| **Tampering** | Modify traffic in transit | 🔴 Cleartext HTTP | 🟢 TLS; Noise for the relay path | P2-S1, P5-1 |
| **Tampering** | Path traversal to escape the shared-folder scope | 🔴 No sandbox; Windows-only denylist | 🟢 Allowlist + `resolve()` + symlink handling + property tests | **P1-S2** |
| **Tampering** | Malicious upload (path in filename, zip slip) | 🟠 Not verified | 🟢 Sanitise, reject absolute/`..` names, scan | P1-S2 |
| **Repudiation** | No trustworthy record of who did what | 🟠 In-memory, 100-entry cap, lost on restart | 🟢 Persistent, signed, redacted audit log | P1-S5, P3-S1 |
| **Information disclosure** | Sniff the token on first request | 🔴 Token never expires, cleartext | 🟢 TLS + short-lived derived session tokens | P2-S1, P2-S6 |
| **Information disclosure** | Token in a query string | 🟠 Leaked to logs/history; also caused a 401 | 🟡 Scoped route set now; signed URLs later | **P0-11 ✅**, P2-S2 |
| **Information disclosure** | `/paired-devices` returns every raw token | 🔴 One compromised device harvests all others | 🟢 Fingerprints only; scopes enforced | P2-S6 |
| **Information disclosure** | Keystroke content written to the log | 🔴 Plaintext passwords on disk | 🟢 Redacted by field class | P3-S1 |
| **Information disclosure** | Token in a cloud backup | 🟠 `SharedPreferences`, backed up by default | 🟢 Keystore/Keychain + backup excluded | **P0-16 ✅**, P2-S3 |
| **Denial service** | Shut the node down from the LAN | 🔴 Required only the public token | 🟢 Authenticated + scoped | **P0-6 ✅**, P2-S5 |
| **Denial service** | Screenshot spam | 🟡 A 1 s cooldown exists (`[CHAOS FIX]`) | 🟢 Per-device token-bucket rate limiting | P2-S5 |
| **Denial service** | Pairing-code brute force locks out the owner | 🟢 Throttle is per source IP | 🟢 Owner can always regenerate locally | **P0-7 ✅** |
| **Elevation of privilege** | Node runs as Administrator by default | 🔴 Auto-UAC on every start | 🟢 Unprivileged; elevation opt-in per feature | P2-S4 |
| **Elevation of privilege** | Any paired device can do anything | 🔴 No capability model | 🟢 Per-device scopes granted at pairing | P2-S5 |
| **Elevation of privilege** | `/apps/launch` runs any path | 🟠 `os.startfile(path)`, no allowlist | 🟢 Identity-based launch + node confirmation | P2-S5 |
| **Elevation of privilege** | DNS rebinding from a website | 🔴 `CORS(app)` wildcard, no Host validation | 🟢 Origin + Host allowlist | P1-S4 |

### 1.4 What is explicitly out of scope

Being honest about limits is part of the security work.

- **A physical attacker with the unlocked PC.** If they have the session, they
  have the session. The overlay indicator (P3-L4) exists so a *remote* capture is
  visible to someone in the room; it does not defend against local access.
- **A compromised OS.** No userland application can defend its own host.
- **Coerced disclosure of the pairing code.** Out of band by nature.
- **Malware already on the PC.** Cypher is not an EDR.
- **Perfect forward secrecy against a recorded-traffic attacker before P5-1.**
  TLS (P2-S1) gives confidentiality and authentication; the Noise handshake
  (P5-1) adds forward secrecy. Until then, assume a long-recorded capture can be
  decrypted if the node key is later compromised.

---

## 2. Authentication: current vs target

### 2.1 Current model

```
Pairing      phone POSTs {pairing_code, device_id, device_name} → /pair_device
             node compares against a 6-digit code shown on its screen
             node returns token = secrets.token_hex(32)
Storage      node:  paired_devices.json  (plaintext, no file mode set)
             phone: SharedPreferences    (plaintext, cloud-backed up)
Per request  phone sends  X-Auth-Token: <token>
             node checks  token in valid_tokens        (a Python set)
Authorisation  binary — a valid token can call every route
Expiry       none
Revocation   /unpair, by device_id
Loopback     shell sends a hardcoded INTERNAL_TOKEN that bypasses everything
Guest        separate token from GuestSessionManager, folder-scoped, expiring
```

Two independent auth systems (device tokens and guest tokens) with different
rules, checked in different places, in a `before_request` hook that mixes
authentication with rate limiting and activity logging.

### 2.2 Target model

```
┌── Enrolment ──────────────────────────────────────────────────────┐
│ 1. Node generates an ephemeral X25519 keypair + a 6-digit code     │
│ 2. Client scans the QR: cypher://pair?host=…&fp=<node pubkey>      │
│    or enters the code after discovering the node via mDNS          │
│ 3. Noise_XX handshake → mutually authenticated, forward-secret     │
│    channel. The code is the out-of-band authentication of the      │
│    handshake, not a bearer credential in itself.                   │
│ 4. Client requests scopes; node's operator approves them on-screen  │
│ 5. Both sides derive a persistent device identity keypair          │
└────────────────────────────────────────────────────────────────────┘
┌── Session ────────────────────────────────────────────────────────┐
│ Per connection: a short-lived (≤ 1 h) session key derived from the  │
│ device identity. Auto-renewed. Revocation is instant because the    │
│ node keeps a per-device generation counter.                         │
└────────────────────────────────────────────────────────────────────┘
┌── Authorisation ──────────────────────────────────────────────────┐
│ Every route declares the capability it needs:                       │
│   @route('/power/shutdown', capability=Capability.POWER)            │
│ The session's granted scopes are checked against it. A device       │
│ paired for FILES cannot call POWER, even with a valid session.      │
└────────────────────────────────────────────────────────────────────┘
```

### 2.3 Capability scopes

The single most valuable change after the sandbox. Today authorisation is
binary: a valid token can do everything. Scopes make a lost phone a partial loss
instead of a total one.

```python
class Capability(str, Enum):
    FILES_READ    = "files.read"
    FILES_WRITE   = "files.write"
    FILES_DELETE  = "files.delete"
    MEDIA_VIEW    = "media.view"      # screenshot, stream
    MEDIA_RECORD  = "media.record"    # screen recording — highest sensitivity
    INPUT_KEYS    = "input.keys"
    INPUT_POINTER = "input.pointer"
    CLIPBOARD     = "clipboard"
    SYSTEM_VIEW   = "system.view"     # stats, processes, windows
    PROCESS_KILL  = "process.kill"
    APP_LAUNCH    = "app.launch"
    POWER         = "power"           # shutdown, restart, sleep, lock
    GUEST_MANAGE  = "guest.manage"
    DEVICE_MANAGE = "device.manage"   # pair, unpair, rescope
```

Granted at pairing, displayed on the node, editable afterwards, and **visible on
the client** so a user knows what they handed over. Presets:

| Preset | Scopes |
| --- | --- |
| **Full control** | everything |
| **File transfer** | `files.read`, `files.write`, `media.view`, `clipboard` |
| **Media remote** | `input.keys`, `input.pointer`, `clipboard`, `system.view`, `media.view` |
| **View only** | `system.view`, `media.view` |
| **Guest** | folder-scoped `files.read` (+ optional `files.write`), expiring |

`DEVICE_MANAGE` deserves special care: a device that can pair other devices can
escalate to full control. Grant it only to the operator's own device, and require
node-local confirmation for any new pairing regardless of who asks.

---

## 3. The filesystem sandbox (P1-S2) — SHIPPED

> **Status, 2026-10-16.** The helper is in `core/sandbox.py`. Every paired-device
> filesystem route and `/apps/launch` call it. The Windows denylist is gone.
> `tests/test_sandbox.py` has zero xfails. The rest of this section is kept as
> the design record; do not re-implement it.

### 3.1 The problem

**A correct sandbox already exists. It is used by exactly the wrong routes.**

`is_path_in_folders()` in `core/server.py` is the textbook implementation:

```python
file_path_obj = Path(file_path).resolve()      # collapses .., follows symlinks
for folder in allowed_folders:
    folder_obj = Path(folder).resolve()
    file_path_obj.relative_to(folder_obj)      # proves containment
    return True
```

Every `/guest/files/*` route calls it. So a **temporary guest holding a shared
link is properly confined** — symlink escapes, `..` traversal and alternate
separators all correctly refused, and `tests/test_sandbox.py::TestExistingHelperIsCorrect`
proves it with 26 assertions.

**None** of the `/files/*` routes a *paired* device calls use it. `/files/browse`
takes `?path=` and iterates it with no check whatsoever. `/files/delete` guards
with a lowercased string prefix check against six Windows directories:

```python
restricted_roots = ["c:\\windows", "c:\\program files", ...]
if any(path_low.startswith(r) for r in restricted_roots):
    return 403
```

That fails three ways: it is a **no-op on Linux and macOS** (nothing starts with
`c:\`); it is **bypassable** (`C:\Users\..\Windows`, `c:/windows`, UNC
`\\?\c:\windows`, and any symlink into a protected tree); and it is a
**denylist**, which protects six directories and leaves `~/.ssh`,
`~/.aws/credentials`, browser profile stores, password vaults and every document
on the machine exposed to any paired device.

`/files/upload` is worse than a read: it accepts an **absolute** `destination`,
calls `os.makedirs(dest, exist_ok=True)`, and writes there. A paired device can
therefore *create directories and write files* anywhere on the filesystem.

The exposure is inverted from what you would expect. **The least-trusted actor is
the best-confined one.** A lost or compromised phone — or anyone who pairs while
the six-digit code is displayed on an unattended screen — gets the whole disk,
while a guest handed a link for one folder gets exactly that folder.

> **Why this changes the work.** P1-S2 is not "design and write a sandbox". It is
> "promote a helper that already exists and is already proven correct, and call it
> from the routes that forgot to". Smaller, safer, and the regression tests are
> already written and currently xfail.

### 3.1.1 The two bugs already fixed in the helper

Writing the tests found defects in the otherwise-correct helper. Both are fixed
and both have regression tests:

1. **Only the first allowed folder ever worked.** `return True` sat inside the
   loop with one `try/except` around the whole body, so the first non-containing
   folder raised `ValueError` and jumped to `return False` — the loop never
   reached folders 2…N. Sharing "Documents + Pictures" with a guest silently
   shared Documents only. → `test_REGRESSION_every_folder_in_a_multi_folder_list_is_honoured`
2. **Revoking a guest session did not revoke it.** `end_session()` set
   `is_active = False`; `validate_token()` only checked `is_expired()`. The
   Security tab dropped the session while the guest kept access until expiry.
   → `test_revocation_actually_revokes_access` and three companions.

Fix each folder independently, and make the *token validator* the single place
that decides whether a session is live — never the caller.

### 3.2 The design

An **allowlist** of user-selected shared folders, resolved canonically, checked
on every access, in one place.

```python
# core/sandbox.py

class SandboxViolation(Exception):
    """Raised when a path escapes every allowed root."""

class Sandbox:
    """
    Owns the answer to exactly one question:
    "may this session touch this path, in this way?"

    Nothing else in the codebase resolves or validates a filesystem path.
    """

    def __init__(self, roots: Iterable[Path], follow_symlinks: bool = False):
        # resolve() canonicalises: collapses .., resolves symlinks,
        # normalises separators and case-folds where the OS does.
        self._roots = [r.resolve(strict=True) for r in roots]
        self._follow_symlinks = follow_symlinks

    def resolve(self, raw: str | Path, *, need: Access) -> Path:
        """
        Return the canonical path if it is inside an allowed root AND the
        session's scopes permit `need`. Raise SandboxViolation otherwise.

        Order matters: containment is checked on the RESOLVED path, so a
        symlink inside a shared folder that points at /etc/shadow is rejected.
        """
        try:
            candidate = Path(raw).expanduser().resolve(strict=False)
        except (OSError, ValueError) as exc:
            raise SandboxViolation(f"unresolvable path: {exc}") from exc

        for root in self._roots:
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            # Contained. Now verify each component is not a symlink escaping
            # the root, unless the operator explicitly allowed symlink follows.
            if not self._follow_symlinks and self._escapes_via_symlink(candidate, root):
                raise SandboxViolation("path traverses a symlink out of the shared root")
            return candidate

        raise SandboxViolation("path is outside every shared folder")
```

### 3.3 Rules that must not be relaxed

1. **Resolve before comparing.** Never string-prefix match. `Path.resolve()` then
   `relative_to()`.
2. **Allowlist, not denylist.** If a folder is not in `shared_folders`, it does
   not exist as far as the API is concerned.
3. **Check the final component *and* every intermediate one** for symlink escape.
4. **Guest sessions get a strictly narrower sandbox** — their own
   `allowed_folders` list, intersected with the node's, never wider.
5. **Uploads are sanitised**: `werkzeug.utils.secure_filename` on every part,
   reject absolute paths and `..`, reject filenames that are empty after
   sanitising, and reject zip entries whose resolved target escapes the
   destination (zip slip).
6. **Writes go to a temp file in the same directory, then `os.replace`.** Never
   write in place — a failed transfer must not leave a truncated file over a
   good one.
7. **Every filesystem route calls `sandbox.resolve()`.** Enforced by a test that
   enumerates all registered routes, asserts each one that touches the filesystem
   is decorated with `@requires_fs`, and fails the build otherwise. That is how
   the S-04 name-drift problem is prevented from recurring in a new form.
8. **The error message must not echo the path.** `403 {"success": false, "error":
   "path is outside the shared folders"}` — leaking the resolved path helps an
   attacker map the filesystem.

### 3.4 Tests required

```python
@pytest.mark.parametrize("payload", [
    "../../etc/passwd",
    "/etc/passwd",
    "C:\\Windows\\System32\\config\\SAM",
    "c:/windows/system32",                      # forward slashes
    "C:\\Users\\..\\Windows\\win.ini",          # traversal
    "\\\\?\\C:\\Windows\\win.ini",              # UNC extended-length
    "C:\\WINDOWS\\WIN.INI",                     # case variation
    "C:\\Windows\\",                            # trailing separator
    "shared/../../etc/passwd",                  # escape from inside
])
def test_traversal_is_rejected(payload): ...

def test_symlink_escaping_root_is_rejected(tmp_path): ...
def test_symlink_inside_root_is_allowed(tmp_path): ...
def test_guest_sandbox_is_never_wider_than_node_sandbox(): ...
def test_zip_slip_is_rejected(): ...
def test_upload_filename_is_sanitised(): ...
def test_write_is_atomic_and_leaves_no_partial_file(): ...
def test_error_response_does_not_leak_the_resolved_path(): ...
def test_every_fs_route_is_decorated(): ...
```

---

## 4. Transport security (P2-S1)

### 4.1 Why cleartext cannot survive

The auth token is a permanent bearer credential sent in a header on every
request over HTTP. **One passive capture equals permanent total compromise** —
there is no expiry to wait out. Clipboard sync carries passwords. Screen frames
carry whatever is on the display. On a shared network this is not theoretical.

### 4.2 Design

**Per-pairing self-signed certificate, pinned at enrolment (TOFU).**

```
Node startup (first run):
  generate a long-lived X25519 / ECDSA P-256 keypair
  self-sign a certificate for CN=cypher-node, SAN = every current LAN IP + mDNS name
  store the private key at 0600 in the app-data dir

Pairing:
  the QR encodes  cypher://pair?host=<ip>&port=<port>&fp=<SHA-256 of SPKI>
  the client pins fp; any certificate whose fingerprint differs is refused
  the operator confirms the fingerprint on the node's screen out of band

Session:
  HTTPS to the node; the pinned SPKI is the trust anchor, not a public CA
```

Why self-signed rather than Let's Encrypt: a LAN IP address cannot obtain a
public certificate, mDNS names are not publicly resolvable, and requiring
internet access to set up would break the local-first contract. Fingerprint
pinning is strictly *better* than a CA here — a public CA can be compelled or
tricked into issuing for a domain; it cannot forge a fingerprint the user
compared on the node's own screen.

Certificate renewal: 90-day validity, automatic rotation, with the new
fingerprint pushed to already-paired devices over the existing authenticated
channel. Only a *new* pairing needs the out-of-band comparison.

**Client-side compensating control — SHIPPED.** This was a sketch in the first
draft of this plan. It is now implemented in `mobile_app/lib/services/api_service.dart`
as `isPermittedTarget` / `assertPrivateTarget` / `assertPrivateUri`, enforced
through `_baseUrl(ip)`, which is the single choke point for all ~60 endpoint
wrappers. Tested by `mobile_app/test/api_service_test.dart`. See
[`../AUDIT.md`](../AUDIT.md) · F-11b for why it mattered that this shipped: the
network security config's comment already claimed the guard existed, so global
cleartext permission was live with no compensation.

The policy, stated precisely:

```dart
/// Cleartext HTTP only to a private host; TLS to anywhere.
///
/// Android's network_security_config matches hostnames only — it has no CIDR
/// syntax — so the cleartext exception cannot be scoped to RFC1918
/// declaratively. This is the compensating control until P2-S1 lands, after
/// which the config flips to cleartextTrafficPermitted="false" and this becomes
/// defence in depth.
static bool isPermittedTarget(String host);   // loopback, link-local, RFC1918,
                                              // IPv6 ULA, localhost, *.local
static void assertPrivateTarget(String host); // throws PrivateNetworkRequiredException
static void assertPrivateUri(Uri uri);        // http -> private only; https -> any host
```

Two deliberate exclusions, both fail-closed:

- **CGNAT `100.64.0.0/10` is refused.** It is carrier infrastructure, not a LAN;
  permitting it would send a paired token in cleartext across an ISP network.
- **Routable hostnames are refused without resolving them.** Classifying a
  hostname needs a DNS lookup, and the lookup itself leaks the destination the
  guard is trying to protect. Refuse, and let TLS handle remote nodes.

`assertPrivateUri` allowing any `https:` host is what keeps the GitHub release
check in `update_service.dart` working — that request is legitimately public.

### 4.3 IP rotation

A node's LAN address changes constantly (DHCP, WiFi → hotspot → USB tethering).
The certificate SAN list must be rebuilt and re-signed on network change, and
clients must re-resolve via mDNS rather than caching an IP. Otherwise TLS breaks
every time the user walks to a different room.

### 4.4 Noise for the relay path (P5-1)

`Noise_XX_25519_ChaChaPoly_BLAKE2s` gives mutual authentication, forward
secrecy, and — critically — **one transport that behaves identically over LAN and
through a relay**. The relay then forwards opaque ciphertext and cannot
distinguish a file transfer from a keystroke. Implement Noise as the session
layer *inside* TLS on the LAN path, so there is one code path to audit rather
than two. This is why P5-1 is designed alongside P2-S1 and not after it.

---

## 5. Signed URLs (P2-S2)

Media elements — `Image.network`, `<video>`, `<audio>`, the PDF viewer — cannot
attach custom headers. The current workaround puts the auth token in the query
string, which leaks into proxies, browser history and `Referer`.

Replace with short-lived signed URLs:

```
GET /files/preview?path=<p>&exp=<unix>&scope=preview&sig=<hmac>

sig = HMAC-SHA256(session_key, canonical(path) | exp | scope)
```

- **Expiry:** 60 s — enough to start a stream, useless to replay later.
- **Scope:** `preview` URLs cannot be used on `/files/delete`. The signature
  binds the operation.
- **Single-use for downloads:** bind to a random nonce consumed on first use.
- **Derived per session**, so revoking a device invalidates every URL it holds.

This retires the `MEDIA_TOKEN_ROUTES` compromise added in P0-11 and removes the
last place a long-lived credential appears in a URL.

---

## 6. Guest access (P1-S2, P2-S5)

Guests are the least-trusted actor: a link deliberately handed to a **third
party**. The `GuestSession` model is already good — `secrets.token_urlsafe(32)`,
expiry, per-session `allowed_folders`, an access log with a bounded tail, a
cleanup thread, a lock. The problems are enforcement and exposure.

| Requirement | Detail |
| --- | --- |
| Narrower than the node sandbox | A guest's folders are the *intersection* of what the host selected and the node's allowlist. Never wider. Enforced by a test. |
| Read-only by default | Write and delete are separate opt-in scopes the host grants explicitly. |
| Hard expiry, no silent extension | `extend` requires host authentication, is capped (e.g. max 24 h total), and is logged. |
| One folder tree, no enumeration of siblings | `/guest/files` must not leak that other folders exist — including their *names*. |
| Rate limited | Guests get a much tighter bucket than paired devices. |
| No system information | `/guest/session` must not reveal the PC name, OS, IP list, uptime, or the host device identity beyond a display name. |
| Visible on the node while active | A persistent indicator, not just an activity-log entry. The operator must be able to see at a glance that a third party has access right now. |
| Download watermarking is out of scope | Do not promise it. Say so. |

The guest landing page is currently ~550 lines of HTML/CSS/JS embedded in an
f-string inside `server.py` (duplicated as the deleted `guest_html.txt`). Extract
to a real template (P1-B4) — and treat it as **untrusted-renderer** code: strict
CSP, no inline scripts, all values escaped, no access to any node API beyond the
guest-scoped endpoints.

---

## 7. Least privilege (P2-S4)

`service.py` calls `elevate()` — a UAC prompt via `ShellExecuteW(runas)` —
whenever the `CYPHER_BRIDGE` firewall rule is missing, i.e. on a **default first
run**. The node then runs as Administrator and opens inbound TCP 5000/5001 and
UDP 5001/5002 across all profiles.

Consequence: every vulnerability in this document yields SYSTEM-level compromise
instead of user-level.

Target:

1. **Run unprivileged.** Always. No automatic elevation, ever.
2. **Firewall rule at install time**, where elevation is expected and visible,
   scoped to **private profiles only** — never public. A user on hotel WiFi
   (profile: public) should not be reachable at all.
3. **Bind to specific interfaces**, not `0.0.0.0`, when the user has selected
   which network to serve. Default to the private interface only.
4. **Elevate per feature, on demand.** Hibernate and some process control need
   it; files, media, input and monitoring do not. Where elevation is unavailable,
   report the capability as absent (P3-L1) rather than failing at call time.
5. **Consider a separate low-privilege service account** on Windows for the
   always-on listener, with the interactive features running in the user session.
6. **Linux:** no `pkexec` at all. Document the port; let the user open it. A
   systemd *user* unit, not a system unit.

---

## 8. Secrets and storage (P2-S3)

| Secret | Today | Target |
| --- | --- | --- |
| Node internal token | ✅ generated, `0600` | Keep; add rotation on demand |
| Device tokens (node side) | `paired_devices.json`, no mode set | `0600`; encrypt at rest with a key derived from a machine-bound secret (DPAPI on Windows, libsecret on Linux, Keychain on macOS) |
| Auth token (mobile) | `SharedPreferences` — plaintext, cloud-backed-up | `flutter_secure_storage` → Android Keystore / iOS Keychain |
| Backup exclusion | ✅ `data_extraction_rules.xml`, `allowBackup=false` | Keep |
| Pairing code | ✅ `secrets`, `0600`, single-use | Keep |
| TLS private key | — | `0600`, never leaves the app-data dir, never in a diagnostic export |
| Guest tokens | In memory only | Correct as-is; do not persist |

**Diagnostics export must be redacted by construction** — build it from an
allowlist of fields, not by scrubbing a denylist of patterns. Scrubbers get
bypassed; allowlists fail closed.

---

## 9. Rate limiting and abuse (P2-S5)

The node currently has exactly one throttle: a 1 s cooldown on `/screenshot`,
added under a `# [CHAOS FIX]` comment.

Target: a per-device token bucket, with tighter buckets for expensive and
sensitive operations.

| Class | Budget | Rationale |
| --- | --- | --- |
| Pairing | ✅ 5 / 5 min, then 15 min lockout | Already shipped (P0-7) |
| Read metadata (`/status`, `/system-stats`) | 60 / min | Cheap, polled |
| File listing | 30 / min | Cheap |
| File download | Unmetered but concurrency-capped (e.g. 4) | Throughput matters; DoS is via concurrency, not rate |
| Screenshot | 10 / min after the existing 1 s cooldown | CPU-expensive |
| Screen stream | 1 concurrent stream per device | Bandwidth- and CPU-bound |
| Input injection | 120 / min | Enough for real typing, stops scripted floods |
| Power / process kill | 5 / min, **plus node-local confirmation** | Irreversible and disruptive |
| Guest (all classes) | ¼ of the paired budget | Least-trusted actor |

Every rejection returns `429` with `Retry-After`, and is logged as a security
event so it appears in the Security console.

---

## 10. Audit logging (P1-S5, P3-S1)

Today: `command_history` is an in-memory list capped at 100 entries, lost on
restart, and it records `f"Typed: {request.json.get('text','')[:20]}"` — the
first 20 characters of everything the user typed, including passwords.

Target:

- **Persistent**, append-only, rotating, at `<appData>/cypher/logs/audit.jsonl`.
- **Schema-typed** (P1-S5): every field is classified `public`, `internal`, or
  `sensitive`. Serialisation drops `sensitive` unless the operator has explicitly
  enabled verbose logging with an on-screen warning.
- **Never log content.** Log the *fact*: `{action: "input.inject", length: 42,
  target_window: "…", device: "…"}`. Never the text.
- **Never log paths outside the sandbox**, and log only the relative path within
  a shared folder otherwise.
- **Record authentication failures and throttling** — including the pairing
  lockouts P0-7 now generates. A lockout nobody can see is not a control.
- **Tamper-evidence:** hash-chained entries (each record includes the hash of its
  predecessor), so silent truncation is detectable. Full signing is optional and
  can come later.
- **Exportable and redacted**, feeding the diagnostics bundle.

---

## 11. Supply chain (A7)

| Control | Status |
| --- | --- |
| Gitleaks over **full git history** in CI | ✅ `ci.yml` → hygiene |
| Hygiene gate blocks keystores, `.env`, Firebase config, build output | ✅ |
| Banned-dependency gate (`firebase\|analytics\|sentry\|mixpanel\|amplitude\|segment\|posthog\|onesignal\|facebook`) | ✅ both Flutter apps |
| Dependabot on pip, pub, gradle, actions | ✅ grouped, weekly, with ignore rules that carry explanatory comments |
| CodeQL `security-extended` + Semgrep `p/security-audit` | ✅ `codeql.yml` |
| License compatibility gate (Apache-2.0) | 🟠 `NOTICE` documents the Syncfusion blocker; automate in P1-B7 |
| `pip-audit` / OSV / `pub outdated --security` | 🟠 P2-S8 |
| Pinned workflow action SHAs instead of tags | 🟠 P2-S8 |
| Artefact signing (Authenticode / minisign) + published keys | 🟠 P2-D3 |
| Build provenance attestations (SLSA) | 🟠 P5 |
| Reproducible PyInstaller builds | 🔵 stretch |
| `NOTICE` lists every third-party component | ✅ |

**The Syncfusion item is a genuine release blocker**, not a nit: its Community
License is proprietary and incompatible with Apache-2.0 redistribution, so no
binary bundling it may be published. Tracked as P1-B9.

---

## 12. Privacy as a security property

The README's promise — *"No cloud. No subscriptions. No data tracking."* — was
false when audited: Firebase Analytics was wired into the Gradle build and
`CentralService` posted install beacons to a third-party Render host. Both are
gone (P0-14), and CI now fails any PR that reintroduces them.

Privacy is a security property here for a concrete reason: **every telemetry
channel is an exfiltration channel and an attack surface.** A product whose
entire value proposition is that data does not leave the network cannot afford an
analytics SDK with its own dependency tree, its own network path, and its own
update cadence.

Rules, enforced in review and in CI:

1. No analytics, no crash reporting that uploads, no install beacon, no A/B
   framework. Ever.
2. The only outbound internet calls permitted are: the user-initiated version
   check against `api.github.com` (version string only, no device identifier),
   the optional update download, and — when the user explicitly opts in — the
   relay. All three are documented in `docs/product/privacy.md`.
3. Crash diagnostics stay **on-device** and are exported only by explicit user
   action, redacted by allowlist.
4. The relay (P5) must be self-hostable, off by default, and visibly indicated
   whenever traffic is flowing through it. A user must be able to point it at
   their own server and never touch ours.
5. Any change to this list requires a `docs/product/privacy.md` update in the
   same PR.

---

## 13. Sequencing

```
Phase 1  ── P1-S2 sandbox helper + apply to all routes + property tests   ← FIRST
            P1-S3 decorator-based public routes          ← SHIPPED
            P1-S4 CORS + Host validation (DNS rebinding) ← SHIPPED
            P1-S1 git history purge + rotate the Firebase key + upgrade notice
            P1-S5 typed audit-log schema

Phase 2  ── P2-S1 TLS + fingerprint pinning + client private-IP guard
            P2-S2 signed URLs (retires the query-string token)
            P2-S3 secure storage on both sides
            P2-S4 least privilege; no auto-elevation
            P2-S5 capability scopes + rate limiting + launch allowlist
            P2-S6 token expiry, rotation, no raw tokens in /paired-devices
            P2-S7 published threat model
            P2-S8 dependency + CVE gating, pinned action SHAs
            P2-S9 fuzzing

Phase 3  ── P3-S1 log redaction by field class

Phase 5  ── P5-1 Noise handshake, P5-7 out-of-band fingerprint verification
```

**Why the sandbox is first:** it is the only finding that lets an *authenticated,
legitimately paired* device do something the user never granted. Everything else
in Phase 1 defends the perimeter; P1-S2 defends the interior. And because P1-B4
decomposes `server.py`, the helper must land before the split or it will be
written once per module.

---

## 14. Verification

Security work without a test is a claim, not a control. Each item must ship with
its check.

| Control | Verification |
| --- | --- |
| Sandbox | The traversal/symlink/zip-slip property suite in §3.4, plus a route-coverage test asserting every FS route is decorated |
| Pairing throttle | Attempt 6 from one IP gets `429` + `Retry-After`; a correct code during lockout is still refused; the code rotates on success |
| Constant-time compare | `hmac.compare_digest` present; assert in a lint rule that `==` is never used on a token |
| No hardcoded secrets | `git grep` gate in CI; Gitleaks over full history |
| TLS pinning | A node presenting a different fingerprint is refused; renewal over an authenticated channel succeeds |
| Signed URLs | A URL expired by 1 s is refused; a `preview` signature is refused on `/files/delete`; revoking the device kills outstanding URLs |
| Capability scopes | A `files`-only device calling `/power/shutdown` gets `403`, and the attempt appears in the Security console |
| Rate limiting | Each class returns `429` at its documented budget |
| Least privilege | The node runs as a standard user end to end on a clean Windows install with no UAC prompt |
| Log redaction | A typed string containing a password never appears in `audit.jsonl`; assert with a canary value in tests |
| Backup exclusion | A device-migration restore does not carry the token |
| Guest narrowness | A guest sandbox can never exceed the node's; enforced by test |
| Diagnostics export | The bundle contains no token, key, or absolute user path — asserted by scanning the produced zip in a test |
