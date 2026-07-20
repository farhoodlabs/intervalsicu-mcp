"""
Wellness-related MCP tools for Intervals.icu.

This module contains tools for retrieving athlete wellness data.
"""

from datetime import datetime, timedelta
from typing import Any

from intervals_mcp_server import credentials
from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.utils.formatting import format_wellness_entry
from intervals_mcp_server.utils.readiness import assess_readiness, render_readiness
from intervals_mcp_server.utils.validation import resolve_date_params, validate_date

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

# snake_case tool param -> Intervals.icu camelCase wellness field. `sleep_hours`
# is handled separately (converted to sleepSecs). Shared by the single-day and
# bulk write tools so their field mapping can never drift.
_WELLNESS_FIELD_MAP: list[tuple[str, str]] = [
    ("weight", "weight"),
    ("resting_hr", "restingHR"),
    ("hrv", "hrv"),
    ("sleep_quality", "sleepQuality"),
    ("calories_consumed", "kcalConsumed"),
    ("carbohydrates", "carbohydrates"),
    ("protein", "protein"),
    ("fat", "fatTotal"),
    ("hydration_volume", "hydrationVolume"),
    ("hydration_score", "hydration"),
    ("soreness", "soreness"),
    ("fatigue", "fatigue"),
    ("stress", "stress"),
    ("mood", "mood"),
    ("motivation", "motivation"),
    ("injury", "injury"),
    ("comments", "comments"),
    ("locked", "locked"),
]


def _wellness_payload(fields: dict[str, Any]) -> dict[str, Any]:
    """Map snake_case wellness fields to the Intervals.icu camelCase payload.

    Only non-None values are included. ``sleep_hours`` becomes ``sleepSecs`` (with
    -1 passing through unscaled as the clear sentinel).
    """
    payload: dict[str, Any] = {}
    for snake, camel in _WELLNESS_FIELD_MAP:
        value = fields.get(snake)
        if value is not None:
            payload[camel] = value
    sleep_hours = fields.get("sleep_hours")
    if sleep_hours is not None:
        payload["sleepSecs"] = -1 if sleep_hours == -1 else int(sleep_hours * 3600)
    return payload


@mcp.tool()
async def get_wellness_data(
    start_date: str | None = None,
    end_date: str | None = None,
    include_all_fields: bool = False,
) -> str:
    """Get wellness data for the signed-in athlete from Intervals.icu.

    By default returns standard wellness fields (training metrics, vitals, sleep,
    subjective scores, etc.). Set include_all_fields=True to also include any
    additional or custom fields configured by the user in Intervals.icu.

    Args:
        start_date: Start date in YYYY-MM-DD format (optional, defaults to 30 days ago)
        end_date: End date in YYYY-MM-DD format (optional, defaults to today)
        include_all_fields: If True, include additional and custom fields beyond the standard set (optional, defaults to False)
    """
    try:
        athlete_id_to_use, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    start_date, end_date = resolve_date_params(start_date, end_date)

    params = {"oldest": start_date, "newest": end_date}

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/wellness", api_key=api_key, params=params
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching wellness data: {result.get('message')}"

    if not result:
        return (
            f"No wellness data found for athlete {athlete_id_to_use} in the specified date range."
        )

    wellness_summary = "Wellness Data:\n\n"

    if isinstance(result, dict):
        for date_str, data in result.items():
            if isinstance(data, dict) and "date" not in data:
                data["date"] = date_str
            wellness_summary += format_wellness_entry(data, include_all_fields=include_all_fields) + "\n\n"
    elif isinstance(result, list):
        for entry in result:
            if isinstance(entry, dict):
                wellness_summary += format_wellness_entry(entry, include_all_fields=include_all_fields) + "\n\n"

    return wellness_summary


@mcp.tool()
async def update_wellness(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    date: str | None = None,
    weight: float | None = None,
    resting_hr: int | None = None,
    hrv: float | None = None,
    sleep_hours: float | None = None,
    sleep_quality: int | None = None,
    calories_consumed: int | None = None,
    carbohydrates: float | None = None,
    protein: float | None = None,
    fat: float | None = None,
    hydration_volume: float | None = None,
    hydration_score: int | None = None,
    soreness: int | None = None,
    fatigue: int | None = None,
    stress: int | None = None,
    mood: int | None = None,
    motivation: int | None = None,
    injury: int | None = None,
    comments: str | None = None,
    locked: bool | None = None,
) -> str:
    """Create or update the signed-in athlete's wellness record for a single day.

    Writes nutrition, hydration, vitals, sleep, and subjective ratings to
    Intervals.icu (PUT /athlete/{id}/wellness/{date}). Only the fields you pass are
    sent; anything omitted is left untouched. To CLEAR an existing numeric value,
    pass ``-1``. Set ``locked=True`` to stop Intervals.icu from overwriting these
    values on its next sync from a connected device or app.

    Args:
        date: Day to update in YYYY-MM-DD format (optional, defaults to today).
        weight: Body weight in kg.
        resting_hr: Resting heart rate in bpm.
        hrv: Heart rate variability (rMSSD).
        sleep_hours: Sleep duration in hours (stored by Intervals.icu as seconds).
            Pass -1 to clear.
        sleep_quality: Sleep quality rating, as used in the Intervals.icu app.
        calories_consumed: Energy intake in kcal.
        carbohydrates: Carbohydrate intake in grams.
        protein: Protein intake in grams.
        fat: Fat intake in grams.
        hydration_volume: Fluid intake volume, in your Intervals.icu units.
        hydration_score: Subjective hydration score, as used in the app.
        soreness: Subjective soreness rating, as used in the Intervals.icu app.
        fatigue: Subjective fatigue rating, as used in the Intervals.icu app.
        stress: Subjective stress rating, as used in the Intervals.icu app.
        mood: Subjective mood rating, as used in the Intervals.icu app.
        motivation: Subjective motivation rating, as used in the Intervals.icu app.
        injury: Injury level rating, as used in the Intervals.icu app.
        comments: Free-text note for the day.
        locked: If True, lock the record so device/app syncs won't overwrite it.
    """
    try:
        athlete_id_to_use, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        date = validate_date(date)
    except ValueError as exc:
        return f"Error: {exc}"

    payload = _wellness_payload(
        {
            "weight": weight,
            "resting_hr": resting_hr,
            "hrv": hrv,
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "calories_consumed": calories_consumed,
            "carbohydrates": carbohydrates,
            "protein": protein,
            "fat": fat,
            "hydration_volume": hydration_volume,
            "hydration_score": hydration_score,
            "soreness": soreness,
            "fatigue": fatigue,
            "stress": stress,
            "mood": mood,
            "motivation": motivation,
            "injury": injury,
            "comments": comments,
            "locked": locked,
        }
    )

    if not payload:
        return "No wellness fields provided. Pass at least one field to update."

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/wellness/{date}",
        api_key=api_key,
        method="PUT",
        data=payload,
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error updating wellness data: {result.get('message')}"

    # Intervals.icu echoes back the full updated record; render it for confirmation.
    # If the echo omits the date, inject the one we wrote to so the confirmation
    # body doesn't read "Date: N/A" under a dated header.
    if isinstance(result, dict):
        if not result.get("id") and not result.get("date"):
            result["date"] = date
        return f"Updated wellness for {date}:\n\n" + format_wellness_entry(result)
    return f"Updated wellness for {date}."


@mcp.tool()
async def update_wellness_bulk(entries: list[dict[str, Any]]) -> str:
    """Create or update multiple days of wellness data in a single call.

    Writes to PUT /athlete/{id}/wellness-bulk. Each entry is a dict with a ``date``
    (YYYY-MM-DD) plus any of the same fields as update_wellness: weight, resting_hr,
    hrv, sleep_hours, sleep_quality, calories_consumed, carbohydrates, protein, fat,
    hydration_volume, hydration_score, soreness, fatigue, stress, mood, motivation,
    injury, comments, locked. Pass -1 to clear a numeric field. Every date is
    validated up front — if any entry is invalid the whole batch is rejected, so
    there are no partial writes.

    Args:
        entries: List of per-day wellness dicts, each with a ``date`` and one or more fields.
    """
    try:
        athlete_id_to_use, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    if not entries:
        return "No entries provided. Pass at least one day to update."
    if len(entries) > 92:
        return f"Too many entries ({len(entries)}). Limit a bulk update to 92 days."

    # Recognized entry keys: the shared snake_case field names plus date/sleep_hours.
    # Anything else (e.g. API-style camelCase like "restingHR") is rejected rather
    # than silently dropped — otherwise values the caller asked to record would be
    # lost behind a success message.
    allowed_keys = {snake for snake, _ in _WELLNESS_FIELD_MAP} | {"date", "sleep_hours"}

    records: list[dict[str, Any]] = []
    summaries: list[str] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return f"Error: entry {i} is not an object."
        raw_date = entry.get("date")
        if not raw_date:
            return f"Error: entry {i} is missing a 'date'."
        try:
            date = validate_date(str(raw_date))
        except ValueError as exc:
            return f"Error in entry {i}: {exc}"

        unknown = sorted(set(entry) - allowed_keys)
        if unknown:
            return (
                f"Error: entry {i} ({date}) has unrecognized field(s): {', '.join(unknown)}. "
                f"Valid fields: {', '.join(sorted(allowed_keys - {'date'}))}."
            )

        payload = _wellness_payload(entry)
        if not payload:
            return f"Error: entry {i} ({date}) has no wellness fields to update."
        payload["id"] = date
        records.append(payload)
        summaries.append(f"{date}: {', '.join(k for k in payload if k != 'id')}")

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/wellness-bulk",
        api_key=api_key,
        method="PUT",
        data=records,
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error updating wellness data: {result.get('message')}"

    return f"Updated {len(records)} day(s):\n" + "\n".join(summaries)


@mcp.tool()
async def get_training_readiness(days: int = 45) -> str:
    """Assess training readiness from recent wellness data.

    Synthesizes the athlete's recent wellness history into a readiness read:
    HRV-guided (7-day rolling lnRMSSD vs baseline +/- smallest worthwhile change),
    resting-HR and sleep trends, and subjective inputs (soreness/fatigue/stress/
    mood/motivation). When there is too little data — notably fewer than ~2 weeks
    of HRV — the verdict is withheld rather than guessed, and the report lists which
    signals it could and could not use.

    Args:
        days: How many days of history to analyze (default 45; minimum 14 is enforced).
    """
    try:
        athlete_id_to_use, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    end = datetime.now()
    start = end - timedelta(days=max(days, 14))
    params = {"oldest": start.strftime("%Y-%m-%d"), "newest": end.strftime("%Y-%m-%d")}

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/wellness", api_key=api_key, params=params
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching wellness data: {result.get('message')}"

    records: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for date_str, data in result.items():
            if isinstance(data, dict):
                data.setdefault("id", date_str)
                records.append(data)
    elif isinstance(result, list):
        records = [r for r in result if isinstance(r, dict)]

    if not records:
        return "No wellness data found to assess readiness."

    # Anchor the calendar windows on today so weeks-old data reads as "no recent
    # data" rather than being presented as the athlete's current state.
    return render_readiness(assess_readiness(records, reference_date=end.strftime("%Y-%m-%d")))
