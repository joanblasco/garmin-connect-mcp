"""Tests for ConfigMiddleware: it must surface the real Garmin auth failure reason
in the ToolError it raises, and reuse the cached client instead of always logging in."""

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext

from garmin_connect_mcp.auth import GarminConfig
from garmin_connect_mcp.client import GarminClientInitError, GarminClientWrapper
from garmin_connect_mcp.middleware import ConfigMiddleware


class FakeFastMCPContext:
    """Minimal stand-in for fastmcp.Context: records what state gets injected."""

    def __init__(self):
        self.state: dict[str, object] = {}

    async def set_state(self, key, value, serializable=False):
        self.state[key] = value


def _tool_call_context(fastmcp_context=None):
    return MiddlewareContext(message=object(), fastmcp_context=fastmcp_context)


async def _call_next(context):
    return "tool-result"


class TestConfigMiddleware:
    async def test_raises_tool_error_when_credentials_not_configured(self, monkeypatch):
        monkeypatch.setattr("garmin_connect_mcp.middleware.load_config", lambda: GarminConfig())
        monkeypatch.setattr(
            "garmin_connect_mcp.middleware.validate_credentials", lambda config: False
        )

        middleware = ConfigMiddleware()

        with pytest.raises(ToolError, match="Garmin credentials not configured"):
            await middleware.on_call_tool(_tool_call_context(), _call_next)

    async def test_raises_tool_error_with_the_real_reason_when_login_fails(self, monkeypatch):
        monkeypatch.setattr("garmin_connect_mcp.middleware.load_config", lambda: GarminConfig())
        monkeypatch.setattr(
            "garmin_connect_mcp.middleware.validate_credentials", lambda config: True
        )

        def fake_get_cached_garmin_client(config, prompt_mfa=None):
            raise GarminClientInitError(
                "Garmin authentication failed: Failed to retrieve social profile. "
                "python-garminconnect#369"
            )

        monkeypatch.setattr(
            "garmin_connect_mcp.middleware.get_cached_garmin_client",
            fake_get_cached_garmin_client,
        )

        middleware = ConfigMiddleware()

        with pytest.raises(ToolError, match="python-garminconnect#369"):
            await middleware.on_call_tool(_tool_call_context(), _call_next)

    async def test_injects_client_and_proceeds_on_success(self, monkeypatch):
        monkeypatch.setattr("garmin_connect_mcp.middleware.load_config", lambda: GarminConfig())
        monkeypatch.setattr(
            "garmin_connect_mcp.middleware.validate_credentials", lambda config: True
        )

        sentinel_client = object()
        monkeypatch.setattr(
            "garmin_connect_mcp.middleware.get_cached_garmin_client",
            lambda config, prompt_mfa=None: sentinel_client,
        )

        middleware = ConfigMiddleware()
        fastmcp_context = FakeFastMCPContext()

        result = await middleware.on_call_tool(_tool_call_context(fastmcp_context), _call_next)

        assert result == "tool-result"
        injected = fastmcp_context.state["client"]
        assert isinstance(injected, GarminClientWrapper)
        assert injected.client is sentinel_client
