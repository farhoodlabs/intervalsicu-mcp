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


def _patch_seq(monkeypatch, results):
    """Patch make_intervals_request to return queued results, one per call."""
    calls: list[dict] = []
    seq = iter(results)

    async def fake(**kwargs):
        calls.append(kwargs)
        return next(seq)

    monkeypatch.setattr(athlete, "make_intervals_request", fake)
    return calls


class _StubCtx:
    """Minimal stand-in for FastMCP Context.elicit used by the guardrail tests."""

    def __init__(self, action="accept", confirm=True, raise_exc=False):
        self._action = action
        self._confirm = confirm
        self._raise = raise_exc
        self.elicit_calls = 0

    async def elicit(self, message, schema):  # noqa: ARG002 - signature parity
        self.elicit_calls += 1
        if self._raise:
            raise RuntimeError("client does not support elicitation")
        data = type("Data", (), {"confirm": self._confirm})()
        return type("Result", (), {"action": self._action, "data": data})()


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
    assert "Fitness (CTL): 78.5" in out
    assert "Form (TSB): 7.5" in out
    assert "By category:" in out
    assert "Ride: 8 activities" in out


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


# --------------------------------------------------------------------------- #
# update_sport_settings (dual-guardrail write)
# --------------------------------------------------------------------------- #
CURRENT_SS = [{"id": 100, "types": ["Ride"], "ftp": 280, "lthr": 165}]


def test_update_sport_settings_no_fields(monkeypatch):
    calls = _patch_seq(monkeypatch, [])
    out = asyncio.run(athlete.update_sport_settings(settings_id=100))
    assert "No settings provided" in out
    assert calls == []  # returns before any fetch


def test_update_sport_settings_refuses_without_confirm_or_ctx(monkeypatch):
    calls = _patch_seq(monkeypatch, [CURRENT_SS])  # only the GET happens
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300))
    assert "⚠️ This will change your Ride thresholds" in out
    assert "ftp: 280 -> 300" in out
    assert "re-run with confirm=true" in out
    assert len(calls) == 1 and calls[0]["url"] == "/athlete/i1/sport-settings"  # no PUT


def test_update_sport_settings_confirm_true_writes(monkeypatch):
    calls = _patch_seq(monkeypatch, [CURRENT_SS, {"id": 100, "types": ["Ride"], "ftp": 300}])
    out = asyncio.run(
        athlete.update_sport_settings(settings_id=100, ftp=300, recalc_hr_zones=True, confirm=True)
    )
    put = calls[1]
    assert put["method"] == "PUT"
    assert put["url"] == "/athlete/i1/sport-settings/100"
    assert put["params"] == {"recalcHrZones": True}
    assert put["data"]["ftp"] == 300  # merged into the full record
    assert "Updated Ride settings" in out


def test_update_sport_settings_elicit_accept_writes(monkeypatch):
    calls = _patch_seq(monkeypatch, [CURRENT_SS, {"id": 100, "types": ["Ride"], "ftp": 300}])
    ctx = _StubCtx(action="accept", confirm=True)
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, ctx=ctx))
    assert ctx.elicit_calls == 1
    assert len(calls) == 2 and calls[1]["method"] == "PUT"
    assert "Updated Ride settings" in out


def test_update_sport_settings_elicit_decline(monkeypatch):
    calls = _patch_seq(monkeypatch, [CURRENT_SS])
    ctx = _StubCtx(action="decline")
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, ctx=ctx))
    assert "did not confirm" in out
    assert "confirm=true" not in out  # no bypass instructions after a refusal
    assert len(calls) == 1  # no PUT


def test_update_sport_settings_elicit_cancel(monkeypatch):
    _patch_seq(monkeypatch, [CURRENT_SS])
    ctx = _StubCtx(action="cancel")
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, ctx=ctx))
    assert "did not confirm" in out


def test_update_sport_settings_accept_without_confirm_refuses_hard(monkeypatch):
    # Submitting the elicitation without ticking confirm is a refusal: the tool
    # must stop and must NOT emit the confirm=true bypass instructions — and an
    # explicit confirm=True param must not override the answered elicitation.
    calls = _patch_seq(monkeypatch, [CURRENT_SS])
    ctx = _StubCtx(action="accept", confirm=False)
    out = asyncio.run(
        athlete.update_sport_settings(settings_id=100, ftp=300, confirm=True, ctx=ctx)
    )
    assert "did not confirm" in out
    assert "confirm=true" not in out
    assert len(calls) == 1  # no PUT


def test_update_sport_settings_elicit_unsupported_falls_back(monkeypatch):
    calls = _patch_seq(monkeypatch, [CURRENT_SS])
    ctx = _StubCtx(raise_exc=True)  # client without elicitation capability
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, ctx=ctx))
    assert "re-run with confirm=true" in out
    assert len(calls) == 1  # refused, no PUT


def test_update_sport_settings_unknown_id(monkeypatch):
    _patch_seq(monkeypatch, [CURRENT_SS])
    out = asyncio.run(athlete.update_sport_settings(settings_id=999, ftp=300, confirm=True))
    assert "No sport settings found with ID 999" in out


def test_update_sport_settings_no_op(monkeypatch):
    _patch_seq(monkeypatch, [CURRENT_SS])
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=280, confirm=True))
    assert "No changes" in out


def test_update_sport_settings_fetch_error(monkeypatch):
    _patch_seq(monkeypatch, [{"error": True, "message": "down"}])
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, confirm=True))
    assert "Error fetching current sport settings: down" in out


def test_update_sport_settings_put_error(monkeypatch):
    _patch_seq(monkeypatch, [CURRENT_SS, {"error": True, "message": "rejected"}])
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, confirm=True))
    assert "Error updating sport settings: rejected" in out


def test_update_sport_settings_empty_echo_renders_merged(monkeypatch):
    # An empty-body 200 parses to {}; the confirmation must render the merged
    # record (with the new FTP), not format_sport_settings({}).
    calls = _patch_seq(monkeypatch, [CURRENT_SS, {}])
    out = asyncio.run(athlete.update_sport_settings(settings_id=100, ftp=300, confirm=True))
    assert len(calls) == 2
    assert "FTP: 300W" in out
    assert "Settings ID: 100" in out
