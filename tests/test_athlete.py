"""
Tests for intervals_mcp_server.tools.athlete.

Covers the athlete-context read tools (get_athlete_profile, get_sport_settings,
get_athlete_summary): request shape, sport filtering, formatting of realistic
fixtures, and the empty / error / credential branches. Default caller credentials
come from the autouse fixture in conftest (athlete ``i1``).
"""

import asyncio

from intervals_mcp_server import credentials
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.tools import athlete

PROFILE = {
    "id": "i1",
    "name": "Test Athlete",
    "sex": "M",
    "weight": 72.5,
    "icu_resting_hr": 48,
    "timezone": "Europe/Madrid",
    "measurement_preference": "meters",
    "city": "Girona",
    "country": "Spain",
    "icu_coach": True,
    "icu_type_settings": [{"id": 1}, {"id": 2}],
}

SPORT_SETTINGS = [
    {
        "id": 100,
        "types": ["Ride", "VirtualRide"],
        "ftp": 280,
        "indoor_ftp": 275,
        "w_prime": 22000,
        "power_zones": [55, 75, 90, 105, 120],
        "power_zone_names": ["Z1", "Z2", "Z3", "Z4", "Z5"],
        "lthr": 165,
        "max_hr": 190,
        "hr_zones": [120, 145, 160, 175],
        "threshold_pace": 4.2,
        "pace_units": "MINS_KM",
        "pace_zones": [3.5, 4.0, 4.5],
        "warmup_time": 600,
        "cooldown_time": 300,
    },
    {"id": 101, "types": ["Run"], "threshold_pace": 3.8, "pace_units": "MINS_KM"},
]

SUMMARY = [
    {
        "date": "2026-07-20",
        "count": 12,
        "moving_time": 43200,
        "distance": 320000,
        "training_load": 640,
        "fitness": 78.5,
        "fatigue": 71.0,
        "form": 7.5,
        "eftp": 285,
        "byCategory": [{"category": "Ride", "count": 8, "training_load": 500, "moving_time": 32400}],
    }
]


def _patch_request(monkeypatch, result):
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(athlete, "make_intervals_request", fake)
    return calls


# --------------------------------------------------------------------------- #
# get_athlete_profile
# --------------------------------------------------------------------------- #
def test_get_athlete_profile_success(monkeypatch):
    calls = _patch_request(monkeypatch, PROFILE)
    out = asyncio.run(athlete.get_athlete_profile())
    assert calls[0]["url"] == "/athlete/i1"
    assert "Name: Test Athlete" in out
    assert "Weight: 72.5 kg" in out
    assert "Resting HR: 48 bpm" in out
    assert "Location: Girona, Spain" in out
    assert "Role: Coach" in out
    assert "2 sport(s) configured" in out


def test_get_athlete_profile_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "nope"})
    assert "Error fetching athlete profile: nope" in asyncio.run(athlete.get_athlete_profile())


def test_get_athlete_profile_non_dict(monkeypatch):
    _patch_request(monkeypatch, [])
    assert "No athlete profile found" in asyncio.run(athlete.get_athlete_profile())


def test_get_athlete_profile_credential_error(monkeypatch):
    async def _deny():
        raise CredentialError("not approved")

    monkeypatch.setattr(credentials, "resolve_caller_credentials", _deny)
    assert "not approved" in asyncio.run(athlete.get_athlete_profile())


# --------------------------------------------------------------------------- #
# get_sport_settings
# --------------------------------------------------------------------------- #
def test_get_sport_settings_all(monkeypatch):
    calls = _patch_request(monkeypatch, SPORT_SETTINGS)
    out = asyncio.run(athlete.get_sport_settings())
    assert calls[0]["url"] == "/athlete/i1/sport-settings"
    assert "Sport Settings — Ride, VirtualRide" in out
    assert "Settings ID: 100" in out
    assert "FTP: 280W" in out
    assert "Z1: 55, Z2: 75" in out  # power zones paired with names
    assert "LTHR: 165 bpm" in out
    assert "Threshold: 4.2 MINS_KM" in out
    assert "Settings ID: 101" in out  # second record rendered too


def test_get_sport_settings_filter_hit(monkeypatch):
    _patch_request(monkeypatch, SPORT_SETTINGS)
    out = asyncio.run(athlete.get_sport_settings(sport="run"))  # case-insensitive
    assert "Settings ID: 101" in out
    assert "Settings ID: 100" not in out


def test_get_sport_settings_filter_miss(monkeypatch):
    _patch_request(monkeypatch, SPORT_SETTINGS)
    out = asyncio.run(athlete.get_sport_settings(sport="Swim"))
    assert "No sport settings found for sport 'Swim'" in out


def test_get_sport_settings_empty(monkeypatch):
    _patch_request(monkeypatch, [])
    assert "No sport settings found" in asyncio.run(athlete.get_sport_settings())


def test_get_sport_settings_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "boom"})
    assert "Error fetching sport settings: boom" in asyncio.run(athlete.get_sport_settings())


# --------------------------------------------------------------------------- #
# get_athlete_summary
# --------------------------------------------------------------------------- #
def test_get_athlete_summary_success(monkeypatch):
    calls = _patch_request(monkeypatch, SUMMARY)
    out = asyncio.run(athlete.get_athlete_summary(start_date="2026-06-20", end_date="2026-07-20"))
    call = calls[0]
    assert call["url"] == "/athlete/i1/athlete-summary"
    assert call["params"]["start"] == "2026-06-20"
    assert call["params"]["end"] == "2026-07-20"
    assert "tags" not in call["params"]
    assert "Fitness (CTL): 78.5" in out
    assert "Form (TSB): 7.5" in out
    assert "By category:" in out
    assert "Ride: 8 activities" in out


def test_get_athlete_summary_tags_split(monkeypatch):
    calls = _patch_request(monkeypatch, SUMMARY)
    asyncio.run(athlete.get_athlete_summary(tags="race, key-workout"))
    assert calls[0]["params"]["tags"] == ["race", "key-workout"]


def test_get_athlete_summary_defaults_dates(monkeypatch):
    calls = _patch_request(monkeypatch, SUMMARY)
    asyncio.run(athlete.get_athlete_summary())
    # resolve_date_params fills both ends with YYYY-MM-DD
    assert len(calls[0]["params"]["start"]) == 10
    assert len(calls[0]["params"]["end"]) == 10


def test_get_athlete_summary_empty(monkeypatch):
    _patch_request(monkeypatch, [])
    assert "No summary data found" in asyncio.run(athlete.get_athlete_summary())


def test_get_athlete_summary_error(monkeypatch):
    _patch_request(monkeypatch, {"error": True, "message": "bad"})
    assert "Error fetching athlete summary: bad" in asyncio.run(athlete.get_athlete_summary())
