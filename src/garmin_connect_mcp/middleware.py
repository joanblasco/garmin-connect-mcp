"""Middleware for Garmin Connect MCP server.

This module provides middleware components that run before tool execution.
"""

from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .auth import load_config, validate_credentials
from .client import GarminClientInitError, GarminClientWrapper, get_cached_garmin_client


class ConfigMiddleware(Middleware):
    """Middleware that provides an authenticated Garmin client for all tool calls.

    This middleware:
    1. Loads the Garmin config from environment variables
    2. Validates that credentials are properly configured
    3. Fetches the (process-cached) authenticated Garmin client
    4. Injects the client into the context state for tools to access via ctx.get_state("client")
    5. Raises ToolError with the real reason if authentication fails
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next: Callable[..., Any]):
        """Provide an authenticated Garmin client before every tool call."""
        # Intervals.icu tools (tools/intervals.py) are a separate data source: they
        # authenticate independently via INTERVALS_API_KEY/INTERVALS_ATHLETE_ID and
        # fetch their own client directly, so they must not be blocked behind Garmin
        # credentials being configured.
        tool_name = getattr(context.message, "name", "")
        if tool_name.startswith("intervals_"):
            return await call_next(context)

        # Load and validate configuration
        config = load_config()

        if not validate_credentials(config):
            raise ToolError(
                "Garmin credentials not configured. "
                "Please run 'garmin-connect-mcp auth' to set up authentication."
            )

        # Reuse the cached client when possible; only logs in when there isn't one
        # yet (or a prior live call invalidated it), instead of on every tool call.
        try:
            client = get_cached_garmin_client(config)
        except GarminClientInitError as err:
            raise ToolError(str(err)) from err

        client_wrapper = GarminClientWrapper(client)

        # Inject client into context state for tools to access
        if context.fastmcp_context:
            await context.fastmcp_context.set_state(
                "client",
                client_wrapper,
                serializable=False,
            )

        # Continue to the tool execution
        return await call_next(context)
