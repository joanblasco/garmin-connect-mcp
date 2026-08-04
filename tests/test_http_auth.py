"""Tests for static bearer-token authentication used by remote HTTP deployments."""

import pytest

from garmin_connect_mcp.auth import GarminConfig, has_inline_tokens, validate_credentials
from garmin_connect_mcp.http_auth import StaticTokenVerifier, build_auth_provider

VALID_TOKEN = "a" * 64


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

        assert isinstance(build_auth_provider(), StaticTokenVerifier)


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
