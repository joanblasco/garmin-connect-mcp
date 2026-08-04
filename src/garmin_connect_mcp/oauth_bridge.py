"""Minimal single-client OAuth 2.1 authorization server fronting MCP_AUTH_TOKEN.

Claude's connector UI only accepts two authentication shapes for a custom
connector: OAuth (with a Client ID and an optional Client Secret), or a
request-header credential that is currently gated behind an admin-only beta
flag. Since neither Claude Desktop nor claude.ai lets an individual paste a
raw bearer token into a header field, this module gives Claude an OAuth
"front door" to walk through while the actual protection stays exactly what
it already was: MCP_AUTH_TOKEN, checked by the same StaticTokenVerifier used
for direct/manual clients (see http_auth.py).

Design, and why it's safe to auto-approve without a login form:

- Dynamic Client Registration is permanently disabled
  (``ClientRegistrationOptions(enabled=False)``), so the ``/register`` route
  is never mounted. There is no way for an unknown caller to mint themselves
  a client.
- Exactly one client is pre-registered at startup, from
  ``OAUTH_CLIENT_ID``/``OAUTH_CLIENT_SECRET``. Only whoever typed that
  client_id/client_secret pair into Claude's connector settings can ever
  reach the token exchange as that client — the SDK's ``ClientAuthenticator``
  enforces the client_secret check on every ``/token`` call.
- Because only the pre-registered client can ever get this far, ``authorize()``
  approving immediately (no login/consent form) doesn't weaken anything: the
  gate already happened, implicitly, the moment Claude presented a valid
  client_secret it could only have gotten from the owner.
- The access token minted at the end of the exchange is MCP_AUTH_TOKEN
  itself, not a freshly generated, disconnected value. This means OAuth
  never becomes a second, independently-trusted path into the server: an
  OAuth-obtained token and a manually-configured bearer token are the same
  string, checked the same way, everywhere.
"""

import secrets
import time

from fastmcp.server.auth.auth import OAuthProvider
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl

# Fixed callback registered by Anthropic for hosted Claude surfaces (web,
# Desktop, mobile, Cowork). Both domains are listed because Claude has
# historically used claude.ai and claude.com interchangeably for this
# callback; Claude Code and other loopback clients are out of scope here.
# https://claude.com/docs/connectors/building/authentication#callback-urls
CLAUDE_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
]

AUTH_CODE_EXPIRY_SECONDS = 5 * 60


class SingleClientOAuthBridge(OAuthProvider):
    """Auto-approving OAuth server for exactly one pre-registered client.

    Unlike fastmcp's ``InMemoryOAuthProvider`` (built for tests: open
    registration, random per-session tokens), this provider never accepts a
    second client and always mints the caller's real MCP_AUTH_TOKEN as the
    access token.
    """

    def __init__(
        self,
        *,
        base_url: AnyHttpUrl | str,
        client_id: str,
        client_secret: str,
        mcp_auth_token: str,
    ) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=False),
        )
        self._mcp_auth_token = mcp_auth_token
        self._client = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[AnyUrl(uri) for uri in CLAUDE_REDIRECT_URIS],
            grant_types=["authorization_code", "refresh_token"],
            token_endpoint_auth_method="client_secret_post",
        )
        self._auth_codes: dict[str, AuthorizationCode] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if client_id != self._client.client_id:
            return None
        return self._client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Unreachable in practice: client_registration_options.enabled=False means
        # FastMCP never mounts the /register route. Refuse defensively in case
        # something calls this directly.
        raise NotImplementedError(
            "Dynamic client registration is disabled; only the pre-configured "
            "OAUTH_CLIENT_ID is accepted."
        )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Issue an authorization code immediately, with no login/consent form.

        Safe because only the single pre-registered client can ever reach this
        point (get_client() rejects any other client_id upstream), and that
        client could only have been configured by whoever knows
        OAUTH_CLIENT_SECRET.
        """
        code_value = f"garmin_mcp_{secrets.token_hex(24)}"
        self._auth_codes[code_value] = AuthorizationCode(
            code=code_value,
            client_id=client.client_id,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTH_CODE_EXPIRY_SECONDS,
            code_challenge=params.code_challenge,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code_value, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        if authorization_code.code not in self._auth_codes:
            raise TokenError("invalid_grant", "Authorization code not found or already used.")
        del self._auth_codes[authorization_code.code]  # one-time use

        return OAuthToken(
            access_token=self._mcp_auth_token,
            token_type="Bearer",
            # MCP_AUTH_TOKEN doesn't expire on a timer; it's only invalidated by
            # rotating it by hand, so there's no meaningful expires_in to report.
            expires_in=None,
            refresh_token=self._mcp_auth_token,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        if refresh_token != self._mcp_auth_token:
            return None
        return RefreshToken(
            token=self._mcp_auth_token,
            client_id=client.client_id,
            scopes=[],
            expires_at=None,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Same static token every time: refreshing never actually rotates
        # anything server-side, it just confirms the caller still holds it.
        return OAuthToken(
            access_token=self._mcp_auth_token,
            token_type="Bearer",
            expires_in=None,
            refresh_token=self._mcp_auth_token,
            scope=" ".join(scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token != self._mcp_auth_token:
            return None
        return AccessToken(
            token=token,
            client_id=self._client.client_id,
            scopes=[],
            expires_at=None,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # MCP_AUTH_TOKEN is a single static secret shared by every caller, not
        # a per-session value tracked here — there's nothing session-scoped to
        # revoke. To invalidate every outstanding token at once, rotate
        # MCP_AUTH_TOKEN itself (and update it in Claude's connector settings).
        pass
