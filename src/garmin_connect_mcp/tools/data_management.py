"""Data management tools for Garmin Connect MCP server."""

import json
from typing import Annotated

from fastmcp import Context

from ..client import GarminAPIError
from ..response_builder import ResponseBuilder
from ..time_utils import parse_date_string


async def log_health_data(
    data_type: Annotated[str, "Data type: 'body_composition', 'blood_pressure', 'hydration'"],
    data: Annotated[
        str,
        "JSON object with the health data fields. "
        "For body_composition: {'weight': 70.5, 'body_fat': 15.2, 'body_water': 60.0}. "
        "For blood_pressure (log): {'systolic': 120, 'diastolic': 80, 'pulse': 65}. "
        "For blood_pressure (delete): {'version': '<value from a prior blood-pressure read>'}. "
        "For hydration: {'volume_ml': 500}",
    ],
    date: Annotated[str | None, "Date (YYYY-MM-DD, defaults to today)"] = None,
    action: Annotated[str, "'log' to record a new entry, or 'delete' to remove one"] = "log",
    ctx: Context | None = None,
) -> str:
    """
    Log or delete health data entries.

    Data types:
    - body_composition: Requires data with weight, body_fat, etc. (log only)
    - blood_pressure: Requires data with systolic, diastolic, pulse (log), or version (delete)
    - hydration: Requires data with volume_ml (log only)

    All data should be provided as a JSON string.
    """
    assert ctx is not None
    try:
        client = await ctx.get_state("client")

        date_str = (
            parse_date_string(date).strftime("%Y-%m-%d")
            if date
            else parse_date_string("today").strftime("%Y-%m-%d")
        )

        # Parse the JSON data
        try:
            params = json.loads(data)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON in data parameter: {e}",
                "invalid_parameters",
                ["Provide valid JSON object with the required fields"],
            )

        if action == "delete":
            if data_type != "blood_pressure":
                return ResponseBuilder.build_error_response(
                    f"Delete is not supported for data_type: {data_type}",
                    "invalid_parameters",
                    ["Only 'blood_pressure' currently supports the delete action"],
                )

            version = params.get("version")
            if not version:
                return ResponseBuilder.build_error_response(
                    "version required to delete a blood pressure entry",
                    "invalid_parameters",
                    [
                        "Provide data with a version field",
                        "The version comes from a prior blood pressure read for that date",
                    ],
                )

            result = client.safe_call("delete_blood_pressure", version, date_str)
            return ResponseBuilder.build_response(
                data={"result": result},
                analysis={"insights": [f"Blood pressure entry deleted for {date_str}"]},
                metadata={"action": "delete", "data_type": "blood_pressure", "date": date_str},
            )

        if action != "log":
            return ResponseBuilder.build_error_response(
                f"Invalid action: {action}",
                "invalid_parameters",
                ["Valid actions: 'log', 'delete'"],
            )

        if data_type == "body_composition":
            # Body composition logging
            result = client.safe_call("add_body_composition", date_str, **params)
            return ResponseBuilder.build_response(
                data={"result": result, "body_composition": params},
                analysis={"insights": [f"Body composition logged for {date_str}"]},
                metadata={"data_type": "body_composition", "date": date_str},
            )

        elif data_type == "blood_pressure":
            # Blood pressure logging. set_blood_pressure requires systolic, diastolic, and
            # pulse as positional arguments — there is no date parameter; the measurement
            # timestamp is passed separately (and defaults to "now" if omitted).
            systolic = params.get("systolic")
            diastolic = params.get("diastolic")
            pulse = params.get("pulse")

            if not systolic or not diastolic or not pulse:
                return ResponseBuilder.build_error_response(
                    "Systolic, diastolic, and pulse values are all required",
                    "invalid_parameters",
                    [
                        "Provide data with systolic, diastolic, and pulse fields",
                        'Example: {"systolic": 120, "diastolic": 80, "pulse": 65}',
                    ],
                )

            notes = params.get("notes", "")
            result = client.safe_call(
                "set_blood_pressure",
                systolic,
                diastolic,
                pulse,
                timestamp=date_str,
                notes=notes,
            )
            return ResponseBuilder.build_response(
                data={
                    "result": result,
                    "systolic": systolic,
                    "diastolic": diastolic,
                    "pulse": pulse,
                },
                analysis={
                    "insights": [
                        f"Blood pressure logged: {systolic}/{diastolic}, pulse {pulse}, on {date_str}"
                    ]
                },
                metadata={"data_type": "blood_pressure", "date": date_str},
            )

        elif data_type == "hydration":
            # Hydration logging
            volume_ml = params.get("volume_ml")

            if not volume_ml:
                return ResponseBuilder.build_error_response(
                    "Volume in ml required",
                    "invalid_parameters",
                    [
                        "Provide data with volume_ml field",
                        'Example: {"volume_ml": 500}',
                    ],
                )

            result = client.safe_call("add_hydration_data", date_str, volume_ml)
            return ResponseBuilder.build_response(
                data={"result": result, "volume_ml": volume_ml},
                analysis={"insights": [f"Hydration logged: {volume_ml} ml on {date_str}"]},
                metadata={"data_type": "hydration", "date": date_str},
            )

        else:
            return ResponseBuilder.build_error_response(
                f"Invalid data type: {data_type}",
                "invalid_parameters",
                ["Valid types: 'body_composition', 'blood_pressure', 'hydration'"],
            )

    except GarminAPIError as e:
        return ResponseBuilder.build_error_response(e.message, "api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
