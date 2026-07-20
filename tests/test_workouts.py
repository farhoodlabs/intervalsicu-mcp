"""
Tests for intervals_mcp_server.tools.workouts (0.3.0 workout library).

Covers get_workouts (list + client-side filters) and get_workout (full detail
with a nested workout_doc), plus empty / error / credential branches.
"""

import asyncio

from intervals_mcp_server import credentials
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.tools import workouts

LIBRARY = [
    {"id": 10, "name": "VO2 5x5", "type": "Ride", "icu_training_load": 95, "moving_time": 3600, "folder_id": 1},
    {"id": 11, "name": "Easy run", "type": "Run", "moving_time": 2400, "folder_id": 2},
]

WORKOUT_DETAIL = {
    "id": 10,
    "name": "VO2 5x5",
    "type": "Ride",
    "indoor": True,
    "moving_time": 3600,
    "icu_training_load": 95,
    "description": "VO2max builder",
    "tags": ["vo2", "key"],
    "workout_doc": {
        "steps": [
            {"duration": 900, "power": {"value": 60, "units": "%ftp"}, "warmup": True},
            {
                "reps": 5,
                "steps": [
                    {"duration": 300, "power": {"value": 115, "units": "%ftp"}, "text": "hard"},
                    {"duration": 300, "power": {"value": 50, "units": "%ftp"}, "text": "easy"},
                ],
            },
            {"duration": 600, "power": {"start": 60, "end": 40, "units": "%ftp"}, "cooldown": True},
        ]
    },
}


def _patch_request(monkeypatch, result):
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(workouts, "make_intervals_request", fake)
    return calls


def test_get_workouts_all(monkeypatch):
    calls = _patch_request(monkeypatch, LIBRARY)
    out = asyncio.run(workouts.get_workouts())
    assert calls[0]["url"] == "/athlete/i1/workouts"
    assert "Workout Library (2)" in out
    assert "VO2 5x5 | Ride  (load 95, 3600s, folder 1)  [id: 10]" in out


def test_get_workouts_filter_folder(monkeypatch):
    _patch_request(monkeypatch, LIBRARY)
    out = asyncio.run(workouts.get_workouts(folder_id=2))
    assert "Easy run" in out
    assert "VO2 5x5" not in out


def test_get_workouts_filter_sport(monkeypatch):
    _patch_request(monkeypatch, LIBRARY)
    out = asyncio.run(workouts.get_workouts(sport_type="ride"))
    assert "VO2 5x5" in out
    assert "Easy run" not in out


def test_get_workouts_empty(monkeypatch):
    _patch_request(monkeypatch, [])
    assert "No workouts found" in asyncio.run(workouts.get_workouts())


def test_get_workouts_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "boom"})
    assert "Error fetching workouts: boom" in asyncio.run(workouts.get_workouts())


def test_get_workout_detail_with_nested_doc(monkeypatch):
    calls = _patch_request(monkeypatch, WORKOUT_DETAIL)
    out = asyncio.run(workouts.get_workout(10))
    assert calls[0]["url"] == "/athlete/i1/workouts/10"
    assert "Workout: VO2 5x5" in out
    assert "Training Load: 95" in out
    assert "Tags: vo2, key" in out
    assert "Steps:" in out
    assert "15m @ 60%ftp (warmup)" in out
    assert "5x:" in out                       # repeat block rendered
    assert "5m @ 115%ftp — hard" in out       # nested step
    assert "10m @ 60-40%ftp (cooldown)" in out  # power range (no ramp flag set)


def test_get_workout_ramp_step(monkeypatch):
    _patch_request(
        monkeypatch,
        {
            "id": 12,
            "name": "Ramp test",
            "workout_doc": {
                "steps": [{"ramp": True, "power": {"start": 100, "end": 300, "units": "w"}}]
            },
        },
    )
    out = asyncio.run(workouts.get_workout(12))
    assert "ramp 100-300w" in out


def test_get_workout_not_found(monkeypatch):
    _patch_request(monkeypatch, {})
    assert "No workout found with ID 99" in asyncio.run(workouts.get_workout(99))


def test_get_workout_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "nope"})
    assert "Error fetching workout: nope" in asyncio.run(workouts.get_workout(10))


def test_get_workout_credential_error(monkeypatch):
    async def _deny():
        raise CredentialError("not approved")

    monkeypatch.setattr(credentials, "resolve_caller_credentials", _deny)
    assert "not approved" in asyncio.run(workouts.get_workout(10))
