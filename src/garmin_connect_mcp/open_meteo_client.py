"""Open-Meteo API client wrapper with error handling.

Open-Meteo (https://open-meteo.com) is a free weather forecast API for
non-commercial use (up to 10,000 calls/day) that needs no API key, no
registration, and no credit card. Unlike every other provider in this project,
there is no config class here at all — there's nothing to configure.
"""

import threading
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT_SECONDS = 30.0

_CURRENT_VARIABLES = (
    "temperature_2m,relative_humidity_2m,precipitation,weather_code,"
    "wind_speed_10m,wind_direction_10m"
)
_DAILY_VARIABLES = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "precipitation_probability_max,weather_code,wind_speed_10m_max"
)
_HOURLY_VARIABLES = "temperature_2m,precipitation_probability,weather_code,wind_speed_10m"


class OpenMeteoAPIError(Exception):
    """Base exception for Open-Meteo API errors."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class OpenMeteoInvalidParamsError(OpenMeteoAPIError):
    """Raised when Open-Meteo rejects the request parameters (HTTP 400).

    Open-Meteo returns `{"error": true, "reason": "..."}` for bad input (e.g. an
    out-of-range latitude/longitude) — the reason is surfaced directly since it's
    already a clear, actionable message.
    """


class OpenMeteoRateLimitError(OpenMeteoAPIError):
    """Raised when Open-Meteo rate-limits the request (HTTP 429).

    The free tier caps non-commercial use at 10,000 calls/day.
    """

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "Open-Meteo rate limit exceeded (free tier: 10,000 calls/day). "
            "Please wait before trying again.",
            original_error=original_error,
        )


def _map_http_status_error(error: httpx.HTTPStatusError) -> OpenMeteoAPIError:
    status = error.response.status_code
    if status == 429:
        return OpenMeteoRateLimitError(original_error=error)
    if status == 400:
        try:
            body = error.response.json()
            reason = body.get("reason") if isinstance(body, dict) else None
        except ValueError:
            reason = None
        return OpenMeteoInvalidParamsError(
            reason or f"Open-Meteo rejected the request parameters: {error.response.text[:200]}",
            original_error=error,
        )
    return OpenMeteoAPIError(
        f"Open-Meteo API error ({status}): {error.response.text[:200]}",
        original_error=error,
    )


class OpenMeteoClientWrapper:
    """Wrapper around the Open-Meteo forecast API for consistent error handling.

    No credentials, no auth header, no login — every request is a plain,
    unauthenticated GET, so unlike the other provider wrappers this constructor
    only takes a `base_url` (useful for pointing at a different Open-Meteo
    endpoint, e.g. the historical-weather or air-quality APIs, in the future).
    """

    def __init__(
        self, base_url: str = DEFAULT_BASE_URL, transport: httpx.BaseTransport | None = None
    ):
        self._client = httpx.Client(
            base_url=base_url, timeout=_REQUEST_TIMEOUT_SECONDS, transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, params: dict[str, Any]) -> Any:
        try:
            response = self._client.get("", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _map_http_status_error(e) from e
        except httpx.HTTPError as e:
            raise OpenMeteoAPIError(
                f"Network error contacting Open-Meteo: {e}", original_error=e
            ) from e

        try:
            return response.json()
        except ValueError as e:
            raise OpenMeteoAPIError(
                "Open-Meteo returned a response that wasn't valid JSON", original_error=e
            ) from e

    def get_current(self, latitude: float, longitude: float, timezone: str = "auto") -> Any:
        """Get current weather conditions for a location."""
        return self._get(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": _CURRENT_VARIABLES,
                "timezone": timezone,
            }
        )

    def get_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        include_hourly: bool = False,
        timezone: str = "auto",
    ) -> Any:
        """Get a daily (and optionally hourly) forecast for a location."""
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": _DAILY_VARIABLES,
            "forecast_days": forecast_days,
            "timezone": timezone,
        }
        if include_hourly:
            params["hourly"] = _HOURLY_VARIABLES
        return self._get(params)


class OpenMeteoClientCache:
    """Process-wide cache of one OpenMeteoClientWrapper per distinct base_url.

    Exists purely so tool calls reuse one httpx connection pool instead of
    opening a fresh one on every call — there's no credential to invalidate on,
    since there's no credential at all.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wrapper: OpenMeteoClientWrapper | None = None
        self._base_url: str | None = None

    def get_wrapper(self, base_url: str) -> OpenMeteoClientWrapper:
        with self._lock:
            if self._wrapper is not None and self._base_url == base_url:
                return self._wrapper
            wrapper = OpenMeteoClientWrapper(base_url)
            self._wrapper = wrapper
            self._base_url = base_url
            return wrapper


_client_cache = OpenMeteoClientCache()


def get_open_meteo_wrapper(base_url: str | None = None) -> OpenMeteoClientWrapper:
    """Return a cached OpenMeteoClientWrapper.

    Unlike every other provider's get_x_wrapper(), this never raises a
    config-missing error — there's nothing to configure.
    """
    return _client_cache.get_wrapper(base_url or DEFAULT_BASE_URL)
