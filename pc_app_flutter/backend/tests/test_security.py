"""
Security tests for the CYPHER node.

These are the controls that keep a stranger off someone's PC. Every one of them
regressed or was absent at some point — see docs/AUDIT.md §1. If you change an
authentication decision, a path check or a network listener, you must add a test
here (AGENTS.md §7).

Run:  pytest tests/test_security.py -v
"""

from __future__ import annotations

import hmac
import os
import secrets

import pytest

pytestmark = pytest.mark.security


# ═════════════════════════════════════════════════════════════
# 1. Authentication is on by default
# ═════════════════════════════════════════════════════════════

# Routes that MUST be reachable without a token. This is asserted as an exact
# set so that adding a route to `public_endpoints` — the change that turns an
# authenticated endpoint into an unauthenticated one — fails a test rather than
# shipping silently. See audit S-04 and roadmap P1-S3.
EXPECTED_PUBLIC_ENDPOINTS = {"ping", "system.get_status", "pairing.pair_device"}


class TestAuthenticationByDefault:
    def test_unauthenticated_request_to_a_protected_route_is_rejected(self, client):
        """No token => 401. This is the single most important assertion in the repo."""
        response = client.get("/processes")
        assert response.status_code == 401
        assert response.get_json()["success"] is False

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/system-stats"),
            ("GET", "/files/shared"),
            ("GET", "/clipboard/pc"),
            ("GET", "/paired-devices"),
            ("GET", "/security/sessions"),
            ("POST", "/power/shutdown"),
            ("POST", "/power/restart"),
            ("POST", "/power/lock"),
            ("POST", "/processes/kill"),
            ("POST", "/apps/launch"),
            ("POST", "/type"),
            ("POST", "/open-link"),
            ("POST", "/keyboard/hotkey"),
            ("POST", "/guest/create"),
            ("POST", "/unpair"),
            ("POST", "/wol"),
            ("DELETE", "/files/delete"),
        ],
    )
    def test_sensitive_routes_all_reject_anonymous_callers(self, client, method, path):
        """Enumerated deliberately: a new route must be added here on purpose."""
        response = client.open(path, method=method)
        assert response.status_code in (401, 403), (
            f"{method} {path} returned {response.status_code} for an anonymous "
            f"caller. If this route is meant to be public, add it to "
            f"EXPECTED_PUBLIC_ENDPOINTS and justify it in the PR."
        )

    def test_a_bogus_token_is_rejected(self, client):
        response = client.get(
            "/system-stats", headers={"X-Auth-Token": "not-a-real-token"}
        )
        assert response.status_code == 401

    def test_a_valid_token_is_accepted(self, client, paired_token):
        response = client.get(
            "/system-stats", headers={"X-Auth-Token": paired_token}
        )
        assert response.status_code == 200

    def test_the_internal_token_is_accepted(self, client, internal_token):
        response = client.get(
            "/system-stats", headers={"X-Auth-Token": internal_token}
        )
        assert response.status_code == 200

    def test_public_endpoint_set_is_exactly_as_documented(self, server):
        """Guards against silent widening of the unauthenticated surface.

        Audit S-04: the allowlist is keyed on view-function names, so renaming a
        handler silently changes what is public. This test fails on either drift.
        """
        assert set(server.PUBLIC_ENDPOINTS) == EXPECTED_PUBLIC_ENDPOINTS, (
            f"the unauthenticated surface changed: {set(server.PUBLIC_ENDPOINTS)}. "
            f"Adding a public endpoint on a node that can execute code requires "
            f"explicit maintainer approval (AGENTS.md §4 I1)."
        )

    def test_every_public_endpoint_actually_exists(self, server):
        """P1-S3: public-ness is a decorator on the view, not a name in a list.
        The documented set must equal the views that carry @public_route."""
        from core.auth import public_endpoint_names

        actual = public_endpoint_names(server.app.view_functions)
        assert actual == EXPECTED_PUBLIC_ENDPOINTS, (
            f"@public_route surface is {actual}, documented is {EXPECTED_PUBLIC_ENDPOINTS}"
        )

    def test_a_view_is_not_public_just_because_it_is_named_like_one(self, server):
        """The S-04 failure mode: a name-based allowlist treated `ping` as public
        even after the function was renamed. The decorator does not."""
        from core.auth import is_public_view

        assert is_public_view(server.app.view_functions["ping"]) is True
        assert is_public_view(server.app.view_functions["pairing.get_paired_devices"]) is False

    def test_media_token_route_names_all_exist(self, server):
        """Same failure mode, different list: a renamed streaming handler would
        silently start rejecting media elements with 401 (audit F-04)."""
        missing = server.MEDIA_TOKEN_ROUTES - set(server.app.view_functions)
        assert not missing, f"MEDIA_TOKEN_ROUTES names routes that do not exist: {missing}"

    def test_ping_is_public(self, client):
        assert client.get("/ping").status_code == 200

    def test_status_is_public_but_leaks_nothing_sensitive(self, client):
        """`/status` is public because discovery needs it. It must not become a
        reconnaissance endpoint."""
        body = client.get("/status").get_json()
        assert body["status"] == "online"
        forbidden = {"token", "internal_token", "pairing_code", "ip", "address"}
        assert not (forbidden & set(body)), f"/status leaked: {forbidden & set(body)}"

    def test_options_preflight_is_allowed_without_a_token(self, client):
        """CORS preflight must not be blocked, or browsers cannot reach the node."""
        response = client.options(
            "/system-stats",
            headers={"Origin": "http://localhost", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code != 401


# ═════════════════════════════════════════════════════════════
# 2. The internal token must never be a published constant
# ═════════════════════════════════════════════════════════════

class TestInternalToken:
    KNOWN_BAD_LITERALS = (
        "cypher-internal-pc-app-token-2024",
        "cypher-internal-pc-app-token",
        "internal-token",
    )

    def test_internal_token_is_not_the_published_literal(self, server):
        """Audit S-01. This literal was committed to a public repo and granted
        full remote control of every install. It must never come back."""
        assert server.INTERNAL_TOKEN not in self.KNOWN_BAD_LITERALS

    def test_internal_token_has_sufficient_entropy(self, server):
        assert len(server.INTERNAL_TOKEN) >= 32, (
            f"internal token is only {len(server.INTERNAL_TOKEN)} chars"
        )

    def test_internal_token_is_persisted_with_restrictive_permissions(self, server):
        """A world-readable loopback token is a local privilege escalation."""
        from core.utils import get_config_path

        token_file = get_config_path("internal_token")
        if not token_file.exists():
            pytest.skip("token file not persisted on this platform/config")

        if os.name != "posix":
            # `os.chmod` EXISTS on Windows — it is not a POSIX-only attribute —
            # so `hasattr(os, "chmod")` was the wrong guard and let the assertion
            # below run there. On Windows chmod only toggles the read-only bit and
            # st_mode reports 0o666 for an ordinary file, so the check failed on
            # windows-latest while the product code was behaving exactly as
            # documented. `os.name` is the idiom the rest of this suite already
            # uses (see test_sandbox.py).
            #
            # The token's protection on Windows is the inherited ACL on
            # %APPDATA%, not a mode bit. That is a real, if lower-severity,
            # difference and is recorded as audit S-19 rather than papered over.
            pytest.skip(
                "POSIX permission bits do not apply; Windows relies on the "
                "inherited %APPDATA% ACL (audit S-19)"
            )

        mode = token_file.stat().st_mode & 0o777
        assert mode & 0o077 == 0, (
            f"internal_token is mode {oct(mode)} — group/other can read it"
        )

    def test_two_fresh_nodes_would_get_different_tokens(self, server):
        """Proves the token is generated, not constant."""
        a = server._get_internal_token()
        # Delete the persisted file and regenerate.
        from core.utils import get_config_path

        token_file = get_config_path("internal_token")
        existing = token_file.read_text(encoding="utf-8") if token_file.exists() else None
        try:
            if token_file.exists():
                token_file.unlink()
            b = server._get_internal_token()
        finally:
            if existing is not None:
                token_file.write_text(existing, encoding="utf-8")

        assert a != b, "internal token did not change after regeneration"


# ═════════════════════════════════════════════════════════════
# 3. Pairing: brute force, entropy, single use
# ═════════════════════════════════════════════════════════════

class TestPairing:
    def _pair(self, client, code, device_id=None):
        return client.post(
            "/pair_device",
            json={
                "pairing_code": code,
                "device_id": device_id or f"dev-{secrets.token_hex(4)}",
                "device_name": "Test Phone",
            },
        )

    def test_correct_code_pairs_and_returns_a_token(self, client, server):
        response = self._pair(client, server.PAIRING_CODE)
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert len(body["token"]) >= 32

    def test_wrong_code_is_rejected(self, client, server):
        wrong = "000000" if server.PAIRING_CODE != "000000" else "000001"
        response = self._pair(client, wrong)
        assert response.status_code == 401
        assert response.get_json()["success"] is False

    def test_pairing_code_is_six_digits(self, server):
        assert server.PAIRING_CODE.isdigit()
        assert len(server.PAIRING_CODE) == server.PAIRING_CODE_LENGTH == 6

    def test_device_token_uses_a_cryptographic_source(self, client, server):
        """A predictable device token is equivalent to no authentication."""
        tokens = set()
        for _ in range(5):
            server.PAIRING_CODE = "123456"  # fixed so we isolate token generation
            body = self._pair(client, "123456").get_json()
            tokens.add(body["token"])
        assert len(tokens) == 5, "device tokens repeated — insufficient entropy"
        assert all(len(t) >= 32 for t in tokens)

    def test_code_rotates_after_a_successful_pairing(self, client, server):
        """Audit S-02 fix. A single-use code cannot be replayed or partially
        guessed across sessions."""
        before = server.PAIRING_CODE
        assert self._pair(client, before).status_code == 200
        assert server.PAIRING_CODE != before, "pairing code did not rotate"

    def test_the_rotated_code_cannot_be_replayed(self, client, server):
        old = server.PAIRING_CODE
        assert self._pair(client, old).status_code == 200
        assert self._pair(client, old).status_code == 401

    def test_missing_device_id_is_a_client_error(self, client, server):
        response = client.post(
            "/pair_device", json={"pairing_code": server.PAIRING_CODE}
        )
        assert response.status_code == 400

    def test_a_non_json_body_does_not_crash_the_node(self, client):
        """Audit: `request.json` raises 415 on a wrong Content-Type. A malformed
        request must produce a 4xx, never a 500."""
        response = client.post(
            "/pair_device", data="not json", content_type="text/plain"
        )
        assert response.status_code < 500


class TestPairingThrottle:
    """Audit S-02: a 10^6 keyspace with no limit is minutes of work for an
    attacker on the LAN. The throttle — not the code — is the boundary."""

    def test_attempts_are_limited_before_lockout(self, client, server):
        for attempt in range(server.PAIRING_MAX_ATTEMPTS):
            response = self._wrong_pair(client)
            assert response.status_code == 401, (
                f"attempt {attempt + 1} should be a normal 401, got "
                f"{response.status_code}"
            )

    def test_exceeding_the_limit_locks_out(self, client, server):
        for _ in range(server.PAIRING_MAX_ATTEMPTS):
            self._wrong_pair(client)

        response = self._wrong_pair(client)
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

    def test_the_correct_code_is_still_refused_during_lockout(self, client, server):
        """The throttle runs BEFORE the comparison. Without that ordering an
        attacker could guess the code while locked out and redeem it later."""
        for _ in range(server.PAIRING_MAX_ATTEMPTS):
            self._wrong_pair(client)
        assert self._wrong_pair(client).status_code == 429

        response = client.post(
            "/pair_device",
            json={
                "pairing_code": server.PAIRING_CODE,
                "device_id": "attacker",
                "device_name": "Attacker",
            },
        )
        assert response.status_code == 429, (
            "a correct code was accepted during lockout — the throttle must be "
            "checked before the comparison"
        )
        assert "attacker" not in server.paired_devices

    def test_lockout_is_logged_as_a_security_event(self, client, server):
        for _ in range(server.PAIRING_MAX_ATTEMPTS + 1):
            self._wrong_pair(client)

        events = [e for e in server.system_activity_log if e["category"] == "Security"]
        assert events, "the lockout was not logged — a control nobody can see is not a control"
        assert events[0]["is_urgent"] is True

    def test_a_successful_pairing_clears_the_counter(self, client, server):
        """A legitimate user who fat-fingers the code twice should not be
        penalised after they get it right."""
        self._wrong_pair(client)
        self._wrong_pair(client)
        assert client.post(
            "/pair_device",
            json={
                "pairing_code": server.PAIRING_CODE,
                "device_id": "legit",
                "device_name": "Legit",
            },
        ).status_code == 200
        assert server._pairing_attempts.get(client.environ_base.get("REMOTE_ADDR")) in (None, [])

    def _wrong_pair(self, client, server=None):
        return client.post(
            "/pair_device",
            json={"pairing_code": "000000", "device_id": "attacker", "device_name": "A"},
        )


# ═════════════════════════════════════════════════════════════
# 4. Secrets must not leak
# ═════════════════════════════════════════════════════════════

class TestNoSecretLeakage:
    def test_the_startup_banner_contains_no_secrets(self, server):
        """The `__main__` block used to print both secrets to stdout:

            print(f"PAIRING KEY: {PAIRING_CODE}")
            print(f"INTERNAL BYPASS TOKEN: {INTERNAL_TOKEN}")

        stdout is not private here. `backend_manager.dart` pipes the child
        process's stdout into the Flutter shell's log buffer; a Windows console
        window shows it to anyone who can see the screen; a service manager or CI
        job captures it to disk. A per-install token stored in a 0600 file is
        worthless if the same process then echoes it somewhere world-readable.

        Printing the pairing code is worse in one specific way: it defeats the
        whole point of a six-digit code, which exists so that pairing requires
        *visual or physical* proximity to the host. Shoulder-surfing a terminal is
        precisely the attack it is meant to stop.

        NOTE on why this test is written against a function. An earlier version
        asserted `server.INTERNAL_TOKEN not in capsys.readouterr().out` — which
        passed only because pytest never executes the `__main__` block, so the
        assertion was vacuously true and the leak stayed in the code. The banner is
        now `build_startup_banner()`, so the real output can be inspected.
        """
        banner = server.build_startup_banner("192.168.1.24")

        assert server.INTERNAL_TOKEN not in banner, "the auth token is printed"
        assert server.PAIRING_CODE not in banner, "the pairing code is printed"

        # Guard the guard: if either secret were an empty string the assertions
        # above would pass for the wrong reason.
        assert server.INTERNAL_TOKEN, "fixture did not generate an internal token"
        assert server.PAIRING_CODE, "fixture did not generate a pairing code"

        # The banner must still be useful — it tells the operator where to look.
        assert "192.168.1.24" in banner
        assert str(server.SERVER_PORT) in banner
        assert "internal_token" in banner

    def test_no_route_returns_the_internal_token(self, client, server, paired_token):
        """Belt and braces: even an authenticated caller should not be handed the
        bypass token by an endpoint. It is a loopback-only credential for the
        desktop shell and reaches it via the filesystem, not the API."""
        for path in ("/status", "/ping", "/connection-info", "/paired-devices",
                     "/system/activity", "/files/shared", "/history"):
            for headers in ({}, {"X-Auth-Token": paired_token}):
                response = client.get(path, headers=headers)
                if response.status_code == 200:
                    assert server.INTERNAL_TOKEN not in response.get_data(as_text=True), (
                        f"{path} leaked the internal token"
                    )

    def test_unauthorized_errors_do_not_echo_the_token(self, client):
        response = client.get(
            "/processes", headers={"X-Auth-Token": "leak-me-please"}
        )
        assert "leak-me-please" not in response.get_data(as_text=True)

    def test_the_pairing_code_is_not_exposed_to_anonymous_callers(self, client, server):
        for path in ("/status", "/ping", "/connection-info", "/paired-devices"):
            response = client.get(path)
            if response.status_code == 200:
                assert server.PAIRING_CODE not in response.get_data(as_text=True), (
                    f"{path} leaked the pairing code to an anonymous caller"
                )


# ═════════════════════════════════════════════════════════════
# 5. Revocation
# ═════════════════════════════════════════════════════════════

class TestRevocation:
    def test_unpairing_invalidates_the_token_immediately(
        self, client, paired_token, internal_token
    ):
        headers = {"X-Auth-Token": paired_token}
        assert client.get("/system-stats", headers=headers).status_code == 200

        assert client.post(
            "/unpair", json={"device_id": "test-device"},
            headers={"X-Auth-Token": internal_token},
        ).status_code == 200

        assert client.get("/system-stats", headers=headers).status_code == 401, (
            "a revoked device retained access"
        )

    def test_unpairing_an_unknown_device_is_not_an_error_that_leaks_state(
        self, client, internal_token
    ):
        response = client.post(
            "/unpair",
            json={"device_id": "does-not-exist"},
            headers={"X-Auth-Token": internal_token},
        )
        assert response.status_code == 404


# ═════════════════════════════════════════════════════════════
# 6. Comparison must be constant time
# ═════════════════════════════════════════════════════════════

class TestConstantTimeComparison:
    def test_the_pairing_route_uses_compare_digest(self):
        """A plain `==` short-circuits on the first differing character and leaks
        the code one digit at a time. Asserted textually because timing a single
        comparison reliably in CI is not practical."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "core" / "routes" / "pairing.py"
        ).read_text(encoding="utf-8")
        assert "hmac.compare_digest" in source, (
            "pairing no longer uses a constant-time comparison"
        )

    def test_hmac_is_imported(self, server):
        assert hmac.compare_digest("a", "a") is True
