"""AEMET (Spain) weather tools for the MCP server.

A separate data source from Garmin/Intervals.icu/Open-Meteo: official Spanish
national forecasts. See ..aemet_client.
"""

from typing import Annotated

from ..aemet_client import AemetAPIError, get_aemet_wrapper
from ..response_builder import ResponseBuilder

_CREDENTIALS_SUGGESTIONS = [
    "Check that AEMET_API_KEY is set and valid "
    "(request a free key at https://opendata.aemet.es/centrodedescargas/inicio)",
    "Verify the municipio_code is a valid 5-digit INE municipality code "
    "(e.g. '08019' for Barcelona) — not a MeteoCat code, which uses a different catalog",
]


async def weather_aemet_forecast_daily(
    municipio_code: Annotated[str, "5-digit INE municipality code (e.g. '08019' for Barcelona)"],
) -> str:
    """
    Get AEMET's official 8-day daily forecast for a Spanish municipality.

    municipio_code is AEMET's own 5-digit INE municipality code — not
    interchangeable with MeteoCat's municipality catalog.
    """
    try:
        wrapper = get_aemet_wrapper()
        forecast = wrapper.get_forecast_daily(municipio_code)

        return ResponseBuilder.build_response(
            data={"forecast": forecast},
            metadata={"municipio_code": municipio_code},
        )
    except AemetAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def weather_aemet_forecast_hourly(
    municipio_code: Annotated[str, "5-digit INE municipality code (e.g. '08019' for Barcelona)"],
) -> str:
    """
    Get AEMET's official 72-hour hourly forecast for a Spanish municipality.

    municipio_code is AEMET's own 5-digit INE municipality code — not
    interchangeable with MeteoCat's municipality catalog.
    """
    try:
        wrapper = get_aemet_wrapper()
        forecast = wrapper.get_forecast_hourly(municipio_code)

        return ResponseBuilder.build_response(
            data={"forecast": forecast},
            metadata={"municipio_code": municipio_code},
        )
    except AemetAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
