"""Tests for the manage_workouts tool, including the schedule/unschedule/delete/
list_scheduled actions."""

import json

from garmin_connect_mcp.tools.workouts import manage_workouts


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestGetAction:
    async def test_get_calls_get_workout_by_id_not_get_workout(self, client_stub, ctx):
        """Regression test: 'get' used to call the nonexistent 'get_workout', which
        always failed with 'Method not found'. It must call get_workout_by_id."""
        client_stub._method_results["get_workout_by_id"] = {"workoutId": 42, "workoutName": "X"}

        result = await manage_workouts(action="get", workout_id=42, ctx=ctx)

        assert _data(result)["workout"] == {"workoutId": 42, "workoutName": "X"}
        called_methods = [name for name, _, _ in client_stub.calls]
        assert "get_workout_by_id" in called_methods
        assert "get_workout" not in called_methods

    async def test_get_without_workout_id_is_a_validation_error(self, ctx):
        result = await manage_workouts(action="get", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestScheduleAndUnschedule:
    async def test_schedule_calls_schedule_workout_with_id_and_date(self, client_stub, ctx):
        client_stub._method_results["schedule_workout"] = {"workoutScheduleId": 999}

        result = await manage_workouts(action="schedule", workout_id=1, date="2026-08-07", ctx=ctx)

        assert _data(result)["scheduled_workout"] == {"workoutScheduleId": 999}
        assert ("schedule_workout", (1, "2026-08-07"), {}) in client_stub.calls

    async def test_unschedule_calls_unschedule_workout_with_scheduled_id(self, client_stub, ctx):
        client_stub._method_results["unschedule_workout"] = {}

        result = await manage_workouts(action="unschedule", scheduled_workout_id=999, ctx=ctx)

        assert _data(result) == {"result": {}}
        assert ("unschedule_workout", (999,), {}) in client_stub.calls

    async def test_unschedule_without_scheduled_workout_id_is_a_validation_error(self, ctx):
        result = await manage_workouts(action="unschedule", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"

    async def test_unschedule_rejects_workout_id_as_a_substitute(self, ctx):
        """workout_id and scheduled_workout_id are different IDs; passing only
        workout_id must not silently be accepted for unschedule."""
        result = await manage_workouts(action="unschedule", workout_id=1, ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestDeleteAction:
    async def test_delete_without_confirmation_is_refused(self, client_stub, ctx):
        result = await manage_workouts(action="delete", workout_id=1, ctx=ctx)

        assert _error(result)["type"] == "confirmation_required"
        assert client_stub.calls == []  # never reached the API

    async def test_delete_with_confirmation_calls_delete_workout(self, client_stub, ctx):
        client_stub._method_results["delete_workout"] = {}

        result = await manage_workouts(action="delete", workout_id=1, confirm_delete=True, ctx=ctx)

        assert _data(result) == {"result": {}}
        assert ("delete_workout", (1,), {}) in client_stub.calls

    async def test_delete_without_workout_id_is_a_validation_error_even_if_confirmed(self, ctx):
        result = await manage_workouts(action="delete", confirm_delete=True, ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


def _calendar_item(item_id, date, title="Workout", workout_id=1, item_type="workout"):
    """A trimmed calendarItems entry shaped like Garmin's get_scheduled_workouts response."""
    return {
        "id": item_id,
        "itemType": item_type,
        "date": date,
        "workoutId": workout_id,
        "title": title,
        "sportTypeKey": "cycling",
    }


class TestListScheduled:
    async def test_requires_both_start_and_end_date(self, ctx):
        result = await manage_workouts(action="list_scheduled", start_date="2026-08-01", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"

    async def test_rejects_start_date_after_end_date(self, ctx):
        result = await manage_workouts(
            action="list_scheduled", start_date="2026-08-31", end_date="2026-08-01", ctx=ctx
        )

        assert _error(result)["type"] == "invalid_parameters"

    async def test_rejects_range_spanning_too_many_months(self, ctx):
        result = await manage_workouts(
            action="list_scheduled", start_date="2020-01-01", end_date="2026-08-01", ctx=ctx
        )

        assert _error(result)["type"] == "invalid_parameters"

    async def test_calls_get_scheduled_workouts_once_per_calendar_month_in_range(
        self, client_stub, ctx
    ):
        client_stub._method_results["get_scheduled_workouts"] = {"calendarItems": []}

        await manage_workouts(
            action="list_scheduled", start_date="2026-07-15", end_date="2026-09-01", ctx=ctx
        )

        called_with = [
            args for name, args, _ in client_stub.calls if name == "get_scheduled_workouts"
        ]
        assert called_with == [(2026, 7), (2026, 8), (2026, 9)]

    async def test_returns_workouts_within_range_with_their_scheduled_workout_id(
        self, client_stub, ctx
    ):
        client_stub._method_results["get_scheduled_workouts"] = {
            "calendarItems": [_calendar_item(999, "2026-08-07", title="Threshold intervals")]
        }

        result = await manage_workouts(
            action="list_scheduled", start_date="2026-08-01", end_date="2026-08-31", ctx=ctx
        )

        assert _data(result)["scheduled_workouts"] == [
            {
                "scheduled_workout_id": 999,
                "workout_id": 1,
                "name": "Threshold intervals",
                "date": "2026-08-07",
                "sport_type": "cycling",
            }
        ]
        assert _data(result)["count"] == 1

    async def test_excludes_items_outside_the_requested_range(self, client_stub, ctx):
        # Garmin's month endpoint pads the response with a few leading/trailing days
        # from adjacent months to fill out the calendar grid.
        client_stub._method_results["get_scheduled_workouts"] = {
            "calendarItems": [
                _calendar_item(1, "2026-07-30", title="Late July"),
                _calendar_item(2, "2026-08-15", title="Mid August"),
                _calendar_item(3, "2026-09-02", title="Early September"),
            ]
        }

        result = await manage_workouts(
            action="list_scheduled", start_date="2026-08-01", end_date="2026-08-31", ctx=ctx
        )

        names = [entry["name"] for entry in _data(result)["scheduled_workouts"]]
        assert names == ["Mid August"]

    async def test_excludes_completed_activities_not_just_scheduled_workouts(
        self, client_stub, ctx
    ):
        client_stub._method_results["get_scheduled_workouts"] = {
            "calendarItems": [
                _calendar_item(1, "2026-08-06", item_type="activity"),
                _calendar_item(2, "2026-08-07", item_type="workout"),
            ]
        }

        result = await manage_workouts(
            action="list_scheduled", start_date="2026-08-01", end_date="2026-08-31", ctx=ctx
        )

        ids = [entry["scheduled_workout_id"] for entry in _data(result)["scheduled_workouts"]]
        assert ids == [2]

    async def test_dedupes_an_entry_returned_by_two_adjacent_month_fetches(self, client_stub, ctx):
        # The calendar-grid response for a given month can include a day that also
        # belongs to the neighbouring month's own response — same id, fetched twice.
        boundary_item = _calendar_item(999, "2026-08-01", title="Month boundary")

        def _get_scheduled_workouts(year, month):
            return {"calendarItems": [boundary_item]}

        client_stub._method_results["get_scheduled_workouts"] = _get_scheduled_workouts

        result = await manage_workouts(
            action="list_scheduled", start_date="2026-07-25", end_date="2026-08-05", ctx=ctx
        )

        assert _data(result)["count"] == 1


class TestInvalidAction:
    async def test_unknown_action_lists_all_valid_actions_including_new_ones(self, ctx):
        result = await manage_workouts(action="bogus", ctx=ctx)

        suggestions = _error(result)["suggestions"][0]
        for action in [
            "list",
            "get",
            "download",
            "upload",
            "schedule",
            "unschedule",
            "delete",
            "list_scheduled",
        ]:
            assert action in suggestions
