# Privacy

**The short version: CYPHER does not collect your data, does not send your data
anywhere, and does not have an account system. Your files, clipboard, screen and
keystrokes stay between your devices.**

This document exists because the claim used to be false. An audit in October 2026
found Firebase Analytics wired into the Android build and an install beacon
posting to a third-party host, while the README's headline read *"No cloud. No
subscriptions. No data tracking."* Both were removed, and CI now fails any pull
request that reintroduces an analytics, crash-reporting or tracking dependency.
See [`AUDIT.md`](../AUDIT.md) §3 (F-10).

This page is the authoritative answer for the Google Play Data Safety form and
the Apple App Privacy labels. **If the code and this page disagree, that is a
bug — please report it.**

---

## 1. What data exists at all

CYPHER necessarily handles sensitive data, because controlling a PC means
touching files, clipboard, screen and input. The question is where it goes.

| Data | Created by | Where it lives | Does it leave your devices? |
| --- | --- | --- | --- |
| Shared-folder list | You, in Settings | Node app-data dir | ❌ No |
| Files you transfer | You | Your PC and your phone | ❌ No — direct device to device |
| Clipboard content (both directions) | You | In memory on both devices | ❌ No |
| Clipboard history (last 50) | You | In memory on the node; lost on restart | ❌ No |
| Screenshots and screen streams | You, on demand | Rendered on your phone; saved only where you choose | ❌ No |
| Screen recordings | You | Your PC's recordings folder | ❌ No |
| System stats (CPU/RAM/disk/battery) | The node | In memory, last 30 samples | ❌ No |
| Process and window lists | The node | In memory, on request | ❌ No |
| Activity log | The node | Node app-data dir | ❌ No |
| Keystroke text | You | **Should never be logged** — see §5 | ❌ No |
| Pairing code | The node | Node app-data dir, `0600`, single-use | ❌ No |
| Device tokens | The node, at pairing | Node app-data dir; phone Keystore/Keychain | ❌ No |
| Device name and model | Your phone | Node app-data dir, shown in the device list | ❌ No |
| Node name and LAN addresses | Your PC | Advertised on your LAN via mDNS/UDP | ⚠️ To the local network only — see §3 |

**No email address, no phone number, no username, no password, no advertising
identifier, no analytics ID, and no account of any kind.** There is nothing to
collect, because there is no server that collects.

---

## 2. What leaves the device

Exactly three things, all optional, all disclosed:

### 2.1 Update check — user-initiated

When you tap "Check for updates", or when the desktop app checks on startup, the
client makes one HTTPS request:

```
GET https://api.github.com/repos/Emerald-dev0/Cypher/releases/latest
```

**Sent:** nothing but the request itself — no device identifier, no version
string, no IP beyond what GitHub sees from any HTTPS request.
**Received:** the latest release tag and asset URLs.

The comparison happens locally. You can disable this in Settings, and the app is
fully functional without it.

### 2.2 Update download — user-initiated

If you choose to install an update, the binary is downloaded from
`github.com` / `objects.githubusercontent.com`. Same disclosure as any browser
download.

### 2.3 The relay — opt-in, off by default

If, and only if, you configure a relay (roadmap Phase 5, not yet shipped), your
device opens an outbound connection to **the relay URL you chose** — which may be
your own server. See [`plans/relay-cloud.md`](../plans/relay-cloud.md).

What a relay operator can see: that your node is connected, when, roughly how
many bytes moved, and which client keys talked to it.

What a relay operator **cannot** see: file contents, clipboard, screen data,
keystrokes, tokens, or your pairing. The payload is `Noise_XX` end-to-end
encrypted between your phone and your PC; the relay forwards ciphertext it
cannot read or alter.

**The LAN path never touches a relay.** If the relay is unreachable or disabled,
local pairing, discovery, transfer and control are completely unaffected. The
client shows a badge whenever traffic is being relayed, and it will never
silently fall back to a public relay.

### 2.4 Nothing else

No crash reports are uploaded — diagnostics stay on-device and are exported only
when you explicitly tap "Export diagnostics", producing a **redacted** bundle.
No analytics. No A/B testing. No advertising. No third-party SDKs. No telemetry
of any kind, aggregate or otherwise.

---

## 3. What is visible on your local network

This is not data collection, but it is honest disclosure: while the node runs, it
advertises its presence so your phone can find it.

- **mDNS/Bonjour** — a `_cypher._tcp` service record with the PC's display name
  and port.
- **A UDP discovery beacon** on the local subnet.
- **An HTTP listener** on the configured port (default 5000).

Anyone else on the same WiFi can therefore see *that a CYPHER node exists* and
*what the PC is named*. They cannot see files, and they cannot control anything
without a valid token.

Mitigations, current and planned:

| Control | Status |
| --- | --- |
| Pairing-code brute-force throttle and lockout | ✅ Shipped |
| Per-install generated internal token (no published secret) | ✅ Shipped |
| Discovery can be disabled in Settings | ✅ Available |
| Bind to a specific interface instead of `0.0.0.0` | 🟠 P2-S4 |
| TLS with fingerprint pinning, so traffic cannot be read on the LAN | 🟠 P2-S1 |
| Capability scopes, so a paired device only does what you granted | 🟠 P2-S5 |
| Filesystem sandbox, so only shared folders are reachable | 🔴 **P1-S2 — in progress** |

**Until P1-S2 ships, treat the shared-folder list as advisory rather than
enforced, and do not run the node on a network you do not trust.** This is stated
in the README and in `SECURITY.md`, and it is the reason the project is not being
publicly promoted yet.

---

## 4. Where data is stored on disk

| Platform | Location |
| --- | --- |
| Windows | `%APPDATA%\Cypher\` |
| Linux | `~/.config/cypher/` (being unified — see roadmap P3-L6) |
| macOS | `~/Library/Application Support/Cypher/` |
| Android | App-private storage; tokens in Keystore |
| iOS | App sandbox; tokens in Keychain |

Contents: settings, the shared-folder list, paired-device records, the activity
log, the generated internal token, and (once P2-S1 lands) the node's TLS key.

Protections:

- Token files are written with mode `0600` where the OS supports it.
- **Android backup and device migration are disabled** for this app, so an auth
  token is never uploaded to Google Drive or transferred to a new handset. A
  restored token would grant silent control of your PC.
- On Android the token moves to Keystore-backed storage (P2-S3).
- Deleting the app-data directory fully un-pairs everything. There is no server
  copy to worry about.

---

## 5. Known issue: keystroke logging

**This is a real defect, disclosed here because hiding it would be worse.**

The activity log currently records the first 20 characters of text sent through
the `/type` endpoint — which is exactly where passwords and 2FA codes appear. It
is written to disk on the node and rendered in the desktop Activity tab.

Tracked as **P3-S1**, with the schema groundwork in **P1-S5**. The fix is not
scrubbing: the log schema classifies every field as `public`, `internal` or
`sensitive`, and `sensitive` fields are dropped at serialisation unless the
operator has explicitly enabled verbose logging behind an on-screen warning.

Until it ships, the mitigation is to disable clipboard/keystroke logging in
Settings, or to delete the activity log file.

---

## 6. Children

CYPHER is not directed at children and does not knowingly collect data from
anyone, including children — there is no collection mechanism to collect with.
It is a tool for controlling your own devices.

That said: it grants real control over a computer. A child with a paired phone
and an unscoped node can delete files and shut the machine down. Capability
scopes (P2-S5) are what make this manageable, and until they ship, pairing a
device is granting it everything.

---

## 7. Permissions we request, and why

### Android

| Permission | Why | When requested |
| --- | --- | --- |
| `INTERNET` | Talk to your PC | Implicit |
| `ACCESS_NETWORK_STATE` | Detect WiFi ↔ cellular ↔ USB changes | Implicit |
| `CHANGE_WIFI_MULTICAST_STATE` | mDNS discovery needs a multicast lock | On discovery |
| `NEARBY_WIFI_DEVICES` (API 33+) | Discovery **without** location | On discovery |
| `ACCESS_FINE_LOCATION` (≤ API 32 only) | Legacy Android requires it for mDNS | On discovery |
| `CAMERA` | Scan a pairing QR code | When you tap "Scan" |
| `READ_MEDIA_*` | Pick photos/videos to send | When you pick a file |
| `POST_NOTIFICATIONS` | Transfer progress | On first transfer |
| `FOREGROUND_SERVICE*` | Keep a transfer alive in the background | During a transfer |
| `WAKE_LOCK` | Don't drop a long transfer when the screen sleeps | During a transfer |
| `MANAGE_EXTERNAL_STORAGE` | The phone file browser | ⚠️ Being removed — P2-M6 replaces it with the Storage Access Framework |

Previously the app requested six of these **at cold start, before showing any
UI**, including camera "for potential future features" and precise location with
no stated justification. That was removed in the October 2026 pass: every
permission is now requested at the moment the feature that needs it is used.

### Windows / Linux (node)

| Access | Why |
| --- | --- |
| Files in folders **you** shared | That is the feature |
| Input injection | Remote keyboard and pointer |
| Screen capture | Screenshots, streaming, recording |
| Audio | Volume and media control |
| Process list | The process manager |
| Inbound TCP/UDP on the node port | LAN connections from your devices |
| Outbound to the relay | Only if you configure one |

The node should run as a **normal user, never elevated**. Older builds requested
UAC automatically on first run; that is being removed (P2-S4).

---

## 8. Third parties

No third party receives your data, because no data is sent.

The dependencies CYPHER is *built from* are listed in [`../NOTICE`](../NOTICE).
Building with a library is not the same as sending it data. The two external
services a build may contact are GitHub (update check, if you initiate it) and
your chosen relay (if you configure one).

There is no data-processing agreement to offer, no DPA to sign, and no sub-
processor list, because there is no processing.

---

## 9. Your rights

Under GDPR, CCPA and similar regimes the usual answer is: **there is nothing to
request.** We hold no personal data about you. There is no account to delete, no
export to produce, and no controller to contact about your data, because your
data never reaches us.

What you *can* do:

- **Delete everything locally** by removing the app-data directory (§4).
- **Un-pair any device** from the desktop Security tab.
- **Stop advertising** by disabling discovery in Settings.
- **Refuse relaying** by leaving the relay field empty — which is the default.

If you are an organisation evaluating CYPHER: it is designed to be usable in
air-gapped and regulated environments precisely because there is no cloud
component. See [`product/features-and-applications.md`](product/features-and-applications.md) §2.2.

---

## 10. Changes

Any change to what leaves a device requires this document to be updated **in the
same pull request**, and is treated as a breaking change for the purposes of the
changelog. The rule is enforced socially today and by review checklist
([`../.github/pull_request_template.md`](../.github/pull_request_template.md));
the CI dependency gate covers the automated part.

**Last reviewed:** 2026-10-15
