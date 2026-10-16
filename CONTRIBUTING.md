# Contributing to CYPHER

Thanks for being here. CYPHER is a remote-control system that people install on
machines holding their private files, so contributions are reviewed against a
higher bar than usual — not because we doubt you, but because the blast radius of
a bad merge is someone's PC.

**Start with [`AGENTS.md`](AGENTS.md).** It is the technical contract: repo map,
commands, invariants, known traps, and the definition of done. This file covers
the process around it.

---

## Before you start

1. **Read [`ROADMAP.md`](ROADMAP.md).** If your idea is already a task, comment
   on it so work is not duplicated. If it is not, open a feature request first —
   we would rather scope it with you than review a large surprise.
2. **Check [`docs/AUDIT.md`](docs/AUDIT.md).** It records 43 defects, 21 of which
   are still open, and explains why each happened. Several look like good ideas
   until you read the finding.
3. **Security-sensitive change?** Read
   [`docs/plans/security-hardening.md`](docs/plans/security-hardening.md) and
   [`SECURITY.md`](SECURITY.md) first. If you found a vulnerability rather than
   wanting to fix one, use the private channel in `SECURITY.md` — **not** a PR.
4. **Small PRs.** One logical change. A 900-line PR touching auth, UI and
   packaging will be asked to split, which wastes everyone's time.

---

## Development setup

### Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.11 **and** 3.12 | CI runs both. 3.12-only code has broken the build before — see `AGENTS.md` §6. |
| Flutter | 3.27.x stable | Pinned in `.github/workflows/*.yml`; match it. |
| Java (JDK) | 17 | Android Gradle build |
| Git | recent | `git filter-repo` knowledge helps for P1-B1 |

Windows-only extras (for node development): a Windows 10/11 machine or VM. The
node's input, capture, audio and window features cannot be exercised on Linux or
macOS, and CI cannot test them either — so say what you verified manually.

### Get going

```bash
git clone https://github.com/Emerald-dev0/Cypher.git
cd Cypher

# Node
cd pc_app_flutter/backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python service.py                                    # starts the node on :5000

# Mobile client
cd ../../mobile_app
flutter pub get
flutter run

# Desktop shell
cd ../pc_app_flutter
flutter pub get
flutter run -d windows     # or -d linux
```

Android release signing needs `mobile_app/android/key.properties` — copy from
`key.properties.example`. Without it, release builds fall back to the debug
keystore with a warning, which is fine for development and rejected by CI for
release.

### Run what CI runs

```bash
# Node
ruff check pc_app_flutter/backend
(cd pc_app_flutter/backend && python -m compileall -q core && pytest tests -q)

# Clients
(cd mobile_app      && flutter analyze --fatal-infos && dart format --set-exit-if-changed lib test && flutter test)
(cd pc_app_flutter  && flutter analyze --fatal-infos && dart format --set-exit-if-changed lib test && flutter test)

# Repo hygiene
git ls-files | grep -E '(^|/)build/|\.idea/|google-services\.json|\.artifact\.md$' && echo "FAIL" || echo "clean"
```

---

## Making a change

### Branches and commits

```bash
git checkout -b fix/pairing-throttle      # type/short-description
```

Conventional Commits, with the component as scope:

| Prefix | Scope examples | Use |
| --- | --- | --- |
| `feat` | `node`, `mobile`, `desktop`, `relay`, `cli` | New capability |
| `fix` | as above | Bug fix |
| `security` | as above | A vulnerability fix — will be called out in `CHANGELOG.md` |
| `refactor` | as above | No behaviour change |
| `perf` | as above | Measurable improvement; include the numbers |
| `docs` | — | Documentation only |
| `ci` | — | Workflows, Dependabot |
| `test` | — | Tests only |
| `chore` | `deps` | Tooling, dependencies |

```
fix(node): throttle pairing attempts per source IP

A 6-digit code is a 10^6 keyspace. Without a limit, an attacker on the
LAN could exhaust it in minutes with parallel requests.

Adds a 5-per-5-minute window and a 15-minute lockout, checked before the
code comparison so a correct guess during lockout is still refused. The
code now rotates on every successful pairing, and comparison is
constant-time.

Closes #123
```

Explain **why**, not what — the diff already shows what.

### Pull requests

Use the template. The two questions that matter most:

- **What did you actually run, and on which OS?** Reading the code is not
  verification. `docs/AUDIT.md` §4 documents a file called
  `FEATURE_VERIFICATION.md` that described real code paths accurately and
  claimed two completely broken features were "WORKING ✅".
- **Does this change an auth decision, a filesystem path check, or a network
  listener?** If yes, a test in `backend/tests/test_security.py` is required,
  not optional (`AGENTS.md` §7).

A good PR:

- [ ] Passes CI.
- [ ] Has tests for new behaviour, especially security-relevant behaviour.
- [ ] Adds no `Color(0x…)` literal, no `print()`, no top-level Windows import.
- [ ] Adds no secret, no telemetry, no unauthenticated route.
- [ ] Uses the sandbox helper for any filesystem access (`AGENTS.md` §4 I3).
- [ ] Updates `CHANGELOG.md` for user-visible changes.
- [ ] Updates `docs/` for architecture or protocol changes.
- [ ] Updates `ROADMAP.md` if it completes or invalidates a planned item.
- [ ] Updates `NOTICE` if a dependency was added or removed.

### Review

A maintainer reviews for correctness, security and fit with
[`AGENTS.md`](AGENTS.md). Expect questions about failure modes — what happens
when the node is unreachable, when a path is outside the sandbox, when a
dependency is missing, when the user is on Wayland.

Review is not adversarial. If a comment is unclear, say so; if you disagree,
argue it. "Because the audit says so" is a starting point for a conversation,
not the end of one.

Merging is squash-only. The commit message becomes the history, so make the PR
title good.

---

## Areas that need help

Ranked by how much they unblock everything else. All are in
[`ROADMAP.md`](ROADMAP.md) with full detail.

| Area | Tasks | Good first contribution? |
| --- | --- | --- |
| **Filesystem sandbox** | P1-S2 | ❌ Security-critical, needs deep review |
| **Node test suite** | P1-T1 | ✅ Great entry point — you learn the codebase by testing it |
| **Design-token migration** | P2-M2 | ✅ Mechanical, reviewable in small chunks, high visible impact |
| **Error/empty/offline states** | P2-M5 | ✅ Self-contained per screen |
| **Linux: files, transfers, monitoring** | P3-L1, P3-L5 | ✅ Pure `psutil`; no platform-specific code needed |
| **Linux: Wayland capture** | P3-L3 | ❌ PipeWire/portal expertise required — but very welcome if you have it |
| **CLI client** | P3-C1 | ✅ Well-bounded, and it doubles as an API test harness |
| **Accessibility** | P2-M8 | ✅ TalkBack/semantics/contrast work |
| **Docs and troubleshooting** | P1-C3 | ✅ Especially from people who just went through setup |
| **Relay** | P5-* | ❌ Crypto and distributed systems; see the plan first |

Look for the `good first issue` and `help wanted` labels.

---

## Things that will get a PR closed

Not a judgement on you — just a short list, so nobody wastes a weekend.

- **Telemetry, analytics, crash upload, or any outbound beacon.** Forbidden by
  the product contract (`AGENTS.md` §4 I4). Firebase Analytics and an install
  beacon were both removed for this reason.
- **Hardcoded secrets, tokens or passwords.** Including "just for development".
- **A new unauthenticated endpoint** without explicit maintainer approval.
- **String-prefix path checks** instead of the sandbox helper.
- **Automatic privilege elevation.**
- **A dependency that is not Apache-2.0-compatible** without updating `NOTICE`.
- **Rewriting git history** without coordinating with maintainers.
- **A large speculative refactor** with no linked issue.

---

## Community

- **Discussions** — setup help, ideas, showing off what you built.
- **Issues** — bugs and tracked feature requests.
- **Private security advisories** — vulnerabilities only. See
  [`SECURITY.md`](SECURITY.md).

Please read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The short version: be
the person you would want reviewing your PR.

---

## Recognition

Contributors are credited in the release notes and in `CHANGELOG.md`. Security
reporters are credited in advisories (see `SECURITY.md`).

If you contribute substantially over time and want a maintainer role, say so.
This project needs more than one person who understands the auth layer.

---

## Dependabot (P1-B7)

Dependabot opens grouped PRs **Monday 06:00 UTC**. Triage that day:

1. Read the changelog for anything that touches auth, crypto, HTTP, or Flutter plugins.
2. Merge patch/minor if CI is green.
3. Major version bumps need a human and a `NOTICE` check for license changes.
