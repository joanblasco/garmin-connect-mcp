"""Tests for static bearer-token authentication used by remote HTTP deployments."""

import pytest
from fastmcp.server.auth import MultiAuth

from garmin_connect_mcp.auth import GarminConfig, has_inline_tokens, validate_credentials
from garmin_connect_mcp.http_auth import StaticTokenVerifier, build_auth_provider
from garmin_connect_mcp.oauth_bridge import SingleClientOAuthBridge

VALID_TOKEN = "a" * 64
VALID_OAUTH_SECRET = "b" * 32


class TestStaticTokenVerifier:
    async def test_accepts_matching_token(self):
        verifier = StaticTokenVerifier(VALID_TOKEN)

        access = await verifier.verify_token(VALID_TOKEN)

        assert access is not None
        assert access.token == VALID_TOKEN

    async def test_rejects_mismatched_token(self):
        verifier = StaticTokenVerifier(VALID_TOKEN)

        assert await verifier.verify_token("b" * 64) is None

    async def test_rejects_empty_token(self):
        verifier = StaticTokenVerifier(VALID_TOKEN)

        assert await verifier.verify_token("") is None

    async def test_rejects_token_that_is_a_prefix_of_the_secret(self):
        verifier = StaticTokenVerifier(VALID_TOKEN)

        assert await verifier.verify_token(VALID_TOKEN[:-1]) is None

    def test_refuses_short_secret(self):
        with pytest.raises(ValueError, match="at least 32 characters"):
            StaticTokenVerifier("too-short")


class TestBuildAuthProvider:
    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

        assert build_auth_provider() is None

    def test_returns_none_when_blank(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", "   ")

        assert build_auth_provider() is None

    def test_builds_verifier_when_set(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.delenv("OAUTH_CLIENT_SECRET", raising=False)

        assert isinstance(build_auth_provider(), StaticTokenVerifier)


class TestBuildAuthProviderWithOAuthBridge:
    """MCP_AUTH_TOKEN + OAUTH_CLIENT_SECRET together enable Claude's OAuth 'Connect'
    flow, on top of (not instead of) the plain bearer-token path."""

    def test_plain_verifier_when_oauth_secret_not_set(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.delenv("OAUTH_CLIENT_SECRET", raising=False)

        assert isinstance(build_auth_provider(), StaticTokenVerifier)

    def test_falls_back_to_plain_verifier_without_a_public_base_url(self, monkeypatch, capsys):
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.setenv("OAUTH_CLIENT_SECRET", VALID_OAUTH_SECRET)
        monkeypatch.delenv("MCP_PUBLIC_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)

        provider = build_auth_provider()

        assert isinstance(provider, StaticTokenVerifier)
        assert "no public base URL was found" in capsys.readouterr().err

    def test_builds_multi_auth_with_oauth_bridge_when_fully_configured(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.setenv("OAUTH_CLIENT_SECRET", VALID_OAUTH_SECRET)
        monkeypatch.setenv("MCP_PUBLIC_URL", "https://garmin-connect-mcp.example.onrender.com")

        provider = build_auth_provider()

        assert isinstance(provider, MultiAuth)
        assert isinstance(provider.server, SingleClientOAuthBridge)
        assert len(provider.verifiers) == 1
        assert isinstance(provider.verifiers[0], StaticTokenVerifier)

    def test_render_external_url_is_used_when_mcp_public_url_is_unset(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.setenv("OAUTH_CLIENT_SECRET", VALID_OAUTH_SECRET)
        monkeypatch.delenv("MCP_PUBLIC_URL", raising=False)
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://garmin-connect-mcp.onrender.com")

        assert isinstance(build_auth_provider(), MultiAuth)

    async def test_oauth_bridged_token_still_verifies_via_the_static_fallback(self, monkeypatch):
        """Direct/manual bearer clients must keep working exactly as before,
        regardless of whether the OAuth bridge is also configured."""
        monkeypatch.setenv("MCP_AUTH_TOKEN", VALID_TOKEN)
        monkeypatch.setenv("OAUTH_CLIENT_SECRET", VALID_OAUTH_SECRET)
        monkeypatch.setenv("MCP_PUBLIC_URL", "https://garmin-connect-mcp.example.onrender.com")

        provider = build_auth_provider()
        assert provider is not None

        access = await provider.verify_token(VALID_TOKEN)
        assert access is not None
        assert await provider.verify_token("wrong-token-entirely") is None


class TestInlineTokens:
    def test_long_token_data_is_inline(self):
        config = GarminConfig(garmin_token_data="x" * 600)

        assert has_inline_tokens(config)

    def test_short_token_data_is_not_inline(self):
        # garminconnect treats short values as filesystem paths, not token data.
        config = GarminConfig(garmin_token_data="x" * 100)

        assert not has_inline_tokens(config)

    def test_inline_tokens_alone_satisfy_credential_validation(self):
        """A remote deploy authenticates from tokens without holding the password."""
        config = GarminConfig(garmin_email="", garmin_password="", garmin_token_data="x" * 600)

        assert validate_credentials(config)

    def test_missing_credentials_and_tokens_fail_validation(self):
        config = GarminConfig(garmin_email="", garmin_password="", garmin_token_data="")

        assert not validate_credentials(config)
