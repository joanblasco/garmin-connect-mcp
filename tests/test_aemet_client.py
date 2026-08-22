"""Tests for AemetClientWrapper, AemetClientCache, and get_aemet_wrapper.

The AEMET network boundary is faked with httpx.MockTransport, exercising the
wrapper's real URL construction, auth header, and — the AEMET-specific piece —
its two-step "envelope then datos URL" fetch and quirky error shapes.
"""

import httpx
import pytest

from garmin_connect_mcp.aemet_auth import AemetConfig
from garmin_connect_mcp.aemet_client import (
    AemetAPIError,
    AemetAuthenticationError,
    AemetClientCache,
    AemetConfigError,
    AemetNotFoundError,
    AemetRateLimitError,
    get_aemet_wrapper,
)

DATOS_URL = "https://opendata.aemet.es/opendata/sh/abc123"


def _two_step_handler(final_payload, final_status=200):
    """A handler mimicking AEMET's real shape: first call returns an envelope
    pointing at a temporary `datos` URL; the second call (to that URL) returns
    the real payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DATOS_URL:
            return httpx.Response(final_status, json=final_payload)
        return httpx.Response(
            200,
            json={
                "descripcion": "exito",
                "estado": 200,
                "datos": DATOS_URL,
                "metadatos": DATOS_URL + "/meta",
            },
        )

    return handler


class TestTwoStepFetch:
    def test_resolves_the_datos_url_transparently(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(_two_step_handler({"temperatura": 22}))

        result = wrapper.get_forecast_daily("08019")

        assert result == {"temperatura": 22}

    def test_sends_the_api_key_header_on_the_first_request(self, make_aemet_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _two_step_handler({"ok": True})(request)

        wrapper = make_aemet_wrapper(handler)
        wrapper.get_forecast_daily("08019")

        assert requests[0].url.path == "/opendata/api/prediccion/especifica/municipio/diaria/08019"
        assert requests[0].headers["api_key"] == "test-api-key"

    def test_hourly_hits_the_hourly_path(self, make_aemet_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _two_step_handler({"ok": True})(request)

        wrapper = make_aemet_wrapper(handler)
        wrapper.get_forecast_hourly("08019")

        assert requests[0].url.path == "/opendata/api/prediccion/especifica/municipio/horaria/08019"

    def test_second_hop_failure_gives_a_retry_hint(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(_two_step_handler({}, final_status=403))

        with pytest.raises(AemetAPIError, match="expired"):
            wrapper.get_forecast_daily("08019")

    def test_missing_datos_url_in_envelope_is_an_error(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(
            lambda request: httpx.Response(200, json={"descripcion": "exito", "estado": 200})
        )

        with pytest.raises(AemetAPIError, match="datos"):
            wrapper.get_forecast_daily("08019")


class TestQuirkyErrorShapes:
    def test_empty_200_body_means_authentication_failed(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(lambda request: httpx.Response(200, content=b""))

        with pytest.raises(AemetAuthenticationError, match="empty response"):
            wrapper.get_forecast_daily("08019")

    def test_401_with_descripcion_surfaces_the_real_message(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(
            lambda request: httpx.Response(
                401,
                json={
                    "descripcion": "JWT strings must contain exactly 2 period characters. Found: 0",
                    "estado": 401,
                },
            )
        )

        with pytest.raises(
            AemetAuthenticationError, match="JWT strings must contain exactly 2 period characters"
        ):
            wrapper.get_forecast_daily("08019")


class TestErrorMapping:
    @pytest.mark.parametrize(
        "status_code,expected_type",
        [
            (401, AemetAuthenticationError),
            (403, AemetAuthenticationError),
            (404, AemetNotFoundError),
            (429, AemetRateLimitError),
        ],
    )
    def test_maps_http_status_codes(self, make_aemet_wrapper, status_code, expected_type):
        wrapper = make_aemet_wrapper(lambda request: httpx.Response(status_code, text="nope"))

        with pytest.raises(expected_type):
            wrapper.get_forecast_daily("08019")

    def test_maps_other_status_codes_to_generic_api_error(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(lambda request: httpx.Response(500, text="boom"))

        with pytest.raises(AemetAPIError, match="500"):
            wrapper.get_forecast_daily("08019")

    def test_maps_network_errors_to_api_error(self, make_aemet_wrapper):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("connection refused", request=request)

        wrapper = make_aemet_wrapper(handler)

        with pytest.raises(AemetAPIError, match="Network error"):
            wrapper.get_forecast_daily("08019")

    def test_maps_non_json_envelope_to_api_error(self, make_aemet_wrapper):
        wrapper = make_aemet_wrapper(lambda request: httpx.Response(200, text="<html></html>"))

        with pytest.raises(AemetAPIError, match="valid JSON"):
            wrapper.get_forecast_daily("08019")


class TestAemetClientCache:
    def test_reuses_cached_wrapper_for_same_config(self, aemet_config):
        cache = AemetClientCache()

        first = cache.get_wrapper(aemet_config)
        second = cache.get_wrapper(aemet_config)

        assert first is second

    def test_builds_new_wrapper_when_config_changes(self, aemet_config):
        cache = AemetClientCache()
        other_config = AemetConfig(aemet_api_key="different-key")

        first = cache.get_wrapper(aemet_config)
        second = cache.get_wrapper(other_config)

        assert first is not second


class TestGetAemetWrapper:
    def test_raises_config_error_when_credentials_missing(self):
        with pytest.raises(AemetConfigError, match="not configured"):
            get_aemet_wrapper(AemetConfig())

    def test_returns_a_wrapper_when_credentials_present(self, aemet_config):
        wrapper = get_aemet_wrapper(aemet_config)

        assert wrapper is not None


class TestAemetConfigToleratesUnrelatedEnvVars:
    def test_ignores_unrelated_kwargs(self):
        # Passed via a dict, not literal kwargs: garmin_email isn't a field
        # AemetConfig declares, so pyright would (correctly) flag it as a literal kwarg.
        config = AemetConfig(
            **{"aemet_api_key": "test-key", "garmin_email": "unrelated@example.com"}
        )

        assert config.aemet_api_key == "test-key"
        assert not hasattr(config, "garmin_email")
