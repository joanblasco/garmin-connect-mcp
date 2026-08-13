"""Tests for GarminClientWrapper, including safe_call's JSON-safety normalization."""

import garminconnect
import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_connect_mcp.auth import GarminConfig
from garmin_connect_mcp.client import (
    GarminAPIError,
    GarminAuthenticationError,
    GarminClientCache,
    GarminClientInitError,
    GarminRateLimitError,
    _to_json_safe,
    init_garmin_client,
)


def _make_config(tmp_path, **overrides):
    """A GarminConfig with credential-login inputs, pointing token storage at tmp_path
    so tests never touch the real ~/.garminconnect directory."""
    defaults = {
        "garmin_email": "athlete@example.com",
        "garmin_password": "hunter2",
        "garmintokens": str(tmp_path / "tokens"),
        "garmintokens_base64": str(tmp_path / "tokens_base64"),
        "garmin_token_data": "",
    }
    defaults.update(overrides)
    return GarminConfig(**defaults)


class FakeHttpResponse:
    """Mimics garminconnect's internal EmptyJSONResp / requests.Response shape: not
    itself JSON-serializable, but exposes a .json() method that returns real data."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class BrokenJsonResponse:
    """A response-like object whose .json() call itself raises."""

    def json(self):
        raise ValueError("not actually JSON")


class TestToJsonSafe:
    def test_passes_through_plain_types_unchanged(self):
        for value in [{"a": 1}, [1, 2, 3], "text", 42, 3.14, True, None]:
            assert _to_json_safe(value) == value

    def test_calls_json_method_on_response_like_objects(self):
        response = FakeHttpResponse({"result": "ok"})

        assert _to_json_safe(response) == {"result": "ok"}

    def test_falls_back_to_str_when_json_method_raises(self):
        result = _to_json_safe(BrokenJsonResponse())

        assert isinstance(result, str)

    def test_falls_back_to_str_for_objects_without_json_method(self):
        class Opaque:
            def __repr__(self):
                return "<Opaque>"

        assert _to_json_safe(Opaque()) == "<Opaque>"


class TestSafeCallNormalization:
    def test_safe_call_normalizes_a_response_like_return_value(self, wrapper, client_stub):
        client_stub._method_results["delete_activity"] = FakeHttpResponse({})

        result = wrapper.safe_call("delete_activity", 123)

        assert result == {}

    def test_safe_call_passes_through_plain_dict_unchanged(self, wrapper, client_stub):
        client_stub._method_results["get_workout_by_id"] = {"workoutId": 1, "workoutName": "X"}

        result = wrapper.safe_call("get_workout_by_id", 1)

        assert result == {"workoutId": 1, "workoutName": "X"}

    def test_safe_call_still_raises_garmin_api_error_for_unknown_method(self, wrapper):
        try:
            wrapper.safe_call("this_method_does_not_exist")
            raise AssertionError("expected GarminAPIError")
        except GarminAPIError as e:
            assert "not found" in e.message


class TestInitGarminClient:
    """init_garmin_client() must raise GarminClientInitError with a message that
    carries the real reason, instead of swallowing it and returning None. The only
    network boundary exercised here is garminconnect.Garmin.login() itself, stubbed
    to fail the way Garmin's servers do."""

    def test_raises_client_init_error_on_authentication_failure(self, tmp_path, monkeypatch):
        def fail_login(self, *_args, **_kwargs):
            raise GarminConnectAuthenticationError("boom")

        monkeypatch.setattr(garminconnect.Garmin, "login", fail_login)

        with pytest.raises(GarminClientInitError, match="Garmin authentication failed: boom"):
            init_garmin_client(_make_config(tmp_path))

    def test_hints_at_known_upstream_issue_for_social_profile_failures(self, tmp_path, monkeypatch):
        def fail_login(self, *_args, **_kwargs):
            raise GarminConnectAuthenticationError("Failed to retrieve social profile")

        monkeypatch.setattr(garminconnect.Garmin, "login", fail_login)

        with pytest.raises(GarminClientInitError, match="python-garminconnect#369"):
            init_garmin_client(_make_config(tmp_path))

    def test_gives_generic_hint_for_other_authentication_failures(self, tmp_path, monkeypatch):
        def fail_login(self, *_args, **_kwargs):
            raise GarminConnectAuthenticationError("Username and password are required")

        monkeypatch.setattr(garminconnect.Garmin, "login", fail_login)

        with pytest.raises(GarminClientInitError) as exc_info:
            init_garmin_client(_make_config(tmp_path))

        message = str(exc_info.value)
        assert "python-garminconnect#369" not in message
        assert "re-authenticate with 'garmin-connect-mcp auth'" in message

    def test_raises_client_init_error_on_rate_limit(self, tmp_path, monkeypatch):
        def fail_login(self, *_args, **_kwargs):
            raise GarminConnectTooManyRequestsError("slow down")

        monkeypatch.setattr(garminconnect.Garmin, "login", fail_login)

        with pytest.raises(GarminClientInitError, match="rate-limited"):
            init_garmin_client(_make_config(tmp_path))

    def test_original_error_is_chained_and_preserved(self, tmp_path, monkeypatch):
        original = GarminConnectAuthenticationError("boom")

        def fail_login(self, *_args, **_kwargs):
            raise original

        monkeypatch.setattr(garminconnect.Garmin, "login", fail_login)

        with pytest.raises(GarminClientInitError) as exc_info:
            init_garmin_client(_make_config(tmp_path))

        assert exc_info.value.original_error is original
        assert exc_info.value.__cause__ is original


class TestGarminClientCache:
    """GarminClientCache sits directly on top of init_garmin_client, which is the
    boundary it's responsible for: whether to call it again or reuse what it already
    got. That boundary is stubbed here rather than going through a real login."""

    def test_reuses_cached_client_for_the_same_config(self, tmp_path, monkeypatch):
        calls = []

        def fake_init(config, prompt_mfa=None):
            calls.append(config)
            return object()

        monkeypatch.setattr("garmin_connect_mcp.client.init_garmin_client", fake_init)
        cache = GarminClientCache()
        config = _make_config(tmp_path)

        first = cache.get_client(config)
        second = cache.get_client(config)

        assert first is second
        assert len(calls) == 1

    def test_reauthenticates_when_config_changes(self, tmp_path, monkeypatch):
        calls = []

        def fake_init(config, prompt_mfa=None):
            calls.append(config)
            return object()

        monkeypatch.setattr("garmin_connect_mcp.client.init_garmin_client", fake_init)
        cache = GarminClientCache()

        first = cache.get_client(_make_config(tmp_path, garmin_email="a@example.com"))
        second = cache.get_client(_make_config(tmp_path, garmin_email="b@example.com"))

        assert first is not second
        assert len(calls) == 2

    def test_invalidate_forces_relogin_on_next_call(self, tmp_path, monkeypatch):
        calls = []

        def fake_init(config, prompt_mfa=None):
            calls.append(config)
            return object()

        monkeypatch.setattr("garmin_connect_mcp.client.init_garmin_client", fake_init)
        cache = GarminClientCache()
        config = _make_config(tmp_path)

        first = cache.get_client(config)
        cache.invalidate()
        second = cache.get_client(config)

        assert first is not second
        assert len(calls) == 2

    def test_does_not_cache_a_failed_login_attempt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "garmin_connect_mcp.client.init_garmin_client",
            lambda config, prompt_mfa=None: (_ for _ in ()).throw(GarminClientInitError("nope")),
        )
        cache = GarminClientCache()
        config = _make_config(tmp_path)

        with pytest.raises(GarminClientInitError):
            cache.get_client(config)

        # A later successful attempt isn't blocked by the earlier failure.
        monkeypatch.setattr(
            "garmin_connect_mcp.client.init_garmin_client",
            lambda config, prompt_mfa=None: "recovered-client",
        )

        assert cache.get_client(config) == "recovered-client"


class TestSafeCallInvalidatesCacheOnAuthError:
    """A live authentication failure from an already-cached client must invalidate
    the process-wide cache, so the next tool call re-authenticates instead of
    repeating the same stale-token failure forever."""

    def test_invalidates_cache_on_direct_authentication_error(
        self, wrapper, client_stub, monkeypatch
    ):
        invalidations = []
        monkeypatch.setattr(
            "garmin_connect_mcp.client.invalidate_cached_garmin_client",
            lambda: invalidations.append(True),
        )
        client_stub._method_results["get_stats"] = GarminConnectAuthenticationError("expired")

        with pytest.raises(GarminAuthenticationError):
            wrapper.safe_call("get_stats", "today")

        assert invalidations == [True]

    def test_invalidates_cache_on_401_flagged_connection_error(
        self, wrapper, client_stub, monkeypatch
    ):
        invalidations = []
        monkeypatch.setattr(
            "garmin_connect_mcp.client.invalidate_cached_garmin_client",
            lambda: invalidations.append(True),
        )
        client_stub._method_results["get_stats"] = GarminConnectConnectionError("401 Unauthorized")

        with pytest.raises(GarminAuthenticationError):
            wrapper.safe_call("get_stats", "today")

        assert invalidations == [True]

    def test_does_not_invalidate_cache_on_unrelated_errors(self, wrapper, client_stub, monkeypatch):
        invalidations = []
        monkeypatch.setattr(
            "garmin_connect_mcp.client.invalidate_cached_garmin_client",
            lambda: invalidations.append(True),
        )
        client_stub._method_results["get_stats"] = GarminConnectTooManyRequestsError("slow down")

        with pytest.raises(GarminRateLimitError):
            wrapper.safe_call("get_stats", "today")

        assert invalidations == []
