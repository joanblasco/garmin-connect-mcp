"""Tests for the typed_splits/split_summaries additions to get_activity_details."""

import json

from garmin_connect_mcp.tools.activities import get_activity_details


def _data(response_json: str):
    return json.loads(response_json)["data"]


class TestDetailedSplits:
    async def test_off_by_default(self, client_stub, ctx):
        client_stub._method_results["get_activity"] = {"activityId": 1}

        result = await get_activity_details(
            activity_id=1,
            include_splits=False,
            include_weather=False,
            include_hr_zones=False,
            include_gear=False,
            ctx=ctx,
        )

        data = _data(result)
        assert "typed_splits" not in data
        assert "split_summaries" not in data

    async def test_typed_splits_calls_get_activity_typed_splits(self, client_stub, ctx):
        client_stub._method_results["get_activity"] = {"activityId": 1}
        client_stub._method_results["get_activity_typed_splits"] = {"splits": []}

        result = await get_activity_details(
            activity_id=1,
            include_splits=False,
            include_weather=False,
            include_hr_zones=False,
            include_gear=False,
            include_typed_splits=True,
            ctx=ctx,
        )

        assert _data(result)["typed_splits"] == {"splits": []}
        assert ("get_activity_typed_splits", (1,), {}) in client_stub.calls

    async def test_split_summaries_calls_get_activity_split_summaries(self, client_stub, ctx):
        client_stub._method_results["get_activity"] = {"activityId": 1}
        client_stub._method_results["get_activity_split_summaries"] = {"splitSummaries": []}

        result = await get_activity_details(
            activity_id=1,
            include_splits=False,
            include_weather=False,
            include_hr_zones=False,
            include_gear=False,
            include_split_summaries=True,
            ctx=ctx,
        )

        assert _data(result)["split_summaries"] == {"splitSummaries": []}
        assert ("get_activity_split_summaries", (1,), {}) in client_stub.calls
