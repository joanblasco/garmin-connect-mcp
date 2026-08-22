"""Tests for OpenMeteoClientWrapper and OpenMeteoClientCache.

The Open-Meteo network boundary is faked with httpx.MockTransport (see
conftest.make_open_meteo_wrapper / json_response), exercising the wrapper's real
URL/param construction and error-mapping logic against a fake server response.
"""

import httpx
import pytest

from garmin_connect_mcp.open_meteo_client import (
    OpenMeteoAPIError,
    OpenMeteoClientCache,
    OpenMeteoInvalidParamsError,
    OpenMeteoRateLimitError,
    get_open_meteo_wrapper,
)
from tests.conftest import json_response


class TestGetCurrent:
    def test_builds_the_expected_request_and_returns_parsed_json(self, make_open_meteo_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"current": {"temperature_2m": 22.5}})

        wrapper = make_open_meteo_wrapper(handler)

        result = wrapper.get_current(41.3874, 2.1686)

        assert result == {"current": {"temperature_2m": 22.5}}
        request = requests[0]
        # httpx normalizes an empty relative path against base_url with a trailing
        # slash — harmless in practice (verified against the real API too).
        assert request.url.path == "/v1/forecast/"
        assert request.url.params["latitude"] == "41.3874"
        assert request.url.params["longitude"] == "2.1686"
        assert "temperature_2m" in request.url.params["current"]
        assert request.url.params["timezone"] == "auto"


class TestGetForecast:
    def test_omits_hourly_param_by_default(self, make_open_meteo_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"daily": {}})

        wrapper = make_open_meteo_wrapper(handler)

        wrapper.get_forecast(41.3874, 2.1686)

        assert "hourly" not in requests[0].url.params
        assert requests[0].url.params["forecast_days"] == "7"

    def test_includes_hourly_param_when_requested(self, make_open_meteo_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"daily": {}, "hourly": {}})

        wrapper = make_open_meteo_wrapper(handler)

        wrapper.get_forecast(41.3874, 2.1686, forecast_days=3, include_hourly=True)

        assert "hourly" in requests[0].url.params
        assert requests[0].url.params["forecast_days"] == "3"


class TestErrorMapping:
    def test_maps_400_with_reason_to_invalid_params_error(self, make_open_meteo_wrapper):
        wrapper = make_open_meteo_wrapper(
            lambda request: httpx.Response(
                400, json={"error": True, "reason": "Latitude must be in range of -90 to 90°"}
            )
        )

        with pytest.raises(OpenMeteoInvalidParamsError, match="Latitude must be in range"):
            wrapper.get_current(999, 2.1686)

    def test_maps_429_to_rate_limit_error(self, make_open_meteo_wrapper):
        wrapper = make_open_meteo_wrapper(lambda request: httpx.Response(429, text="slow down"))

        with pytest.raises(OpenMeteoRateLimitError):
            wrapper.get_current(41.3874, 2.1686)

    def test_maps_other_status_codes_to_generic_api_error(self, make_open_meteo_wrapper):
        wrapper = make_open_meteo_wrapper(lambda request: httpx.Response(500, text="boom"))

        with pytest.raises(OpenMeteoAPIError, match="500"):
            wrapper.get_current(41.3874, 2.1686)

    def test_maps_network_errors_to_api_error(self, make_open_meteo_wrapper):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("connection refused", request=request)

        wrapper = make_open_meteo_wrapper(handler)

        with pytest.raises(OpenMeteoAPIError, match="Network error"):
            wrapper.get_current(41.3874, 2.1686)

    def test_maps_non_json_response_to_api_error(self, make_open_meteo_wrapper):
        wrapper = make_open_meteo_wrapper(lambda request: httpx.Response(200, text="<html></html>"))

        with pytest.raises(OpenMeteoAPIError, match="valid JSON"):
            wrapper.get_current(41.3874, 2.1686)


class TestOpenMeteoClientCache:
    def test_reuses_the_cached_wrapper_for_the_same_base_url(self):
        cache = OpenMeteoClientCache()

        first = cache.get_wrapper("https://api.open-meteo.com/v1/forecast")
        second = cache.get_wrapper("https://api.open-meteo.com/v1/forecast")

        assert first is second

    def test_builds_a_new_wrapper_when_base_url_changes(self):
        cache = OpenMeteoClientCache()

        first = cache.get_wrapper("https://api.open-meteo.com/v1/forecast")
        second = cache.get_wrapper("https://custom.example.com/v1/forecast")

        assert first is not second


class TestGetOpenMeteoWrapper:
    def test_never_raises_a_config_error(self):
        # There's nothing to misconfigure — this should always succeed.
        wrapper = get_open_meteo_wrapper()

        assert wrapper is not None
