"""
Tests for intervals_mcp_server.tools.events.

Verifies the request payloads sent to the API (create vs update, note vs workout),
the delete-by-range accounting, and the response/error handling branches — not just
that a happy-path string comes back.
"""

import asyncio

import pytest

from intervals_mcp_server.tools import events
from intervals_mcp_server.tools.events import _handle_event_response, _prepare_event_data
from intervals_mcp_server.utils.types import Step, WorkoutDoc


class _Recorder:
    """Fake make_intervals_request that records calls and returns canned data."""

    def __init__(self, handler):
        self.calls: list[dict] = []
        self._handler = handler

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)


def _patch(monkeypatch, handler):
    rec = _Recorder(handler)
    monkeypatch.setattr(events, "make_intervals_request", rec)
    return rec


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# _prepare_event_data / _handle_event_response (pure helpers)
# --------------------------------------------------------------------------- #
def test_prepare_event_data_shapes_payload():
    doc = WorkoutDoc(description="VO2", steps=[Step(duration=600)])
    data = _prepare_event_data("Morning Ride", "", "2026-07-10", doc, 3600, 40000)
    assert data["start_date_local"] == "2026-07-10T00:00:00"
    assert data["category"] == "WORKOUT"
    assert data["type"] == "Ride"  # resolved from the name "Morning Ride"
    assert data["moving_time"] == 3600
    assert data["distance"] == 40000
    assert "VO2" in data["description"]


def test_prepare_event_data_null_description_without_doc():
    data = _prepare_event_data("Run", "Run", "2026-07-10", None, None, None)
    assert data["description"] is None


@pytest.mark.parametrize(
    "result,action,needle",
    [
        ({"error": "x", "message": "boom"}, "creating", "Error creating event: boom"),
        (None, "created", "No events created"),
        ({"id": "e42"}, "created", "Successfully created event id: e42"),
        ([{"id": 1}], "updated", "Event updated successfully"),
    ],
)
def test_handle_event_response_branches(result, action, needle):
    assert needle in _handle_event_response(result, action, "i1", "2026-07-10")


# --------------------------------------------------------------------------- #
# get_events / get_event_by_id
# --------------------------------------------------------------------------- #
def test_get_events_sends_date_params_and_formats(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: [{"start_date_local": "2026-07-10", "id": "e1", "name": "Race", "race": True}])
    out = _run(events.get_events(start_date="2026-07-01", end_date="2026-07-31"))
    call = rec.calls[0]
    assert call["url"] == "/athlete/i1/events"
    assert call["params"] == {"oldest": "2026-07-01", "newest": "2026-07-31"}
    assert "Events:" in out and "Race" in out


def test_get_events_error_surfaced(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "rate limited"})
    out = _run(events.get_events())
    assert "Error fetching events: rate limited" in out


def test_get_events_empty(monkeypatch):
    _patch(monkeypatch, lambda _k: [])
    out = _run(events.get_events())
    assert "No events found" in out


def test_get_event_by_id_invalid_format(monkeypatch):
    _patch(monkeypatch, lambda _k: [1, 2, 3])  # list, not a dict
    out = _run(events.get_event_by_id("e1"))
    assert "Invalid event format" in out


def test_get_event_by_id_error(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "nope"})
    out = _run(events.get_event_by_id("e1"))
    assert "Error fetching event details: nope" in out


# --------------------------------------------------------------------------- #
# create / update
# --------------------------------------------------------------------------- #
def test_add_event_posts_when_no_event_id(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": "e99"})
    out = _run(
        events.add_or_update_event(
            workout_type="Ride", name="Threshold",
            start_date="2026-07-10", moving_time=3600, distance=40000,
            workout_doc=WorkoutDoc(description="d", steps=[Step(duration=600)]),
        )
    )
    call = rec.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "/athlete/i1/events"
    assert call["data"]["name"] == "Threshold"
    assert "Successfully created event id: e99" in out


def test_update_event_puts_when_event_id(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": "e5"})
    _run(
        events.add_or_update_event(
            workout_type="Ride", name="Threshold",
            event_id="e5", start_date="2026-07-10",
        )
    )
    call = rec.calls[0]
    assert call["method"] == "PUT"
    assert call["url"] == "/athlete/i1/events/e5"


def test_add_event_invalid_date_returns_error(monkeypatch):
    _patch(monkeypatch, lambda _k: {"id": "e1"})
    out = _run(events.add_or_update_event(workout_type="Ride", name="X", start_date="07/10/2026"))
    assert out.startswith("Error:")


def test_add_note_uses_note_category_and_color(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": "n1"})
    _run(events.add_or_update_note(name="Sick day", description="rest", start_date="2026-07-10", color="red"))
    data = rec.calls[0]["data"]
    assert data["category"] == "NOTE"
    assert data["color"] == "red"
    assert data["description"] == "rest"


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
def test_delete_event_requires_id(monkeypatch):
    _patch(monkeypatch, lambda _k: {})
    out = _run(events.delete_event(""))
    assert "No event ID provided" in out


def test_delete_event_uses_delete_method(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"deleted": True})
    _run(events.delete_event("e7"))
    call = rec.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"] == "/athlete/i1/events/e7"


def test_delete_by_range_counts_successes_and_failures(monkeypatch):
    def handler(kwargs):
        if kwargs.get("method") == "DELETE":
            return {"error": True, "message": "no"} if kwargs["url"].endswith("/2") else {}
        return [{"id": 1}, {"id": 2}]  # the GET listing

    _patch(monkeypatch, handler)
    out = _run(events.delete_events_by_date_range("2026-07-01", "2026-07-31"))
    assert "Deleted 1 events" in out
    assert "Failed to delete 1 events: [2]" in out


def test_delete_by_range_fetch_error(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "boom"})
    out = _run(events.delete_events_by_date_range("2026-07-01", "2026-07-31"))
    assert "Error deleting events: boom" in out
