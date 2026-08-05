"""Tests for query_nutrition (daily food log, meals, and settings)."""

import json

from garmin_connect_mcp.tools.nutrition import query_nutrition


def _data(response_json: str):
    return json.loads(response_json)["data"]


class TestDefaults:
    async def test_food_log_and_meals_included_by_default_settings_are_not(self, client_stub, ctx):
        client_stub._method_results["get_nutrition_daily_food_log"] = {"mealDate": "2026-08-04"}
        client_stub._method_results["get_nutrition_daily_meals"] = {"meals": []}

        result = await query_nutrition(date="2026-08-04", ctx=ctx)

        data = _data(result)
        assert "food_log" in data
        assert "meals" in data
        assert "settings" not in data

    async def test_settings_included_when_requested(self, client_stub, ctx):
        client_stub._method_results["get_nutrition_daily_food_log"] = {}
        client_stub._method_results["get_nutrition_daily_meals"] = {"meals": []}
        client_stub._method_results["get_nutrition_daily_settings"] = {"calories": 1730}

        result = await query_nutrition(date="2026-08-04", include_settings=True, ctx=ctx)

        assert _data(result)["settings"] == {"calories": 1730}

    async def test_calls_use_the_given_date(self, client_stub, ctx):
        client_stub._method_results["get_nutrition_daily_food_log"] = {}
        client_stub._method_results["get_nutrition_daily_meals"] = {}

        await query_nutrition(date="2026-08-04", ctx=ctx)

        assert ("get_nutrition_daily_food_log", ("2026-08-04",), {}) in client_stub.calls
        assert ("get_nutrition_daily_meals", ("2026-08-04",), {}) in client_stub.calls


class TestInsights:
    async def test_reports_meal_count_when_meals_are_logged(self, client_stub, ctx):
        client_stub._method_results["get_nutrition_daily_food_log"] = {}
        client_stub._method_results["get_nutrition_daily_meals"] = {
            "meals": [{"name": "Breakfast"}, {"name": "Lunch"}]
        }

        result = await query_nutrition(date="2026-08-04", ctx=ctx)

        insights = json.loads(result)["analysis"]["insights"]
        assert any("2 meal" in i for i in insights)

    async def test_reports_no_meals_when_empty(self, client_stub, ctx):
        client_stub._method_results["get_nutrition_daily_food_log"] = {}
        client_stub._method_results["get_nutrition_daily_meals"] = {"meals": []}

        result = await query_nutrition(date="2026-08-04", ctx=ctx)

        insights = json.loads(result)["analysis"]["insights"]
        assert any("No meals logged" in i for i in insights)
