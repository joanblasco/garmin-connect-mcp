"""Open-Meteo weather tools for the MCP server.

A separate data source from Garmin/Intervals.icu: global weather forecasts,
needing no API key or registration at all (free, non-commercial use up to
10,000 calls/day). See ..open_meteo_client.
"""

from typing import Annotated

from ..open_meteo_client import OpenMeteoAPIError, get_open_meteo_wrapper
from ..response_builder import ResponseBuilder


async def weather_openmeteo_current(
    latitude: Annotated[float, "Latitude of the location (WGS84, e.g. 41.3874)"],
    longitude: Annotated[float, "Longitude of the location (WGS84, e.g. 2.1686)"],
    timezone: Annotated[
        str, "IANA timezone name, or 'auto' to resolve it from the coordinates"
    ] = "auto",
) -> str:
    """
    Get current weather conditions (temperature, humidity, precipitation, wind,
    weather code) for any location worldwide.
    """
    try:
        wrapper = get_open_meteo_wrapper()
        current = wrapper.get_current(latitude, longitude, timezone=timezone)

        return ResponseBuilder.build_response(
            data={"current": current},
            metadata={"latitude": latitude, "longitude": longitude},
        )
    except OpenMeteoAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            "api_error",
            [
                "Check that latitude/longitude are valid coordinates",
                "Verify your internet connection",
            ],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")


async def weather_openmeteo_forecast(
    latitude: Annotated[float, "Latitude of the location (WGS84, e.g. 41.3874)"],
    longitude: Annotated[float, "Longitude of the location (WGS84, e.g. 2.1686)"],
    forecast_days: Annotated[int, "Number of days ahead to forecast (1-16)"] = 7,
    include_hourly: Annotated[
        bool, "Also include an hourly breakdown (temperature/precipitation/wind)"
    ] = False,
    timezone: Annotated[
        str, "IANA timezone name, or 'auto' to resolve it from the coordinates"
    ] = "auto",
) -> str:
    """
    Get a daily weather forecast (and optionally hourly detail) for any location
    worldwide, up to 16 days ahead.
    """
    try:
        wrapper = get_open_meteo_wrapper()
        forecast = wrapper.get_forecast(
            latitude,
            longitude,
            forecast_days=forecast_days,
            include_hourly=include_hourly,
            timezone=timezone,
        )

        return ResponseBuilder.build_response(
            data={"forecast": forecast},
            metadata={
                "latitude": latitude,
                "longitude": longitude,
                "forecast_days": forecast_days,
                "include_hourly": include_hourly,
            },
        )
    except OpenMeteoAPIError as e:
        return ResponseBuilder.build_error_response(
            e.message,
            "api_error",
            [
                "Check that latitude/longitude are valid coordinates",
                "Verify your internet connection",
            ],
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(str(e), "internal_error")
