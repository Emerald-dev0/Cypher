"""
Guest session tests.

Guests are the least-trusted actor in the system: a link deliberately handed to a
THIRD PARTY. The GuestSession model was already well designed when audited —
secrets.token_urlsafe(32), expiry, per-session folder scoping, a bounded access
log, a cleanup thread, a lock. The bug was that the module was never imported at
module level, so all 14 call sites raised NameError and every guest route
returned HTTP 500 (audit F-02).

These tests exist so that regression cannot recur silently.

See docs/plans/security-hardening.md §6 for the full requirement set.
"""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture()
def manager():
    """A fresh GuestSessionManager, isolated from the module-level singleton so
    tests cannot leak sessions into each other."""
    from core.guest_manager import GuestSessionManager

    return GuestSessionManager()


class TestSessionCreation:
    def test_create_returns_a_token(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host-device")
        assert isinstance(token, str)
        assert len(token) >= 32

    def test_tokens_are_cryptographically_unique(self, manager):
        tokens = {manager.create_session(["/tmp/shared"], 30, "host") for _ in range(20)}
        assert len(tokens) == 20, "guest tokens collided — insufficient entropy"

    def test_session_validates_immediately(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        assert manager.validate_token(token) is not None

    def test_an_unknown_token_is_rejected(self, manager):
        assert manager.validate_token("not-a-real-guest-token") is None

    def test_an_empty_token_is_rejected(self, manager):
        assert manager.validate_token("") is None
        assert manager.validate_token(None) is None


class TestExpiry:
    def test_a_session_expires_on_time(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        session = manager.validate_token(token)
        # Force expiry rather than sleeping for 30 minutes.
        session.expires_at = session.expires_at - timedelta(minutes=31)
        assert session.is_expired() is True
        assert manager.validate_token(token) is None, "an expired guest token was still accepted"

    def test_a_fresh_session_is_not_expired(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        session = manager.validate_token(token)
        assert session.is_expired() is False

    def test_extend_pushes_the_deadline(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        before = manager.validate_token(token).expires_at
        manager.extend_session(token, 15)
        after = manager.validate_token(token).expires_at
        assert after > before

    def test_extending_an_unknown_token_does_not_raise(self, manager):
        assert manager.extend_session("nope", 15) is False

    def test_ending_a_session_revokes_it_immediately(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        assert manager.validate_token(token) is not None
        assert manager.end_session(token) is True
        assert manager.validate_token(token) is None

    def test_revocation_actually_revokes_access(self, manager):
        """REGRESSION — a real security bug found while writing this suite.

        end_session() set is_active = False, but validate_token() only checked
        is_expired(). So /guest/end reported success, the desktop Security tab
        dropped the session from its list, and the guest kept reading files until
        natural expiry. The host believed a third party had been cut off and they
        had not been.
        """
        token = manager.create_session(["/tmp/shared"], 30, "host")

        assert manager.validate_token(token) is not None, "precondition: guest has access"
        assert manager.end_session(token) is True, "end_session must report success"

        assert manager.validate_token(token) is None, (
            "the guest token still validates after the session was ended — "
            "revocation is not effective"
        )

    def test_a_revoked_session_disappears_from_the_active_list_too(self, manager):
        """The UI list and the auth check must agree. If they diverge, the host
        sees one thing and the node enforces another."""
        token = manager.create_session(["/tmp/shared"], 30, "host")
        assert len(manager.get_all_active_sessions()) == 1

        manager.end_session(token)

        assert manager.get_all_active_sessions() == []
        assert manager.validate_token(token) is None

    def test_a_revoked_session_cannot_be_extended_back_to_life(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        manager.end_session(token)
        assert manager.extend_session(token, 60) is False
        assert manager.validate_token(token) is None

    def test_a_revoked_session_cannot_log_access(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        manager.end_session(token)
        manager.log_guest_access(token, "/tmp/shared/a.txt", "download")
        assert manager.get_session(token).access_count == 0

    def test_remaining_time_counts_down(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        remaining = manager.validate_token(token).to_dict()["time_remaining_seconds"]
        assert 0 < remaining <= 30 * 60


class TestFolderScoping:
    """The security property that matters most: a guest sees ONLY what the host
    selected, and the enforcement must not be wider than the node's own sandbox.

    The session model stores the allowlist correctly today. The ROUTES that
    enforce it inherit the path-check weakness from audit S-03 — see
    test_sandbox.py. Fixing P1-S2 must not regress anything asserted here.
    """

    def test_the_session_carries_its_allowed_folders(self, manager):
        folders = ["/tmp/shared/photos"]
        token = manager.create_session(folders, 30, "host")
        assert manager.validate_token(token).allowed_folders == folders

    def test_two_sessions_do_not_share_scopes(self, manager):
        a = manager.create_session(["/tmp/a"], 30, "host")
        b = manager.create_session(["/tmp/b"], 30, "host")
        assert manager.validate_token(a).allowed_folders == ["/tmp/a"]
        assert manager.validate_token(b).allowed_folders == ["/tmp/b"]

    def test_an_empty_folder_list_grants_nothing(self, manager):
        token = manager.create_session([], 30, "host")
        assert manager.validate_token(token).allowed_folders == []

    def test_the_host_device_is_recorded(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host-device-42")
        assert manager.validate_token(token).host_device_id == "host-device-42"


class TestAccessLogging:
    def test_access_is_counted_and_logged(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        manager.log_guest_access(token, "/tmp/shared/a.txt", "download")
        session = manager.validate_token(token)
        assert session.access_count == 1
        assert session.access_log[-1]["action"] == "download"

    def test_the_access_log_is_bounded(self, manager):
        """A guest must not be able to grow node memory without limit by
        requesting files in a loop. to_dict() always sliced the tail for
        serialisation, but the underlying list was unbounded."""
        from core.guest_manager import GuestSession

        token = manager.create_session(["/tmp/shared"], 30, "host")
        for i in range(GuestSession.MAX_LOG_ENTRIES * 3):
            manager.log_guest_access(token, f"/tmp/shared/f{i}.txt", "browse")
        session = manager.validate_token(token)

        # The true total is still counted...
        assert session.access_count == GuestSession.MAX_LOG_ENTRIES * 3
        # ...but memory is bounded.
        assert len(session.access_log) <= GuestSession.MAX_LOG_ENTRIES, (
            f"access_log grew to {len(session.access_log)} entries"
        )

    def test_serialisation_does_not_leak_host_identity(self, manager):
        """to_dict() is returned by /guest/session to the GUEST — a third party.
        It must not reveal which device created the link."""
        token = manager.create_session(["/tmp/shared"], 30, "host-device-secret-id")
        payload = manager.validate_token(token).to_dict()
        assert "host_device_id" not in payload, (
            "the host device id is exposed to the guest"
        )
        assert "host-device-secret-id" not in str(payload)

    def test_serialisation_exposes_only_the_guests_own_scope(self, manager):
        """A guest may see the folders they were granted; never anyone else's."""
        mine = manager.create_session(["/tmp/mine"], 30, "host")
        manager.create_session(["/tmp/someone-elses"], 30, "host")
        payload = manager.validate_token(mine).to_dict()
        assert payload["allowed_folders"] == ["/tmp/mine"]
        assert "someone-elses" not in str(payload)

    def test_the_remaining_time_is_never_negative(self, manager):
        token = manager.create_session(["/tmp/shared"], 30, "host")
        session = manager.validate_token(token)
        session.expires_at = session.expires_at - timedelta(minutes=31)
        assert session.to_dict()["time_remaining_seconds"] == 0


class TestEnumeration:
    def test_sessions_can_be_listed_for_the_host(self, manager):
        manager.create_session(["/tmp/a"], 30, "host-1")
        manager.create_session(["/tmp/b"], 30, "host-2")
        all_sessions = manager.get_all_active_sessions()
        assert len(all_sessions) >= 2

    def test_sessions_can_be_filtered_by_host(self, manager):
        manager.create_session(["/tmp/a"], 30, "host-1")
        manager.create_session(["/tmp/b"], 30, "host-2")
        only = manager.get_all_active_sessions(host_device_id="host-1")
        assert len(only) == 1
        assert only[0]["allowed_folders"] == ["/tmp/a"]

    def test_a_host_cannot_see_another_hosts_sessions(self, manager):
        """Multi-device households: one paired phone must not be able to enumerate
        (or revoke) guest links created by a different phone."""
        manager.create_session(["/tmp/a"], 30, "host-1")
        assert manager.get_all_active_sessions(host_device_id="host-2") == []
