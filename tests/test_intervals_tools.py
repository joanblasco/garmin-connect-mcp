"""Tests for the Intervals.icu tools (tools/intervals.py).

Each tool calls get_intervals_wrapper() directly (no ctx/middleware injection —
see the module docstring in tools/intervals.py), so tests monkeypatch that single
factory function to return a MockTransport-backed wrapper, keeping the mocked
boundary at the HTTP layer rather than inside the tool logic itself.
"""

import json

import httpx
import pytest

from garmin_connect_mcp.intervals_client import IntervalsConfigError
from garmin_connect_mcp.tools import intervals as intervals_tools
from tests.conftest import json_response


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


@pytest.fixture
def use_wrapper(monkeypatch, make_intervals_wrapper):
    """Monkeypatch get_intervals_wrapper() to return a wrapper for the given handler."""

    def _use(handler):
        wrapper = make_intervals_wrapper(handler)
        monkeypatch.setattr(intervals_tools, "get_intervals_wrapper", lambda: wrapper)
        return wrapper

    return _use


class TestListActivities:
    async def test_returns_activities_for_the_default_range(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([{"id": "i1", "type": "Run"}, {"id": "i2", "type": "Ride"}])

        use_wrapper(handler)

        result = await intervals_tools.intervals_list_activities()

        assert _data(result)["count"] == 2
        assert "oldest" in requests[0].url.params
        assert "newest" in requests[0].url.params

    async def test_filters_by_activity_type_client_side(self, use_wrapper):
        use_wrapper(
            lambda request: json_response(
                [{"id": "i1", "type": "Run"}, {"id": "i2", "type": "Ride"}]
            )
        )

        result = await intervals_tools.intervals_list_activities(activity_type="run")

        activities = _data(result)["activities"]
        assert len(activities) == 1
        assert activities[0]["id"] == "i1"

    async def test_uses_explicit_date_range(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([])

        use_wrapper(handler)

        await intervals_tools.intervals_list_activities(
            start_date="2026-01-01", end_date="2026-01-31"
        )

        assert requests[0].url.params["oldest"] == "2026-01-01"
        assert requests[0].url.params["newest"] == "2026-01-31"

    async def test_surfaces_api_errors_as_structured_error_response(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(401, text="nope"))

        result = await intervals_tools.intervals_list_activities()

        assert "authentication failed" in _error(result)["message"].lower()

    async def test_surfaces_missing_credentials_as_structured_error_response(self, monkeypatch):
        def raise_config_error():
            raise IntervalsConfigError("Intervals.icu credentials not configured.")

        monkeypatch.setattr(intervals_tools, "get_intervals_wrapper", raise_config_error)

        result = await intervals_tools.intervals_list_activities()

        assert "not configured" in _error(result)["message"]


class TestGetActivityDetails:
    async def test_returns_activity_detail(self, use_wrapper):
        use_wrapper(lambda request: json_response({"id": "i55751783", "icu_training_load": 85}))

        result = await intervals_tools.intervals_get_activity_details("i55751783")

        assert _data(result)["activity"]["id"] == "i55751783"

    async def test_passes_include_intervals_through(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"id": "i55751783"})

        use_wrapper(handler)

        await intervals_tools.intervals_get_activity_details("i55751783", include_intervals=True)

        assert requests[0].url.params["intervals"] == "true"

    async def test_not_found_surfaces_as_structured_error(self, use_wrapper):
        use_wrapper(lambda request: httpx.Response(404, text="nope"))

        result = await intervals_tools.intervals_get_activity_details("i-does-not-exist")

        assert "not found" in _error(result)["message"].lower()


class TestGetTrainingLoad:
    async def test_single_date_computes_form_from_ctl_and_atl(self, use_wrapper):
        use_wrapper(lambda request: json_response({"id": "2026-08-17", "ctl": 55.0, "atl": 60.0}))

        result = await intervals_tools.intervals_get_training_load(date="2026-08-17")

        load = _data(result)["training_load"]
        assert load["ctl"] == 55.0
        assert load["atl"] == 60.0
        assert load["form"] == -5.0
        assert any("Form is neutral" in i for i in json.loads(result)["analysis"]["insights"])

    async def test_defaults_to_today_when_no_date_given(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response({"id": "today", "ctl": 50.0, "atl": 45.0})

        use_wrapper(handler)

        await intervals_tools.intervals_get_training_load()

        assert requests[0].url.path.startswith("/api/v1/athlete/i12345/wellness/")

    async def test_missing_wellness_record_returns_null_training_load_not_an_error(
        self, use_wrapper
    ):
        use_wrapper(lambda request: httpx.Response(404, text="nope"))

        result = await intervals_tools.intervals_get_training_load(date="2020-01-01")

        assert _data(result)["training_load"] is None
        assert "No wellness data" in json.loads(result)["analysis"]["insights"][0]

    async def test_range_query_returns_a_trend_with_form_per_day(self, use_wrapper):
        use_wrapper(
            lambda request: json_response(
                [
                    {"id": "2026-08-16", "ctl": 54.0, "atl": 58.0},
                    {"id": "2026-08-17", "ctl": 55.0, "atl": 60.0},
                ]
            )
        )

        result = await intervals_tools.intervals_get_training_load(
            start_date="2026-08-16", end_date="2026-08-17"
        )

        trend = _data(result)["trend"]
        assert len(trend) == 2
        assert trend[0]["form"] == -4.0
        assert trend[1]["form"] == -5.0


class TestGetCalendar:
    async def test_returns_events(self, use_wrapper):
        use_wrapper(
            lambda request: json_response(
                [{"id": 1, "category": "WORKOUT", "name": "Threshold intervals"}]
            )
        )

        result = await intervals_tools.intervals_get_calendar()

        assert _data(result)["count"] == 1
        assert _data(result)["events"][0]["name"] == "Threshold intervals"

    async def test_passes_category_filter_through(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([])

        use_wrapper(handler)

        await intervals_tools.intervals_get_calendar(category="WORKOUT,NOTE")

        assert requests[0].url.params["category"] == "WORKOUT,NOTE"

    async def test_omits_category_param_when_not_given(self, use_wrapper):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return json_response([])

        use_wrapper(handler)

        await intervals_tools.intervals_get_calendar()

        assert "category" not in requests[0].url.params
