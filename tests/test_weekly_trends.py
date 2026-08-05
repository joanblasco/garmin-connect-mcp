"""Tests for query_weekly_trends (weekly steps/stress/intensity-minutes aggregates)."""

import json

from garmin_connect_mcp.tools.health_wellness import query_weekly_trends


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestBasicQuery:
    async def test_all_three_metrics_included_by_default(self, client_stub, ctx):
        client_stub._method_results["get_weekly_steps"] = [{"calendarDate": "2026-07-08"}]
        client_stub._method_results["get_weekly_stress"] = [{"calendarDate": "2026-07-08"}]
        client_stub._method_results["get_weekly_intensity_minutes"] = [
            {"calendarDate": "2026-07-08"}
        ]

        result = await query_weekly_trends(end_date="2026-08-04", weeks=4, ctx=ctx)

        data = _data(result)
        assert "weekly_steps" in data
        assert "weekly_stress" in data
        assert "weekly_intensity_minutes" in data

    async def test_weekly_steps_called_with_end_date_and_weeks(self, client_stub, ctx):
        client_stub._method_results["get_weekly_steps"] = []
        client_stub._method_results["get_weekly_stress"] = []
        client_stub._method_results["get_weekly_intensity_minutes"] = []

        await query_weekly_trends(end_date="2026-08-04", weeks=4, ctx=ctx)

        assert ("get_weekly_steps", ("2026-08-04", 4), {}) in client_stub.calls

    async def test_can_disable_individual_metrics(self, client_stub, ctx):
        client_stub._method_results["get_weekly_steps"] = [{"calendarDate": "2026-07-08"}]

        result = await query_weekly_trends(
            end_date="2026-08-04",
            include_stress=False,
            include_intensity_minutes=False,
            ctx=ctx,
        )

        data = _data(result)
        assert "weekly_steps" in data
        assert "weekly_stress" not in data
        assert "weekly_intensity_minutes" not in data


class TestValidation:
    async def test_weeks_out_of_range_is_rejected(self, ctx):
        result = await query_weekly_trends(weeks=100, ctx=ctx)

        assert _error(result)["type"] == "validation_error"

    async def test_zero_weeks_is_rejected(self, ctx):
        result = await query_weekly_trends(weeks=0, ctx=ctx)

        assert _error(result)["type"] == "validation_error"
