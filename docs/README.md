# CYPHER Documentation

**Start here.** Everything else in `docs/` is linked from this page.

| If you are… | Read |
| --- | --- |
| A **user** trying to install and pair | [`README.md`](../README.md) |
| A **user** whose connection is not working | `product/troubleshooting.md` — **not written yet (P1-C3)**; until then use [`AUDIT.md`](AUDIT.md) §8 and [`plans/test-matrix.md`](plans/test-matrix.md) |
| A **contributor** about to open a PR | [`AGENTS.md`](../AGENTS.md), then [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| A **maintainer** cutting a release | [`RELEASES.md`](RELEASES.md) |
| Someone who found a **vulnerability** | [`SECURITY.md`](../SECURITY.md) — private channel, not an issue |
| Curious **what is wrong and what is planned** | [`AUDIT.md`](AUDIT.md), then [`ROADMAP.md`](../ROADMAP.md) |

---

## Top level

| Document | What it is |
| --- | --- |
| [`../README.md`](../README.md) | User-facing entry point: what CYPHER does, how to install it, what it will not do |
| [`../AGENTS.md`](../AGENTS.md) | **The technical contract.** Repo map, commands, seven invariants, known traps, testing expectations, definition of done |
| [`../ROADMAP.md`](../ROADMAP.md) | Phased plan with stable task IDs. The single source of truth for project status |
| [`../CHANGELOG.md`](../CHANGELOG.md) | User-facing release history, Keep a Changelog format |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Setup, branch/commit conventions, PR expectations, areas needing help |
| [`../SECURITY.md`](../SECURITY.md) | Vulnerability reporting, scope, supported versions, security-relevant configuration |
| [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 plus project-specific expectations |
| [`../LICENSE`](../LICENSE) · [`../NOTICE`](../NOTICE) | Apache-2.0 and third-party attributions |
| [`RELEASES.md`](RELEASES.md) | How releases are cut, what the pipeline verifies, rollback, Play Store notes |
| [`AUDIT.md`](AUDIT.md) | The 2026-10 codebase audit: 43 findings with evidence, and what was fixed |

## `docs/architecture/`

How the system works. Update these when you change the design, in the same PR.

| Document | Contents |
| --- | --- |
| [`architecture/overview.md`](architecture/overview.md) | System design, components, data flow |
| [`architecture/pairing.md`](architecture/pairing.md) | The pairing protocol: code, handshake, token issuance |
| [`architecture/file-transfer.md`](architecture/file-transfer.md) | Chunked transfer protocol, progress, resume |
| [`architecture/design-system.md`](architecture/design-system.md) | Visual language: color, type, spacing, motion |
| `architecture/threat-model.md` | STRIDE across all transports — **P2-S7**, not yet written |
| `architecture/api.md` | The ~95 node endpoints — **P1-B4** generates this from the Blueprint split |

## `docs/plans/`

Forward-looking work. Each maps to roadmap task IDs.

| Document | Roadmap | Contents |
| --- | --- | --- |
| [`plans/security-hardening.md`](plans/security-hardening.md) | P1-S*, P2-S*, P3-S1 | Threat model, target auth, capability scopes, the filesystem sandbox, TLS, signed URLs, least privilege, rate limiting, audit logging, privacy |
| [`plans/rebuild-desktop-ui.md`](plans/rebuild-desktop-ui.md) | P1-D*, P2-D* | Desktop diagnosis, supervision contract, capability-driven UI, IA redesign, key screens, the Linux port, migration order |
| [`plans/rebuild-mobile-ui.md`](plans/rebuild-mobile-ui.md) | P2-M* | Mobile diagnosis, target layering, Riverpod migration, design-token fixes, screen inventory (25 routes → 16), key screens, migration order |
| [`plans/relay-cloud.md`](plans/relay-cloud.md) | P5-* | What the relay is and is not, architecture, Noise E2EE, self-hosting, WoL through a relay, operating a public instance |
| [`plans/cross-platform.md`](plans/cross-platform.md) | P3-L*, P4-* | Support matrix, the capability registry, Linux and Wayland specifics, packaging, iOS/macOS requirements, CI matrix |
| [`plans/test-matrix.md`](plans/test-matrix.md) | P1-T4 | The manual device/transport matrix that must be run before every release |

## `docs/product/`

Why the product is the way it is.

| Document | Contents |
| --- | --- |
| [`product/features-and-applications.md`](product/features-and-applications.md) | Personas, the competitive gap, a scored feature backlog, what to build, what to explore, **what to refuse**, and the anti-surveillance position |
| [`product/privacy.md`](product/privacy.md) | Exactly what data exists, where it lives, and what leaves the device. Feeds the Play Store Data Safety form |
| [`product/positioning.md`](product/positioning.md) | The one-sentence product, the two properties that must not be traded away |
| [`product/branding.md`](product/branding.md) | Name, logo, marks, and the fork-rebranding requirement under Apache-2.0 |
| `product/troubleshooting.md` | Connection and setup help — **P1-C3, not yet written.** Deliberately not linked from anywhere until it exists: the CI `docs` job fails on a relative link to a missing file, so a planned document must be named as text, not linked. |

---

## Documentation rules

These exist because the audit found 17 root-level markdown files, 12 of which
were point-in-time status reports that contradicted each other — including one
declaring the project "COMPLETE & PRODUCTION-READY" when the backend would not
parse on Python 3.11 and two entire features returned HTTP 500.

1. **One status document: `ROADMAP.md`.** No `*_STATUS.md`, no
   `FINAL_*.md`, no `*_VERIFICATION.md`. A closed issue is the record of
   completed work.
2. **Specs live in `docs/`,** not the repo root. The root holds `README.md`,
   `AGENTS.md`, `ROADMAP.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`,
   `CODE_OF_CONDUCT.md`, `LICENSE`, `NOTICE` — and nothing else.
3. **Reading code is not verification.** A document that claims a feature works
   must say what was *run*, on which OS. See
   [`../.github/pull_request_template.md`](../.github/pull_request_template.md).
4. **Update docs in the same PR as the change.** `AGENTS.md` §8 makes this part
   of the definition of done; CI fails on broken relative links.
5. **No AI scratch files.** `.artifacts/`, `*.artifact.md` and similar are
   git-ignored and blocked by a CI hygiene gate. Ten of them were committed here.
6. **Filenames are lowercase-kebab.** The deleted `File transfer protocol.md`,
   `Pairing Specification.md` and `UI Design System.md` had spaces in their
   names, which breaks links on some shells and hosting.

## Adding a document

Put it in the right directory, add it to the table above, and link it from
whatever should lead a reader to it. An unlinked document is an undiscoverable
one — and CI checks that relative links resolve, so a link to a file you forgot
to create will fail the build.
