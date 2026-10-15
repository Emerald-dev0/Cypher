# Positioning

## The one sentence

> **An authenticated, user-consented control channel between a phone and a PC
> that works without the internet.**

Every product decision should be testable against that sentence. If a proposal
requires an account, a cloud dependency, or a weakening of consent, it is not
CYPHER — it is something else wearing the name.

## The two properties that must not be traded away

**1. No cloud, no account.** The trust boundary is the local network and a code
the user read off their own screen. There is nothing to breach, nothing to
subpoena, nothing to bill, and no vendor sitting between a person and their own
machine. This is not a privacy feature bolted onto a product; it *is* the
product. See [`privacy.md`](privacy.md).

**2. Deep OS access, deliberately granted.** Files, input, power, processes,
screen. This is real control, not a notification mirror. Which is precisely why
the capability-scope work (roadmap P2-S5) matters more than any feature in the
backlog: depth without granularity is a liability.

## The gap being filled

| Alternative | What it costs the user |
| --- | --- |
| TeamViewer / AnyDesk | Account, vendor relay, internet dependency, free-tier nagging, a company that can see your sessions |
| KDE Connect | Closest peer; Linux-first, weaker on Windows, no deep file or power control |
| Chrome Remote Desktop | Google account, cloud relay, browser-bound |
| SSH + Termux | Real power, but a terminal — no file browser, no media, no screen |
| USB / Bluetooth | Slow, fiddly, one file at a time |
| Emailing yourself a file | The thing the landing page already mocks, correctly |

**CYPHER sits between KDE Connect and TeamViewer:** deeper than the former, more
private than the latter, easier than SSH.

That gap is real and it is narrow, which argues for **depth over breadth**. The
failure mode for a project like this is a long list of half-working features; the
success mode is file transfer, remote input and screen access that simply always
work, on every transport, including a flaky one.

## The honest status

CYPHER is **pre-1.0 in substance and post-1.0 in marketing**. Version stamps say
`1.0.0`; an October 2026 audit found the node would not start on Python 3.11, two
whole features returned HTTP 500 on every request, and a public authentication
token committed to the repository
([`../AUDIT.md`](../AUDIT.md)).

That is why the roadmap has a **public-security gate**: the project is not
announced, listed or promoted until Phase 1 closes. Publishing a remote-control
tool with an open filesystem sandbox would expose every early adopter's machine,
and a first impression of "this thing got my PC compromised" is unrecoverable.

Say what it is, say what it is not yet, and say when it will be. A small honest
audience is worth more than a large surprised one.

## Voice

- Plain, concrete, no jargon. "Move a photo from your phone to your PC without a
  cable" beats "seamless cross-device interoperability".
- Honest about limits. "Works on your LAN. Not over the internet — yet, and only
  through a relay you can host yourself."
- Confident about the security posture, without being smug. State the controls,
  name the open items, link to the roadmap.
- Never promise what the code does not do. The deleted `SYSTEM_AUDIT.md` claimed
  "COMPLETE & PRODUCTION-READY" while the backend failed to parse. That document
  cost more trust than any competitor could.

## Anti-positioning

Equally important. CYPHER is **not**:

- a cloud storage or sync service — see
  [`features-and-applications.md`](features-and-applications.md) §3.3
- a surveillance or employee-monitoring tool — see §4.2 of the same document
- a TeamViewer replacement for supporting *other people's* computers at scale
- a game-streaming platform (latency and codec budgets are different)
- an MDM or fleet-management system

Each of those is a plausible feature request and a plausible revenue stream, and
each would require giving up one of the two properties above. Declining them is
the strategy, not a limitation of it.
