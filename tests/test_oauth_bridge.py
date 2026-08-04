"""Tests for the single-client OAuth bridge used to satisfy Claude's connector UI."""

import time

import pytest
from mcp.server.auth.provider import AuthorizationParams, TokenError
from pydantic import AnyUrl

from garmin_connect_mcp.oauth_bridge import SingleClientOAuthBridge

CLIENT_ID = "garmin-connect-mcp-test"
CLIENT_SECRET = "s" * 32
MCP_AUTH_TOKEN = "t" * 64
REDIRECT_URI = AnyUrl("https://claude.ai/api/mcp/auth_callback")


def make_bridge() -> SingleClientOAuthBridge:
    return SingleClientOAuthBridge(
        base_url="http://127.0.0.1:8000",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        mcp_auth_token=MCP_AUTH_TOKEN,
    )


def make_params(**overrides) -> AuthorizationParams:
    defaults = dict(
        state="xyz",
        scopes=None,
        code_challenge="challenge",
        redirect_uri=REDIRECT_URI,
        redirect_uri_provided_explicitly=True,
    )
    defaults.update(overrides)
    return AuthorizationParams(**defaults)


class TestClientLookup:
    async def test_returns_the_preregistered_client(self):
        bridge = make_bridge()

        client = await bridge.get_client(CLIENT_ID)

        assert client is not None
        assert client.client_id == CLIENT_ID
        assert client.client_secret == CLIENT_SECRET

    async def test_returns_none_for_any_other_client_id(self):
        bridge = make_bridge()

        assert await bridge.get_client("someone-else") is None

    async def test_dynamic_registration_is_refused(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)

        with pytest.raises(NotImplementedError):
            await bridge.register_client(client)


class TestAuthorizeAndExchange:
    async def test_authorize_issues_a_redirect_with_a_code(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)

        redirect = await bridge.authorize(client, make_params())

        assert redirect.startswith(str(REDIRECT_URI))
        assert "code=garmin_mcp_" in redirect
        assert "state=xyz" in redirect

    async def test_exchange_returns_mcp_auth_token_as_the_access_token(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)
        await bridge.authorize(client, make_params())
        auth_code = next(iter(bridge._auth_codes.values()))

        token = await bridge.exchange_authorization_code(client, auth_code)

        assert token.access_token == MCP_AUTH_TOKEN
        assert token.refresh_token == MCP_AUTH_TOKEN
        assert token.token_type == "Bearer"

    async def test_code_is_single_use(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)
        await bridge.authorize(client, make_params())
        auth_code = next(iter(bridge._auth_codes.values()))

        await bridge.exchange_authorization_code(client, auth_code)

        with pytest.raises(TokenError, match="already used"):
            await bridge.exchange_authorization_code(client, auth_code)

    async def test_load_authorization_code_rejects_expired_codes(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)
        await bridge.authorize(client, make_params())
        code_value, auth_code = next(iter(bridge._auth_codes.items()))
        bridge._auth_codes[code_value] = auth_code.model_copy(
            update={"expires_at": time.time() - 1}
        )

        assert await bridge.load_authorization_code(client, code_value) is None

    async def test_load_authorization_code_rejects_a_different_clients_code(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)
        assert client is not None
        await bridge.authorize(client, make_params())
        code_value, auth_code = next(iter(bridge._auth_codes.items()))
        other_client = client.model_copy(update={"client_id": "not-the-real-client"})

        assert await bridge.load_authorization_code(other_client, code_value) is None


class TestRefreshToken:
    async def test_refresh_returns_mcp_auth_token_again(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)

        token = await bridge.exchange_refresh_token(client, refresh_token=None, scopes=[])

        assert token.access_token == MCP_AUTH_TOKEN

    async def test_load_refresh_token_accepts_only_mcp_auth_token(self):
        bridge = make_bridge()
        client = await bridge.get_client(CLIENT_ID)

        assert await bridge.load_refresh_token(client, MCP_AUTH_TOKEN) is not None
        assert await bridge.load_refresh_token(client, "some-other-value") is None


class TestAccessTokenVerification:
    async def test_verify_token_accepts_mcp_auth_token(self):
        bridge = make_bridge()

        access = await bridge.verify_token(MCP_AUTH_TOKEN)

        assert access is not None
        assert access.token == MCP_AUTH_TOKEN

    async def test_verify_token_rejects_anything_else(self):
        bridge = make_bridge()

        assert await bridge.verify_token("a-random-guess") is None
        assert await bridge.verify_token("") is None

    async def test_revoke_token_does_not_raise(self):
        bridge = make_bridge()
        access = await bridge.verify_token(MCP_AUTH_TOKEN)

        await bridge.revoke_token(access)
