"""AEMET OpenData API client wrapper with error handling.

AEMET's OpenData API (https://opendata.aemet.es/opendata/api) is a free REST API
for Spain's national weather service, authenticated with an `api_key` request
header (a JWT string AEMET issues by email on request — no OAuth flow).

Two confirmed quirks this wrapper works around, verified against the live API:

1. A missing or rejected key doesn't cleanly 401 — it can come back as a plain
   `HTTP 200` with an *empty body*. Error bodies that ARE returned use AEMET's own
   `{"estado": <code>, "descripcion": "..."}` shape rather than relying purely on
   the HTTP status.
2. Successful requests don't return the actual weather data directly. They
   return `{"descripcion": "exito", "estado": 200, "datos": "<url>", "metadatos": "<url>"}`
   — the real payload lives at the `datos` URL, which is only valid for a few
   minutes. This wrapper's `_get()` performs that second fetch transparently, so
   callers never see the two-step envelope.
"""

import json
import threading
from typing import Any

import httpx

from .aemet_auth import AemetConfig, load_aemet_config, validate_aemet_credentials

BASE_URL = "https://opendata.aemet.es/opendata/api"
_REQUEST_TIMEOUT_SECONDS = 30.0


class AemetAPIError(Exception):
    """Base exception for AEMET API errors."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class AemetConfigError(AemetAPIError):
    """Raised when AEMET_API_KEY isn't configured."""


class AemetAuthenticationError(AemetAPIError):
    """Raised when AEMET rejects the API key (401/403, or a silent empty 200)."""

    def __init__(self, message: str | None = None, original_error: Exception | None = None):
        super().__init__(
            message
            or (
                "AEMET authentication failed. Check that AEMET_API_KEY is set and valid "
                "(request one at https://opendata.aemet.es/centrodedescargas/inicio)."
            ),
            original_error=original_error,
        )


class AemetNotFoundError(AemetAPIError):
    """Raised when a resource is not found (404), e.g. an unknown municipio code."""

    def __init__(self, resource: str = "Resource", original_error: Exception | None = None):
        super().__init__(
            f"{resource} not found on AEMET. Check the municipio code and try again.",
            original_error=original_error,
        )


class AemetRateLimitError(AemetAPIError):
    """Raised when AEMET rate-limits the request (429)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "AEMET rate limit exceeded. Please wait a few minutes before trying again.",
            original_error=original_error,
        )


def _parse_json(response: httpx.Response) -> Any:
    """Parse a response body as JSON, honoring its declared charset.

    Confirmed live: AEMET's data payloads are served as
    `text/plain;charset=ISO-8859-15`, not UTF-8 — httpx.Response.json() decodes
    unconditionally as UTF-8 (per the JSON RFC) and raises UnicodeDecodeError on
    the accented characters AEMET's Spanish-language text routinely contains.
    response.text, unlike .json(), does honor the Content-Type charset, so JSON
    is parsed from that instead.
    """
    return json.loads(response.text)


def _describe_error_body(response: httpx.Response) -> str | None:
    """Extract AEMET's `descripcion` field from an error body, if present."""
    try:
        body = _parse_json(response)
    except ValueError:
        return None
    if isinstance(body, dict) and "descripcion" in body:
        return str(body["descripcion"])
    return None


def _map_http_status_error(error: httpx.HTTPStatusError) -> AemetAPIError:
    status = error.response.status_code
    descripcion = _describe_error_body(error.response)

    if status in (401, 403):
        message = f"AEMET authentication failed: {descripcion}" if descripcion else None
        return AemetAuthenticationError(message=message, original_error=error)
    if status == 404:
        return AemetNotFoundError(original_error=error)
    if status == 429:
        return AemetRateLimitError(original_error=error)
    return AemetAPIError(
        f"AEMET API error ({status}): {descripcion or error.response.text[:200]}",
        original_error=error,
    )


class AemetClientWrapper:
    """Wrapper around the AEMET OpenData API for consistent error handling.

    No SDK to proxy onto — this makes the HTTP calls itself, funnelling every
    request through `_get()`, which also resolves AEMET's two-step data-URL
    envelope transparently (see module docstring).
    """

    def __init__(self, config: AemetConfig, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"api_key": config.aemet_api_key},
            timeout=_REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(path)
        except httpx.HTTPError as e:
            raise AemetAPIError(f"Network error contacting AEMET: {e}", original_error=e) from e

        # Confirmed quirk: a missing/rejected key can come back as HTTP 200 with
        # an empty body, rather than a clean 401 — must be checked before
        # raise_for_status(), which would otherwise treat this as success.
        if response.status_code == 200 and not response.content:
            raise AemetAuthenticationError(
                "AEMET returned an empty response, which usually means AEMET_API_KEY "
                "is missing or was silently rejected."
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _map_http_status_error(e) from e

        try:
            envelope = _parse_json(response)
        except ValueError as e:
            raise AemetAPIError(
                "AEMET returned a response that wasn't valid JSON", original_error=e
            ) from e

        datos_url = envelope.get("datos") if isinstance(envelope, dict) else None
        if not datos_url:
            raise AemetAPIError(f"AEMET response was missing the expected 'datos' URL: {envelope}")

        try:
            data_response = self._client.get(datos_url)
            data_response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise AemetAPIError(
                "AEMET's temporary data link could not be fetched — it may have expired "
                "(valid for only a few minutes). Retry the request.",
                original_error=e,
            ) from e
        except httpx.HTTPError as e:
            raise AemetAPIError(
                f"Network error fetching AEMET data payload: {e}", original_error=e
            ) from e

        try:
            return _parse_json(data_response)
        except ValueError as e:
            raise AemetAPIError("AEMET data payload wasn't valid JSON", original_error=e) from e

    def get_forecast_daily(self, municipio_code: str) -> Any:
        """Get the 8-day daily forecast for a municipality (5-digit INE code)."""
        return self._get(f"/prediccion/especifica/municipio/diaria/{municipio_code}")

    def get_forecast_hourly(self, municipio_code: str) -> Any:
        """Get the 72-hour hourly forecast for a municipality (5-digit INE code)."""
        return self._get(f"/prediccion/especifica/municipio/horaria/{municipio_code}")


class AemetClientCache:
    """Process-wide cache of one AemetClientWrapper per distinct config.

    Purely for httpx connection-pool reuse — AEMET's api_key is a stable,
    non-expiring credential, so there's no login/invalidation dance needed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wrapper: AemetClientWrapper | None = None
        self._fingerprint: str | None = None

    def get_wrapper(self, config: AemetConfig) -> AemetClientWrapper:
        fingerprint = config.aemet_api_key
        with self._lock:
            if self._wrapper is not None and self._fingerprint == fingerprint:
                return self._wrapper
            wrapper = AemetClientWrapper(config)
            self._wrapper = wrapper
            self._fingerprint = fingerprint
            return wrapper


_client_cache = AemetClientCache()


def get_aemet_wrapper(config: AemetConfig | None = None) -> AemetClientWrapper:
    """Return a cached, validated AemetClientWrapper.

    Raises:
        AemetConfigError: AEMET_API_KEY isn't configured.
    """
    cfg = config or load_aemet_config()
    if not validate_aemet_credentials(cfg):
        raise AemetConfigError(
            "AEMET credentials not configured. Set the AEMET_API_KEY environment "
            "variable (request a free key at "
            "https://opendata.aemet.es/centrodedescargas/inicio)."
        )
    return _client_cache.get_wrapper(cfg)
