"""Nutrition tools for Garmin Connect MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..client import GarminAPIError
from ..response_builder import ResponseBuilder
from ..time_utils import parse_date_string


async def query_nutrition(
    date: Annotated[str | None, "Date (YYYY-MM-DD, defaults to today)"] = None,
    include_food_log: Annotated[bool, "Include the daily food log summary"] = True,
    include_meals: Annotated[bool, "Include meal-by-meal breakdown"] = True,
    include_settings: Annotated[bool, "Include nutrition goal/tracking settings"] = False,
    ctx: Context | None = None,
) -> str:
    """
    Query daily nutrition tracking: food log, meals, and tracking settings.

    Requires food logging to actually be used in the Garmin Connect app for that date —
    an empty result for a given day usually means nothing was logged, not an error.
    """
    assert ctx is not None
    try:
        client = await ctx.get_state("client")

        date_str = (
            parse_date_string(date).strftime("%Y-%m-%d")
            if date
            else parse_date_string("today").strftime("%Y-%m-%d")
        )

        data: dict[str, Any] = {}

        if include_food_log:
            try:
                data["food_log"] = client.safe_call("get_nutrition_daily_food_log", date_str)
            except Exception:
                data["food_log"] = None

        if include_meals:
            try:
                data["meals"] = client.safe_call("get_nutrition_daily_meals", date_str)
            except Exception:
                data["meals"] = None

        if include_settings:
            try:
                data["settings"] = client.safe_call("get_nutrition_daily_settings", date_str)
            except Exception:
                data["settings"] = None

        insights = []
        meals = data.get("meals")
        if isinstance(meals, dict) and meals.get("meals"):
            insights.append(f"{len(meals['meals'])} meal(s) logged on {date_str}")
        elif include_meals:
            insights.append(f"No meals logged on {date_str}")

        return ResponseBuilder.build_response(
            data=data,
            analysis={"insights": insights} if insights else None,
            metadata={"date": date_str},
        )

    except GarminAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            "api_error",
            ["Check your Garmin Connect credentials", "Verify your internet connection"],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
