"""Tests for the manage_workouts tool, including the new schedule/unschedule/delete actions."""

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


class TestInvalidAction:
    async def test_unknown_action_lists_all_valid_actions_including_new_ones(self, ctx):
        result = await manage_workouts(action="bogus", ctx=ctx)

        suggestions = _error(result)["suggestions"][0]
        for action in ["list", "get", "download", "upload", "schedule", "unschedule", "delete"]:
            assert action in suggestions
