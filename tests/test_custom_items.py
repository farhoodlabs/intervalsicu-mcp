"""
Tests for intervals_mcp_server.tools.custom_items.

Focuses on the write-path logic: which fields end up in the POST/PUT payload,
JSON-string content parsing (and the invalid-JSON guard), method/URL selection,
and the error/empty branches.
"""

import asyncio

import pytest

from intervals_mcp_server.tools import custom_items


class _Recorder:
    def __init__(self, handler):
        self.calls: list[dict] = []
        self._handler = handler

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(kwargs)


def _patch(monkeypatch, handler):
    rec = _Recorder(handler)
    monkeypatch.setattr(custom_items, "make_intervals_request", rec)
    return rec


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# read
# --------------------------------------------------------------------------- #
def test_get_custom_items_lists(monkeypatch):
    _patch(monkeypatch, lambda _k: [{"id": 1, "name": "Zones", "type": "ZONES", "description": "d"}])
    out = _run(custom_items.get_custom_items())
    assert "Custom Items:" in out
    assert "ID: 1" in out and "Name: Zones" in out and "Type: ZONES" in out


def test_get_custom_items_error(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "boom"})
    assert "Error fetching custom items: boom" in _run(custom_items.get_custom_items())


def test_get_custom_item_by_id_not_found(monkeypatch):
    _patch(monkeypatch, lambda _k: [])  # falsy / not a dict
    assert "No custom item found with ID 7" in _run(custom_items.get_custom_item_by_id(7))


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def test_create_builds_full_payload(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": 9, "name": "Chart", "type": "FITNESS_CHART"})
    out = _run(
        custom_items.create_custom_item(
            name="Chart", item_type="FITNESS_CHART", 
            description="desc", content={"a": 1}, visibility="PRIVATE",
        )
    )
    call = rec.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "/athlete/i1/custom-item"
    assert call["data"] == {
        "name": "Chart", "type": "FITNESS_CHART", "description": "desc",
        "content": {"a": 1}, "visibility": "PRIVATE",
    }
    assert "Successfully created custom item" in out


def test_create_parses_json_string_content(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": 1, "name": "X", "type": "ZONES"})
    _run(
        custom_items.create_custom_item(
            name="X", item_type="ZONES", content='{"expression": "icu_training_load"}'
        )
    )
    assert rec.calls[0]["data"]["content"] == {"expression": "icu_training_load"}  # parsed to dict


def test_create_rejects_invalid_json_string(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": 1})
    out = _run(
        custom_items.create_custom_item(name="X", item_type="ZONES", content="{not json")
    )
    assert "content must be valid JSON" in out
    assert rec.calls == []  # bailed before any request


def test_create_error_surfaced(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "bad type"})
    out = _run(custom_items.create_custom_item(name="X", item_type="NOPE"))
    assert "Error creating custom item: bad type" in out


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
def test_update_sends_only_provided_fields_via_put(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": 5, "name": "New", "type": "ZONES"})
    _run(custom_items.update_custom_item(item_id=5, name="New"))
    call = rec.calls[0]
    assert call["method"] == "PUT"
    assert call["url"] == "/athlete/i1/custom-item/5"
    assert call["data"] == {"name": "New"}  # only the field that was set


def test_update_invalid_json_string(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {"id": 5})
    out = _run(custom_items.update_custom_item(item_id=5, content="{bad"))
    assert "content must be valid JSON" in out
    assert rec.calls == []


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
def test_delete_uses_delete_method(monkeypatch):
    rec = _patch(monkeypatch, lambda _k: {})
    out = _run(custom_items.delete_custom_item(item_id=3))
    call = rec.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"] == "/athlete/i1/custom-item/3"
    assert "Successfully deleted custom item 3" in out


def test_delete_error(monkeypatch):
    _patch(monkeypatch, lambda _k: {"error": True, "message": "locked"})
    assert "Error deleting custom item: locked" in _run(custom_items.delete_custom_item(item_id=3))
