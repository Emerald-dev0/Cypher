# Cloud Relay Plan

**Roadmap phase:** P5-1 … P5-7 · target `v2.1.0`
**Decision (locked):** the cloud component is a **self-hostable relay**, not a
storage or account backend.
**Prerequisite:** Phase 2 transport security (P2-S1) and the threat model (P2-S7).

---

## 1. The problem, precisely

CYPHER works when the phone and the PC are on the same network. That covers most
real use — but the moments people remember are the ones it does not:

- The PC is at home; you are at the office and need a file from it.
- The PC is asleep and you want to wake it (Wake-on-LAN cannot cross a subnet).
- You are on mobile data in a taxi and want to lock the PC you left running.
- A friend needs one folder, and neither of you is on the same LAN.

Every one of those is a **NAT traversal** problem, not a data-storage problem.
The user does not want their files in someone else's cloud. They want their two
devices to find each other.

That distinction drives the whole design.

---

## 2. What the relay is — and is not

| ✅ The relay IS | ❌ The relay is NOT |
| --- | --- |
| A forwarding node for encrypted bytes between two devices that cannot reach each other | A storage backend |
| Self-hostable: one `docker compose up` | A required service |
| Off by default; the LAN path is bit-for-bit unchanged when it is disabled | On the critical path for local use |
| Able to see: connection metadata, timing, byte volume | Able to see: file contents, keystrokes, screen frames, clipboard, tokens |
| Identified by a URL the user chooses | Identified by an account |
| Optionally operated by Emerald as a free convenience | Required to be operated by Emerald |

**No account is ever needed for LAN use.** The relay must not become a login
wall. If a future hosted tier wants accounts, that is a separate product
decision layered on top of a relay that works without one.

**The LAN path must not depend on the relay.** If `relay.emerald.dev` is down,
local pairing, discovery, transfer and control must be completely unaffected.
Test this explicitly: a CI job that runs the full LAN flow with the relay
hostname pointed at a black hole.

---

## 3. Architecture

```
        ┌────────────────────────┐
        │   Relay (self-hosted   │
        │   or Emerald public)   │
        │                        │
        │  · no plaintext        │
        │  · no storage          │
        │  · no accounts         │
        │  · auth = node pubkey  │
        └───▲────────────────▲───┘
     tunnel │                │ tunnel
   (outbound only, both directions)
            │                │
   ┌────────┴──────┐  ┌──────┴─────────┐
   │  PC node      │  │  Phone client  │
   │  behind NAT A │  │  behind NAT B  │
   │  (or asleep)  │  │  on mobile data│
   └───────────────┘  └────────────────┘

   Payload: Noise_XX ciphertext. The relay forwards frames.
```

### 3.1 Both sides dial out

Neither device can accept an inbound connection — that is the entire problem. So
both maintain a **persistent outbound** connection to the relay, and the relay
splices the two streams. Outbound-only also means:

- No inbound firewall rule, no port forwarding, no router configuration. This is
  what makes it usable by non-technical people.
- The node never listens on a public interface. Its `0.0.0.0:5000` listener stays
  LAN-only; the relay tunnel is a separate outbound socket.
- NAT and carrier-grade NAT are traversed without help.

### 3.2 Registration

A node registers with a relay using its **long-term public key** (the same one
whose fingerprint is pinned at pairing, P2-S1):

```
node → relay:  REGISTER { node_pubkey, signature over relay challenge }
relay → node:  OK { node_id = BLAKE2s(node_pubkey)[0:8], keepalive_interval }
```

No email, no password, no username. The `node_id` is derived from the key, so it
is stable across restarts and cannot be squatted.

A client that wants to reach a node presents the `node_id` it learned at pairing:

```
client → relay:  CONNECT { node_id, client_pubkey, signature }
relay  → node:   INCOMING { connection_id, client_pubkey }
node   → relay:  ACCEPT { connection_id } | REJECT { reason }
relay:           splices the two streams
```

**The node decides.** A relay cannot force a connection onto a node. The node
shows the incoming request in its Security console with the client's fingerprint
and the operator can reject or accept — and can require confirmation for unknown
clients while auto-accepting known ones.

### 3.3 The relay never terminates crypto

Payload is `Noise_XX_25519_ChaChaPoly_BLAKE2s` end-to-end between client and node
(P5-1). The relay:

- cannot read the payload (no key),
- cannot modify it without breaking the MAC,
- cannot impersonate either side (mutual authentication via static keys),
- **can** observe: which `node_id`s exist, when they connect, byte volumes,
  timing, and which clients talk to which nodes.

That last line is the honest limit of the design and must appear in
`docs/product/privacy.md` and in the relay's own README. Traffic analysis is
real. The mitigation is self-hosting: a relay you run learns nothing about you
that you do not already know.

### 3.4 Direct connection preference

Relaying costs bandwidth and adds latency, so it is a fallback, not a default:

```
1. mDNS / UDP beacon on the LAN      ← if this works, never touch the relay
2. STUN-assisted hole punching       ← direct peer-to-peer, relay not in path
3. Relay forwarding                  ← last resort
```

The client races 1 and 2 with a short timeout and upgrades to 3 only on failure.
Once a direct path is established mid-session, migrate to it and tear down the
tunnel.

**The UI must show which path is in use.** A badge reading
`via relay: relay.example.com` whenever traffic is not direct is non-negotiable —
a user who believes they are on the LAN while traffic crosses a third party has
been deceived by their own software.

---

## 4. Wake-on-LAN through the relay

The killer feature, and the hardest constraint: **the PC is off.** A tunnel
cannot reach a powered-down machine.

Options, in order of practicality:

| Approach | How | Limits |
| --- | --- | --- |
| **Keep the node alive in a low-power state** | Modern standby (S0ix) on Windows, or a sleep state that keeps the NIC powered; the node holds the tunnel with minimal duty cycle | Not available on all hardware; battery cost on laptops |
| **WoL from a second always-on device** | A Raspberry Pi, router, or NAS on the LAN runs a tiny relay agent that listens for a wake command and emits the magic packet locally | Needs a second device — but many target users already have one |
| **NIC-level WoL trigger** | Some NICs wake on a magic packet from any source; the relay would need to be on the LAN, which defeats the purpose | Not usable remotely |
| **Smart plug + BIOS "restore on AC loss"** | The relay tells a smart plug to cycle power; the BIOS boots the machine | Clunky, but genuinely works and needs no software on the PC |

**Recommendation:** implement the WoL *forwarding* path (relay → LAN agent →
magic packet) and document the modern-standby option. Do **not** promise remote
wake from a fully powered-off state without a helper device; that is a lie the
product cannot keep, and it is the most-likely feature request to be
over-promised.

The node already implements `/wol` (magic packet to a MAC on the local
broadcast). The relay work is exposing that endpoint to a LAN-side agent and
letting a remote client trigger it.

---

## 5. Relay implementation

### 5.1 Stack

| Concern | Choice | Why |
| --- | --- | --- |
| Language | **Rust** (tokio + tungstenite) or Go | Rust preferred: memory safety matters in an internet-facing forwarder, and the performance ceiling is higher. Go is acceptable if the maintainers know it better — a relay nobody can audit is worse than a slower one. |
| Transport | WebSocket over TLS, with a raw TCP fallback | WebSocket traverses corporate proxies that block raw TCP; the fallback avoids the overhead where it is not needed |
| Crypto | `snow` (Rust) / `Noise` implementations, `Noise_XX_25519_ChaChaPoly_BLAKE2s` | Same handshake as the LAN path — one implementation to audit |
| Storage | **None.** In-memory connection table only | A relay that persists anything becomes a target and a liability |
| State | Stateless across restarts; clients reconnect | Enables horizontal scaling and zero-downtime deploys |
| Scale-out | Consistent-hash on `node_id` at the load balancer so both ends of a pair land on the same instance | Avoids cross-instance splicing in the common case |

### 5.2 Hardening (it is internet-facing)

Non-negotiable before operating a public instance:

- **Per-IP and per-key rate limiting** on REGISTER and CONNECT.
- **Connection caps** per node and per IP; global connection ceiling.
- **Bandwidth accounting** with per-connection and per-node caps. An unmetered
  public relay *will* be used as a free CDN and a Tor exit node.
- **Idle timeouts** and keepalive enforcement; reap half-open tunnels.
- **Backpressure** — a slow consumer must not be able to exhaust relay memory.
  Bound every buffer; drop or stall, never grow unboundedly.
- **Amplification guard** — refuse to forward to a `node_id` that has not
  registered, and never reflect unauthenticated traffic.
- **No open-redirect / no arbitrary dialling** — the relay connects only to
  registered nodes, never to attacker-specified addresses. Otherwise it is an
  SSRF proxy into whoever's network hosts it.
- **Structured logging with retention limits.** Log `node_id`, byte counts and
  durations; never payload. Publish the retention period.
- **Observability:** Prometheus metrics on a private interface, health endpoint,
  graceful drain on shutdown.
- **A published abuse policy** and a way to block a key.

### 5.3 Self-hosting experience

The measure of "self-hostable" is whether a stranger can do it in one command:

```bash
docker run -d --name cypher-relay \
  -p 443:8443 \
  -v relay-certs:/certs \
  ghcr.io/emerald-dev0/cypher-relay:latest
```

Ship: a Dockerfile (multi-stage, distroless runtime, non-root user), a
`docker-compose.yml` with Caddy for automatic TLS, a Helm chart, and a `RELAY.md`
covering DNS, certificates, capacity sizing, and how to point a node at it.

The node setting is a **single URL field**. Empty means "LAN only, relay
disabled". That is the default.

---

## 6. Client and node integration

### 6.1 Node

- A `relay_client` module maintaining the outbound tunnel with exponential
  backoff and jitter.
- Enabled only when a relay URL is configured. Disabled ⇒ the module never
  initialises and never opens a socket.
- Incoming connection requests surface in the Security console with the client
  fingerprint; auto-accept policy is configurable per known device.
- The tunnel is **one capability among many**, so a node with no relay configured
  advertises `relay: false` and clients hide relay-dependent UI (P3-L1 pattern).

### 6.2 Mobile / desktop client

- Path badge on every screen that talks to a node: `LAN` · `Direct (P2P)` ·
  `Relay · <host>`.
- A per-node setting: `LAN only` / `Allow relay` / `Use this relay: <url>`.
- If the configured path fails, **do not silently fall back to a public relay.**
  Ask. Silent fallback would route a user's traffic through Emerald's
  infrastructure without consent — the exact behaviour Phase 0 removed.
- Offline queue for non-urgent commands (wake, lock) that can be delivered when
  the node next appears.

---

## 7. Trust and verification (P5-7)

A relay operator could, in principle, run a MITM if the client would accept any
certificate. It must not.

- The client pins the **node's** public key from pairing (P2-S1). The Noise
  handshake authenticates that key end-to-end regardless of what carries it.
- At pairing, the QR encodes the node fingerprint; the operator confirms it on
  the node's screen. That out-of-band check is what makes the relay untrustworthy
  by construction — it does not need to be trusted.
- The client displays the pinned fingerprint in node settings so a user can
  re-verify at any time, and warns loudly if a connection ever presents a
  different one.

**Test:** run the entire flow through a relay configured to actively attempt
MITM (substitute its own key). The connection must fail with a clear error, not
degrade.

---

## 8. Operating a public relay

If Emerald runs one, these decisions must be made *before* launch, not after:

| Question | Recommendation |
| --- | --- |
| Free or paid? | Free tier with a per-node monthly byte cap; a paid or self-host path for heavy use. An unmetered free relay is a liability, not a service. |
| Registration? | None. Key-based only. Adding accounts would break the "no account" contract. |
| Logging? | Connection metadata only, 7-day retention, published in the privacy policy. |
| Abuse? | A documented policy, a blocklist of keys, and a contact address. |
| Jurisdiction & disclosure? | State where it is hosted and what you would do with a legal request. |
| Shutdown plan | Announce well in advance; the product must remain fully functional LAN-only afterwards. This is the real test of "optional". |
| Capacity | Model it before launch. 10,000 nodes × 200 KB/h keepalive is already meaningful egress. |
| Status page | Yes — users need to distinguish "the relay is down" from "my PC is asleep". |

**Consider not operating one at all.** Shipping an excellent self-hostable relay
and a documented list of community instances is a defensible position that
carries no abuse liability, no bandwidth bill, and no privacy exposure. Decide
this deliberately; do not drift into running infrastructure.

---

## 9. What this explicitly does not include

Deliberately out of scope, and should stay that way:

- ❌ Cloud file storage or sync. Cypher is not Dropbox.
- ❌ Accounts, profiles, or a user database.
- ❌ Cross-device clipboard *history* stored server-side.
- ❌ Remote desktop rendering in a browser (that is a different product with a
  far larger attack surface).
- ❌ Team/organisation management, SSO, SCIM — unless a genuine B2B demand
  appears, and then only as an additive layer that does not touch the LAN path.
- ❌ Any telemetry about relay usage. Aggregate capacity metrics only, on the
  relay itself, never in the client.

Each of these would erode the local-first contract that is the product's entire
differentiation. See [`../product/features-and-applications.md`](../product/features-and-applications.md)
for the adjacent ideas that *are* worth pursuing.

---

## 10. Delivery order

| # | Task | Depends on | Est. |
| --- | --- | --- | --- |
| 1 | P5-1 Noise handshake in the node + client, LAN path first | P2-S1 | 10d |
| 2 | P2-S7 threat model, reviewed against §1 of `security-hardening.md` | — | 3d |
| 3 | P5-2 relay MVP: register, connect, splice, no persistence | 1, 2 | 12d |
| 4 | P5-5 Docker + compose + Helm + `RELAY.md` | 3 | 3d |
| 5 | P5-3 STUN direct-path preference; relay as fallback | 3 | 6d |
| 6 | P5-4 node relay client + client path badge + settings | 3 | 5d |
| 7 | P5-7 fingerprint verification UX + active-MITM test | 1, 6 | 4d |
| 8 | P5-6 public relay ops decision, ToS, capacity, abuse policy | 4 | 5d |
| 9 | WoL forwarding via a LAN agent | 6 | 5d |

**Total:** ~8 weeks. Do not start before Phase 2 closes — building a relay on
top of cleartext HTTP would mean relaying plaintext through third-party
infrastructure, which is worse than not having a relay at all.
