"""Tests for query_training_plans (list / detail / adaptive)."""

import json

from garmin_connect_mcp.tools.training import query_training_plans


def _data(response_json: str):
    return json.loads(response_json)["data"]


class TestListPlans:
    async def test_no_plan_id_lists_all_plans(self, client_stub, ctx):
        client_stub._method_results["get_training_plans"] = {
            "trainingPlanList": [{"trainingPlanId": 1}, {"trainingPlanId": 2}]
        }

        result = await query_training_plans(ctx=ctx)

        assert _data(result)["count"] == 2
        assert all(name != "get_training_plan_by_id" for name, _, _ in client_stub.calls)


class TestPlanDetail:
    async def test_plan_id_fetches_full_plan_by_default(self, client_stub, ctx):
        client_stub._method_results["get_training_plan_by_id"] = {"trainingPlanId": 39447987}

        result = await query_training_plans(plan_id=39447987, ctx=ctx)

        assert _data(result)["training_plan"]["trainingPlanId"] == 39447987
        assert ("get_training_plan_by_id", (39447987,), {}) in client_stub.calls
        assert all(name != "get_adaptive_training_plan_by_id" for name, _, _ in client_stub.calls)

    async def test_adaptive_true_fetches_the_adaptive_view_instead(self, client_stub, ctx):
        client_stub._method_results["get_adaptive_training_plan_by_id"] = {
            "trainingPlanId": 39447987
        }

        result = await query_training_plans(plan_id=39447987, adaptive=True, ctx=ctx)

        assert _data(result)["training_plan"]["trainingPlanId"] == 39447987
        assert ("get_adaptive_training_plan_by_id", (39447987,), {}) in client_stub.calls
        assert all(name != "get_training_plan_by_id" for name, _, _ in client_stub.calls)
