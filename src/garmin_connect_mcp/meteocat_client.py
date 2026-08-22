"""MeteoCat API client wrapper with error handling.

MeteoCat's forecast API (https://api.meteo.cat/pronostic/v1) is the Catalan
regional weather service's REST API, authenticated with a simple `x-api-key`
request header (no JWT quirks, no two-step data-URL fetch — a single request
returns the real payload directly, unlike AEMET). These endpoints also take no
query parameters, just path segments, so there's no `_clean_params()` helper
here — a deliberate simplification, not an oversight.
"""

import threading
from typing import Any

import httpx

from .meteocat_auth import MeteocatConfig, load_meteocat_config, validate_meteocat_credentials

BASE_URL = "https://api.meteo.cat/pronostic/v1"
_REQUEST_TIMEOUT_SECONDS = 30.0


class MeteocatAPIError(Exception):
    """Base exception for MeteoCat API errors."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class MeteocatConfigError(MeteocatAPIError):
    """Raised when METEOCAT_API_KEY isn't configured."""


class MeteocatAuthenticationError(MeteocatAPIError):
    """Raised when MeteoCat rejects the API key (401/403)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "MeteoCat authentication failed. Check that METEOCAT_API_KEY is set and "
            "valid, and that your subscription covers the 'Predicció' data category "
            "(see https://apidocs.meteocat.gencat.cat/).",
            original_error=original_error,
        )


class MeteocatNotFoundError(MeteocatAPIError):
    """Raised when a resource is not found (404), e.g. an unknown municipality code."""

    def __init__(self, resource: str = "Resource", original_error: Exception | None = None):
        super().__init__(
            f"{resource} not found on MeteoCat. Check the municipality code and try again.",
            original_error=original_error,
        )


class MeteocatRateLimitError(MeteocatAPIError):
    """Raised when MeteoCat rate-limits or quota-exceeds the request (429)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "MeteoCat rate limit or subscription quota exceeded. Please wait before "
            "trying again, or check your plan at https://apidocs.meteocat.gencat.cat/.",
            original_error=original_error,
        )


def _map_http_status_error(error: httpx.HTTPStatusError) -> MeteocatAPIError:
    status = error.response.status_code
    if status in (401, 403):
        return MeteocatAuthenticationError(original_error=error)
    if status == 404:
        return MeteocatNotFoundError(original_error=error)
    if status == 429:
        return MeteocatRateLimitError(original_error=error)
    return MeteocatAPIError(
        f"MeteoCat API error ({status}): {error.response.text[:200]}",
        original_error=error,
    )


class MeteocatClientWrapper:
    """Wrapper around the MeteoCat forecast API for consistent error handling."""

    def __init__(self, config: MeteocatConfig, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"x-api-key": config.meteocat_api_key},
            timeout=_REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _map_http_status_error(e) from e
        except httpx.HTTPError as e:
            raise MeteocatAPIError(
                f"Network error contacting MeteoCat: {e}", original_error=e
            ) from e

        try:
            return response.json()
        except ValueError as e:
            raise MeteocatAPIError(
                "MeteoCat returned a response that wasn't valid JSON", original_error=e
            ) from e

    def get_municipal_forecast(self, codi_municipi: str) -> Any:
        """Get the 8-day forecast for a municipality (MeteoCat's own code)."""
        return self._get(f"/municipal/{codi_municipi}")

    def get_municipal_hourly_forecast(self, codi_municipi: str) -> Any:
        """Get the 72-hour hourly forecast for a municipality."""
        return self._get(f"/municipalHoraria/{codi_municipi}")

    def get_uv_index_forecast(self, codi_municipi: str) -> Any:
        """Get the 3-day UV index forecast for a municipality."""
        return self._get(f"/uvi/{codi_municipi}")


class MeteocatClientCache:
    """Process-wide cache of one MeteocatClientWrapper per distinct config.

    Purely for httpx connection-pool reuse — the api_key is a stable,
    non-expiring credential, so there's no login/invalidation dance needed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wrapper: MeteocatClientWrapper | None = None
        self._fingerprint: str | None = None

    def get_wrapper(self, config: MeteocatConfig) -> MeteocatClientWrapper:
        fingerprint = config.meteocat_api_key
        with self._lock:
            if self._wrapper is not None and self._fingerprint == fingerprint:
                return self._wrapper
            wrapper = MeteocatClientWrapper(config)
            self._wrapper = wrapper
            self._fingerprint = fingerprint
            return wrapper


_client_cache = MeteocatClientCache()


def get_meteocat_wrapper(config: MeteocatConfig | None = None) -> MeteocatClientWrapper:
    """Return a cached, validated MeteocatClientWrapper.

    Raises:
        MeteocatConfigError: METEOCAT_API_KEY isn't configured.
    """
    cfg = config or load_meteocat_config()
    if not validate_meteocat_credentials(cfg):
        raise MeteocatConfigError(
            "MeteoCat credentials not configured. Set the METEOCAT_API_KEY environment "
            "variable (registration is free but requires a form and can take up to ~7 "
            "days for approval — see https://apidocs.meteocat.gencat.cat/)."
        )
    return _client_cache.get_wrapper(cfg)
