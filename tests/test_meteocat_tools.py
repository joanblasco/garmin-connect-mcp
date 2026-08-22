"""Tests for the MeteoCat tools (tools/meteocat.py).

Each tool calls get_meteocat_wrapper() directly, so tests monkeypatch that
factory function to return a MockTransport-backed wrapper.
"""

import json

import httpx
import pytest

from garmin_connect_mcp.meteocat_client import MeteocatConfigError
from garmin_connect_mcp.tools import meteocat as meteocat_tools


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


@pytest.fixture
def use_wrapper(monkeypatch, make_meteocat_wrapper):
    def _use(handler):
        wrapper = make_meteocat_wrapper(handler)
        monkeypatch.setattr(meteocat_tools, "get_meteocat_wrapper", lambda: wrapper)
        return wrapper

    return _use


class TestWeatherMeteocatForecastMunicipal:
    async def test_returns_forecast(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(200, json={"dia": []}))

        result = await meteocat_tools.weather_meteocat_forecast_municipal("080193")

        assert _data(result)["forecast"] == {"dia": []}

    async def test_surfaces_authentication_errors(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(401, text="nope"))

        result = await meteocat_tools.weather_meteocat_forecast_municipal("080193")

        assert "authentication failed" in _error(result)["message"].lower()

    async def test_surfaces_missing_credentials(self, monkeypatch):
        def raise_config_error():
            raise MeteocatConfigError("MeteoCat credentials not configured.")

        monkeypatch.setattr(meteocat_tools, "get_meteocat_wrapper", raise_config_error)

        result = await meteocat_tools.weather_meteocat_forecast_municipal("080193")

        assert "not configured" in _error(result)["message"]


class TestWeatherMeteocatForecastHourly:
    async def test_returns_forecast(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(200, json={"hora": []}))

        result = await meteocat_tools.weather_meteocat_forecast_hourly("080193")

        assert _data(result)["forecast"] == {"hora": []}


class TestWeatherMeteocatUvIndex:
    async def test_returns_uv_index(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(200, json={"uvi": 5}))

        result = await meteocat_tools.weather_meteocat_uv_index("080193")

        assert _data(result)["uv_index"] == {"uvi": 5}

    async def test_surfaces_not_found_errors(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(404, text="nope"))

        result = await meteocat_tools.weather_meteocat_uv_index("99999")

        assert "not found" in _error(result)["message"].lower()
