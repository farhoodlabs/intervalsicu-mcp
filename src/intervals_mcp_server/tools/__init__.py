"""
MCP tools registry for Intervals.icu MCP Server.

This module registers all available MCP tools with the FastMCP server instance.
"""

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error

# Import all tools for re-export
# Note: Tools register themselves via @mcp.tool() decorators when imported
from intervals_mcp_server.tools.activities import (  # noqa: F401
    get_activities,
    get_activity_best_efforts,
    get_activity_details,
    get_activity_interval_stats,
    get_activity_intervals,
    get_activity_streams,
    search_activities,
)
from intervals_mcp_server.tools.events import (  # noqa: F401
    add_or_update_event,
    delete_event,
    delete_events_by_date_range,
    get_event_by_id,
    get_events,
)
from intervals_mcp_server.tools.custom_items import (  # noqa: F401
    create_custom_item,
    delete_custom_item,
    get_custom_item_by_id,
    get_custom_items,
    update_custom_item,
)
from intervals_mcp_server.tools.power_curves import (  # noqa: F401
    get_athlete_power_curves,
)
from intervals_mcp_server.tools.gear import get_gear_list  # noqa: F401
from intervals_mcp_server.tools.wellness import (  # noqa: F401
    get_training_readiness,
    get_wellness_data,
    update_wellness,
    update_wellness_bulk,
)
from intervals_mcp_server.tools.athlete import (  # noqa: F401
    get_athlete_profile,
    get_athlete_summary,
    get_sport_settings,
    update_sport_settings,
)
from intervals_mcp_server.tools.workouts import get_workout, get_workouts  # noqa: F401


def register_tools(mcp_instance: FastMCP) -> None:
    """
    Register all MCP tools with the FastMCP server instance.

    This function imports all tool modules, which causes their @mcp.tool()
    decorators to register the tools. The tools need access to the mcp instance,
    so they will be imported after the mcp instance is created.

    Args:
        mcp_instance (FastMCP): The FastMCP server instance to register tools with.
    """
    # Tools are registered via decorators when modules are imported above
    # The mcp_instance parameter is kept for future use if needed
    _ = mcp_instance


__all__ = [
    "register_tools",
    "get_activities",
    "get_activity_details",
    "get_activity_intervals",
    "get_activity_streams",
    "search_activities",
    "get_activity_best_efforts",
    "get_activity_interval_stats",
    "get_events",
    "get_event_by_id",
    "delete_event",
    "delete_events_by_date_range",
    "add_or_update_event",
    "get_custom_items",
    "get_custom_item_by_id",
    "create_custom_item",
    "update_custom_item",
    "delete_custom_item",
    "get_athlete_power_curves",
    "get_gear_list",
    "get_wellness_data",
    "update_wellness",
    "update_wellness_bulk",
    "get_training_readiness",
    "get_athlete_profile",
    "get_sport_settings",
    "get_athlete_summary",
    "update_sport_settings",
    "get_workouts",
    "get_workout",
]
