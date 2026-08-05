"""Tests for the manage_activities tool (rename, list_types, set_type, delete)."""

import json

from garmin_connect_mcp.tools.activities import manage_activities

ACTIVITY_TYPES = [
    {"typeId": 1, "typeKey": "running", "parentTypeId": 17},
    {"typeId": 2, "typeKey": "cycling", "parentTypeId": 17},
    {"typeId": 10, "typeKey": "road_biking", "parentTypeId": 2},
]


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestRename:
    async def test_rename_calls_set_activity_name(self, client_stub, ctx):
        client_stub._method_results["set_activity_name"] = {"activityId": 5}

        result = await manage_activities(action="rename", activity_id=5, name="New title", ctx=ctx)

        assert _data(result)["result"] == {"activityId": 5}
        assert ("set_activity_name", (5, "New title"), {}) in client_stub.calls

    async def test_rename_without_name_is_a_validation_error(self, ctx):
        result = await manage_activities(action="rename", activity_id=5, ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"

    async def test_rename_without_activity_id_is_a_validation_error(self, ctx):
        result = await manage_activities(action="rename", name="X", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestListTypes:
    async def test_list_types_returns_all_entries_with_a_count(self, client_stub, ctx):
        client_stub._method_results["get_activity_types"] = ACTIVITY_TYPES

        result = await manage_activities(action="list_types", ctx=ctx)

        data = _data(result)
        assert data["count"] == 3
        assert data["activity_types"] == ACTIVITY_TYPES


class TestSetType:
    async def test_set_type_resolves_type_key_to_ids_and_calls_set_activity_type(
        self, client_stub, ctx
    ):
        client_stub._method_results["get_activity_types"] = ACTIVITY_TYPES
        client_stub._method_results["set_activity_type"] = {"activityId": 5}

        result = await manage_activities(
            action="set_type", activity_id=5, type_key="road_biking", ctx=ctx
        )

        assert _data(result)["result"] == {"activityId": 5}
        assert ("set_activity_type", (5, 10, "road_biking", 2), {}) in client_stub.calls

    async def test_set_type_with_unknown_key_suggests_close_matches(self, client_stub, ctx):
        client_stub._method_results["get_activity_types"] = ACTIVITY_TYPES

        result = await manage_activities(
            action="set_type", activity_id=5, type_key="biking", ctx=ctx
        )

        error = _error(result)
        assert error["type"] == "invalid_parameters"
        assert "road_biking" in error["suggestions"][0]
        # never reaches the actual mutation call
        assert all(name != "set_activity_type" for name, _, _ in client_stub.calls)

    async def test_set_type_without_type_key_is_a_validation_error(self, ctx):
        result = await manage_activities(action="set_type", activity_id=5, ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestDelete:
    async def test_delete_without_confirmation_is_refused(self, client_stub, ctx):
        result = await manage_activities(action="delete", activity_id=5, ctx=ctx)

        assert _error(result)["type"] == "confirmation_required"
        assert client_stub.calls == []

    async def test_delete_with_confirmation_calls_delete_activity(self, client_stub, ctx):
        client_stub._method_results["delete_activity"] = {}

        result = await manage_activities(
            action="delete", activity_id=5, confirm_delete=True, ctx=ctx
        )

        assert _data(result) == {"result": {}}
        assert ("delete_activity", (5,), {}) in client_stub.calls


class TestInvalidAction:
    async def test_unknown_action_is_a_validation_error(self, ctx):
        result = await manage_activities(action="bogus", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"
