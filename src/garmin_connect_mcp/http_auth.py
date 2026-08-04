"""Static bearer-token authentication for remote HTTP deployments.

The stdio transport is protected by the OS: only the local user can speak to the
process. Once the server is exposed over HTTP, anything that can reach the URL can
read the owner's Garmin data, so a shared secret is required.

This module is only wired up when ``MCP_AUTH_TOKEN`` is set, so local stdio usage
keeps working unchanged.
"""

import os
import secrets
import sys

from fastmcp.server.auth import AccessToken, MultiAuth, TokenVerifier

from .oauth_bridge import SingleClientOAuthBridge

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


DEFAULT_OAUTH_CLIENT_ID = "garmin-connect-mcp"


def build_auth_provider() -> StaticTokenVerifier | MultiAuth | None:
    """Build the auth provider from the environment, if configured.

    Returns None when ``MCP_AUTH_TOKEN`` is unset, leaving the server unauthenticated.
    That is the correct default for stdio but unsafe over HTTP, which
    :func:`garmin_connect_mcp.server.main` guards against separately.

    When ``OAUTH_CLIENT_SECRET`` is also set, wraps the static verifier with
    :class:`~garmin_connect_mcp.oauth_bridge.SingleClientOAuthBridge` so clients that
    can only speak OAuth (such as Claude's connector UI, which has no field for a raw
    bearer token) can complete a normal-looking "Connect" flow. This is purely a
    protocol adapter: the token it ultimately hands out is MCP_AUTH_TOKEN itself, so
    every caller — OAuth or direct bearer — is checked the exact same way.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return None

    static_verifier = StaticTokenVerifier(token)

    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "").strip()
    if not client_secret:
        return static_verifier

    base_url = (
        os.environ.get("MCP_PUBLIC_URL", "").strip()
        or os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    )
    if not base_url:
        print(
            "OAUTH_CLIENT_SECRET is set but no public base URL was found "
            "(MCP_PUBLIC_URL or RENDER_EXTERNAL_URL). Falling back to plain bearer-token "
            "auth; Claude's OAuth 'Connect' flow will not work until one is set.",
            file=sys.stderr,
        )
        return static_verifier

    client_id = os.environ.get("OAUTH_CLIENT_ID", DEFAULT_OAUTH_CLIENT_ID).strip()
    oauth_bridge = SingleClientOAuthBridge(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        mcp_auth_token=token,
    )
    return MultiAuth(server=oauth_bridge, verifiers=[static_verifier])
