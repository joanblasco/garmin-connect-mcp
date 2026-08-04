"""Static bearer-token authentication for remote HTTP deployments.

The stdio transport is protected by the OS: only the local user can speak to the
process. Once the server is exposed over HTTP, anything that can reach the URL can
read the owner's Garmin data, so a shared secret is required.

This module is only wired up when ``MCP_AUTH_TOKEN`` is set, so local stdio usage
keeps working unchanged.
"""

import os
import secrets

from fastmcp.server.auth import AccessToken, TokenVerifier

MIN_TOKEN_LENGTH = 32


class StaticTokenVerifier(TokenVerifier):
    """Verify bearer tokens against a single shared secret.

    Intended for single-user self-hosted deployments where a full OAuth provider
    would be disproportionate. Comparison is constant-time to avoid leaking the
    secret through response timing.
    """

    def __init__(self, token: str, **kwargs) -> None:
        if len(token) < MIN_TOKEN_LENGTH:
            raise ValueError(
                f"MCP_AUTH_TOKEN must be at least {MIN_TOKEN_LENGTH} characters; "
                f"got {len(token)}. Generate one with: openssl rand -hex 32"
            )
        super().__init__(**kwargs)
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return an access token when the presented bearer matches the secret."""
        if not secrets.compare_digest(token, self._token):
            return None

        return AccessToken(
            token=token,
            client_id="garmin-connect-mcp-owner",
            scopes=[],
            expires_at=None,
        )


def build_auth_provider() -> StaticTokenVerifier | None:
    """Build the auth provider from the environment, if configured.

    Returns None when ``MCP_AUTH_TOKEN`` is unset, leaving the server unauthenticated.
    That is the correct default for stdio but unsafe over HTTP, which
    :func:`garmin_connect_mcp.server.main` guards against separately.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return None
    return StaticTokenVerifier(token)
