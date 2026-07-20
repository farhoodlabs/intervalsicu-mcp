"""
Training-readiness computation for Intervals.icu wellness data.

Pure functions (no I/O) so they can be unit-tested on fixtures. The HRV method
follows Plews & Laursen: a 7-day rolling mean of ``ln(rMSSD)`` compared to a
rolling baseline, with a "normal" band of baseline mean +/- the smallest
worthwhile change (SWC = 0.5 x baseline SD). Resting HR, sleep and subjective
inputs are each compared to their own recent baseline.

Nothing is fabricated: a metric with too little data reports "no data" rather
than defaulting, and the overall verdict is withheld (not guessed) when the
objective signals are too sparse to be meaningful. Subjective fields use the
conventional Intervals.icu direction (soreness/fatigue/stress/injury: higher is
worse; mood/motivation: higher is better) and only ever contribute a soft
warning, never a hard alert.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

_MIN_HRV_DAYS = 14  # rolling-baseline HRV method needs at least this many samples
_MIN_RHR_DAYS = 7
_MIN_SLEEP_DAYS = 5
_MIN_SUBJ_DAYS = 5
_RECENT_DAYS = 7
_BASELINE_DAYS = 30

_SUBJ_WORSE_HIGH = ("soreness", "fatigue", "stress", "injury")
_SUBJ_WORSE_LOW = ("motivation", "mood")


def _numeric_series(records: list[dict[str, Any]], key: str, positive: bool = False) -> list[float]:
    """Ordered numeric values for ``key`` (records assumed oldest->newest)."""
    out: list[float] = []
    for r in records:
        v = r.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if positive and v <= 0:
                continue
            out.append(float(v))
    return out


def _sorted_by_date(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [r for r in records if isinstance(r, dict)],
        key=lambda r: str(r.get("id") or r.get("date") or ""),
    )


def hrv_signal(records: list[dict[str, Any]]) -> dict[str, Any]:
    """HRV readiness via 7-day rolling lnRMSSD vs baseline band (mean +/- SWC)."""
    vals = _numeric_series(records, "hrv", positive=True)
    if len(vals) < _MIN_HRV_DAYS:
        return {
            "name": "HRV",
            "level": "nodata",
            "detail": f"only {len(vals)} day(s) of HRV — need >= {_MIN_HRV_DAYS} for a baseline",
        }
    ln = [math.log(v) for v in vals]
    recent = ln[-_RECENT_DAYS:]
    baseline = ln[:-_RECENT_DAYS][-_BASELINE_DAYS:]
    if len(baseline) < 2:
        return {"name": "HRV", "level": "nodata", "detail": "not enough baseline days"}
    recent_mean = statistics.mean(recent)
    base_mean = statistics.mean(baseline)
    swc = 0.5 * statistics.pstdev(baseline)
    if recent_mean < base_mean - swc:
        return {
            "name": "HRV",
            "level": "alert",
            "detail": "7-day lnHRV below baseline band — parasympathetic suppression",
        }
    if recent_mean > base_mean + swc:
        return {
            "name": "HRV",
            "level": "warn",
            "detail": "7-day lnHRV above baseline band — super-compensation, "
            "or saturation if resting HR is also elevated",
        }
    return {"name": "HRV", "level": "ok", "detail": "7-day lnHRV within normal band"}


def rhr_signal(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Resting-HR readiness: 7-day mean vs baseline, flag if >5% above."""
    vals = _numeric_series(records, "restingHR", positive=True)
    if len(vals) < _MIN_RHR_DAYS:
        return {"name": "Resting HR", "level": "nodata", "detail": f"only {len(vals)} day(s) of RHR"}
    recent = statistics.mean(vals[-_RECENT_DAYS:])
    baseline = vals[:-_RECENT_DAYS][-_BASELINE_DAYS:] or vals[:-1]
    base = statistics.mean(baseline)
    if base > 0 and (recent - base) / base > 0.05:
        return {
            "name": "Resting HR",
            "level": "warn",
            "detail": f"7-day RHR {recent:.0f} is >5% above baseline {base:.0f}",
        }
    return {
        "name": "Resting HR",
        "level": "ok",
        "detail": f"7-day RHR {recent:.0f} near baseline {base:.0f}",
    }


def sleep_signal(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Sleep readiness: last night vs baseline mean, flag if <85%."""
    vals = _numeric_series(records, "sleepSecs", positive=True)
    if len(vals) < _MIN_SLEEP_DAYS:
        return {"name": "Sleep", "level": "nodata", "detail": "not enough sleep data"}
    last = vals[-1] / 3600
    baseline = [v / 3600 for v in vals[:-1][-_BASELINE_DAYS:]]
    mean = statistics.mean(baseline)
    if mean > 0 and last < 0.85 * mean:
        return {
            "name": "Sleep",
            "level": "warn",
            "detail": f"last night {last:.1f}h below baseline {mean:.1f}h",
        }
    return {
        "name": "Sleep",
        "level": "ok",
        "detail": f"last night {last:.1f}h near baseline {mean:.1f}h",
    }


def subjective_signals(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Soft warnings when a subjective field has moved off baseline in the worse direction."""
    signals: list[dict[str, Any]] = []
    fields = [(f, True) for f in _SUBJ_WORSE_HIGH] + [(f, False) for f in _SUBJ_WORSE_LOW]
    for field, worse_high in fields:
        vals = _numeric_series(records, field)
        if len(vals) < _MIN_SUBJ_DAYS:
            continue
        latest = vals[-1]
        baseline = vals[:-1][-_BASELINE_DAYS:]
        mean = statistics.mean(baseline)
        sd = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
        threshold = max(sd, 0.5)  # require a meaningful move, not noise
        worse = (latest - mean > threshold) if worse_high else (mean - latest > threshold)
        if worse:
            direction = "elevated" if worse_high else "low"
            signals.append(
                {
                    "name": field.capitalize(),
                    "level": "warn",
                    "detail": f"{field} {direction} vs baseline ({latest:g} vs {mean:.1f})",
                }
            )
    return signals


def form_context(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest Form (TSB = CTL - ATL) if both components are present."""
    if not records:
        return None
    latest = records[-1]
    ctl, atl = latest.get("ctl"), latest.get("atl")
    if isinstance(ctl, (int, float)) and isinstance(atl, (int, float)):
        return {"form": round(ctl - atl, 1), "ctl": ctl, "atl": atl}
    return None


def assess_readiness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a structured readiness assessment from wellness records."""
    records = _sorted_by_date(records)
    core = [hrv_signal(records), rhr_signal(records), sleep_signal(records)]
    signals = core + subjective_signals(records)

    alerts = [s for s in signals if s["level"] == "alert"]
    warns = [s for s in signals if s["level"] == "warn"]
    core_with_data = [s for s in core if s["level"] != "nodata"]

    if core[0]["level"] == "nodata" and len(core_with_data) < 2:
        verdict = "insufficient"
    elif alerts or len(warns) >= 3:
        verdict = "red"
    elif warns:
        verdict = "amber"
    else:
        verdict = "green"

    return {"verdict": verdict, "signals": signals, "form": form_context(records), "days": len(records)}


_VERDICT_LABEL = {
    "green": "🟢 Ready — signals within normal range",
    "amber": "🟡 Caution — one or more signals off baseline",
    "red": "🔴 Compromised — strong or multiple negative signals",
    "insufficient": "⚪ Verdict withheld — not enough data to judge",
}
_LEVEL_ICON = {"ok": "✓", "warn": "!", "alert": "‼", "nodata": "·"}


def render_readiness(assessment: dict[str, Any]) -> str:
    """Render a readiness assessment into a plain-language report."""
    lines = [
        "Training Readiness:",
        "",
        _VERDICT_LABEL.get(assessment["verdict"], assessment["verdict"]),
        f"(based on {assessment['days']} day(s) of wellness data)",
        "",
        "Signals:",
    ]
    for s in assessment["signals"]:
        lines.append(f"  {_LEVEL_ICON.get(s['level'], '-')} {s['name']}: {s['detail']}")

    form = assessment["form"]
    if form:
        lines += ["", f"Form (TSB): {form['form']} (CTL {form['ctl']} / ATL {form['atl']})"]

    if assessment["verdict"] == "insufficient":
        lines += [
            "",
            "Log daily HRV (and resting HR) for ~2+ weeks to enable a readiness verdict.",
        ]
    return "\n".join(lines)
