"""Workout management tools for Garmin Connect MCP server."""

from datetime import datetime
from typing import Annotated

from fastmcp import Context

from ..client import GarminAPIError
from ..response_builder import ResponseBuilder

# Calendar range queries fetch one API call per calendar month; cap the span so a
# careless request can't fan out into dozens of calls.
MAX_LIST_SCHEDULED_MONTHS = 13


def _iter_year_months(start_date: str, end_date: str):
    """Yield (year, month) tuples for every calendar month between two dates, inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


async def manage_workouts(
    action: Annotated[
        str,
        "Action: 'list', 'get', 'download', 'upload', 'schedule', 'unschedule', 'delete', "
        "'list_scheduled'",
    ],
    workout_id: Annotated[
        int | None, "Workout template ID (for get/download/schedule/delete actions)"
    ] = None,
    workout_data: Annotated[str | None, "Workout data (for upload action)"] = None,
    date: Annotated[str | None, "Target date in YYYY-MM-DD format (for schedule action)"] = None,
    scheduled_workout_id: Annotated[
        int | None,
        "Calendar scheduling ID returned by 'schedule' (for unschedule action) — "
        "this is NOT the same as workout_id",
    ] = None,
    start_date: Annotated[
        str | None, "Range start date in YYYY-MM-DD format (for list_scheduled action)"
    ] = None,
    end_date: Annotated[
        str | None, "Range end date in YYYY-MM-DD format (for list_scheduled action)"
    ] = None,
    confirm_delete: Annotated[
        bool,
        "Must be explicitly set to true to actually delete. Deleting a workout template is "
        "PERMANENT and cannot be undone — only pass true after the user has explicitly "
        "confirmed, in this conversation, that they want this specific workout deleted. "
        "Do not infer consent from a general request; ask first.",
    ] = False,
    ctx: Context | None = None,
) -> str:
    """
    Manage structured workouts.

    Actions:
    - list: Get all workouts
    - get: Get specific workout by ID
    - download: Download workout file
    - upload: Upload a new workout
    - schedule: Place an existing workout on a calendar date (equivalent to dragging
      the workout onto a day in Garmin Connect)
    - unschedule: Remove a workout from the calendar without deleting the template
      (requires scheduled_workout_id, the ID returned by 'schedule', not workout_id)
    - delete: PERMANENTLY delete a workout template from the library. IRREVERSIBLE.
      Requires confirm_delete=true — only set this after the user has explicitly confirmed
      they want this specific workout deleted.
    - list_scheduled: List workouts already placed on the calendar within a date range
      (requires start_date and end_date), including each entry's scheduled_workout_id —
      needed to 'unschedule' an entry that wasn't just scheduled in this conversation.
    """
    assert ctx is not None
    try:
        client = await ctx.get_state("client")

        if action == "list":
            workouts = client.safe_call("get_workouts")
            return ResponseBuilder.build_response(
                data={
                    "workouts": workouts,
                    "count": len(workouts) if isinstance(workouts, list) else 0,
                },
                metadata={"action": "list"},
            )

        elif action == "get":
            if workout_id is None:
                return ResponseBuilder.build_error_response(
                    "Workout ID required for get action",
                    "invalid_parameters",
                    ["Provide workout_id parameter"],
                )

            workout = client.safe_call("get_workout_by_id", workout_id)
            return ResponseBuilder.build_response(
                data={"workout": workout},
                metadata={"action": "get", "workout_id": workout_id},
            )

        elif action == "download":
            if workout_id is None:
                return ResponseBuilder.build_error_response(
                    "Workout ID required for download action",
                    "invalid_parameters",
                    ["Provide workout_id parameter"],
                )

            download_info = client.safe_call("download_workout", workout_id)
            return ResponseBuilder.build_response(
                data={"download_info": download_info},
                metadata={"action": "download", "workout_id": workout_id},
            )

        elif action == "upload":
            if not workout_data:
                return ResponseBuilder.build_error_response(
                    "Workout data required for upload action",
                    "invalid_parameters",
                    ["Provide workout_data parameter"],
                )

            result = client.safe_call("upload_workout", workout_data)
            return ResponseBuilder.build_response(
                data={"result": result},
                analysis={"insights": ["Workout uploaded successfully"]},
                metadata={"action": "upload"},
            )

        elif action == "schedule":
            if workout_id is None:
                return ResponseBuilder.build_error_response(
                    "Workout ID required for schedule action",
                    "invalid_parameters",
                    ["Provide workout_id parameter"],
                )
            if not date:
                return ResponseBuilder.build_error_response(
                    "Date required for schedule action",
                    "invalid_parameters",
                    ["Provide date parameter in YYYY-MM-DD format"],
                )

            result = client.safe_call("schedule_workout", workout_id, date)
            return ResponseBuilder.build_response(
                data={"scheduled_workout": result},
                analysis={"insights": [f"Workout {workout_id} scheduled for {date}"]},
                metadata={"action": "schedule", "workout_id": workout_id, "date": date},
            )

        elif action == "unschedule":
            if scheduled_workout_id is None:
                return ResponseBuilder.build_error_response(
                    "scheduled_workout_id required for unschedule action",
                    "invalid_parameters",
                    [
                        "Provide the scheduled_workout_id returned by the 'schedule' action "
                        "(not the workout_id)"
                    ],
                )

            result = client.safe_call("unschedule_workout", scheduled_workout_id)
            return ResponseBuilder.build_response(
                data={"result": result},
                analysis={
                    "insights": [f"Scheduled workout {scheduled_workout_id} removed from calendar"]
                },
                metadata={"action": "unschedule", "scheduled_workout_id": scheduled_workout_id},
            )

        elif action == "list_scheduled":
            if not start_date or not end_date:
                return ResponseBuilder.build_error_response(
                    "start_date and end_date required for list_scheduled action",
                    "invalid_parameters",
                    ["Provide both start_date and end_date in YYYY-MM-DD format"],
                )
            if start_date > end_date:
                return ResponseBuilder.build_error_response(
                    "start_date must not be after end_date",
                    "invalid_parameters",
                    ["Swap start_date and end_date, or narrow the range"],
                )

            months = list(_iter_year_months(start_date, end_date))
            if len(months) > MAX_LIST_SCHEDULED_MONTHS:
                return ResponseBuilder.build_error_response(
                    f"Date range spans {len(months)} calendar months, "
                    f"exceeding the limit of {MAX_LIST_SCHEDULED_MONTHS}",
                    "invalid_parameters",
                    ["Narrow start_date/end_date to a shorter range"],
                )

            # Garmin's month endpoint returns a calendar-grid view that includes a few
            # leading/trailing days from adjacent months, so a date near a month
            # boundary can appear twice across consecutive month fetches — dedupe by id.
            scheduled_by_id: dict[object, dict] = {}
            for year, month in months:
                calendar = client.safe_call("get_scheduled_workouts", year, month)
                for item in calendar.get("calendarItems", []):
                    if item.get("itemType") != "workout":
                        continue
                    item_date = item.get("date")
                    if item_date is None or not (start_date <= item_date <= end_date):
                        continue
                    scheduled_by_id[item.get("id")] = {
                        "scheduled_workout_id": item.get("id"),
                        "workout_id": item.get("workoutId"),
                        "name": item.get("title"),
                        "date": item_date,
                        "sport_type": item.get("sportTypeKey"),
                    }

            scheduled = sorted(scheduled_by_id.values(), key=lambda entry: entry["date"])
            return ResponseBuilder.build_response(
                data={"scheduled_workouts": scheduled, "count": len(scheduled)},
                metadata={
                    "action": "list_scheduled",
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )

        elif action == "delete":
            if workout_id is None:
                return ResponseBuilder.build_error_response(
                    "Workout ID required for delete action",
                    "invalid_parameters",
                    ["Provide workout_id parameter"],
                )
            if not confirm_delete:
                return ResponseBuilder.build_error_response(
                    "Deletion requires explicit confirmation",
                    "confirmation_required",
                    [
                        "This permanently deletes the workout template and cannot be undone.",
                        "Ask the user to explicitly confirm before retrying with "
                        "confirm_delete=true.",
                    ],
                )

            result = client.safe_call("delete_workout", workout_id)
            return ResponseBuilder.build_response(
                data={"result": result},
                analysis={"insights": [f"Workout {workout_id} permanently deleted"]},
                metadata={"action": "delete", "workout_id": workout_id},
            )

        else:
            return ResponseBuilder.build_error_response(
                f"Invalid action: {action}",
                "invalid_parameters",
                [
                    "Valid actions: 'list', 'get', 'download', 'upload', 'schedule', "
                    "'unschedule', 'delete', 'list_scheduled'"
                ],
            )

    except GarminAPIError as e:
        return ResponseBuilder.build_error_response(e.message, "api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
