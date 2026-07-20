"""
Tests for the 0.3.0 activity search + analytics tools in
intervals_mcp_server.tools.activities: search_activities,
get_activity_best_efforts, get_activity_interval_stats.

HTTP is stubbed at the module level; the autouse conftest fixture supplies the
caller credentials (athlete ``i1``).
"""

import asyncio

from intervals_mcp_server.tools import activities


def _patch_request(monkeypatch, result):
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(activities, "make_intervals_request", fake)
    return calls


# --------------------------------------------------------------------------- #
# search_activities
# --------------------------------------------------------------------------- #
SEARCH_HITS = [
    {
        "id": "a1",
        "name": "Threshold intervals",
        "start_date_local": "2026-07-18T07:00:00",
        "type": "Ride",
        "distance": 42000,
        "moving_time": 5400,
        "race": False,
    },
    {"id": "a2", "name": "Local crit", "start_date_local": "2026-07-15", "type": "Ride", "race": True},
]


def test_search_activities_success(monkeypatch):
    calls = _patch_request(monkeypatch, SEARCH_HITS)
    out = asyncio.run(activities.search_activities("threshold", limit=5))
    assert calls[0]["url"] == "/athlete/i1/activities/search"
    assert calls[0]["params"] == {"q": "threshold", "limit": 5}
    assert "Found 2 activities" in out
    assert "2026-07-18 | Ride | Threshold intervals" in out
    assert "[id: a1]" in out
    assert "RACE" in out  # the crit


def test_search_activities_empty_query(monkeypatch):
    calls = _patch_request(monkeypatch, SEARCH_HITS)
    out = asyncio.run(activities.search_activities("   "))
    assert "non-empty search query is required" in out
    assert calls == []  # no request made


def test_search_activities_no_results(monkeypatch):
    _patch_request(monkeypatch, [])
    assert "No activities found matching 'zzz'" in asyncio.run(activities.search_activities("zzz"))


def test_search_activities_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "boom"})
    assert "Error searching activities: boom" in asyncio.run(activities.search_activities("x"))


# --------------------------------------------------------------------------- #
# get_activity_best_efforts
# --------------------------------------------------------------------------- #
BEST_EFFORTS = {
    "efforts": [
        {"duration": 300, "average": 320, "start_index": 100, "end_index": 400},
        {"distance": 1000, "average": 305, "start_index": 500, "end_index": 700},
    ]
}


def test_best_efforts_success_and_param_passthrough(monkeypatch):
    calls = _patch_request(monkeypatch, BEST_EFFORTS)
    out = asyncio.run(
        activities.get_activity_best_efforts("a1", stream="watts", duration=300, count=5)
    )
    params = calls[0]["params"]
    assert calls[0]["url"] == "/activity/a1/best-efforts"
    assert params["stream"] == "watts"
    assert params["duration"] == 300
    assert params["count"] == 5
    assert "distance" not in params  # None omitted
    assert "Best Efforts (watts)" in out
    assert "5m: avg 320" in out
    assert "1000m: avg 305" in out


def test_best_efforts_empty(monkeypatch):
    _patch_request(monkeypatch, {"efforts": []})
    out = asyncio.run(activities.get_activity_best_efforts("a1"))
    assert "No best-effort data found" in out


def test_best_efforts_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "nope"})
    assert "Error fetching best efforts: nope" in asyncio.run(
        activities.get_activity_best_efforts("a1")
    )


# --------------------------------------------------------------------------- #
# get_activity_interval_stats
# --------------------------------------------------------------------------- #
INTERVAL_STATS = {
    "moving_time": 1200,
    "average_watts": 265,
    "weighted_average_watts": 272,
    "max_watts": 410,
    "intensity": 0.88,
    "training_load": 45,
    "average_heartrate": 158,
    "decoupling": 3.2,
}


def test_interval_stats_success(monkeypatch):
    calls = _patch_request(monkeypatch, INTERVAL_STATS)
    out = asyncio.run(activities.get_activity_interval_stats("a1", 100, 500))
    assert calls[0]["url"] == "/activity/a1/interval-stats"
    assert calls[0]["params"] == {"start_index": 100, "end_index": 500}
    assert "Interval Stats:" in out
    assert "Avg Power: 265 W" in out
    assert "Weighted Avg Power: 272 W" in out
    assert "Decoupling: 3.2 %" in out


def test_interval_stats_bad_indices(monkeypatch):
    calls = _patch_request(monkeypatch, INTERVAL_STATS)
    out = asyncio.run(activities.get_activity_interval_stats("a1", 500, 100))
    assert "end_index must be greater than start_index" in out
    assert calls == []  # no request


def test_interval_stats_empty(monkeypatch):
    _patch_request(monkeypatch, {})
    out = asyncio.run(activities.get_activity_interval_stats("a1", 0, 100))
    assert "No interval stats found" in out


def test_interval_stats_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "bad range"})
    assert "Error fetching interval stats: bad range" in asyncio.run(
        activities.get_activity_interval_stats("a1", 0, 100)
    )
