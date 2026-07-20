"""
Tests for the training-readiness feature.

The pure compute layer (utils/readiness.py) is exercised directly on deterministic
fixtures; one integration test drives the get_training_readiness tool with the HTTP
layer stubbed. Fixtures are built so verdicts are unambiguous.
"""

import asyncio
from datetime import date, timedelta

from intervals_mcp_server.tools import wellness
from intervals_mcp_server.utils import readiness


def _days(specs: list[dict]) -> list[dict]:
    """Build wellness records with sequential dates from a list of field dicts."""
    return [{"id": f"2026-06-{i + 1:02d}", **spec} for i, spec in enumerate(specs)]


def _days_ending_today(specs: list[dict]) -> list[dict]:
    """Like _days, but the last record is dated today (for tool-level tests)."""
    start = date.today() - timedelta(days=len(specs) - 1)
    return [
        {"id": (start + timedelta(days=i)).isoformat(), **spec} for i, spec in enumerate(specs)
    ]


def _stable(n: int, **fields) -> list[dict]:
    return _days([dict(fields) for _ in range(n)])


# --------------------------------------------------------------------------- #
# HRV signal
# --------------------------------------------------------------------------- #
def test_hrv_insufficient_data():
    recs = _stable(10, hrv=50)
    sig = readiness.hrv_signal(recs)
    assert sig["level"] == "nodata"


def test_hrv_normal_band():
    # 23 stable baseline days + 7 stable recent days -> within band
    recs = _days([{"hrv": 50 + (i % 3)} for i in range(30)])
    assert readiness.hrv_signal(recs)["level"] == "ok"


def test_hrv_suppressed_alert():
    baseline = [{"hrv": 50 + (i % 3)} for i in range(23)]
    recent = [{"hrv": 34} for _ in range(7)]
    assert readiness.hrv_signal(_days(baseline + recent))["level"] == "alert"


def test_hrv_elevated_warn():
    baseline = [{"hrv": 50 + (i % 3)} for i in range(23)]
    recent = [{"hrv": 75} for _ in range(7)]
    assert readiness.hrv_signal(_days(baseline + recent))["level"] == "warn"


def test_hrv_constant_baseline_small_dip_is_not_alert():
    # A near-constant baseline gives SWC ~ 0; the floor must keep a trivial
    # 50 -> 49 fluctuation from producing a false "Compromised" alert.
    recs = _days([{"hrv": 50} for _ in range(23)] + [{"hrv": 49} for _ in range(7)])
    assert readiness.hrv_signal(recs)["level"] == "ok"


# --------------------------------------------------------------------------- #
# RHR / sleep signals
# --------------------------------------------------------------------------- #
def test_rhr_elevated_warn():
    recs = _days([{"restingHR": 48} for _ in range(23)] + [{"restingHR": 56} for _ in range(7)])
    assert readiness.rhr_signal(recs)["level"] == "warn"


def test_rhr_normal_ok():
    assert readiness.rhr_signal(_stable(20, restingHR=48))["level"] == "ok"


def test_rhr_minimum_days_is_nodata_not_self_baseline():
    # With only 7 samples there is no disjoint baseline; a uniformly-elevated
    # (ill) week must NOT read "ok" from being compared against itself.
    sig = readiness.rhr_signal(_stable(7, restingHR=58))
    assert sig["level"] == "nodata"


def test_sleep_short_warn():
    recs = _days([{"sleepSecs": 28800} for _ in range(10)] + [{"sleepSecs": 18000}])
    assert readiness.sleep_signal(recs)["level"] == "warn"


def test_sleep_nodata():
    assert readiness.sleep_signal(_stable(3, sleepSecs=28800))["level"] == "nodata"


# --------------------------------------------------------------------------- #
# subjective signals (conventional direction)
# --------------------------------------------------------------------------- #
def test_subjective_fatigue_elevated_warns():
    recs = _days([{"fatigue": 2} for _ in range(10)] + [{"fatigue": 4}])
    sigs = readiness.subjective_signals(recs)
    assert any(s["name"] == "Fatigue" and s["level"] == "warn" for s in sigs)


def test_subjective_stable_no_warning():
    assert readiness.subjective_signals(_stable(10, fatigue=2, mood=3)) == []


# --------------------------------------------------------------------------- #
# overall verdict
# --------------------------------------------------------------------------- #
def test_verdict_green_all_stable():
    recs = _days(
        [{"hrv": 50 + (i % 3), "restingHR": 48, "sleepSecs": 28800} for i in range(30)]
    )
    assert readiness.assess_readiness(recs)["verdict"] == "green"


def test_verdict_red_on_hrv_suppression():
    recs = _days(
        [{"hrv": 50 + (i % 3), "restingHR": 48, "sleepSecs": 28800} for i in range(23)]
        + [{"hrv": 33, "restingHR": 57, "sleepSecs": 28800} for _ in range(7)]
    )
    assert readiness.assess_readiness(recs)["verdict"] == "red"


def test_verdict_insufficient_when_hrv_sparse_and_little_else():
    # Only 3 days total, no HRV baseline and <2 other core signals with data.
    recs = _stable(3, restingHR=48)
    out = readiness.assess_readiness(recs)
    assert out["verdict"] == "insufficient"


def test_verdict_uses_rhr_and_sleep_when_hrv_missing():
    # No HRV, but RHR + sleep both have data -> a verdict is still produced (green here).
    recs = _days([{"restingHR": 48, "sleepSecs": 28800} for _ in range(20)])
    out = readiness.assess_readiness(recs)
    assert out["verdict"] == "green"
    assert any(s["name"] == "HRV" and s["level"] == "nodata" for s in out["signals"])


def test_form_context_computed():
    recs = _days([{"ctl": 60, "atl": 70}])
    assert readiness.form_context(recs) == {"form": -10.0, "ctl": 60, "atl": 70}


# --------------------------------------------------------------------------- #
# render + tool integration
# --------------------------------------------------------------------------- #
def test_stale_data_withholds_verdict():
    # Daily logging that STOPPED 3 weeks ago must not produce a current verdict:
    # with today as the reference date every calendar window is empty.
    old = _days([{"hrv": 50 + (i % 3), "restingHR": 48, "sleepSecs": 28800} for i in range(30)])
    out = readiness.assess_readiness(old, reference_date=date.today().isoformat())
    assert out["verdict"] == "insufficient"
    assert all(s["level"] == "nodata" for s in out["signals"])


def test_sleep_not_logged_recently_is_nodata():
    recs = _days([{"sleepSecs": 28800} for _ in range(10)])
    sig = readiness.sleep_signal(recs, reference_date="2026-07-01")  # 3 weeks later
    assert sig["level"] == "nodata"
    assert "no sleep logged since" in sig["detail"]


def test_render_insufficient_mentions_logging():
    out = readiness.render_readiness(readiness.assess_readiness(_stable(3, restingHR=48)))
    assert "Verdict withheld" in out
    assert "Log daily HRV" in out


def test_get_training_readiness_tool(monkeypatch):
    # Wellness API returns a date-keyed dict; the tool must normalize and assess it.
    start = date.today() - timedelta(days=29)
    records = {
        (start + timedelta(days=i)).isoformat(): {
            "hrv": 50 + (i % 3),
            "restingHR": 48,
            "sleepSecs": 28800,
        }
        for i in range(30)
    }
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return records

    monkeypatch.setattr(wellness, "make_intervals_request", fake)
    out = asyncio.run(wellness.get_training_readiness(days=45))
    assert calls[0]["url"] == "/athlete/i1/wellness"
    assert "Training Readiness:" in out
    assert "🟢 Ready" in out


def test_get_training_readiness_no_data(monkeypatch):
    async def fake(**kwargs):
        return {}

    monkeypatch.setattr(wellness, "make_intervals_request", fake)
    assert "No wellness data found" in asyncio.run(wellness.get_training_readiness())


def test_get_training_readiness_error(monkeypatch):
    async def fake(**kwargs):
        return {"error": True, "message": "down"}

    monkeypatch.setattr(wellness, "make_intervals_request", fake)
    assert "Error fetching wellness data: down" in asyncio.run(wellness.get_training_readiness())
