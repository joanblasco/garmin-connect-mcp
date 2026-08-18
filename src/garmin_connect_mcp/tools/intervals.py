"""Intervals.icu tools for the MCP server.

A separate data source from Garmin Connect: these tools talk to the Intervals.icu
REST API directly (see ..intervals_client) rather than going through the
Garmin-specific ConfigMiddleware/client-cache, and are configured independently via
INTERVALS_API_KEY / INTERVALS_ATHLETE_ID.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

from ..intervals_client import IntervalsAPIError, IntervalsNotFoundError, get_intervals_wrapper
from ..response_builder import ResponseBuilder

_CREDENTIALS_SUGGESTIONS = [
    "Check that INTERVALS_API_KEY and INTERVALS_ATHLETE_ID are set correctly",
    "Verify your internet connection",
]


def _default_date_range(days_back: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _with_form(record: dict[str, Any]) -> dict[str, Any]:
    """Add TSB ('form') to a wellness record: CTL minus ATL.

    Intervals.icu calculates CTL/ATL natively but doesn't return TSB/form as its
    own field, so it's derived here the same way Intervals.icu itself defines it.
    """
    enriched = dict(record)
    ctl = record.get("ctl")
    atl = record.get("atl")
    if ctl is not None and atl is not None:
        enriched["form"] = round(ctl - atl, 1)
    return enriched


def _training_load_insights(load: dict[str, Any]) -> list[str]:
    insights = []

    ctl = load.get("ctl")
    atl = load.get("atl")
    form = load.get("form")

    if ctl is not None:
        insights.append(f"CTL (fitness): {ctl}")
    if atl is not None:
        insights.append(f"ATL (fatigue): {atl}")

    if form is not None:
        if form < -30:
            insights.append(
                f"Form is very negative ({form}): high fatigue, elevated injury/overtraining risk"
            )
        elif form < -10:
            insights.append(f"Form is negative ({form}): building fitness, carrying fatigue")
        elif form <= 5:
            insights.append(f"Form is neutral ({form}): balanced fitness and fatigue")
        elif form <= 25:
            insights.append(f"Form is positive ({form}): fresh, likely race/peak ready")
        else:
            insights.append(f"Form is very positive ({form}): well-rested, possibly detraining")

    return insights


async def intervals_list_activities(
    start_date: Annotated[
        str | None, "Range start date (YYYY-MM-DD). Defaults to 30 days ago."
    ] = None,
    end_date: Annotated[str | None, "Range end date (YYYY-MM-DD). Defaults to today."] = None,
    activity_type: Annotated[
        str, "Filter by activity type (e.g. 'Run', 'Ride', 'Swim'). Empty for all."
    ] = "",
    limit: Annotated[int | None, "Max number of activities to return"] = None,
) -> str:
    """
    List activities recorded in Intervals.icu for a date range, most recent first.

    Intervals.icu ingests activities from Garmin, Strava, Wahoo, Zwift, and direct
    uploads, so this may include activities not present in the Garmin data source.
    """
    try:
        wrapper = get_intervals_wrapper()
        default_start, default_end = _default_date_range(30)
        start = start_date or default_start
        end = end_date or default_end

        activities = wrapper.list_activities(oldest=start, newest=end, limit=limit)

        if activity_type:
            activities = [
                a for a in activities if (a.get("type") or "").lower() == activity_type.lower()
            ]

        return ResponseBuilder.build_response(
            data={"activities": activities, "count": len(activities)},
            metadata={
                "start_date": start,
                "end_date": end,
                "activity_type": activity_type or "all",
            },
        )
    except IntervalsAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def intervals_get_activity_details(
    activity_id: Annotated[str, "Intervals.icu activity ID (e.g. 'i12345678')"],
    include_intervals: Annotated[
        bool, "Include the lap/interval breakdown for the activity"
    ] = False,
) -> str:
    """
    Get full details for a single Intervals.icu activity, including its calculated
    training load (icu_training_load), CTL/ATL at the time (icu_ctl/icu_atl), power
    curve summary, and zone distribution.
    """
    try:
        wrapper = get_intervals_wrapper()
        activity = wrapper.get_activity(activity_id, include_intervals=include_intervals)

        return ResponseBuilder.build_response(
            data={"activity": activity},
            metadata={"activity_id": activity_id, "include_intervals": include_intervals},
        )
    except IntervalsAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            "api_error",
            ["Check the activity ID is correct", *_CREDENTIALS_SUGGESTIONS],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def intervals_get_training_load(
    date: Annotated[
        str | None, "Specific date (YYYY-MM-DD) for a single-day snapshot. Defaults to today."
    ] = None,
    start_date: Annotated[str | None, "Range start date (YYYY-MM-DD) for a daily trend"] = None,
    end_date: Annotated[str | None, "Range end date (YYYY-MM-DD) for a daily trend"] = None,
) -> str:
    """
    Get training load — CTL/ATL/TSB — as calculated natively by Intervals.icu.

    - CTL (Chronic Training Load / "Fitness"): long-term (~42-day) rolling training load.
    - ATL (Acute Training Load / "Fatigue"): short-term (~7-day) rolling training load.
    - TSB (Training Stress Balance / "Form"): CTL minus ATL. Intervals.icu doesn't
      expose this as its own field, so it's computed here from the ctl/atl it returns.

    Provide `date` for a single-day snapshot (default: today), or both `start_date`
    and `end_date` for a daily trend across a range.
    """
    try:
        wrapper = get_intervals_wrapper()

        if start_date and end_date:
            records = wrapper.list_wellness(oldest=start_date, newest=end_date)
            trend = [_with_form(r) for r in records if r]

            return ResponseBuilder.build_response(
                data={"trend": trend, "count": len(trend)},
                analysis={"insights": _training_load_insights(trend[-1])} if trend else None,
                metadata={"start_date": start_date, "end_date": end_date},
            )

        query_date = date or datetime.now().strftime("%Y-%m-%d")
        try:
            record = wrapper.get_wellness(query_date)
        except IntervalsNotFoundError:
            record = None

        if not record:
            return ResponseBuilder.build_response(
                data={"training_load": None},
                analysis={"insights": [f"No wellness data recorded for {query_date}"]},
                metadata={"date": query_date},
            )

        load = _with_form(record)
        return ResponseBuilder.build_response(
            data={"training_load": load},
            analysis={"insights": _training_load_insights(load)},
            metadata={"date": query_date},
        )
    except IntervalsAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def intervals_get_calendar(
    start_date: Annotated[str | None, "Range start date (YYYY-MM-DD). Defaults to today."] = None,
    end_date: Annotated[
        str | None, "Range end date (YYYY-MM-DD). Defaults to start_date + 6 days."
    ] = None,
    category: Annotated[
        str, "Comma-separated categories to filter for (e.g. 'WORKOUT,NOTE,RACE_A'). Empty for all."
    ] = "",
    limit: Annotated[int | None, "Max number of events to return"] = None,
) -> str:
    """
    Query the Intervals.icu calendar: planned/scheduled workouts and other events
    (notes, races, etc.).
    """
    try:
        wrapper = get_intervals_wrapper()
        events = wrapper.list_events(
            oldest=start_date,
            newest=end_date,
            category=category or None,
            limit=limit,
        )

        return ResponseBuilder.build_response(
            data={"events": events, "count": len(events)},
            metadata={
                "start_date": start_date or "today",
                "end_date": end_date or "start_date + 6 days",
                "category": category or "all",
            },
        )
    except IntervalsAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
