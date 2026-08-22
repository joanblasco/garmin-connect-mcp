"""Tests for the AEMET tools (tools/aemet.py).

Each tool calls get_aemet_wrapper() directly, so tests monkeypatch that factory
function to return a MockTransport-backed wrapper, using AEMET's two-step
envelope/datos-URL response shape.
"""

import json

import httpx
import pytest

from garmin_connect_mcp.aemet_client import AemetConfigError
from garmin_connect_mcp.tools import aemet as aemet_tools

DATOS_URL = "https://opendata.aemet.es/opendata/sh/xyz789"


def _two_step_handler(final_payload):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DATOS_URL:
            return httpx.Response(200, json=final_payload)
        return httpx.Response(200, json={"descripcion": "exito", "estado": 200, "datos": DATOS_URL})

    return handler


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


@pytest.fixture
def use_wrapper(monkeypatch, make_aemet_wrapper):
    def _use(handler):
        wrapper = make_aemet_wrapper(handler)
        monkeypatch.setattr(aemet_tools, "get_aemet_wrapper", lambda: wrapper)
        return wrapper

    return _use


class TestWeatherAemetForecastDaily:
    async def test_returns_forecast(self, use_wrapper):
        use_wrapper(_two_step_handler({"prediccion": {"dia": []}}))

        result = await aemet_tools.weather_aemet_forecast_daily("08019")

        assert _data(result)["forecast"] == {"prediccion": {"dia": []}}

    async def test_surfaces_authentication_errors(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(200, content=b""))

        result = await aemet_tools.weather_aemet_forecast_daily("08019")

        assert "empty response" in _error(result)["message"].lower()

    async def test_surfaces_not_found_errors(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(404, text="nope"))

        result = await aemet_tools.weather_aemet_forecast_daily("99999")

        assert "not found" in _error(result)["message"].lower()

    async def test_surfaces_missing_credentials(self, monkeypatch):
        def raise_config_error():
            raise AemetConfigError("AEMET credentials not configured.")

        monkeypatch.setattr(aemet_tools, "get_aemet_wrapper", raise_config_error)

        result = await aemet_tools.weather_aemet_forecast_daily("08019")

        assert "not configured" in _error(result)["message"]


class TestWeatherAemetForecastHourly:
    async def test_returns_forecast(self, use_wrapper):
        use_wrapper(_two_step_handler({"prediccion": {"hora": []}}))

        result = await aemet_tools.weather_aemet_forecast_hourly("08019")

        assert _data(result)["forecast"] == {"prediccion": {"hora": []}}
