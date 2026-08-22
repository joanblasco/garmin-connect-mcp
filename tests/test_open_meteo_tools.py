"""Tests for the Open-Meteo tools (tools/open_meteo.py).

Each tool calls get_open_meteo_wrapper() directly (no ctx/middleware injection),
so tests monkeypatch that factory function to return a MockTransport-backed
wrapper, keeping the mocked boundary at the HTTP layer.
"""

import json

import httpx
import pytest

from garmin_connect_mcp.tools import open_meteo as open_meteo_tools
from tests.conftest import json_response


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


@pytest.fixture
def use_wrapper(monkeypatch, make_open_meteo_wrapper):
    def _use(handler):
        wrapper = make_open_meteo_wrapper(handler)
        monkeypatch.setattr(open_meteo_tools, "get_open_meteo_wrapper", lambda: wrapper)
        return wrapper

    return _use


class TestWeatherOpenmeteoCurrent:
    async def test_returns_current_conditions(self, use_wrapper):
        use_wrapper(lambda request: json_response({"temperature_2m": 22.5}))

        result = await open_meteo_tools.weather_openmeteo_current(41.3874, 2.1686)

        assert _data(result)["current"]["temperature_2m"] == 22.5

    async def test_surfaces_api_errors_as_structured_error_response(self, use_wrapper):
        use_wrapper(
            lambda request: httpx.Response(400, json={"error": True, "reason": "bad latitude"})
        )

        result = await open_meteo_tools.weather_openmeteo_current(999, 2.1686)

        assert "bad latitude" in _error(result)["message"]


class TestWeatherOpenmeteoForecast:
    async def test_returns_forecast(self, use_wrapper):
        use_wrapper(
            lambda request: json_response({"time": ["2026-08-22"], "temperature_2m_max": [30]})
        )

        result = await open_meteo_tools.weather_openmeteo_forecast(41.3874, 2.1686)

        assert _data(result)["forecast"]["temperature_2m_max"] == [30]

    async def test_passes_forecast_days_and_hourly_through(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({})

        use_wrapper(handler)

        await open_meteo_tools.weather_openmeteo_forecast(
            41.3874, 2.1686, forecast_days=3, include_hourly=True
        )

        assert requests[0].url.params["forecast_days"] == "3"
        assert "hourly" in requests[0].url.params

    async def test_surfaces_rate_limit_errors_as_structured_error_response(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(429, text="slow down"))

        result = await open_meteo_tools.weather_openmeteo_forecast(41.3874, 2.1686)

        assert "rate limit" in _error(result)["message"].lower()
