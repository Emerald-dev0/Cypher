# Security Policy

CYPHER is a remote-control system. It reads and writes files, injects keystrokes,
captures the screen, kills processes and shuts machines down, and it listens on a
network interface. **A security bug in this project is not a defect — it is
someone losing control of their computer.**

We treat vulnerability reports accordingly, and we ask reporters to treat them
accordingly too.

---

## 🔒 Reporting a vulnerability

**Do not open a public GitHub issue.** Do not post on Discussions, X, Reddit or
anywhere else. Do not demonstrate against a machine you do not own.

### Use GitHub's private vulnerability reporting

👉 **<https://github.com/Emerald-dev0/Cypher/security/advisories/new>**

Private Security Advisories keep the report, the discussion and any proof of
concept hidden until a fix ships. This is the preferred channel.

### If that is unavailable

Email the maintainers at the address listed in the repository's
[profile](https://github.com/Emerald-dev0), with the subject prefix
`[CYPHER-SEC]`. If you have a PGP key preference, state it and we will respond
encrypted.

### What to include

The more of this you can give us, the faster we can act:

- **What you found**, in one or two sentences.
- **Affected versions** — a release tag or a commit SHA. "Latest" is not enough;
  we need to know how far back it goes.
- **Reproduction steps** from a clean install, including the OS, the transport
  (LAN / hotspot / USB tethering / relay), and whether the node was running
  elevated.
- **Proof of concept** — a script, a `curl` command, a packet capture. Please do
  not attach captured credentials or another person's data; describe them instead.
- **Impact** — what does an attacker end up able to do, and what do they need
  first (LAN access? a paired device? a guest link? nothing?).
- **Whether you have told anyone else**, and whether you intend to publish.

---

## What to expect from us

| When | What happens |
| --- | --- |
| **Within 72 hours** | Acknowledgement that we received it. |
| **Within 7 days** | An initial triage: confirmed, needs more information, or out of scope with reasoning. |
| **Within 14 days** | A remediation plan and an expected fix date, or an explanation of why we disagree about severity. |
| **On fix** | A release, a `SECURITY` entry in `CHANGELOG.md`, and a credit in the advisory (unless you ask to stay anonymous). |
| **Disclosure** | Coordinated. We will agree a date with you, and we default to disclosing once a fix has been public for at least 7 days. |

If we miss a deadline, chase us. That is a legitimate thing to do and we would
rather be chased than have a report sit unread.

We aim to publish an advisory for every confirmed vulnerability, including ones
we consider low severity. Silence about a fixed bug leaves every older install
exposed.

---

## Scope

### In scope — please report these

- Authentication bypass on any node endpoint.
- Escaping the shared-folder sandbox (path traversal, symlink escape, zip slip).
- Guest sessions exceeding their folder scope, expiry, or rate limits.
- Token prediction, reuse after revocation, or leakage (logs, URLs, backups,
  error messages, diagnostics exports).
- Pairing-code brute force, prediction, or replay.
- Cross-origin attacks against the node: DNS rebinding, CSRF, `Host` header
  abuse, WebSocket origin confusion.
- Privilege escalation: a device paired for one capability invoking another.
- Unencrypted transmission of credentials, clipboard content, files or screen
  data — including over the relay.
- Relay MITM, or a relay able to read or alter payload.
- Memory-safety or injection bugs reachable over the network.
- Insecure defaults: an unexpected listener, an over-broad firewall rule,
  elevation without consent, a debug endpoint left enabled.
- Supply chain: a malicious or vulnerable dependency, a compromised CI workflow,
  a tampered release artefact.
- Android/iOS local privilege issues: exported components, world-readable token
  storage, unsafe intents, backup/migration carrying credentials.

### Out of scope

- Attacks requiring **physical access to an unlocked PC**. If an attacker has an
  active desktop session, they have an active desktop session.
- Attacks requiring the user to **install malware** or run a malicious binary
  with their own hands.
- **Compromised operating system** — CYPHER cannot defend its own host.
- Social engineering of the user into reading out a pairing code.
- Traffic analysis against a relay (connection metadata is visible to the relay
  operator by design — see [`docs/plans/relay-cloud.md`](docs/plans/relay-cloud.md) §3.3).
  Self-hosting is the mitigation, and it is documented.
- Missing rate limits on endpoints that are already correctly authenticated,
  unless you can show a concrete impact.
- Reports from automated scanners with no demonstrated impact.
- Vulnerabilities in third-party services we link to but do not operate.

We may still fix out-of-scope items — this list is about what we commit to
treating as a vulnerability, not about what we care about.

---

## Supported versions

Security fixes land on the **latest two minor versions**. Older versions get a
forced-upgrade notice rather than a backport.

This is stricter than usual for a deliberate reason: a remote-control tool with an
unpatched install on someone's network is an active liability, not a legacy
compatibility question. We would rather push an upgrade than leave a hole open.

| Version | Status | Security fixes |
| --- | --- | --- |
| Latest release | ✅ Supported | Yes |
| Previous minor | ✅ Supported | Yes, critical/high only |
| Older | ❌ Unsupported | Upgrade notice only |
| Anything before the Phase 0/1 hardening | 🚫 **Actively unsafe** | See below |

### ⚠️ Pre-hardening builds

Any build produced before the 2026-10 hardening pass (see
[`docs/AUDIT.md`](docs/AUDIT.md)) contained a **hardcoded authentication token
published in this repository**. That token granted full remote control of the
node to anyone who could reach port 5000.

If you are running such a build: **uninstall it, delete
`%APPDATA%\Cypher\paired_devices.json`, and install a current release.** Do not
simply update in place — assume the token was known.

The literal also remains in this repository's git history until P1-S1 completes.

---

## Security-relevant configuration

If you are deploying CYPHER, these settings materially change your exposure. All
of them are covered in [`docs/plans/security-hardening.md`](docs/plans/security-hardening.md).

- **Bind to a private interface**, not `0.0.0.0`, when you have a choice.
- **Do not run the node as Administrator/root.** P2-S4 makes this the default; if
  you are on an older build, stop elevating it manually.
- **On shared or public WiFi, turn the node off.** Hotel and conference networks
  are the threat model, not an edge case.
- **Keep the shared-folder allowlist minimal.** Every folder you add is readable
  by every paired device until capability scopes (P2-S5) ship.
- **Review paired devices periodically** in the desktop Security tab and revoke
  anything you do not recognise — especially after losing a phone.
- **Self-host the relay** if you use one, or leave it disabled.

---

## Recognition

We credit every reporter in the advisory and in `CHANGELOG.md` unless you ask us
not to. If you would like a CVE ID, say so in your report and we will request one
through our CNA.

Thank you for reporting responsibly. Users of this software are trusting it with
their machines, and the people who tell us when we got it wrong are the reason
that trust is not misplaced.
