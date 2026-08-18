"""Intervals.icu API client wrapper with error handling.

Intervals.icu's public API (https://intervals.icu/api/v1) is a plain REST API
authenticated with HTTP Basic auth: username "API_KEY", password the athlete's
generated API key (Settings > Developer Settings on intervals.icu). There's no
OAuth flow and no expiring session/token to refresh, so — unlike the Garmin
client — this wrapper needs no login step and no "invalidate cache on 401" dance;
a 401/403 here simply means the configured key or athlete ID is wrong.
"""

import threading
from typing import Any

import httpx

from .intervals_auth import IntervalsConfig, load_intervals_config, validate_intervals_credentials

BASE_URL = "https://intervals.icu/api/v1"
_REQUEST_TIMEOUT_SECONDS = 30.0


class IntervalsAPIError(Exception):
    """Base exception for Intervals.icu API errors."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class IntervalsConfigError(IntervalsAPIError):
    """Raised when INTERVALS_API_KEY/INTERVALS_ATHLETE_ID aren't configured."""


class IntervalsAuthenticationError(IntervalsAPIError):
    """Raised when Intervals.icu rejects the API key (401/403)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "Intervals.icu authentication failed. Check that INTERVALS_API_KEY and "
            "INTERVALS_ATHLETE_ID are correct (Settings > Developer Settings on "
            "intervals.icu).",
            original_error=original_error,
        )


class IntervalsNotFoundError(IntervalsAPIError):
    """Raised when a resource is not found (404)."""

    def __init__(self, resource: str = "Resource", original_error: Exception | None = None):
        super().__init__(
            f"{resource} not found on Intervals.icu. Check the ID or date and try again.",
            original_error=original_error,
        )


class IntervalsRateLimitError(IntervalsAPIError):
    """Raised when Intervals.icu rate-limits the request (429)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "Intervals.icu rate limit exceeded. Please wait a few minutes before trying again.",
            original_error=original_error,
        )


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop None-valued query params so they're omitted rather than sent as 'None'."""
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


def _map_http_status_error(error: httpx.HTTPStatusError) -> IntervalsAPIError:
    status = error.response.status_code
    if status in (401, 403):
        return IntervalsAuthenticationError(original_error=error)
    if status == 404:
        return IntervalsNotFoundError(original_error=error)
    if status == 429:
        return IntervalsRateLimitError(original_error=error)
    return IntervalsAPIError(
        f"Intervals.icu API error ({status}): {error.response.text[:200]}",
        original_error=error,
    )


class IntervalsClientWrapper:
    """Wrapper around the Intervals.icu REST API for consistent error handling.

    Unlike GarminClientWrapper (which proxies method calls onto an existing SDK
    object), Intervals.icu has no Python SDK to wrap — so this class makes the HTTP
    calls itself, one typed method per endpoint the tools need, all funnelled
    through `_get()` for uniform error mapping and response handling.
    """

    def __init__(self, config: IntervalsConfig, transport: httpx.BaseTransport | None = None):
        self.athlete_id = config.intervals_athlete_id
        self._client = httpx.Client(
            base_url=BASE_URL,
            auth=("API_KEY", config.intervals_api_key),
            timeout=_REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.get(path, params=_clean_params(params))
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _map_http_status_error(e) from e
        except httpx.HTTPError as e:
            raise IntervalsAPIError(
                f"Network error contacting Intervals.icu: {e}", original_error=e
            ) from e

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise IntervalsAPIError(
                "Intervals.icu returned a response that wasn't valid JSON", original_error=e
            ) from e

    def list_activities(
        self, oldest: str, newest: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """List activities for the configured athlete in [oldest, newest], newest first."""
        data = self._get(
            f"/athlete/{self.athlete_id}/activities",
            {"oldest": oldest, "newest": newest, "limit": limit},
        )
        return data or []

    def get_activity(self, activity_id: str, include_intervals: bool = False) -> Any:
        """Get full details for a single activity."""
        params = {"intervals": "true"} if include_intervals else None
        return self._get(f"/activity/{activity_id}", params)

    def list_wellness(
        self, oldest: str | None = None, newest: str | None = None
    ) -> list[dict[str, Any]]:
        """List daily wellness records (incl. CTL/ATL) for a date range."""
        data = self._get(
            f"/athlete/{self.athlete_id}/wellness", {"oldest": oldest, "newest": newest}
        )
        return data or []

    def get_wellness(self, date: str) -> Any:
        """Get the wellness record (incl. CTL/ATL) for a single date."""
        return self._get(f"/athlete/{self.athlete_id}/wellness/{date}")

    def list_events(
        self,
        oldest: str | None = None,
        newest: str | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List calendar events (planned workouts, notes, races, etc.) for a date range."""
        data = self._get(
            f"/athlete/{self.athlete_id}/events",
            {"oldest": oldest, "newest": newest, "category": category, "limit": limit},
        )
        return data or []


class IntervalsClientCache:
    """Process-wide cache of one IntervalsClientWrapper per distinct config.

    There's no login round trip to avoid repeating here (see module docstring) —
    this exists purely so tool calls reuse one httpx connection pool instead of
    opening a fresh one on every call, mirroring the caching pattern used for the
    Garmin client.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wrapper: IntervalsClientWrapper | None = None
        self._fingerprint: tuple[str, str] | None = None

    @staticmethod
    def _fingerprint_of(config: IntervalsConfig) -> tuple[str, str]:
        return (config.intervals_api_key, config.intervals_athlete_id)

    def get_wrapper(self, config: IntervalsConfig) -> IntervalsClientWrapper:
        fingerprint = self._fingerprint_of(config)
        with self._lock:
            if self._wrapper is not None and self._fingerprint == fingerprint:
                return self._wrapper
            wrapper = IntervalsClientWrapper(config)
            self._wrapper = wrapper
            self._fingerprint = fingerprint
            return wrapper


_client_cache = IntervalsClientCache()


def get_intervals_wrapper(config: IntervalsConfig | None = None) -> IntervalsClientWrapper:
    """Return a cached, validated IntervalsClientWrapper.

    This is the entry point tool functions use. Intervals.icu tools don't go
    through a middleware-injected client the way Garmin tools do (see
    tools/intervals.py) — they call this directly, since API-key auth needs no
    request-scoped setup.

    Raises:
        IntervalsConfigError: INTERVALS_API_KEY/INTERVALS_ATHLETE_ID aren't configured.
    """
    cfg = config or load_intervals_config()
    if not validate_intervals_credentials(cfg):
        raise IntervalsConfigError(
            "Intervals.icu credentials not configured. Set the INTERVALS_API_KEY and "
            "INTERVALS_ATHLETE_ID environment variables (find your API key and athlete "
            "ID under Settings > Developer Settings on intervals.icu)."
        )
    return _client_cache.get_wrapper(cfg)
