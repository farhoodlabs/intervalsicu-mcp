"""
Tests for intervals_mcp_server.tools.wellness.

Covers the wellness write tool (``update_wellness``): field mapping to the
Intervals.icu camelCase schema, the sleep hours->seconds conversion and the
``-1`` clear sentinel, request shape (PUT + path), the empty-payload guard, and
the error / credential branches. The default caller credentials come from the
autouse fixture in conftest (athlete ``i1``).
"""

import asyncio

from intervals_mcp_server import credentials
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.tools import wellness


def _patch_request(monkeypatch, result):
    """Patch make_intervals_request; capture the call kwargs, return ``result``."""
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(wellness, "make_intervals_request", fake)
    return calls


def test_update_wellness_maps_fields_and_puts(monkeypatch):
    calls = _patch_request(monkeypatch, {"id": "2025-05-24", "weight": 78})
    out = asyncio.run(
        wellness.update_wellness(
            date="2025-05-24",
            weight=78,
            resting_hr=50,
            hrv=65.5,
            sleep_hours=8,
            calories_consumed=2200,
            carbohydrates=300,
            protein=140,
            fat=70,
            hydration_volume=2.5,
            comments="felt good",
        )
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "PUT"
    assert call["url"] == "/athlete/i1/wellness/2025-05-24"
    assert call["api_key"] == "testkey"

    payload = call["data"]
    assert payload["weight"] == 78
    assert payload["restingHR"] == 50
    assert payload["hrv"] == 65.5
    assert payload["sleepSecs"] == 8 * 3600  # hours -> seconds
    assert payload["kcalConsumed"] == 2200
    assert payload["carbohydrates"] == 300
    assert payload["protein"] == 140
    assert payload["fatTotal"] == 70
    assert payload["hydrationVolume"] == 2.5
    assert payload["comments"] == "felt good"
    # Omitted fields must not be sent.
    assert "mood" not in payload
    assert "locked" not in payload

    assert "Updated wellness for 2025-05-24" in out


def test_update_wellness_defaults_date_to_today(monkeypatch):
    calls = _patch_request(monkeypatch, {"id": "today"})
    asyncio.run(wellness.update_wellness(weight=80))
    # URL date segment defaults to today's date (YYYY-MM-DD, 10 chars).
    date_seg = calls[0]["url"].rsplit("/", 1)[1]
    assert len(date_seg) == 10 and date_seg.count("-") == 2


def test_update_wellness_no_fields_returns_message(monkeypatch):
    calls = _patch_request(monkeypatch, {})
    out = asyncio.run(wellness.update_wellness(date="2025-05-24"))
    assert "No wellness fields provided" in out
    assert calls == []  # no request made


def test_update_wellness_clear_with_negative_one(monkeypatch):
    calls = _patch_request(monkeypatch, {"id": "2025-05-24"})
    asyncio.run(wellness.update_wellness(date="2025-05-24", weight=-1, sleep_hours=-1))
    payload = calls[0]["data"]
    assert payload["weight"] == -1
    # -1 is the clear sentinel and must NOT be scaled to -3600.
    assert payload["sleepSecs"] == -1


def test_update_wellness_locked_false_is_sent(monkeypatch):
    calls = _patch_request(monkeypatch, {"id": "2025-05-24"})
    asyncio.run(wellness.update_wellness(date="2025-05-24", locked=False))
    assert calls[0]["data"]["locked"] is False


def test_update_wellness_error_path(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "boom"})
    out = asyncio.run(wellness.update_wellness(date="2025-05-24", weight=80))
    assert "Error updating wellness data: boom" in out


def test_update_wellness_invalid_date(monkeypatch):
    calls = _patch_request(monkeypatch, {})
    out = asyncio.run(wellness.update_wellness(date="not-a-date", weight=80))
    assert out.startswith("Error:")
    assert calls == []


def test_update_wellness_credential_error(monkeypatch):
    async def _deny():
        raise CredentialError("not approved")

    monkeypatch.setattr(credentials, "resolve_caller_credentials", _deny)
    out = asyncio.run(wellness.update_wellness(date="2025-05-24", weight=80))
    assert "not approved" in out


def test_update_wellness_non_dict_result(monkeypatch):
    # If the API returns a list (unexpected), we still confirm the write.
    _patch_request(monkeypatch, [])
    out = asyncio.run(wellness.update_wellness(date="2025-05-24", weight=80))
    assert out == "Updated wellness for 2025-05-24."


def test_update_wellness_echo_without_date_shows_written_date(monkeypatch):
    # If the API echo omits id/date, the confirmation body must not read "Date: N/A".
    _patch_request(monkeypatch, {"weight": 80})
    out = asyncio.run(wellness.update_wellness(date="2025-05-24", weight=80))
    assert "Date: 2025-05-24" in out
    assert "Date: N/A" not in out


# --------------------------------------------------------------------------- #
# update_wellness_bulk
# --------------------------------------------------------------------------- #
def test_update_wellness_bulk_success(monkeypatch):
    calls = _patch_request(monkeypatch, [{"id": "2026-07-18"}, {"id": "2026-07-19"}])
    out = asyncio.run(
        wellness.update_wellness_bulk(
            [
                {"date": "2026-07-18", "weight": 80, "carbohydrates": 300},
                {"date": "2026-07-19", "sleep_hours": 8},
            ]
        )
    )
    call = calls[0]
    assert call["method"] == "PUT"
    assert call["url"] == "/athlete/i1/wellness-bulk"
    body = call["data"]
    assert isinstance(body, list) and len(body) == 2
    assert body[0]["id"] == "2026-07-18"
    assert body[0]["weight"] == 80
    assert body[0]["carbohydrates"] == 300  # camelCase mapping shared with update_wellness
    assert body[1]["sleepSecs"] == 8 * 3600
    assert "Updated 2 day(s)" in out


def test_update_wellness_bulk_mapping_matches_single(monkeypatch):
    # The bulk payload for a day must equal the single-day payload for the same fields
    # (plus the id) — proving the shared _wellness_payload helper prevents drift.
    fields = {"weight": 78, "resting_hr": 50, "sleep_hours": 7.5, "fat": 60, "locked": True}
    from intervals_mcp_server.tools.wellness import _wellness_payload

    single = _wellness_payload(fields)
    calls = _patch_request(monkeypatch, [{}])
    asyncio.run(wellness.update_wellness_bulk([{"date": "2026-07-18", **fields}]))
    bulk_entry = {k: v for k, v in calls[0]["data"][0].items() if k != "id"}
    assert bulk_entry == single


def test_update_wellness_bulk_invalid_date_rejects_whole_batch(monkeypatch):
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(
        wellness.update_wellness_bulk(
            [{"date": "2026-07-18", "weight": 80}, {"date": "not-a-date", "weight": 81}]
        )
    )
    assert "Error in entry 1" in out
    assert calls == []  # no partial write


def test_update_wellness_bulk_missing_date(monkeypatch):
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(wellness.update_wellness_bulk([{"weight": 80}]))
    assert "entry 0 is missing a 'date'" in out
    assert calls == []


def test_update_wellness_bulk_entry_no_fields(monkeypatch):
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(wellness.update_wellness_bulk([{"date": "2026-07-18"}]))
    assert "has no wellness fields" in out
    assert calls == []


def test_update_wellness_bulk_empty(monkeypatch):
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(wellness.update_wellness_bulk([]))
    assert "No entries provided" in out
    assert calls == []


def test_update_wellness_bulk_too_many(monkeypatch):
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(
        wellness.update_wellness_bulk([{"date": "2026-01-01", "weight": 80}] * 93)
    )
    assert "Too many entries" in out
    assert calls == []


def test_update_wellness_bulk_rejects_unknown_keys(monkeypatch):
    # camelCase/API-style names must be rejected, not silently dropped: the value
    # the caller asked to record would otherwise be lost behind a success message.
    calls = _patch_request(monkeypatch, [{}])
    out = asyncio.run(
        wellness.update_wellness_bulk(
            [{"date": "2026-07-18", "weight": 80, "restingHR": 50}]
        )
    )
    assert "unrecognized field(s): restingHR" in out
    assert "resting_hr" in out  # the error names the valid fields
    assert calls == []  # whole batch rejected, nothing written


def test_update_wellness_bulk_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "boom"})
    out = asyncio.run(wellness.update_wellness_bulk([{"date": "2026-07-18", "weight": 80}]))
    assert "Error updating wellness data: boom" in out
