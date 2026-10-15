# Cutting a Release

Releases are produced by [`release.yml`](../.github/workflows/release.yml) and
triggered by a **git tag**. Never create a GitHub Release by hand and never
upload a binary from a laptop — that is how an unsigned or debug-signed build
reaches users.

---

## 1. Prerequisites

### One-time repository setup

| Item | Where | Notes |
| --- | --- | --- |
| `ANDROID_KEYSTORE_B64` | Settings → Secrets → Actions | `base64 -w0 cypher-release.jks` |
| `ANDROID_SIGNING_STOREPASSWORD` | " | |
| `ANDROID_SIGNING_KEYALIAS` | " | |
| `ANDROID_SIGNING_KEYPASSWORD` | " | |
| `WINDOWS_CODESIGN_CERT_B64` *(optional)* | " | Authenticode PKCS#12 |
| `WINDOWS_CODESIGN_PASSWORD` *(optional)* | " | |
| `GITLEAKS_LICENSE` *(optional)* | " | Required for org repos; free for individuals |
| GitHub Pages enabled | Settings → Pages → Source: **GitHub Actions** | For `pages.yml` |
| Branch protection on `main` | Settings → Branches | Require CI, require review, no force-push |
| Private vulnerability reporting | Settings → Security | Enable; `SECURITY.md` links to it |

**Generate the Android key once and back it up offline.** Losing it means every
existing install can never be updated again:

```bash
keytool -genkey -v \
  -keystore cypher-release.jks \
  -keyalg RSA -keysize 4096 \
  -validity 9125 \
  -alias cypher
base64 -w0 cypher-release.jks   # → ANDROID_KEYSTORE_B64
```

`9125` days ≈ 25 years, which is the Play Store minimum. Store the `.jks` and
both passwords in a password manager **and** on offline media. Do not commit
them; `.gitignore` blocks `*.jks` and `key.properties`, and the CI hygiene job
fails the build if either appears.

---

## 2. The release process

### Step 1 — Decide the version

[SemVer](https://semver.org). `MAJOR.MINOR.PATCH`.

| Bump | When |
| --- | --- |
| `MAJOR` | A breaking change to the node ↔ client protocol, or to the public API of any package |
| `MINOR` | New capability, backwards compatible |
| `PATCH` | Fixes only |
| `-rc.N` / `-beta.N` | A pre-release. Published as a GitHub pre-release and excluded from "latest". |

Security fixes are always at least a `PATCH`, and are released out of band —
do not wait for a feature batch.

### Step 2 — Bump every version stamp

The `preflight` job in `release.yml` extracts all four and **fails the release**
if any disagrees with the tag. Update them together:

| File | Field |
| --- | --- |
| `mobile_app/pubspec.yaml` | `version: X.Y.Z+<build>` |
| `pc_app_flutter/pubspec.yaml` | `version: X.Y.Z+<build>` |
| `pc_app_flutter/backend/metadata.json` | `app_version` |
| `pc_app_flutter/backend/cypher_installer.iss` | `AppVersion=` |

Increment the Android `+<build>` number on every release, including patches — the
Play Store requires a strictly increasing build number.

> **P1-B8** replaces this manual step with a single generated source of truth.
> Until then, the preflight gate is what stops drift.

### Step 3 — Update the changelog

`CHANGELOG.md`, Keep a Changelog format, **written for users**. Add a
`## [X.Y.Z] - YYYY-MM-DD` section with `Added` / `Changed` / `Fixed` /
`Security` / `Removed`. A `Security` entry should describe the *impact*, not the
mechanism, and link to the advisory.

### Step 4 — Verify the release blockers

- [ ] CI green on `main`.
- [ ] No open issue labelled `release-blocker`.
- [ ] No critical/high CVE in `pip-audit` / `flutter pub deps` output (P2-S8).
- [ ] `NOTICE` reflects the dependency set that actually shipped.
- [ ] **P1-B9 resolved:** no proprietary-license component bundled
      (currently `syncfusion_flutter_pdfviewer` — see `NOTICE`). Publishing a
      binary containing it violates our own Apache-2.0 licensing.
- [ ] The manual device matrix in [`plans/test-matrix.md`](plans/test-matrix.md)
      has been run for this version.
- [ ] For a security release: the advisory is prepared and scheduled to publish
      alongside.

### Step 5 — Tag

```bash
git checkout main
git pull --ff-only
git tag -s v1.2.0 -m "CYPHER 1.2.0"      # -s signs, if you have a GPG key
git push origin v1.2.0
```

Pushing the tag starts `release.yml`.

### Step 6 — Review the draft

The pipeline creates a **draft** release. Deliberately: a human checks it before
users see it.

- [ ] Every expected artefact is attached (see the table below).
- [ ] `SHA256SUMS.txt` is present and covers all artefacts.
- [ ] The Android artefact is **release-signed** — the pipeline asserts this and
      fails on a debug certificate, but confirm the log line
      `Release signature confirmed.`
- [ ] The generated notes read sensibly.
- [ ] The pre-release flag matches the tag (a `-rc.1` tag must be pre-release).
- [ ] The version in the release name matches the tag.

### Step 7 — Publish

```bash
gh release edit v1.2.0 --draft=false
```

Then:

- [ ] Publish the security advisory, if any (`gh api` or the Security tab).
- [ ] Upload the `.aab` to the Play Store internal track → production.
- [ ] Announce where the project announces things.

---

## 3. Artefacts produced

| Artefact | Platform | Contents |
| --- | --- | --- |
| `Cypher-Setup-<v>.exe` | Windows | Inno Setup installer; installs to `%LOCALAPPDATA%\CYPHER`, no admin needed |
| `cypher-desktop-<v>-windows-x64.zip` | Windows | Portable shell **with the node bundled** |
| `cypher-node-<v>-windows-x64.zip` | Windows | Headless node only |
| `cypher-desktop-<v>-linux-x64.tar.gz` | Linux | Portable shell with the node bundled |
| `cypher-node-<v>-linux-x64.tar.gz` | Linux | Headless node only |
| `cypher-<v>-android-universal.apk` | Android | Sideload, any ABI |
| `cypher-<v>-android-arm64-v8a.apk` | Android | Sideload, 64-bit ARM (smallest) |
| `cypher-<v>-android-armeabi-v7a.apk` | Android | Sideload, 32-bit ARM |
| `cypher-<v>-android-x86_64.apk` | Android | Sideload, emulator/Chromebook |
| `cypher-<v>-android.aab` | Android | Play Store upload bundle |
| `SHA256SUMS.txt` | — | Checksums for all of the above |

Every archive contains `LICENSE.txt` and `NOTICE.txt`, as Apache-2.0 §4 requires.

---

## 4. What the pipeline checks

`release.yml` is deliberately paranoid, because each of these caught a real
defect during the audit (see [`AUDIT.md`](AUDIT.md)):

| Check | Failure mode it prevents |
| --- | --- |
| Semver tag validation | A malformed tag producing a nonsense version |
| Version-stamp consistency | The mobile app claiming `2.0.0` while every artefact says `1.0.0` (audit A-05) |
| Signing secrets present | A 30-minute build ending in an unsigned artefact |
| Node tests before packaging | Shipping a binary whose module does not import (audit F-01, F-02, F-03) |
| `apksigner verify` / `keytool -printcert` | A debug-signed "release" (audit S-05) |
| Keystore destroyed in `if: always()` | A signing key persisting on a runner |
| Checksums generated and attached | Users unable to verify a download |
| Draft by default | An unreviewed artefact reaching users |

---

## 5. Rollback and hotfix

**A release cannot be un-published.** Users may already have downloaded it. So:

1. Cut a `PATCH` release with the fix. Do not edit or delete the bad tag.
2. If the bad release is actively harmful (a security regression, a build that
   corrupts data), mark it as pre-release and edit the body to say **DO NOT
   INSTALL — see v1.2.1**, then publish the fix immediately.
3. For a security issue, publish the advisory at the same time as the fix. Never
   before, and not weeks after.
4. Consider a forced-upgrade notice. For a remote-control tool an unpatched
   install is an active liability — `SECURITY.md` commits to this.

---

## 6. Troubleshooting the pipeline

| Symptom | Cause | Fix |
| --- | --- | --- |
| `preflight` fails on version drift | A stamp was not bumped | Update all four, re-tag (delete the tag first: `git push origin :refs/tags/v1.2.0`) |
| `preflight` fails on missing secrets | Signing secrets not configured | See §1 |
| Android job fails at "Verify release signing" | `key.properties` not written, or the wrong keystore | Check `ANDROID_KEYSTORE_B64` is the *whole* file, base64-encoded with no line wrapping |
| Node job fails on Linux but not Windows | A Windows-only import at module top level | Route it through a lazy loader (`AGENTS.md` §4 I6) |
| Node job fails on Python 3.11 only | 3.12-only syntax, e.g. a backslash in an f-string expression | Compute the value on its own line (audit F-01) |
| Desktop Linux job fails to find GTK | Missing apt packages | They are listed in the `Install Linux desktop toolchain` step |
| Inno Setup not found | The `choco install innosetup` step failed | Check runner image changes; pin the ISCC path |
| Release has no artefacts | `fail_on_unmatched_files: true` fired | An upstream build job silently produced nothing; check its upload step |
| Pages does not update | Pages source is not "GitHub Actions" | Settings → Pages |

---

## 7. Play Store notes

- Upload the `.aab`, never the `.apk`.
- `applicationId` is `io.github.emerald_dev0.cypher` and is **permanent** —
  changing it after the first upload breaks update continuity for every install.
  Decide before you publish (audit A-06).
- The Data Safety form must match [`product/privacy.md`](product/privacy.md).
  The honest answer for almost every question is "no data collected" — which was
  *not* true before Phase 0 removed Firebase Analytics and the install beacon.
- `MANAGE_EXTERNAL_STORAGE` triggers a permissions declaration and is frequently
  rejected. P2-M6 removes it in favour of SAF. Until then, expect to justify it.
- The app's category is Tools/Utilities, and the listing should state plainly
  that it is a remote-control tool for your **own** devices. See
  [`product/features-and-applications.md`](product/features-and-applications.md) §4.2
  for the anti-surveillance position.
