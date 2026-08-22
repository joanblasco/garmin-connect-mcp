"""MeteoCat (Catalonia) weather tools for the MCP server.

A separate data source from Garmin/Intervals.icu/Open-Meteo/AEMET: official
Catalan regional forecasts. See ..meteocat_client.
"""

from typing import Annotated

from ..meteocat_client import MeteocatAPIError, get_meteocat_wrapper
from ..response_builder import ResponseBuilder

_CREDENTIALS_SUGGESTIONS = [
    "Check that METEOCAT_API_KEY is set and valid, and that your subscription "
    "covers the 'Predicció' data category (see https://apidocs.meteocat.gencat.cat/)",
    "Verify the codi_municipi is a valid MeteoCat municipality code — not an AEMET "
    "INE code, which uses a different catalog",
]


async def weather_meteocat_forecast_municipal(
    codi_municipi: Annotated[str, "MeteoCat municipality code"],
) -> str:
    """
    Get MeteoCat's official 8-day forecast for a Catalan municipality.

    codi_municipi is MeteoCat's own municipality code — not interchangeable
    with AEMET's INE municipality codes.
    """
    try:
        wrapper = get_meteocat_wrapper()
        forecast = wrapper.get_municipal_forecast(codi_municipi)

        return ResponseBuilder.build_response(
            data={"forecast": forecast},
            metadata={"codi_municipi": codi_municipi},
        )
    except MeteocatAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def weather_meteocat_forecast_hourly(
    codi_municipi: Annotated[str, "MeteoCat municipality code"],
) -> str:
    """
    Get MeteoCat's official 72-hour hourly forecast for a Catalan municipality.

    codi_municipi is MeteoCat's own municipality code — not interchangeable
    with AEMET's INE municipality codes.
    """
    try:
        wrapper = get_meteocat_wrapper()
        forecast = wrapper.get_municipal_hourly_forecast(codi_municipi)

        return ResponseBuilder.build_response(
            data={"forecast": forecast},
            metadata={"codi_municipi": codi_municipi},
        )
    except MeteocatAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def weather_meteocat_uv_index(
    codi_municipi: Annotated[str, "MeteoCat municipality code"],
) -> str:
    """
    Get MeteoCat's official 3-day UV index forecast for a Catalan municipality.

    codi_municipi is MeteoCat's own municipality code — not interchangeable
    with AEMET's INE municipality codes.
    """
    try:
        wrapper = get_meteocat_wrapper()
        uv_index = wrapper.get_uv_index_forecast(codi_municipi)

        return ResponseBuilder.build_response(
            data={"uv_index": uv_index},
            metadata={"codi_municipi": codi_municipi},
        )
    except MeteocatAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message, "api_error", _CREDENTIALS_SUGGESTIONS
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
