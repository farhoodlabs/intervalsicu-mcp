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
from intervals_mcp_server.tools import activities, custom_items, events, gear, power_curves, wellness

# (tool callable, minimal required positional args)
TOOL_CALLS = [
    (activities.get_activities, ()),
    (activities.get_activity_details, ("1",)),
    (activities.get_activity_intervals, ("1",)),
    (activities.get_activity_streams, ("1",)),
    (activities.get_activity_messages, ("1",)),
    (activities.add_activity_message, ("1", "hi")),
    (events.get_events, ()),
    (events.get_event_by_id, ("e1",)),
    (events.delete_event, ("e1",)),
    (events.delete_events_by_date_range, ("2026-07-01", "2026-07-31")),
    (events.add_or_update_event, ("Ride", "Name")),
    (events.add_or_update_note, ("Name", "desc")),
    (wellness.get_wellness_data, ()),
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


def test_all_20_tools_covered():
    """Guard: if a tool is added, add it here so its auth gate is tested."""
    assert len(TOOL_CALLS) == 20
