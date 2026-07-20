"""
Training-readiness computation for Intervals.icu wellness data.

Pure functions (no I/O) so they can be unit-tested on fixtures. The HRV method
follows Plews & Laursen: a rolling mean of ``ln(rMSSD)`` over the last 7 calendar
days compared to a baseline from the preceding ~30 days, with a "normal" band of
baseline mean +/- the smallest worthwhile change (SWC = 0.5 x baseline SD, with a
floor so a near-constant baseline can't produce a zero-width band). Resting HR,
sleep and subjective inputs are each compared to their own recent baseline.

All windows are **calendar-based**, anchored on ``reference_date`` (callers should
pass today): a metric whose samples are older than the window reports "no recent
data" instead of silently treating stale samples as current. Nothing is
fabricated: a metric with too little data in its window reports "no data" rather
than defaulting, and the overall verdict is withheld (not guessed) when the
objective signals are too sparse to be meaningful. Subjective fields use the
conventional Intervals.icu direction (soreness/fatigue/stress/injury: higher is
worse; mood/motivation: higher is better) and only ever contribute a soft
warning, never a hard alert.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any

_RECENT_DAYS = 7
_BASELINE_DAYS = 30
_MIN_HRV_RECENT = 4  # samples needed inside the 7-day window
_MIN_HRV_BASELINE = 7
_MIN_RHR_RECENT = 4
_MIN_RHR_BASELINE = 5
_MIN_SLEEP_BASELINE = 5
_MIN_SUBJ_BASELINE = 5
_SUBJ_LATEST_MAX_AGE = 3  # days; older subjective entries aren't "current" feelings

# Floor for the HRV smallest-worthwhile-change band, in ln(rMSSD) units. A
# near-constant baseline (coarsely-rounded device output, very steady athlete)
# would otherwise give SWC ~= 0 and flag trivial fluctuations as alerts. 0.05 ln
# units is ~5% in rMSSD — on the order of normal day-to-day variation.
_SWC_FLOOR = 0.05

_SUBJ_WORSE_HIGH = ("soreness", "fatigue", "stress", "injury")
_SUBJ_WORSE_LOW = ("motivation", "mood")


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _dated_series(
    records: list[dict[str, Any]], key: str, positive: bool = False
) -> list[tuple[date, float]]:
    """Date-sorted ``(date, value)`` pairs for ``key``; undated/non-numeric skipped."""
    out: list[tuple[date, float]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        d = _parse_date(r.get("id") or r.get("date"))
        v = r.get(key)
        if d is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if positive and v <= 0:
            continue
        out.append((d, float(v)))
    out.sort(key=lambda p: p[0])
    return out


def _windows(
    pairs: list[tuple[date, float]], ref: date
) -> tuple[list[float], list[float]]:
    """Split values into recent (last 7 calendar days) and baseline (30 before that)."""
    recent_start = ref - timedelta(days=_RECENT_DAYS)
    baseline_start = recent_start - timedelta(days=_BASELINE_DAYS)
    recent = [v for d, v in pairs if recent_start < d <= ref]
    baseline = [v for d, v in pairs if baseline_start < d <= recent_start]
    return recent, baseline


def _newest_date(records: list[dict[str, Any]]) -> date | None:
    dates = [
        d
        for d in (_parse_date(r.get("id") or r.get("date")) for r in records if isinstance(r, dict))
        if d is not None
    ]
    return max(dates) if dates else None


def _resolve_ref(records: list[dict[str, Any]], reference_date: str | None) -> date | None:
    return _parse_date(reference_date) if reference_date else _newest_date(records)


def hrv_signal(records: list[dict[str, Any]], reference_date: str | None = None) -> dict[str, Any]:
    """HRV readiness via 7-day rolling lnRMSSD vs baseline band (mean +/- SWC)."""
    pairs = _dated_series(records, "hrv", positive=True)
    ref = _resolve_ref(records, reference_date)
    if ref is None or not pairs:
        return {"name": "HRV", "level": "nodata", "detail": "no HRV data"}
    recent_vals, baseline_vals = _windows(pairs, ref)
    if len(recent_vals) < _MIN_HRV_RECENT:
        return {
            "name": "HRV",
            "level": "nodata",
            "detail": f"only {len(recent_vals)} HRV sample(s) in the last {_RECENT_DAYS} days",
        }
    if len(baseline_vals) < _MIN_HRV_BASELINE:
        return {
            "name": "HRV",
            "level": "nodata",
            "detail": f"only {len(baseline_vals)} baseline day(s) — need >= {_MIN_HRV_BASELINE}",
        }
    recent_mean = statistics.mean(math.log(v) for v in recent_vals)
    ln_base = [math.log(v) for v in baseline_vals]
    base_mean = statistics.mean(ln_base)
    swc = max(0.5 * statistics.pstdev(ln_base), _SWC_FLOOR)
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


def rhr_signal(records: list[dict[str, Any]], reference_date: str | None = None) -> dict[str, Any]:
    """Resting-HR readiness: 7-day mean vs a disjoint 30-day baseline, flag if >5% above."""
    pairs = _dated_series(records, "restingHR", positive=True)
    ref = _resolve_ref(records, reference_date)
    if ref is None or not pairs:
        return {"name": "Resting HR", "level": "nodata", "detail": "no resting-HR data"}
    recent_vals, baseline_vals = _windows(pairs, ref)
    if len(recent_vals) < _MIN_RHR_RECENT:
        return {
            "name": "Resting HR",
            "level": "nodata",
            "detail": f"only {len(recent_vals)} RHR sample(s) in the last {_RECENT_DAYS} days",
        }
    if len(baseline_vals) < _MIN_RHR_BASELINE:
        return {
            "name": "Resting HR",
            "level": "nodata",
            "detail": f"only {len(baseline_vals)} baseline day(s) of RHR — need >= {_MIN_RHR_BASELINE}",
        }
    recent = statistics.mean(recent_vals)
    base = statistics.mean(baseline_vals)
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


def sleep_signal(records: list[dict[str, Any]], reference_date: str | None = None) -> dict[str, Any]:
    """Sleep readiness: last night (dated within a day of reference) vs baseline mean."""
    pairs = _dated_series(records, "sleepSecs", positive=True)
    ref = _resolve_ref(records, reference_date)
    if ref is None or not pairs:
        return {"name": "Sleep", "level": "nodata", "detail": "no sleep data"}
    last_date, last_secs = pairs[-1]
    if (ref - last_date).days > 1:
        return {
            "name": "Sleep",
            "level": "nodata",
            "detail": f"no sleep logged since {last_date.isoformat()}",
        }
    baseline = [
        v / 3600
        for d, v in pairs
        if d != last_date and ref - timedelta(days=_BASELINE_DAYS) < d <= ref
    ]
    if len(baseline) < _MIN_SLEEP_BASELINE:
        return {"name": "Sleep", "level": "nodata", "detail": "not enough sleep data"}
    last = last_secs / 3600
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


def subjective_signals(
    records: list[dict[str, Any]], reference_date: str | None = None
) -> list[dict[str, Any]]:
    """Soft warnings when a *current* subjective field has moved off baseline for the worse."""
    signals: list[dict[str, Any]] = []
    ref = _resolve_ref(records, reference_date)
    if ref is None:
        return signals
    fields = [(f, True) for f in _SUBJ_WORSE_HIGH] + [(f, False) for f in _SUBJ_WORSE_LOW]
    for field, worse_high in fields:
        pairs = _dated_series(records, field)
        if not pairs:
            continue
        latest_date, latest = pairs[-1]
        if (ref - latest_date).days > _SUBJ_LATEST_MAX_AGE:
            continue  # stale entries aren't current feelings
        baseline = [
            v
            for d, v in pairs
            if d != latest_date and ref - timedelta(days=_BASELINE_DAYS) < d <= ref
        ]
        if len(baseline) < _MIN_SUBJ_BASELINE:
            continue
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
    dated = sorted(
        [r for r in records if isinstance(r, dict)],
        key=lambda r: str(r.get("id") or r.get("date") or ""),
    )
    if not dated:
        return None
    latest = dated[-1]
    ctl, atl = latest.get("ctl"), latest.get("atl")
    if isinstance(ctl, (int, float)) and isinstance(atl, (int, float)):
        return {"form": round(ctl - atl, 1), "ctl": ctl, "atl": atl}
    return None


def assess_readiness(
    records: list[dict[str, Any]], reference_date: str | None = None
) -> dict[str, Any]:
    """Produce a structured readiness assessment from wellness records.

    ``reference_date`` (YYYY-MM-DD) anchors the calendar windows — pass today so
    stale data reads as "no recent data" instead of masquerading as current. If
    omitted, the newest record's date is used (fixture-friendly, but blind to
    how old that record is).
    """
    core = [
        hrv_signal(records, reference_date),
        rhr_signal(records, reference_date),
        sleep_signal(records, reference_date),
    ]
    signals = core + subjective_signals(records, reference_date)

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

    return {
        "verdict": verdict,
        "signals": signals,
        "form": form_context(records),
        "days": len(records),
    }


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
