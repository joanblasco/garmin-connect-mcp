"""Garmin Connect MCP Server - Main entry point."""

import os
import sys
from textwrap import dedent

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# Load environment variables
load_dotenv()

from .http_auth import build_auth_provider

# Initialize FastMCP server. The auth provider is only active when MCP_AUTH_TOKEN is
# set, so stdio usage is unaffected.
mcp = FastMCP("Garmin Connect", auth=build_auth_provider())

# Register middleware
from .middleware import ConfigMiddleware

mcp.add_middleware(ConfigMiddleware())

# Import and register all tools
from .tools.activities import (
    get_activity_details,
    get_activity_social,
    manage_activities,
    query_activities,
)
from .tools.analysis import (
    compare_activities,
    find_similar_activities,
)
from .tools.challenges import (
    query_badges,
    query_challenges,
    query_goals_and_records,
)
from .tools.data_management import log_health_data
from .tools.devices import query_devices
from .tools.gear import query_gear
from .tools.health_wellness import (
    query_activity_metrics,
    query_health_summary,
    query_heart_rate_data,
    query_sleep_data,
    query_weekly_trends,
)
from .tools.intervals import (
    intervals_get_activity_details,
    intervals_get_calendar,
    intervals_get_training_load,
    intervals_list_activities,
)
from .tools.nutrition import query_nutrition
from .tools.training import (
    analyze_training_period,
    get_performance_metrics,
    get_training_effect,
    query_training_plans,
)
from .tools.user_profile import get_user_profile
from .tools.weight import manage_weight_data, query_weight_data
from .tools.womens_health import query_womens_health
from .tools.workouts import manage_workouts

# Register activity tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_activities)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(get_activity_details)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(get_activity_social)
mcp.tool(
    annotations={
        "readOnlyHint": False,
        "openWorldHint": False,
        "destructiveHint": True,
    }
)(manage_activities)

# Register analysis tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(compare_activities)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(find_similar_activities)

# Register health & wellness tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_health_summary)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_sleep_data)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_heart_rate_data)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_activity_metrics)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_weekly_trends)

# Register device & gear tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_devices)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_gear)

# Register user profile tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(get_user_profile)

# Register challenge tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_goals_and_records)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_challenges)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_badges)

# Register training tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(analyze_training_period)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(get_performance_metrics)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(get_training_effect)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_training_plans)

# Register nutrition tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_nutrition)

# Register weight tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_weight_data)
mcp.tool(
    annotations={
        "readOnlyHint": False,
        "openWorldHint": False,
        "destructiveHint": False,
    }
)(manage_weight_data)

# Register workout tools
mcp.tool(
    annotations={
        "readOnlyHint": False,
        "openWorldHint": False,
        "destructiveHint": True,
    }
)(manage_workouts)

# Register data management tools
mcp.tool(
    annotations={
        "readOnlyHint": False,
        "openWorldHint": False,
        "destructiveHint": True,
    }
)(log_health_data)

# Register women's health tools
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(query_womens_health)

# Register Intervals.icu tools (separate data source, see tools/intervals.py)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(intervals_list_activities)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(intervals_get_activity_details)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(intervals_get_training_load)
mcp.tool(
    annotations={
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)(intervals_get_calendar)


# ============================================================================
# MCP Resources - Provide ongoing context to the LLM
# ============================================================================


@mcp.resource(
    "garmin://athlete/profile",
    annotations={
        "readOnlyHint": True,
    },
)
async def athlete_profile_resource() -> str:
    """Provide athlete profile with stats and zones for context-aware clients."""
    # Resources don't go through middleware, so we fetch the cached client directly
    from .auth import load_config
    from .client import GarminClientInitError, GarminClientWrapper, get_cached_garmin_client
    from .response_builder import ResponseBuilder

    config = load_config()
    try:
        client = get_cached_garmin_client(config)
    except GarminClientInitError as err:
        return ResponseBuilder.build_error_response(str(err))

    wrapper = GarminClientWrapper(client)

    # Get basic profile
    full_name = wrapper.safe_call("get_full_name")
    unit_system = wrapper.safe_call("get_unit_system")

    # Get stats
    user_summary = wrapper.safe_call("get_user_summary")
    daily_stats = wrapper.safe_call("get_stats", "today")

    return ResponseBuilder.build_response(
        data={
            "profile": {"name": full_name, "unit_system": unit_system},
            "summary": user_summary,
            "stats": daily_stats,
        },
        metadata={"resource": "athlete_profile"},
    )


@mcp.resource(
    "garmin://training/readiness",
    annotations={
        "readOnlyHint": True,
    },
)
async def training_readiness_resource() -> str:
    """Provide current training readiness, Body Battery, and recovery status."""
    from .auth import load_config
    from .client import GarminClientInitError, GarminClientWrapper, get_cached_garmin_client
    from .response_builder import ResponseBuilder

    config = load_config()
    try:
        client = get_cached_garmin_client(config)
    except GarminClientInitError as err:
        return ResponseBuilder.build_error_response(str(err))

    wrapper = GarminClientWrapper(client)

    # Get today's health data
    daily_stats = wrapper.safe_call("get_stats", "today")

    return ResponseBuilder.build_response(
        data={"readiness": daily_stats},
        metadata={"resource": "training_readiness", "date": "today"},
    )


@mcp.resource(
    "garmin://health/today",
    annotations={
        "readOnlyHint": True,
    },
)
async def health_today_resource() -> str:
    """Provide today's health snapshot (steps, sleep, stress, HR)."""
    from .auth import load_config
    from .client import GarminClientInitError, GarminClientWrapper, get_cached_garmin_client
    from .response_builder import ResponseBuilder

    config = load_config()
    try:
        client = get_cached_garmin_client(config)
    except GarminClientInitError as err:
        return ResponseBuilder.build_error_response(str(err))

    wrapper = GarminClientWrapper(client)

    # Get today's health data
    daily_stats = wrapper.safe_call("get_stats", "today")

    return ResponseBuilder.build_response(
        data={"health": daily_stats},
        metadata={"resource": "health_today", "date": "today"},
    )


# ============================================================================
# MCP Prompts - Pre-built query templates for common tasks
# ============================================================================


@mcp.prompt()
async def analyze_recent_training(period: str = "30d") -> str:
    """Analyze Garmin training for a given period."""
    return dedent(
        f"""
        Analyze my Garmin training over the past {period}.

        Focus on:
        1. Total volume (distance, time, elevation)
        2. Training distribution by activity type
        3. Weekly trends and patterns
        4. Performance metrics (VO2 max, training load)
        5. Key insights and recommendations

        Use the analyze_training_period tool with period="{period}" to get comprehensive analysis,
        then present the findings in a clear, actionable format.
        """
    ).strip()


@mcp.prompt()
async def sleep_quality_report(period: str = "7d") -> str:
    """Analyze sleep quality over a period."""
    return dedent(
        f"""
        Analyze my sleep quality over the past {period}.

        Include:
        1. Average sleep duration and quality scores
        2. Sleep stage breakdown (deep, light, REM)
        3. Sleep consistency and patterns
        4. HRV and resting heart rate trends
        5. Recommendations for improvement

        Use query_sleep_data with a date range to get sleep data,
        then provide actionable insights.
        """
    ).strip()


@mcp.prompt()
async def training_readiness_check() -> str:
    """Check if I'm ready to train today."""
    return dedent(
        """
        Assess my current training readiness.

        Include:
        1. Today's Body Battery and recovery status
        2. Last night's sleep quality and HRV
        3. Recent training load and fatigue
        4. Stress levels and recovery time
        5. Recommendation: train hard, train easy, or rest

        Use query_health_summary for today, query_sleep_data for last night,
        and get_performance_metrics for recent training status.
        """
    ).strip()


@mcp.prompt()
async def activity_deep_dive(activity_id: int) -> str:
    """Provide comprehensive analysis of an activity."""
    return dedent(
        f"""
        Provide a comprehensive analysis of activity {activity_id}.

        Include:
        1. Basic metrics (distance, time, pace, elevation)
        2. Heart rate zones and training effect
        3. Lap-by-lap breakdown
        4. Weather conditions
        5. Gear used
        6. Comparison to similar activities
        7. Performance insights

        Use get_activity_details with activity_id={activity_id} for enriched data,
        then use find_similar_activities to compare with past performances.
        """
    ).strip()


@mcp.prompt()
async def compare_recent_runs() -> str:
    """Compare recent runs to identify trends."""
    return dedent(
        """
        Compare my most recent runs to identify trends and improvements.

        Steps:
        1. Use query_activities to get my last 5-10 runs (activity_type="running")
        2. Extract the activity IDs from the most recent runs
        3. Use compare_activities to do side-by-side comparison
        4. Highlight improvements in pace, heart rate efficiency, or consistency
        5. Provide actionable feedback

        Focus on progress and areas for improvement.
        """
    ).strip()


@mcp.prompt()
async def health_summary(period: str = "7d") -> str:
    """Provide comprehensive health overview."""
    return dedent(
        f"""
        Provide a comprehensive health overview for the past {period}.

        Include:
        1. Daily steps and activity levels
        2. Sleep quality and consistency
        3. Stress levels and recovery
        4. Heart rate and HRV trends
        5. Body Battery patterns
        6. Overall health insights and recommendations

        Use query_activity_metrics for steps/stress, query_sleep_data for sleep,
        query_heart_rate_data for HR/HRV, and synthesize into actionable insights.
        """
    ).strip()


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> PlainTextResponse:
    """Liveness probe for hosting platforms.

    Deliberately unauthenticated and free of Garmin API calls: it reports only that
    the process is serving traffic, so it neither leaks data nor consumes the
    account's rate limit on every probe.
    """
    return PlainTextResponse("ok")


HTTP_TRANSPORTS = {"http", "sse", "streamable-http"}


def main():
    """Main entry point for the Garmin Connect MCP server.

    Transport is chosen by FASTMCP_TRANSPORT (default: stdio). When an HTTP
    transport is selected the server refuses to start without MCP_AUTH_TOKEN,
    because an open HTTP endpoint would expose the owner's Garmin account to
    anyone who can reach the URL.
    """
    transport = os.environ.get("FASTMCP_TRANSPORT", "stdio").strip().lower()

    if transport in HTTP_TRANSPORTS:
        if not os.environ.get("MCP_AUTH_TOKEN", "").strip():
            print(
                f"Refusing to start: transport '{transport}' exposes this server over "
                "HTTP but MCP_AUTH_TOKEN is not set, which would leave your Garmin "
                "account readable by anyone who can reach the URL.\n"
                "Set MCP_AUTH_TOKEN to a long random secret "
                "(generate one with: openssl rand -hex 32).",
                file=sys.stderr,
            )
            sys.exit(1)

        # Host and port are passed explicitly rather than via environment variables:
        # fastmcp.settings is populated at import time, so mutating os.environ here
        # would be too late to take effect.
        #
        # Platforms such as Render assign the listening port via PORT, and containers
        # must bind all interfaces to be reachable (FastMCP defaults to 127.0.0.1).
        port = os.environ.get("PORT") or os.environ.get("FASTMCP_PORT") or "8000"
        host = os.environ.get("FASTMCP_HOST") or "0.0.0.0"

        mcp.run(transport=transport, host=host, port=int(port))
        return

    mcp.run()


if __name__ == "__main__":
    main()
