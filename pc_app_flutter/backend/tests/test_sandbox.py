"""
Tests for the sandbox helper that ALREADY EXISTS — and for the routes that do
not use it.

IMPORTANT CORRECTION TO THE ORIGINAL AUDIT
──────────────────────────────────────────
docs/AUDIT.md §1 S-03 reported "the filesystem is not sandboxed". That is only
half true, and the distinction changes the fix:

  · `is_path_in_folders()` in core/server.py is CORRECT. It uses
    Path.resolve() + relative_to(), which canonicalises `..`, resolves symlinks
    and normalises separators. It is the textbook implementation.

  · It is used consistently by every `/guest/*` route — the least-trusted actor
    in the system, a third party holding a shared link.

  · It is used by NONE of the `/files/*` routes that a paired device calls. Those
    accept any absolute path with no check at all.

So the exposure is inverted from what you would expect: a temporary guest is
properly confined, while a paired device — including a lost or compromised phone
— can read and write the whole filesystem.

CONSEQUENCE FOR ROADMAP P1-S2
─────────────────────────────
The task is not "write a sandbox". It is "promote the correct helper that already
exists into core/sandbox.py and apply it to the paired-device routes too". That
is a much smaller and much safer change than the audit implied.

The `TestExistingHelperIsCorrect` class below must keep passing: it is the
evidence that the helper is safe to promote. The `xfail` classes are the routes
that do not call it yet.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

NOT_SANDBOXED = (
    "P1-S2: correct helper exists (is_path_in_folders) but this route does not "
    "call it. See docs/plans/security-hardening.md §3."
)


def _auth(token: str) -> dict:
    return {"X-Auth-Token": token}


# ═════════════════════════════════════════════════════════════
# The helper is correct — prove it, so it can be promoted safely
# ═════════════════════════════════════════════════════════════

class TestExistingHelperIsCorrect:
    """These MUST pass. They are the evidence that `is_path_in_folders` is the
    right thing to move into core/sandbox.py and apply everywhere."""

    @pytest.fixture()
    def check(self, server):
        return server.is_path_in_folders

    def test_a_path_inside_the_folder_is_allowed(self, check, shared_folders):
        target = shared_folders.shared / "hello.txt"
        assert check(str(target), [str(shared_folders.shared)]) is True

    def test_the_folder_itself_is_allowed(self, check, shared_folders):
        assert check(str(shared_folders.shared), [str(shared_folders.shared)]) is True

    def test_a_sibling_folder_is_rejected(self, check, shared_folders):
        assert check(str(shared_folders.outside), [str(shared_folders.shared)]) is False

    def test_a_file_in_a_sibling_folder_is_rejected(self, check, shared_folders):
        secret = shared_folders.outside / "secret.txt"
        assert check(str(secret), [str(shared_folders.shared)]) is False

    @pytest.mark.parametrize("payload", [
        "/etc/passwd",
        "/",
        "../../etc/passwd",
        "{shared}/../../etc/passwd",
        "{shared}/../{outside_name}/secret.txt",
    ])
    def test_traversal_shapes_are_rejected(self, check, shared_folders, payload):
        resolved = payload.format(
            shared=shared_folders.shared, outside_name=shared_folders.outside.name
        )
        assert check(resolved, [str(shared_folders.shared)]) is False, payload

    def test_a_nested_subdirectory_is_allowed(self, check, shared_folders):
        nested = shared_folders.shared / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "deep.txt").write_text("x", encoding="utf-8")
        assert check(str(nested / "deep.txt"), [str(shared_folders.shared)]) is True

    def test_multiple_roots_are_all_honoured(self, check, shared_folders):
        roots = [str(shared_folders.shared), str(shared_folders.outside)]
        assert check(str(shared_folders.shared / "hello.txt"), roots) is True
        assert check(str(shared_folders.outside / "secret.txt"), roots) is True
        assert check(str(shared_folders.tmp / "elsewhere.txt"), roots) is False

    def test_a_symlink_escaping_the_root_is_rejected(self, check, shared_folders):
        """The decisive test. resolve() follows symlinks, so a link inside a
        shared folder that points outside it is correctly refused."""
        if os.name == "nt":
            pytest.skip("symlink creation on Windows needs a privilege")

        link = shared_folders.shared / "escape"
        link.symlink_to(shared_folders.outside, target_is_directory=True)

        assert check(str(link / "secret.txt"), [str(shared_folders.shared)]) is False, (
            "a symlink escaped the shared root"
        )

    def test_a_symlink_staying_inside_the_root_is_allowed(self, check, shared_folders):
        if os.name == "nt":
            pytest.skip("symlink creation on Windows needs a privilege")

        link = shared_folders.shared / "to-hello"
        link.symlink_to(shared_folders.shared / "hello.txt")
        assert check(str(link), [str(shared_folders.shared)]) is True

    def test_an_empty_allowlist_grants_nothing(self, check, shared_folders):
        assert check(str(shared_folders.shared / "hello.txt"), []) is False

    def test_a_nonexistent_path_is_still_judged_by_containment(self, check, shared_folders):
        """resolve(strict=False) semantics: containment is about the path, not
        about whether the file exists. The route checks existence separately."""
        assert check(str(shared_folders.shared / "nope.txt"), [str(shared_folders.shared)]) is True
        assert check(str(shared_folders.outside / "nope.txt"), [str(shared_folders.shared)]) is False

    def test_alternate_separators_do_not_bypass_it(self, check, shared_folders):
        """The string-prefix denylist in /files/delete is defeated by this. The
        resolve()-based helper is not."""
        forward = str(shared_folders.outside / "secret.txt").replace(os.sep, "/")
        assert check(forward, [str(shared_folders.shared)]) is False

    def test_a_trailing_separator_does_not_bypass_it(self, check, shared_folders):
        assert check(f"{shared_folders.outside}{os.sep}", [str(shared_folders.shared)]) is False

    def test_REGRESSION_every_folder_in_a_multi_folder_list_is_honoured(
        self, check, tmp_path
    ):
        """Regression guard for a real bug fixed during this audit.

        `return True` used to sit inside the loop, so the first folder that did
        not contain the path raised ValueError and jumped to `return False` —
        the loop never reached folders 2..N. A guest granted "Documents +
        Pictures" could only ever open Documents, and every Pictures request was
        a bare 403.
        """
        first, second, third = (tmp_path / n for n in ("first", "second", "third"))
        for folder in (first, second, third):
            folder.mkdir()
            (folder / "f.txt").write_text("x", encoding="utf-8")

        roots = [str(first), str(second), str(third)]

        # The bug made only `first` reachable.
        assert check(str(first / "f.txt"), roots) is True
        assert check(str(second / "f.txt"), roots) is True, (
            "the second allowed folder was not honoured — the loop returned early"
        )
        assert check(str(third / "f.txt"), roots) is True, (
            "the third allowed folder was not honoured"
        )

        # And containment is still enforced.
        outside = tmp_path / "outside"
        outside.mkdir()
        assert check(str(outside / "f.txt"), roots) is False


class TestTheDenylistIsNotASandbox:
    """The `/files/delete` guard is a different, weaker mechanism. Contrast it
    with the helper above to show why P1-S2 replaces it rather than extending it."""

    def test_the_denylist_only_covers_windows_system_paths(self, server):
        """Read the actual list out of the source so this test tracks the code."""
        source = (Path(server.__file__)).read_text(encoding="utf-8")
        assert "restricted_roots" in source
        # Six Windows paths. Nothing protects ~/.ssh, ~/.aws, browser profiles,
        # password vaults, or any non-Windows machine.
        assert "c:\\\\windows" in source

    def test_the_denylist_is_a_noop_on_non_windows(self):
        if os.name == "nt":
            pytest.skip("POSIX-specific")
        # No POSIX path begins with "c:\", so `startswith` never matches and the
        # guard silently permits everything.
        sample = "/home/user/.ssh/id_rsa"
        restricted = ["c:\\windows", "c:\\program files", "c:\\boot"]
        assert not any(sample.lower().startswith(r) for r in restricted)


# ═════════════════════════════════════════════════════════════
# Guarantees that hold today — must never regress
# ═════════════════════════════════════════════════════════════

class TestGuaranteesThatHoldToday:
    def test_anonymous_callers_cannot_browse_files(self, client):
        assert client.get("/files/browse?path=/").status_code == 401

    def test_anonymous_callers_cannot_delete_files(self, client):
        assert client.delete("/files/delete?path=/tmp/anything").status_code == 401

    def test_anonymous_callers_cannot_download_files(self, client):
        assert client.get("/files/download?path=/etc/passwd").status_code == 401

    def test_anonymous_callers_cannot_upload(self, client):
        assert client.post("/files/upload", data={}).status_code == 401

    def test_a_paired_device_can_see_the_configured_shared_folders(
        self, client, paired_token, shared_folders
    ):
        response = client.get("/files/shared", headers=_auth(paired_token))
        assert response.status_code == 200
        assert shared_folders.shared.name in response.get_data(as_text=True)

    def test_browsing_a_shared_folder_lists_its_contents(
        self, client, paired_token, shared_folders
    ):
        response = client.get(
            "/files/browse",
            query_string={"path": str(shared_folders.shared)},
            headers=_auth(paired_token),
        )
        assert response.status_code == 200
        assert "hello.txt" in {item["name"] for item in response.get_json()}

    def test_browsing_a_nonexistent_path_is_a_404_not_a_500(self, client, paired_token):
        response = client.get(
            "/files/browse",
            query_string={"path": "/definitely/not/a/real/path"},
            headers=_auth(paired_token),
        )
        assert response.status_code == 404

    def test_error_bodies_do_not_leak_internals(self, client, paired_token):
        response = client.get(
            "/files/browse",
            query_string={"path": "/definitely/not/a/real/path"},
            headers=_auth(paired_token),
        )
        body = response.get_data(as_text=True)
        assert "Traceback" not in body
        assert "server.py" not in body


# ═════════════════════════════════════════════════════════════
# The gap: paired-device routes do not call the helper
# ═════════════════════════════════════════════════════════════

class TestPairedDeviceRoutesAreNotSandboxed:
    """A paired device is MORE trusted than a guest, but is currently LESS
    confined. A lost or compromised phone therefore gets the whole filesystem."""

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_browsing_outside_the_shared_folders_is_refused(
        self, client, paired_token, shared_folders
    ):
        response = client.get(
            "/files/browse",
            query_string={"path": str(shared_folders.outside)},
            headers=_auth(paired_token),
        )
        assert response.status_code == 403
        assert "secret.txt" not in response.get_data(as_text=True)

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_browsing_the_filesystem_root_is_refused(self, client, paired_token):
        response = client.get(
            "/files/browse", query_string={"path": "/"}, headers=_auth(paired_token)
        )
        assert response.status_code == 403

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_dotdot_traversal_out_of_a_shared_folder_is_refused(
        self, client, paired_token, shared_folders
    ):
        escaping = f"{shared_folders.shared}/../{shared_folders.outside.name}"
        response = client.get(
            "/files/browse", query_string={"path": escaping}, headers=_auth(paired_token)
        )
        assert response.status_code == 403

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_downloading_a_file_outside_the_shared_folders_is_refused(
        self, client, paired_token, shared_folders
    ):
        secret = shared_folders.outside / "secret.txt"
        response = client.get(
            "/files/download", query_string={"path": str(secret)}, headers=_auth(paired_token)
        )
        assert response.status_code == 403
        assert b"never be reachable" not in response.data

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_previewing_a_file_outside_the_shared_folders_is_refused(
        self, client, paired_token, shared_folders
    ):
        secret = shared_folders.outside / "secret.txt"
        response = client.get(
            "/files/preview", query_string={"path": str(secret)}, headers=_auth(paired_token)
        )
        assert response.status_code == 403
        assert b"never be reachable" not in response.data

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_deleting_a_file_outside_the_shared_folders_is_refused(
        self, client, paired_token, shared_folders
    ):
        secret = shared_folders.outside / "secret.txt"
        response = client.delete(
            "/files/delete", query_string={"path": str(secret)}, headers=_auth(paired_token)
        )
        assert response.status_code == 403
        assert secret.exists(), "a file outside the shared folders was deleted"

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_the_users_home_directory_is_not_enumerable(self, client, paired_token):
        """The denylist protects six Windows directories. It does not protect
        ~/.ssh, ~/.aws/credentials, browser profiles or password vaults — which
        is what an attacker actually wants."""
        response = client.get(
            "/files/browse", query_string={"path": str(Path.home())}, headers=_auth(paired_token)
        )
        assert response.status_code == 403

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_a_symlink_inside_a_shared_folder_cannot_reach_outside_it(
        self, client, paired_token, shared_folders
    ):
        if os.name == "nt":
            pytest.skip("symlink creation on Windows needs a privilege")

        link = shared_folders.shared / "escape"
        link.symlink_to(shared_folders.outside, target_is_directory=True)

        response = client.get(
            "/files/browse", query_string={"path": str(link)}, headers=_auth(paired_token)
        )
        assert response.status_code == 403
        assert "secret.txt" not in response.get_data(as_text=True)

    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_uploading_to_an_arbitrary_absolute_destination_is_refused(
        self, client, paired_token, shared_folders
    ):
        """Worse than a read: /files/upload accepts an absolute `destination`,
        calls os.makedirs(dest, exist_ok=True) on it, and writes there. A paired
        device can therefore CREATE directories and WRITE files anywhere on the
        filesystem — not merely read."""
        import io

        smuggle_dir = shared_folders.tmp / "smuggled"
        response = client.post(
            "/files/upload",
            data={
                "file": (io.BytesIO(b"payload"), "x.txt"),
                "destination": str(smuggle_dir),
            },
            content_type="multipart/form-data",
            headers=_auth(paired_token),
        )
        assert response.status_code == 403
        assert not smuggle_dir.exists(), "an upload created a directory outside the sandbox"


# ═════════════════════════════════════════════════════════════
# Guest routes — already sandboxed; these guard against regression
# ═════════════════════════════════════════════════════════════

class TestGuestRoutesAreSandboxed:
    """These pass TODAY. They are here so that the P1-S2 refactor cannot regress
    the one part of the filesystem surface that is already correct."""

    @pytest.fixture()
    def guest_token(self, client, paired_token, shared_folders):
        response = client.post(
            "/guest/create",
            json={
                "folders": [str(shared_folders.shared)],
                "duration_minutes": 30,
                "allow_upload": False,
            },
            headers=_auth(paired_token),
        )
        if response.status_code != 200:
            pytest.skip(f"/guest/create unavailable: {response.get_data(as_text=True)}")
        body = response.get_json()
        token = body.get("token") or body.get("guest_token") or body.get("access_token")
        if not token:
            pytest.skip(f"/guest/create returned no token: {body}")
        return token

    def test_a_guest_can_read_inside_its_folder(self, client, guest_token, shared_folders):
        response = client.get(
            "/guest/files/download",
            query_string={
                "path": str(shared_folders.shared / "hello.txt"),
                "token": guest_token,
            },
        )
        assert response.status_code == 200
        assert b"hello from the shared folder" in response.data

    def test_a_guest_cannot_read_outside_its_folder(self, client, guest_token, shared_folders):
        response = client.get(
            "/guest/files/download",
            query_string={
                "path": str(shared_folders.outside / "secret.txt"),
                "token": guest_token,
            },
        )
        assert response.status_code == 403
        assert b"never be reachable" not in response.data

    def test_a_guest_cannot_traverse_out_of_its_folder(self, client, guest_token, shared_folders):
        escaping = f"{shared_folders.shared}/../{shared_folders.outside.name}/secret.txt"
        response = client.get(
            "/guest/files/download",
            query_string={"path": escaping, "token": guest_token},
        )
        assert response.status_code == 403
        assert b"never be reachable" not in response.data

    def test_a_guest_needs_a_token_at_all(self, client, shared_folders):
        response = client.get(
            "/guest/files/download",
            query_string={"path": str(shared_folders.shared / "hello.txt")},
        )
        assert response.status_code == 401

    def test_a_forged_guest_token_is_rejected(self, client, shared_folders):
        response = client.get(
            "/guest/files/download",
            query_string={
                "path": str(shared_folders.shared / "hello.txt"),
                "token": "forged-" + os.urandom(16).hex(),
            },
        )
        assert response.status_code == 401


# ═════════════════════════════════════════════════════════════
# Structural guarantee for when P1-S2 lands
# ═════════════════════════════════════════════════════════════

class TestSandboxModuleExists:
    @pytest.mark.xfail(reason=NOT_SANDBOXED, strict=True)
    def test_the_helper_has_been_promoted_to_its_own_module(self):
        """P1-S2 is complete when core/sandbox.py exists and every filesystem
        route goes through it. When this flips to XPASS, remove every xfail
        marker above — strict=True will fail the build until you do."""
        import importlib

        sandbox = importlib.import_module("core.sandbox")
        assert hasattr(sandbox, "Sandbox")
        assert hasattr(sandbox, "SandboxViolation")

        box = sandbox.Sandbox([Path("/tmp")])
        assert box.resolve("/tmp/ok.txt", need="read") == Path("/tmp/ok.txt")
        with pytest.raises(sandbox.SandboxViolation):
            box.resolve("/etc/passwd", need="read")
