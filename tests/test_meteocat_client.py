"""Tests for MeteocatClientWrapper, MeteocatClientCache, and get_meteocat_wrapper.

The MeteoCat network boundary is faked with httpx.MockTransport. Unlike AEMET,
there's no two-step fetch here — a single request returns the real payload
directly — so this suite is deliberately simpler than test_aemet_client.py.
"""

import httpx
import pytest

from garmin_connect_mcp.meteocat_auth import MeteocatConfig
from garmin_connect_mcp.meteocat_client import (
    MeteocatAPIError,
    MeteocatAuthenticationError,
    MeteocatClientCache,
    MeteocatConfigError,
    MeteocatNotFoundError,
    MeteocatRateLimitError,
    get_meteocat_wrapper,
)


class TestMunicipalForecast:
    def test_builds_the_expected_request_and_returns_parsed_json(self, make_meteocat_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"forecast": "data"})

        wrapper = make_meteocat_wrapper(handler)

        result = wrapper.get_municipal_forecast("080193")

        assert result == {"forecast": "data"}
        assert requests[0].url.path == "/pronostic/v1/municipal/080193"
        assert requests[0].headers["x-api-key"] == "test-api-key"

    def test_hourly_hits_the_hourly_path(self, make_meteocat_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={})

        wrapper = make_meteocat_wrapper(handler)
        wrapper.get_municipal_hourly_forecast("080193")

        assert requests[0].url.path == "/pronostic/v1/municipalHoraria/080193"

    def test_uv_index_hits_the_uvi_path(self, make_meteocat_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={})

        wrapper = make_meteocat_wrapper(handler)
        wrapper.get_uv_index_forecast("080193")

        assert requests[0].url.path == "/pronostic/v1/uvi/080193"


class TestErrorMapping:
    @pytest.mark.parametrize(
        "status_code,expected_type",
        [
            (401, MeteocatAuthenticationError),
            (403, MeteocatAuthenticationError),
            (404, MeteocatNotFoundError),
            (429, MeteocatRateLimitError),
        ],
    )
    def test_maps_http_status_codes(self, make_meteocat_wrapper, status_code, expected_type):
        wrapper = make_meteocat_wrapper(lambda request: httpx.Response(status_code, text="nope"))

        with pytest.raises(expected_type):
            wrapper.get_municipal_forecast("080193")

    def test_maps_other_status_codes_to_generic_api_error(self, make_meteocat_wrapper):
        wrapper = make_meteocat_wrapper(lambda request: httpx.Response(500, text="boom"))

        with pytest.raises(MeteocatAPIError, match="500"):
            wrapper.get_municipal_forecast("080193")

    def test_maps_network_errors_to_api_error(self, make_meteocat_wrapper):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("connection refused", request=request)

        wrapper = make_meteocat_wrapper(handler)

        with pytest.raises(MeteocatAPIError, match="Network error"):
            wrapper.get_municipal_forecast("080193")

    def test_maps_non_json_response_to_api_error(self, make_meteocat_wrapper):
        wrapper = make_meteocat_wrapper(lambda request: httpx.Response(200, text="<html></html>"))

        with pytest.raises(MeteocatAPIError, match="valid JSON"):
            wrapper.get_municipal_forecast("080193")


class TestMeteocatClientCache:
    def test_reuses_cached_wrapper_for_same_config(self, meteocat_config):
        cache = MeteocatClientCache()

        first = cache.get_wrapper(meteocat_config)
        second = cache.get_wrapper(meteocat_config)

        assert first is second

    def test_builds_new_wrapper_when_config_changes(self, meteocat_config):
        cache = MeteocatClientCache()
        other_config = MeteocatConfig(meteocat_api_key="different-key")

        first = cache.get_wrapper(meteocat_config)
        second = cache.get_wrapper(other_config)

        assert first is not second


class TestGetMeteocatWrapper:
    def test_raises_config_error_when_credentials_missing(self):
        with pytest.raises(MeteocatConfigError, match="not configured"):
            get_meteocat_wrapper(MeteocatConfig())

    def test_returns_a_wrapper_when_credentials_present(self, meteocat_config):
        wrapper = get_meteocat_wrapper(meteocat_config)

        assert wrapper is not None


class TestMeteocatConfigToleratesUnrelatedEnvVars:
    def test_ignores_unrelated_kwargs(self):
        config = MeteocatConfig(
            **{"meteocat_api_key": "test-key", "garmin_email": "unrelated@example.com"}
        )

        assert config.meteocat_api_key == "test-key"
        assert not hasattr(config, "garmin_email")
