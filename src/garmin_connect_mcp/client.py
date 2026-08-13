"""Garmin Connect API client wrapper with error handling."""

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .auth import GarminConfig, get_token_base64_path, get_token_store, has_inline_tokens

_JSON_SAFE_TYPES = (dict, list, str, int, float, bool, type(None))


def _to_json_safe(value: Any) -> Any:
    """Normalize a garminconnect method's return value to something JSON-serializable.

    Most write/delete endpoints return a 204 with no body. Some garminconnect methods
    call `.json()` on the underlying HTTP response before returning (yielding a plain
    dict), but others don't and hand back the raw response-like object instead — which
    for a 204 is a library-internal sentinel class that isn't JSON-serializable. This
    normalizes either shape so every safe_call() result is safe to embed directly in a
    tool's response, regardless of which convention a given library method follows.
    """
    if isinstance(value, _JSON_SAFE_TYPES):
        return value

    json_method = getattr(value, "json", None)
    if callable(json_method):
        try:
            return json_method()
        except Exception:
            pass

    return str(value)


class GarminAPIError(Exception):
    """Custom exception for Garmin API errors."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class GarminRateLimitError(GarminAPIError):
    """Exception raised when rate limit is exceeded (HTTP 429)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "Rate limit exceeded. Please wait a few minutes before trying again.",
            original_error=original_error,
        )


class GarminNotFoundError(GarminAPIError):
    """Exception raised when resource is not found (HTTP 404)."""

    def __init__(self, resource: str = "Resource", original_error: Exception | None = None):
        super().__init__(
            f"{resource} not found. Please check the ID or date and try again.",
            original_error=original_error,
        )


class GarminAuthenticationError(GarminAPIError):
    """Exception raised when authentication fails (HTTP 401/403)."""

    def __init__(self, original_error: Exception | None = None):
        super().__init__(
            "Authentication failed. Please run 'garmin-connect-mcp auth' to re-authenticate.",
            original_error=original_error,
        )


class GarminClientInitError(Exception):
    """Raised when the Garmin client could not be authenticated/initialized.

    Carries a ready-to-show message with the real underlying reason, so callers
    (MCP tool middleware, resource handlers) can surface it directly to the end
    user instead of it only being visible in server logs.
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


# Login failures that come back from Garmin's profile/settings endpoints after an
# otherwise-successful authentication step match a known, still-open issue in the
# underlying garminconnect library rather than bad credentials on our end:
# https://github.com/cyberjunky/python-garminconnect/issues/369 (and #357). Garmin's
# API has been rejecting freshly-issued tokens there intermittently since mid-2026.
_PROFILE_FETCH_HINT = (
    "Garmin's profile/settings endpoint rejected an otherwise-valid login. This "
    "matches a known, still-open issue in the underlying garminconnect library "
    "(github.com/cyberjunky/python-garminconnect#369) rather than a problem with "
    "your credentials, and is often transient — retrying usually works. If it keeps "
    "happening, re-authenticate with 'garmin-connect-mcp auth'."
)
_GENERIC_AUTH_HINT = (
    "Check that your Garmin credentials/tokens are still valid, or re-authenticate "
    "with 'garmin-connect-mcp auth'."
)


def _describe_auth_error(err: GarminConnectAuthenticationError) -> str:
    """Build a user-facing message for a Garmin login failure, with a targeted hint."""
    reason = str(err)
    reason_lower = reason.lower()
    hint = (
        _PROFILE_FETCH_HINT
        if "social profile" in reason_lower or "user settings" in reason_lower
        else _GENERIC_AUTH_HINT
    )
    return f"Garmin authentication failed: {reason}. {hint}"


def init_garmin_client(config: GarminConfig, prompt_mfa: Callable[[], str] | None = None) -> Garmin:
    """
    Initialize and authenticate Garmin client.

    Follows the authentication pattern from the original garmin_mcp project:
    1. Try token-based login first
    2. Fall back to credential-based login with MFA support
    3. Persist tokens for future use

    Args:
        config: Garmin configuration with credentials
        prompt_mfa: Optional callback for interactive MFA prompts. Only pass this from
            interactive setup flows, not MCP runtime.

    Returns:
        Authenticated Garmin client.

    Raises:
        GarminClientInitError: Authentication/initialization failed. The message
            includes the real underlying reason so it's safe to show directly to
            the end user, not just log server-side.
    """
    try:
        # Inline tokens take precedence: on hosts with an ephemeral disk there is no
        # token directory to read, and this path never needs the account password.
        if has_inline_tokens(config):
            garmin = Garmin()
            garmin.login(config.garmin_token_data.strip())
            print("Logged in using inline token data from environment.", file=sys.stderr)
            return garmin

        tokenstore = get_token_store()

        # Try token-based login first
        try:
            # Check if tokens exist
            token_path = Path(tokenstore)
            if token_path.exists() and any(token_path.iterdir()):
                # Try to login with existing tokens
                garmin = Garmin()
                garmin.login(tokenstore)
                print("Logged in using token data from directory.", file=sys.stderr)
                return garmin
            else:
                raise FileNotFoundError("No tokens found")

        except (
            FileNotFoundError,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        ) as e:
            # Token login failed, try credential login
            print(f"Token login failed: {e}. Attempting credential-based login...", file=sys.stderr)

            # Create Garmin client with credentials. MFA prompts are only enabled when
            # an interactive caller explicitly supplies a callback.
            garmin = Garmin(
                email=config.garmin_email,
                password=config.garmin_password,
                prompt_mfa=prompt_mfa,
            )

            # Attempt credential-based login.
            garmin.login()

            # Save tokens for future use
            garmin.client.dump(tokenstore)
            print(f"OAuth tokens saved to directory: {tokenstore}", file=sys.stderr)

            # Also save base64 encoded tokens
            token_base64_path = get_token_base64_path()
            Path(token_base64_path).write_text(garmin.client.dumps())
            print(f"OAuth tokens encoded as base64: {token_base64_path}", file=sys.stderr)

            return garmin

    except GarminConnectAuthenticationError as err:
        message = _describe_auth_error(err)
        print(message, file=sys.stderr)
        raise GarminClientInitError(message, original_error=err) from err

    except GarminConnectTooManyRequestsError as err:
        message = (
            f"Garmin rate-limited the login attempt: {err}. Wait a few minutes before retrying."
        )
        print(message, file=sys.stderr)
        raise GarminClientInitError(message, original_error=err) from err

    except Exception as err:
        message = f"Unexpected error during Garmin login: {err}"
        print(message, file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        raise GarminClientInitError(message, original_error=err) from err


class GarminClientCache:
    """Process-wide cache for the authenticated Garmin client.

    garminconnect's login() always ends with a round trip to Garmin's
    `/userprofile-service/socialProfile` endpoint, which is known to be
    intermittently flaky server-side (see GarminClientInitError's docstring /
    python-garminconnect#357, #369). Its request layer also already refreshes an
    expiring or rejected token transparently on ordinary API calls (see
    garminconnect's Client._run_request), so there's no need to repeat the full
    login flow on every tool call — doing so only multiplies exposure to that
    flaky endpoint and to Garmin's own login rate limits.

    This cache keeps one authenticated client per distinct config for the life of
    the process, re-authenticating only when the config changes or invalidate()
    is called.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: Garmin | None = None
        self._cached_fingerprint: tuple[str, str, str, str] | None = None

    @staticmethod
    def _fingerprint(config: GarminConfig) -> tuple[str, str, str, str]:
        return (
            config.garmin_email,
            config.garmin_password,
            config.garmintokens,
            config.garmin_token_data,
        )

    def get_client(
        self, config: GarminConfig, prompt_mfa: Callable[[], str] | None = None
    ) -> Garmin:
        """Return the cached client, authenticating first if there isn't one yet.

        Raises:
            GarminClientInitError: See init_garmin_client.
        """
        fingerprint = self._fingerprint(config)
        with self._lock:
            if self._client is not None and self._cached_fingerprint == fingerprint:
                return self._client

            try:
                client = init_garmin_client(config, prompt_mfa)
            except GarminClientInitError:
                # Never serve a stale entry after a failed re-authentication attempt.
                self._client = None
                self._cached_fingerprint = None
                raise

            self._client = client
            self._cached_fingerprint = fingerprint
            return client

    def invalidate(self) -> None:
        """Drop the cached client, forcing the next get_client() to re-authenticate.

        Called after a live API call comes back with an authentication error: the
        cached client looked fine when it was cached but is no longer trustworthy.
        """
        with self._lock:
            self._client = None
            self._cached_fingerprint = None


_client_cache = GarminClientCache()


def get_cached_garmin_client(
    config: GarminConfig, prompt_mfa: Callable[[], str] | None = None
) -> Garmin:
    """Return a cached, authenticated Garmin client, logging in only when needed.

    This is the entry point tool middleware and resource handlers should use
    instead of calling init_garmin_client() directly, so repeated calls within
    the same process reuse one login instead of repeating it every time.

    Raises:
        GarminClientInitError: See init_garmin_client.
    """
    return _client_cache.get_client(config, prompt_mfa)


def invalidate_cached_garmin_client() -> None:
    """Force the next get_cached_garmin_client() call to re-authenticate.

    Call this after a live Garmin API call fails with an authentication error, so
    a client that looked valid at cache time but has since been rejected doesn't
    keep getting reused.
    """
    _client_cache.invalidate()


class GarminClientWrapper:
    """Wrapper around Garmin client for consistent error handling."""

    def __init__(self, client: Garmin):
        self.client = client

    def safe_call(self, method_name: str, *args, **kwargs) -> Any:
        """
        Safely call a Garmin client method with error handling.

        This method uses `Any` as the return type because it dynamically proxies calls
        to the external garminconnect library, which doesn't have type stubs. The actual
        return type depends on which Garmin API method is called.

        Args:
            method_name: Name of the Garmin client method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Method result or raises GarminAPIError

        Raises:
            GarminAuthenticationError: Authentication failed (401/403)
            GarminNotFoundError: Resource not found (404)
            GarminRateLimitError: Rate limit exceeded (429)
            GarminAPIError: Other API errors
        """
        try:
            method = getattr(self.client, method_name)
            return _to_json_safe(method(*args, **kwargs))
        except AttributeError as e:
            raise GarminAPIError(
                f"Method '{method_name}' not found on Garmin client", original_error=e
            ) from e
        except GarminConnectAuthenticationError as e:
            # The cached client looked fine when it was cached but Garmin is now
            # rejecting it live — drop it so the next call re-authenticates instead
            # of repeating the same failure indefinitely.
            invalidate_cached_garmin_client()
            raise GarminAuthenticationError(original_error=e) from e
        except GarminConnectTooManyRequestsError as e:
            raise GarminRateLimitError(original_error=e) from e
        except GarminConnectConnectionError as e:
            # Parse HTTP status code from error
            error_str = str(e)
            if "429" in error_str or "Too Many Requests" in error_str:
                raise GarminRateLimitError(original_error=e) from e
            elif "404" in error_str or "Not Found" in error_str:
                raise GarminNotFoundError(original_error=e) from e
            elif "401" in error_str or "403" in error_str or "Unauthorized" in error_str:
                invalidate_cached_garmin_client()
                raise GarminAuthenticationError(original_error=e) from e
            else:
                raise GarminAPIError(f"Garmin API error: {str(e)}", original_error=e) from e
        except Exception as e:
            raise GarminAPIError(f"Unexpected error: {str(e)}", original_error=e) from e
