"""Tests for get_performance_metrics: FTP, lactate threshold, and VO2max/HRV trends."""

import json

from garmin_connect_mcp.tools.training import get_performance_metrics


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestFtpAndLactateThreshold:
    async def test_ftp_is_included_when_requested(self, client_stub, ctx):
        client_stub._method_results["get_cycling_ftp"] = {"functionalThresholdPower": 216}
        client_stub._method_results["get_max_metrics"] = {}
        client_stub._method_results["get_hrv_data"] = {}
        client_stub._method_results["get_fitness_age"] = {}

        result = await get_performance_metrics(date="2026-08-04", include_ftp=True, ctx=ctx)

        assert _data(result)["cycling_ftp"] == {"functionalThresholdPower": 216}

    async def test_ftp_omitted_by_default(self, client_stub, ctx):
        client_stub._method_results["get_max_metrics"] = {}
        client_stub._method_results["get_hrv_data"] = {}
        client_stub._method_results["get_fitness_age"] = {}

        result = await get_performance_metrics(date="2026-08-04", ctx=ctx)

        assert "cycling_ftp" not in _data(result)

    async def test_lactate_threshold_single_day_calls_with_no_args(self, client_stub, ctx):
        client_stub._method_results["get_lactate_threshold"] = {"heartRate": 166}
        client_stub._method_results["get_max_metrics"] = {}
        client_stub._method_results["get_hrv_data"] = {}
        client_stub._method_results["get_fitness_age"] = {}

        result = await get_performance_metrics(
            date="2026-08-04", include_lactate_threshold=True, ctx=ctx
        )

        assert _data(result)["lactate_threshold"] == {"heartRate": 166}
        assert ("get_lactate_threshold", (), {}) in client_stub.calls

    async def test_lactate_threshold_range_uses_daily_aggregation(self, client_stub, ctx):
        client_stub._method_results["get_lactate_threshold"] = {"series": []}
        client_stub._method_results["get_hill_score"] = {}
        client_stub._method_results["get_endurance_score"] = {}

        await get_performance_metrics(
            start_date="2026-07-01",
            end_date="2026-07-07",
            include_vo2_max=False,
            include_hrv=False,
            include_lactate_threshold=True,
            ctx=ctx,
        )

        name, args, kwargs = next(c for c in client_stub.calls if c[0] == "get_lactate_threshold")
        assert kwargs == {
            "latest": False,
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "aggregation": "daily",
        }


class TestVo2MaxAndHrvTrends:
    async def test_range_query_builds_a_trend_by_querying_each_day(self, client_stub, ctx):
        client_stub._method_results["get_hill_score"] = {}
        client_stub._method_results["get_endurance_score"] = {}

        def vo2_for_day(day):
            # Only two of the three days have real data, like Garmin in practice.
            return {"vo2MaxValue": 60} if day in ("2026-08-01", "2026-08-03") else None

        client_stub._method_results["get_max_metrics"] = lambda day: vo2_for_day(day)
        client_stub._method_results["get_hrv_data"] = lambda day: None

        result = await get_performance_metrics(
            start_date="2026-08-01", end_date="2026-08-03", ctx=ctx
        )

        data = _data(result)
        assert len(data["vo2_max_trend"]) == 2
        assert data["vo2_max_trend"][0]["date"] == "2026-08-01"
        assert data["hrv_trend"] == []

    async def test_a_days_error_does_not_abort_the_whole_trend(self, client_stub, ctx):
        client_stub._method_results["get_hill_score"] = {}
        client_stub._method_results["get_endurance_score"] = {}
        client_stub._method_results["get_hrv_data"] = None

        def vo2_for_day(day):
            if day == "2026-08-02":
                raise RuntimeError("transient upstream error")
            return {"vo2MaxValue": 60}

        client_stub._method_results["get_max_metrics"] = lambda day: vo2_for_day(day)

        result = await get_performance_metrics(
            start_date="2026-08-01", end_date="2026-08-03", ctx=ctx
        )

        # 2 good days out of 3; the erroring day is skipped, not fatal.
        assert len(_data(result)["vo2_max_trend"]) == 2

    async def test_range_over_90_days_is_rejected_before_any_calls(self, client_stub, ctx):
        result = await get_performance_metrics(
            start_date="2026-01-01", end_date="2026-08-04", ctx=ctx
        )

        assert _error(result)["type"] == "invalid_parameters"
        assert client_stub.calls == []

    async def test_exactly_90_days_is_accepted(self, client_stub, ctx):
        client_stub._method_results["get_hill_score"] = {}
        client_stub._method_results["get_endurance_score"] = {}
        client_stub._method_results["get_max_metrics"] = None
        client_stub._method_results["get_hrv_data"] = None

        result = await get_performance_metrics(
            start_date="2026-01-01",
            end_date="2026-03-31",
            ctx=ctx,  # 90 days inclusive
        )

        assert "error" not in json.loads(result)
