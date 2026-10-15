# Features & Applications

**Purpose:** scope what CYPHER could become, and — equally important — what it
should refuse to become.
**Status:** ideas and analysis, **not commitments**. Nothing here is scheduled
until it earns a task ID in [`ROADMAP.md`](../../ROADMAP.md).

---

## 1. What CYPHER actually is

Strip the feature list and the product is one sentence:

> **An authenticated, user-consented control channel between a phone and a PC
> that works without the internet.**

Two properties make it distinctive, and every idea below should be judged against
them:

1. **No cloud, no account.** The trust boundary is the local network and a code
   the user read off their own screen. Nothing to breach, nothing to subpoena,
   nothing to bill.
2. **Deep OS access, deliberately granted.** Files, input, power, processes,
   screen. This is not a notification mirror or a media remote — it is real
   control, which is why the capability-scope work (P2-S5) matters more than any
   feature here.

The competitive set is instructive:

| Alternative | What it costs the user |
| --- | --- |
| TeamViewer / AnyDesk | Account, vendor relay, internet dependency, free-tier nagging, a company that can see your sessions |
| KDE Connect | Closest peer, Linux-first, weaker on Windows, no deep file/power control |
| Chrome Remote Desktop | Google account, cloud relay, browser-bound |
| SSH + Termux | Real power, but a terminal — no file browser, no media, no screen |
| USB cable / Bluetooth | Slow, fiddly, one file at a time |
| Emailing yourself a file | The thing the landing page already mocks, correctly |

**CYPHER's position:** deeper than KDE Connect, more private than TeamViewer,
easier than SSH. That is a real gap. It is also narrow — which is an argument for
depth over breadth.

---

## 2. Who actually uses this

### 2.1 Primary personas

**The couch computer.** PC in the bedroom or study, person on the sofa. Pause the
download, skip the track, shut it down without getting up, grab the file that just
finished rendering. *Highest-frequency, lowest-stakes use. This is what keeps the
app installed.*

**The cable-hater.** Phone photos and videos need to get to the PC; PC documents
need to get to the phone. No USB cable, no cloud quota, no "email it to yourself".
*This is the acquisition use case — the one people describe to friends.*

**The presenter.** Laptop connected to a projector; the phone is the clicker, the
slide remote, the timer and the laser pointer. Walk the room instead of standing
at the podium. *Distinct enough to be its own mode (§4.2).*

**The home-lab tinkerer.** A machine under the desk or in a closet, no monitor
attached. Check on it, restart a service, pull a log, reboot. *Currently served
badly: SSH exists, but file browsing and screen access do not come with it.*

**The careful parent / remote helper.** A less-technical family member's machine
needs a look. Today that means installing TeamViewer and handing over a session
code to a vendor. CYPHER's guest link with a folder scope and an expiry is a
genuinely better answer — *if* the security work lands.

### 2.2 Contexts worth designing for

| Context | Implication |
| --- | --- |
| **Low-bandwidth / metered links** | The relay and any streaming must degrade gracefully; a screenshot-on-demand beats a 20 fps stream on a bad link. Relevant to the project's own home market. |
| **Older Android hardware** | `armeabi-v7a` splits still matter; do not chase only flagships. |
| **Shared / hostile WiFi** | Dorms, cafés, conferences. This is the threat model, not an edge case. |
| **Air-gapped and regulated environments** | No cloud means CYPHER is usable where TeamViewer is banned outright. Underserved and genuinely valuable — clinics, labs, government, finance. |
| **Accessibility** | A user who cannot easily reach a keyboard or mouse gains real independence from phone-based control. Worth more than any power-user feature, and it needs the P2-M8 accessibility pass first. |

---

## 3. Feature backlog

Scored on **value** (does it make the product meaningfully better for a primary
persona), **cost** (days, including tests and docs), and **risk** (does it widen
the attack surface?).

Rule: anything that widens the attack surface must land *after* the security work
that contains it. A feature built on an unsandboxed file API inherits the bug.

### 3.1 Should build

| Feature | Value | Cost | Risk | Notes |
| --- | --- | --- | --- | --- |
| **Multi-node** — one phone, several PCs, with a switcher | High | 6d | Low | Today the client stores one IP and one token. Real households have 2–4 machines. Requires a device-list model in `SharedPreferences`/Keystore and a node picker. Do this before anything exotic. |
| **Transfer queue + resume** | High | 5d | Low | The chunked protocol exists (`docs/architecture/file-transfer.md`); expose it: pause, resume, retry, reorder, per-item cancel. Survives the WiFi drop that will definitely happen mid-transfer. |
| **Clipboard history with encryption at rest** | High | 4d | Medium | Already 50 items in memory. Persisting it creates a credential store — must be encrypted (P2-S3) and off by default with an explicit warning. |
| **Folder sync (one-way, scheduled)** | High | 8d | Medium | "Keep my phone's camera roll on the PC" is the single most requested thing in this category. Needs the sandbox (P1-S2) and conflict semantics. |
| **Wake-on-LAN scheduler + saved profiles** | Medium | 3d | Low | `/wol` exists. Add saved machines, a schedule, and a "wake before I get home" trigger. |
| **Remote terminal (developer mode)** | High for the lab persona | 10d | **High** | A shell over the tunnel. Genuinely useful, and genuinely the most dangerous feature in the product. Gate it behind an explicit `Capability.TERMINAL` scope, off by default, with node-local confirmation per session. Do not ship before P2-S5. |
| **Notification mirroring (phone → PC and back)** | Medium | 6d | Low | Table stakes for the category; KDE Connect has it. Cheap, expected, and it does not touch the filesystem. |
| **Find my phone / find my PC** | Medium | 2d | Low | Ring the device, flash the screen. Trivial, delightful, and it demos well. |
| **Media remote polish** — now-playing metadata, album art, per-app volume | High | 5d | Low | The most-used surface after file transfer. Currently volume only. |
| **Macro recorder** — record a sequence of input actions, replay on demand | Medium | 6d | Medium | Powerful, and a shareable macro format could become a community asset. Must respect scopes: a macro cannot exceed what its device may do. |
| **Diagnostics export** | High (support cost) | 3d | Low | Redacted bundle (P2-S3). Turns "it doesn't work" into something actionable. Already in the desktop plan §4.5. |
| **CLI client** | High | 8d | Low | P3-C1. `cypher get ./report.pdf`, `cypher shot`, `cypher lock`. Unlocks scripting, CI, and every user who finds a GUI remote control absurd. Also the best possible test harness for the API. |

### 3.2 Worth exploring

| Feature | Why interesting | Why not yet |
| --- | --- | --- |
| **Presentation mode** | A distinct, well-defined job: clicker + timer + spotlight + slide preview on the phone. Could be a separate lightweight app or a mode. | Needs a display-aware API the node does not have; competes with dedicated clickers that cost less than the effort. |
| **LAN file drop without pairing** | An AirDrop-style ephemeral public drop zone: anyone on the WiFi can *send* to the PC, nobody can read. Genuinely novel and useful for classrooms and events. | An unauthenticated upload endpoint is a serious abuse vector — disk-fill, malware delivery. Needs size caps, per-IP limits, an operator-visible queue, and mandatory review before anything lands. Only after P2-S5. |
| **Plugin API** | A sandboxed manifest format so third parties add node capability without forking. The way a niche tool becomes a platform. | Absolutely not before capability scopes, sandboxing and signing. A plugin system on top of today's auth model is remote code execution with extra steps. |
| **Home Assistant / MQTT integration** | The node as an automation actuator: "when I leave geofence X, lock the PC". Fits the no-cloud ethos perfectly. | Small audience, meaningful protocol surface. Revisit after the CLI proves the API is stable. |
| **Kiosk / digital signage mode** | A locked-down node driven remotely: one app, fullscreen, no input, remote reboot. Real commercial demand. | A different product with different buyers. Could be a paid tier — but do not let it distort the consumer app. |
| **Web client** | A browser tab that controls the PC. Zero install on the client side. | The node would serve a UI to the LAN, which massively widens the DNS-rebinding surface (S-07). Only after P1-S4 and P2-S1, and only over TLS with a pinned origin. |
| **Encrypted cloud backup of the pairing config** | Losing a phone means re-pairing everything. | Directly contradicts the no-cloud contract. A local encrypted export/import file achieves 90% of the value with none of the exposure. Do that instead. |

### 3.3 Should refuse

These will be requested. Refusing them is part of the product.

| Request | Why no |
| --- | --- |
| **Cloud file storage / sync-as-a-service** | CYPHER is not Dropbox. Adding storage makes it a data custodian, with all the legal, security and infrastructure burden, and destroys the differentiator. The relay (P5) deliberately stops at forwarding bytes. |
| **Accounts and login** | An account is a credential store, a support queue and a breach surface. The pairing code is already the account, and it is better because it never leaves the LAN. |
| **Telemetry / "anonymous usage stats"** | Explicitly forbidden by the product contract (`AGENTS.md` §4 I4, `security-hardening.md` §12). Firebase Analytics was removed for exactly this reason. |
| **Ads or sponsored placements** | In an app that controls your PC. No. |
| **Always-on screen monitoring / employee surveillance** | The technology could do it; the product must not. Add an explicit anti-surveillance position to the README: a persistent on-screen indicator whenever capture is active (the recording overlay exists precisely for this), and no stealth mode. This is a values commitment, and writing it down is what makes it stick. |
| **Bypassing OS security prompts** | Wayland portals, macOS TCC, Android permissions. These are the platform telling the user the truth. Working around them would make CYPHER behave like malware. |

---

## 4. Two ideas worth their own section

### 4.1 The guest link, done properly

CYPHER already has the right primitives and nobody has noticed how good they are:
`secrets.token_urlsafe(32)`, expiry, per-session folder allowlists, access
logging with a bounded tail, a cleanup thread.

Wired up correctly, "share a folder with someone for 30 minutes without giving
them your PC" is a **category-defining** capability:

- A landlord shares the utility bills folder with an accountant for a day.
- A photographer shares a proofing folder with a client for an hour, read-only.
- A teacher collects assignments into a drop folder from a classroom of phones.
- A family member grabs one photo album without touching anything else.

No alternative does this without an account, a cloud, or full remote-desktop
access. It is the strongest differentiated feature in the product, and it was
**completely broken until Phase 0** (audit F-02 — every guest route returned
HTTP 500 from an unimported module).

What it needs: the sandbox (P1-S2), read-only by default, a persistent on-node
indicator while a guest session is live, tight rate limiting, no leakage of
sibling folder names or system info, and a UI that makes scope and expiry obvious
to the person *creating* the link.

### 4.2 Anti-surveillance as a feature

A remote-control tool is dual-use by nature: the same capability that lets you
pause a movie from the sofa lets a stalker watch a screen. The market's default
answer is to ignore this. CYPHER's should be the opposite, and it is cheap:

- **A persistent, non-dismissable on-screen indicator** whenever the screen is
  captured, streamed or recorded. `recording_overlay.py` already exists and was
  deliberately preserved in the Phase 0 cleanup for this reason. Extend it to
  streaming and screenshots, and port it natively (P3-L4).
- **No stealth mode. Ever.** Not as a setting, not as a flag, not for "kiosk
  use". Say so in the README.
- **Capability scopes visible on both sides** (P2-S5) — the phone shows what it
  may do; the PC shows what each device may do.
- **A node-local kill switch**: one keystroke or tray click revokes every remote
  session instantly, with no confirmation dialog.
- **Pairing requires physical presence** at the PC to read the code. Preserve
  this. Never add "remote approve".
- **An explicit statement** in the README and the Play Store listing that CYPHER
  is not designed or licensed for covert monitoring.

This is not marketing. It is a design constraint that prevents a category of
harm, and it costs roughly three days of work on top of what is already planned.

---

## 5. Prioritisation

If the roadmap had to be reduced to five user-visible additions after security,
these are the ones:

1. **Multi-node** — because a single-PC remote control is a demo, and every real
   household has more than one machine.
2. **Transfer queue with resume** — because a file transfer that dies at 90% on a
   flaky WiFi link is the most likely reason someone uninstalls.
3. **The guest link, done properly** — because it is the only capability here that
   no alternative offers without a cloud account.
4. **Notification mirroring** — because users will compare against KDE Connect
   and notice its absence within a day.
5. **The CLI** — because it makes the API honest, is the best test harness
   available, and wins the developer audience that writes about tools like this.

Everything else in §3 is secondary to those, and everything in §3.3 is out.

---

## 6. How a feature gets added

1. Open a **feature request** issue (`.github/ISSUE_TEMPLATE/feature_request.yml`)
   — it asks, deliberately, for the *problem* and for the **security surface**.
2. A maintainer scores value / cost / risk against §1's two properties.
3. If it touches files, input, power, capture or the network, it must reference
   the security task that contains it, and must not be scheduled before it.
4. Accepted ideas get a task ID in [`ROADMAP.md`](../../ROADMAP.md) with an
   estimate. Ideas that are rejected get a comment saying why — including "this
   is §3.3", which is a legitimate and final answer.
5. Implementation follows [`AGENTS.md`](../../AGENTS.md) §8 (definition of done),
   which requires tests, docs and a `CHANGELOG.md` entry.
