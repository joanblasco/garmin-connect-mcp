"""Tests for log_health_data, including the blood-pressure fix and delete action."""

import json

from garmin_connect_mcp.tools.data_management import log_health_data


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestBloodPressureLog:
    async def test_log_calls_set_blood_pressure_with_systolic_diastolic_pulse(
        self, client_stub, ctx
    ):
        """Regression test: the old call passed (date_str, systolic, diastolic)
        positionally into a signature of (systolic, diastolic, pulse, ...), silently
        mismatching every argument. It must pass systolic/diastolic/pulse correctly and
        the date via the timestamp keyword, not as a positional argument."""
        client_stub._method_results["set_blood_pressure"] = {"version": 123}

        result = await log_health_data(
            data_type="blood_pressure",
            data='{"systolic": 120, "diastolic": 80, "pulse": 65}',
            date="2026-08-01",
            ctx=ctx,
        )

        assert _data(result)["systolic"] == 120
        name, args, kwargs = client_stub.calls[0]
        assert name == "set_blood_pressure"
        assert args == (120, 80, 65)
        assert kwargs["timestamp"] == "2026-08-01"

    async def test_log_without_pulse_is_a_validation_error_not_a_silent_api_call(
        self, client_stub, ctx
    ):
        result = await log_health_data(
            data_type="blood_pressure",
            data='{"systolic": 120, "diastolic": 80}',
            ctx=ctx,
        )

        assert _error(result)["type"] == "invalid_parameters"
        assert client_stub.calls == []  # never reached the (broken) API call


class TestBloodPressureDelete:
    async def test_delete_calls_delete_blood_pressure_with_version_and_date(self, client_stub, ctx):
        client_stub._method_results["delete_blood_pressure"] = {}

        result = await log_health_data(
            data_type="blood_pressure",
            action="delete",
            data='{"version": 1785945403601}',
            date="2026-08-01",
            ctx=ctx,
        )

        assert _data(result) == {"result": {}}
        assert ("delete_blood_pressure", (1785945403601, "2026-08-01"), {}) in client_stub.calls

    async def test_delete_without_version_is_a_validation_error(self, ctx):
        result = await log_health_data(
            data_type="blood_pressure", action="delete", data="{}", ctx=ctx
        )

        assert _error(result)["type"] == "invalid_parameters"

    async def test_delete_is_only_supported_for_blood_pressure(self, ctx):
        result = await log_health_data(data_type="hydration", action="delete", data="{}", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestBodyCompositionAndHydrationUnaffected:
    """These data types weren't touched by the fix; confirm they still work."""

    async def test_body_composition_log_still_works(self, client_stub, ctx):
        client_stub._method_results["add_body_composition"] = {}

        result = await log_health_data(
            data_type="body_composition", data='{"weight": 70.5}', date="2026-08-01", ctx=ctx
        )

        assert _data(result)["body_composition"] == {"weight": 70.5}

    async def test_hydration_log_still_works(self, client_stub, ctx):
        client_stub._method_results["add_hydration_data"] = {}

        result = await log_health_data(
            data_type="hydration", data='{"volume_ml": 500}', date="2026-08-01", ctx=ctx
        )

        assert _data(result)["volume_ml"] == 500


class TestInvalidAction:
    async def test_unknown_top_level_action_is_a_validation_error(self, ctx):
        result = await log_health_data(
            data_type="blood_pressure", action="bogus", data="{}", ctx=ctx
        )

        assert _error(result)["type"] == "invalid_parameters"
