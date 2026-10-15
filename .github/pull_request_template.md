<!--
Thanks for the PR. Please read AGENTS.md §8 (definition of done) before
requesting review. Small, single-purpose PRs are reviewed far faster than large
ones.

Delete any section that genuinely does not apply — but do not delete the
"What did you actually run?" section. That one is mandatory.
-->

## What does this change?

<!-- One or two sentences. Link the issue or roadmap task. -->

Closes #
Roadmap task: <!-- e.g. P1-S2 — leave blank if none -->

## Why?

<!-- The problem, not the solution. If this fixes an audit finding, cite it
     (e.g. "audit F-02"). -->

## What did you actually run?

<!--
MANDATORY. "I read the code" is not verification.

docs/AUDIT.md §4 documents a file called FEATURE_VERIFICATION.md that described
real code paths accurately and claimed two completely broken features were
"WORKING ✅". This section exists so that never happens again.

State the OS, the transport, and what you observed. If you could not test
something, say so explicitly and why.
-->

| What | Platform / OS | Result |
| --- | --- | --- |
| <!-- e.g. Pair a device over USB tethering --> | <!-- Windows 11 24H2 + Android 15 --> | <!-- ✅ / ❌ / not tested --> |
| | | |

**Could not verify:** <!-- e.g. "Linux node — no Linux machine available" -->

## Security checklist

<!--
If ANY box below is checked "yes", a test in backend/tests/test_security.py is
required, not optional (AGENTS.md §7), and a maintainer must approve explicitly.
-->

- [ ] This changes an **authentication or authorization decision**.
- [ ] This adds or modifies a **filesystem path** check or a file route.
- [ ] This adds or modifies a **network listener**, binding, or CORS/Host policy.
- [ ] This adds a route to `public_endpoints` or `MEDIA_TOKEN_ROUTES`.
- [ ] This handles a **secret, token, key, or password**.
- [ ] This executes a **subprocess** or otherwise runs code.
- [ ] This changes **logging** in a way that could record sensitive content.
- [ ] This adds a **dependency**.

If any are checked, describe the abuse case you considered and how this PR
handles it:

<!-- e.g. "A paired device with only files.read scope calling /power/shutdown
     now gets 403 and the attempt is logged to the Security console. Test:
     test_scope_denies_power_for_files_only_device" -->

## Conventions

- [ ] `ruff check` and `ruff format --check` clean (node changes)
- [ ] `python -m compileall -q core` passes on **3.11 and 3.12** (node changes)
- [ ] `pytest tests -q` passes; new behaviour has a test
- [ ] `flutter analyze --fatal-infos` clean (client changes)
- [ ] `dart format --set-exit-if-changed lib test` clean
- [ ] `flutter test` passes
- [ ] No new `Color(0x…)` literal — design tokens only
- [ ] No `print()` — `debugPrint` or the logging facade
- [ ] No Windows-only module imported at module top level
- [ ] Filesystem access goes through the sandbox helper (AGENTS.md §4 I3)
- [ ] No new telemetry, analytics, or outbound beacon (AGENTS.md §4 I4)

## Documentation

- [ ] `CHANGELOG.md` updated — required for any user-visible change
- [ ] `docs/` updated — required for architecture or protocol changes
- [ ] `ROADMAP.md` updated — if this completes or invalidates a planned item
- [ ] `NOTICE` updated — if a dependency was added or removed
- [ ] `AGENTS.md` updated — if this changes an invariant or introduces a new trap

## Screenshots / recordings

<!-- Required for UI changes: before and after, in both light and dark theme.
     Blur anything identifying — machine names, file names, IPs. -->

## Notes for reviewers

<!-- Anything subtle, any trade-off you made, anything you would like a second
     opinion on. -->
