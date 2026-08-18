"""Tests for IntervalsClientWrapper, IntervalsClientCache, and get_intervals_wrapper.

The Intervals.icu network boundary is faked with httpx.MockTransport (see
conftest.make_intervals_wrapper / json_response), so these tests exercise the
wrapper's real URL/param construction, auth header, JSON handling, and
error-mapping logic against a fake server response — not against a hand-stubbed
wrapper method.
"""

import base64

import httpx
import pytest

from garmin_connect_mcp.intervals_auth import IntervalsConfig
from garmin_connect_mcp.intervals_client import (
    IntervalsAPIError,
    IntervalsAuthenticationError,
    IntervalsClientCache,
    IntervalsConfigError,
    IntervalsNotFoundError,
    IntervalsRateLimitError,
    get_intervals_wrapper,
)
from tests.conftest import json_response


class TestListActivities:
    def test_builds_the_expected_request_and_returns_parsed_json(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([{"id": "i1", "type": "Run"}])

        wrapper = make_intervals_wrapper(handler)

        result = wrapper.list_activities(oldest="2026-07-01", newest="2026-08-01", limit=10)

        assert result == [{"id": "i1", "type": "Run"}]
        request = requests[0]
        assert request.url.path == "/api/v1/athlete/i12345/activities"
        assert request.url.params["oldest"] == "2026-07-01"
        assert request.url.params["newest"] == "2026-08-01"
        assert request.url.params["limit"] == "10"
        scheme, _, encoded = request.headers["authorization"].partition(" ")
        assert scheme == "Basic"
        assert base64.b64decode(encoded).decode() == "API_KEY:test-api-key"

    def test_omits_none_valued_params_instead_of_sending_the_string_none(
        self, make_intervals_wrapper
    ):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([])

        wrapper = make_intervals_wrapper(handler)

        wrapper.list_activities(oldest="2026-07-01")

        assert "newest" not in requests[0].url.params
        assert "limit" not in requests[0].url.params

    def test_returns_empty_list_when_the_api_returns_no_body(self, make_intervals_wrapper):
        wrapper = make_intervals_wrapper(lambda request: httpx.Response(200))

        assert wrapper.list_activities(oldest="2026-07-01") == []


class TestGetActivity:
    def test_include_intervals_adds_the_query_param(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"id": "i55751783"})

        wrapper = make_intervals_wrapper(handler)

        result = wrapper.get_activity("i55751783", include_intervals=True)

        assert result == {"id": "i55751783"}
        assert requests[0].url.path == "/api/v1/activity/i55751783"
        assert requests[0].url.params["intervals"] == "true"

    def test_omits_the_intervals_param_by_default(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"id": "i55751783"})

        wrapper = make_intervals_wrapper(handler)

        wrapper.get_activity("i55751783")

        assert "intervals" not in requests[0].url.params


class TestWellness:
    def test_get_wellness_hits_the_single_date_endpoint(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"id": "2026-08-17", "ctl": 55.2, "atl": 60.1})

        wrapper = make_intervals_wrapper(handler)

        result = wrapper.get_wellness("2026-08-17")

        assert result == {"id": "2026-08-17", "ctl": 55.2, "atl": 60.1}
        assert requests[0].url.path == "/api/v1/athlete/i12345/wellness/2026-08-17"

    def test_list_wellness_hits_the_range_endpoint(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([{"id": "2026-08-16"}, {"id": "2026-08-17"}])

        wrapper = make_intervals_wrapper(handler)

        result = wrapper.list_wellness(oldest="2026-08-16", newest="2026-08-17")

        assert len(result) == 2
        assert requests[0].url.path == "/api/v1/athlete/i12345/wellness"
        assert requests[0].url.params["oldest"] == "2026-08-16"


class TestListEvents:
    def test_builds_the_expected_request(self, make_intervals_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([{"id": 1, "category": "WORKOUT"}])

        wrapper = make_intervals_wrapper(handler)

        result = wrapper.list_events(
            oldest="2026-08-18", newest="2026-08-24", category="WORKOUT,NOTE"
        )

        assert result == [{"id": 1, "category": "WORKOUT"}]
        request = requests[0]
        assert request.url.path == "/api/v1/athlete/i12345/events"
        assert request.url.params["category"] == "WORKOUT,NOTE"


class TestErrorMapping:
    @pytest.mark.parametrize(
        "status_code,expected_type",
        [
            (401, IntervalsAuthenticationError),
            (403, IntervalsAuthenticationError),
            (404, IntervalsNotFoundError),
            (429, IntervalsRateLimitError),
        ],
    )
    def test_maps_http_status_codes_to_the_right_exception(
        self, make_intervals_wrapper, status_code, expected_type
    ):
        wrapper = make_intervals_wrapper(lambda request: httpx.Response(status_code, text="nope"))

        with pytest.raises(expected_type):
            wrapper.list_activities(oldest="2026-07-01")

    def test_maps_other_status_codes_to_the_generic_api_error(self, make_intervals_wrapper):
        wrapper = make_intervals_wrapper(lambda request: httpx.Response(500, text="boom"))

        with pytest.raises(IntervalsAPIError, match="500"):
            wrapper.list_activities(oldest="2026-07-01")

    def test_maps_network_errors_to_api_error(self, make_intervals_wrapper):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("connection refused", request=request)

        wrapper = make_intervals_wrapper(handler)

        with pytest.raises(IntervalsAPIError, match="Network error"):
            wrapper.list_activities(oldest="2026-07-01")

    def test_maps_non_json_response_to_api_error(self, make_intervals_wrapper):
        wrapper = make_intervals_wrapper(
            lambda request: httpx.Response(200, text="<html>not json</html>")
        )

        with pytest.raises(IntervalsAPIError, match="valid JSON"):
            wrapper.list_activities(oldest="2026-07-01")


class TestIntervalsClientCache:
    def test_reuses_the_cached_wrapper_for_the_same_config(self, intervals_config):
        cache = IntervalsClientCache()

        first = cache.get_wrapper(intervals_config)
        second = cache.get_wrapper(intervals_config)

        assert first is second

    def test_builds_a_new_wrapper_when_config_changes(self, intervals_config):
        cache = IntervalsClientCache()
        other_config = IntervalsConfig(
            intervals_api_key="different-key", intervals_athlete_id="i12345"
        )

        first = cache.get_wrapper(intervals_config)
        second = cache.get_wrapper(other_config)

        assert first is not second


class TestIntervalsConfigToleratesUnrelatedEnvVars:
    """The .env is shared with GarminConfig (see tests/test_auth.py for the mirror
    case) — IntervalsConfig must equally tolerate keys it doesn't declare."""

    def test_ignores_unrelated_kwargs(self):
        # Passed via a dict, not literal kwargs: garmin_email isn't a field
        # IntervalsConfig declares, so pyright would (correctly) flag it as a literal kwarg.
        config = IntervalsConfig(
            **{"intervals_api_key": "test-api-key", "garmin_email": "unrelated@example.com"}
        )

        assert config.intervals_api_key == "test-api-key"
        assert not hasattr(config, "garmin_email")


class TestGetIntervalsWrapper:
    def test_raises_config_error_when_credentials_missing(self):
        with pytest.raises(IntervalsConfigError, match="not configured"):
            get_intervals_wrapper(IntervalsConfig())

    def test_returns_a_wrapper_when_credentials_are_present(self, intervals_config):
        wrapper = get_intervals_wrapper(intervals_config)

        assert wrapper.athlete_id == "i12345"
