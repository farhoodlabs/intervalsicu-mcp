"""
Wellness-related MCP tools for Intervals.icu.

This module contains tools for retrieving athlete wellness data.
"""

from datetime import datetime
from typing import Any

from intervals_mcp_server import credentials
from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.utils.formatting import format_wellness_entry
from intervals_mcp_server.utils.validation import resolve_date_params, validate_date

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401


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

    # Sleep is passed in hours but stored as seconds; -1 is the clear sentinel and
    # must pass through unscaled.
    sleep_secs: int | None = None
    if sleep_hours is not None:
        sleep_secs = -1 if sleep_hours == -1 else int(sleep_hours * 3600)

    # Map snake_case tool params to the Intervals.icu camelCase wellness fields.
    field_map: list[tuple[str, Any]] = [
        ("weight", weight),
        ("restingHR", resting_hr),
        ("hrv", hrv),
        ("sleepSecs", sleep_secs),
        ("sleepQuality", sleep_quality),
        ("kcalConsumed", calories_consumed),
        ("carbohydrates", carbohydrates),
        ("protein", protein),
        ("fatTotal", fat),
        ("hydrationVolume", hydration_volume),
        ("hydration", hydration_score),
        ("soreness", soreness),
        ("fatigue", fatigue),
        ("stress", stress),
        ("mood", mood),
        ("motivation", motivation),
        ("injury", injury),
        ("comments", comments),
        ("locked", locked),
    ]
    payload: dict[str, Any] = {k: v for k, v in field_map if v is not None}

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
