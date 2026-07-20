"""
Every tool must refuse to act (and surface a helpful message) when the caller
has no usable credentials — a disabled/unapproved user, or one who hasn't set up
their Intervals.icu key. This guards the admin-approval gate: there is no tool
parameter a caller can pass to bypass it.
"""

import asyncio

import pytest

from intervals_mcp_server import credentials
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.tools import (
    activities,
    athlete,
    custom_items,
    events,
    gear,
    power_curves,
    wellness,
    workouts,
)

# (tool callable, minimal required positional args)
TOOL_CALLS: list[tuple] = [
    (activities.get_activities, ()),
    (activities.get_activity_details, ("1",)),
    (activities.get_activity_intervals, ("1",)),
    (activities.get_activity_streams, ("1",)),
    (activities.get_activity_messages, ("1",)),
    (activities.add_activity_message, ("1", "hi")),
    (activities.search_activities, ("ride",)),
    (activities.get_activity_best_efforts, ("1",)),
    (activities.get_activity_interval_stats, ("1", 0, 100)),
    (events.get_events, ()),
    (events.get_event_by_id, ("e1",)),
    (events.delete_event, ("e1",)),
    (events.delete_events_by_date_range, ("2026-07-01", "2026-07-31")),
    (events.add_or_update_event, ("Ride", "Name")),
    (events.add_or_update_note, ("Name", "desc")),
    (wellness.get_wellness_data, ()),
    (wellness.update_wellness, ()),
    (wellness.update_wellness_bulk, ([],)),
    (wellness.get_training_readiness, ()),
    (athlete.get_athlete_profile, ()),
    (athlete.get_sport_settings, ()),
    (athlete.get_athlete_summary, ()),
    (athlete.update_sport_settings, (1,)),
    (workouts.get_workouts, ()),
    (workouts.get_workout, (1,)),
    (power_curves.get_athlete_power_curves, ()),
    (gear.get_gear_list, ()),
    (custom_items.get_custom_items, ()),
    (custom_items.get_custom_item_by_id, (1,)),
    (custom_items.create_custom_item, ("N", "TYPE")),
    (custom_items.update_custom_item, (1,)),
    (custom_items.delete_custom_item, (1,)),
]


async def _deny():
    raise CredentialError("ACCOUNT NOT APPROVED")


@pytest.mark.parametrize("func,args", TOOL_CALLS, ids=[f.__name__ for f, _ in TOOL_CALLS])
def test_tool_returns_message_when_unauthorized(monkeypatch, func, args):
    # override the autouse fixture: the caller has no usable credentials
    monkeypatch.setattr(credentials, "resolve_caller_credentials", _deny)
    result = asyncio.run(func(*args))
    assert result == "ACCOUNT NOT APPROVED"


def test_all_tools_covered():
    """Guard: every registered MCP tool must appear in TOOL_CALLS.

    Compares against the live tool registry instead of a hand-maintained count,
    so adding a tool without adding its auth-gate test fails loudly here.
    """
    from intervals_mcp_server.mcp_instance import mcp

    registered = {t.name for t in asyncio.run(mcp.list_tools())}
    covered = {f.__name__ for f, _ in TOOL_CALLS}
    assert covered == registered, (
        f"auth-gate matrix out of sync: missing={sorted(registered - covered)} "
        f"extra={sorted(covered - registered)}"
    )
