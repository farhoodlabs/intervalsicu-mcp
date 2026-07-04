"""
Tests for intervals_mcp_server.tools.activities.

Covers the result-parsing helpers, the named-activity filtering + fetch-more
top-up logic, request params, and the per-tool error/empty/format branches.
Gear resolution is stubbed so these isolate the activity logic.
"""

import asyncio

import pytest

from intervals_mcp_server.tools import activities
from intervals_mcp_server.tools.activities import (
    _filter_named_activities,
    _format_activities_response,
    _parse_activities_from_result,
)


async def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _stub_gear(monkeypatch):
    monkeypatch.setattr(activities, "resolve_gear_for_activities", _noop)
    monkeypatch.setattr(activities, "resolve_gear_for_activity", _noop)


def _patch_request(monkeypatch, handler):
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return handler(len(calls), kwargs)

    monkeypatch.setattr(activities, "make_intervals_request", fake)
    return calls


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_parse_from_list_keeps_only_dicts():
    assert _parse_activities_from_result([{"a": 1}, "junk", {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_parse_from_container_dict():
    result = {"activities": [{"name": "Ride"}], "meta": 1}
    assert _parse_activities_from_result(result) == [{"name": "Ride"}]


def test_parse_single_activity_dict():
    single = {"name": "Ride", "distance": 1000}
    assert _parse_activities_from_result(single) == [single]


def test_parse_unrecognized_dict_returns_empty():
    assert _parse_activities_from_result({"foo": "bar"}) == []


def test_filter_named_drops_unnamed_and_blank():
    acts = [{"name": "Ride"}, {"name": "Unnamed"}, {"name": ""}, {"id": 1}]
    assert _filter_named_activities(acts) == [{"name": "Ride"}]


def test_format_response_empty_named_hint():
    out = _format_activities_response([], "i1", include_unnamed=False)
    assert "include_unnamed=True" in out


# --------------------------------------------------------------------------- #
# get_activities
# --------------------------------------------------------------------------- #
def test_get_activities_error(monkeypatch):
    _patch_request(monkeypatch, lambda _n, _k: {"error": True, "message": "rate limited"})
    out = asyncio.run(activities.get_activities(athlete_id="i1"))
    assert "Error fetching activities: rate limited" in out


def test_get_activities_requests_triple_limit_and_filters(monkeypatch):
    def handler(n, _k):
        if n == 1:
            return [{"name": "Ride A", "id": 1, "distance": 1000}]
        return [{"name": "Ride B", "id": 2, "distance": 2000}, {"name": "Unnamed", "id": 3}]

    calls = _patch_request(monkeypatch, handler)
    out = asyncio.run(
        activities.get_activities(athlete_id="i1", start_date="2026-06-01", end_date="2026-06-30", limit=5)
    )
    assert calls[0]["params"]["limit"] == 15  # limit * 3 when filtering unnamed
    assert len(calls) == 2  # topped up because named < limit
    assert "Ride A" in out and "Ride B" in out
    assert "Unnamed" not in out


def test_get_activities_include_unnamed_no_topup(monkeypatch):
    calls = _patch_request(monkeypatch, lambda _n, _k: [{"name": "Unnamed", "id": 1, "distance": 5}])
    out = asyncio.run(activities.get_activities(athlete_id="i1", include_unnamed=True, limit=10))
    assert calls[0]["params"]["limit"] == 10  # no *3
    assert len(calls) == 1  # no fetch-more
    assert "Activities:" in out


# --------------------------------------------------------------------------- #
# get_activity_details
# --------------------------------------------------------------------------- #
def test_activity_details_renders_zones(monkeypatch):
    _patch_request(
        monkeypatch,
        lambda _n, _k: {
            "name": "Ride",
            "id": 1,
            "distance": 1000,
            "zones": {
                "power": [{"number": 1, "secondsInZone": 100}],
                "hr": [{"number": 2, "secondsInZone": 200}],
            },
        },
    )
    out = asyncio.run(activities.get_activity_details("1"))
    assert "Power Zones:" in out and "Zone 1: 100 seconds" in out
    assert "Heart Rate Zones:" in out and "Zone 2: 200 seconds" in out


def test_activity_details_error(monkeypatch):
    _patch_request(monkeypatch, lambda _n, _k: {"error": True, "message": "nope"})
    assert "Error fetching activity details: nope" in asyncio.run(activities.get_activity_details("1"))


# --------------------------------------------------------------------------- #
# get_activity_intervals
# --------------------------------------------------------------------------- #
def test_activity_intervals_unrecognized_format(monkeypatch):
    _patch_request(monkeypatch, lambda _n, _k: {"something": "else"})
    out = asyncio.run(activities.get_activity_intervals("1"))
    assert "unrecognized format" in out


# --------------------------------------------------------------------------- #
# get_activity_streams
# --------------------------------------------------------------------------- #
def test_streams_default_types_and_small_preview(monkeypatch):
    calls = _patch_request(
        monkeypatch,
        lambda _n, _k: [{"type": "watts", "name": "Power", "data": [1, 2, 3], "valueType": "int"}],
    )
    out = asyncio.run(activities.get_activity_streams("1"))
    assert "time,watts,heartrate" in calls[0]["params"]["types"]  # default stream types
    assert "Data Points: 3" in out
    assert "Values: [1, 2, 3]" in out


def test_streams_large_preview_first_last_five(monkeypatch):
    _patch_request(
        monkeypatch,
        lambda _n, _k: [{"type": "watts", "data": list(range(20)), "valueType": "int"}],
    )
    out = asyncio.run(activities.get_activity_streams("1", stream_types="watts"))
    assert "First 5 values: [0, 1, 2, 3, 4]" in out
    assert "Last 5 values: [15, 16, 17, 18, 19]" in out


def test_streams_empty(monkeypatch):
    _patch_request(monkeypatch, lambda _n, _k: [])
    assert "No stream data found" in asyncio.run(activities.get_activity_streams("1"))


# --------------------------------------------------------------------------- #
# messages
# --------------------------------------------------------------------------- #
def test_get_activity_messages_empty(monkeypatch):
    _patch_request(monkeypatch, lambda _n, _k: [])
    assert "No messages found" in asyncio.run(activities.get_activity_messages("1"))


def test_add_activity_message_posts_content(monkeypatch):
    calls = _patch_request(monkeypatch, lambda _n, _k: {"id": 55})
    out = asyncio.run(activities.add_activity_message("1", "great ride"))
    call = calls[0]
    assert call["method"] == "POST"
    assert call["data"] == {"content": "great ride"}
    assert "Successfully added message (ID: 55)" in out
