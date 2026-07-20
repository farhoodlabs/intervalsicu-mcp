"""
Athlete-profile and configuration MCP tools for Intervals.icu.

Read tools exposing the athlete's profile, per-sport training settings
(FTP / zones / thresholds), and training-load summaries — the context an AI
coach needs to reason about intensity and readiness.
"""

from typing import Any

from mcp.server.fastmcp import Context  # pylint: disable=import-error
from pydantic import BaseModel  # pylint: disable=import-error

from intervals_mcp_server import credentials
from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.utils.formatting import (
    format_athlete_profile,
    format_athlete_summary,
    format_sport_settings,
)
from intervals_mcp_server.utils.validation import resolve_date_params

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401


class _ConfirmThresholdChange(BaseModel):
    """Elicitation schema: the user confirms (or not) a threshold change."""

    confirm: bool = False


@mcp.tool()
async def get_athlete_profile() -> str:
    """Get the signed-in athlete's profile from Intervals.icu.

    Returns identity and physiology basics (name, sex, weight, resting HR,
    timezone, units, location). For per-sport FTP / zones / thresholds use
    get_sport_settings instead.
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    result = await make_intervals_request(url=f"/athlete/{athlete_id}", api_key=api_key)

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching athlete profile: {result.get('message')}"
    if not isinstance(result, dict):
        return "No athlete profile found."
    return format_athlete_profile(result)


@mcp.tool()
async def get_sport_settings(sport: str | None = None) -> str:
    """Get the athlete's per-sport training settings (FTP, zones, thresholds).

    These are the values that drive load, intensity and zone calculations across
    Intervals.icu. Each record's "Settings ID" is the identifier update_sport_settings
    uses to target a specific sport.

    Args:
        sport: Optional sport type to filter by (e.g. "Ride", "Run"). Matches the
            record's sport types case-insensitively. If omitted, all sports are returned.
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id}/sport-settings", api_key=api_key
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching sport settings: {result.get('message')}"

    records = [r for r in result if isinstance(r, dict)] if isinstance(result, list) else []
    if not records:
        return "No sport settings found."

    if sport:
        want = sport.strip().lower()
        records = [
            r for r in records if any(want == str(t).lower() for t in (r.get("types") or []))
        ]
        if not records:
            return f"No sport settings found for sport '{sport}'."

    return "\n\n".join(format_sport_settings(r) for r in records)


@mcp.tool()
async def get_athlete_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    tags: str | None = None,
) -> str:
    """Get a training-load summary (fitness/fatigue/form and totals) over a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format (optional, defaults to 30 days ago).
        end_date: End date in YYYY-MM-DD format (optional, defaults to today).
        tags: Optional comma-separated activity tags to filter by.
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    start_date, end_date = resolve_date_params(start_date, end_date)
    params: dict[str, Any] = {"start": start_date, "end": end_date}
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            params["tags"] = tag_list

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id}/athlete-summary", api_key=api_key, params=params
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching athlete summary: {result.get('message')}"

    if isinstance(result, list):
        summaries = [s for s in result if isinstance(s, dict)]
    elif isinstance(result, dict):
        summaries = [result]
    else:
        summaries = []

    if not summaries:
        return "No summary data found for the specified date range."

    header = f"Athlete Summary ({start_date} to {end_date}):\n\n"
    return header + "\n\n".join(format_athlete_summary(s) for s in summaries)


@mcp.tool()
async def update_sport_settings(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements
    settings_id: int,
    ftp: int | None = None,
    indoor_ftp: int | None = None,
    w_prime: int | None = None,
    lthr: int | None = None,
    max_hr: int | None = None,
    threshold_pace: float | None = None,
    recalc_hr_zones: bool = False,
    confirm: bool = False,
    ctx: Context | None = None,
) -> str:
    """⚠️ Change the athlete's training thresholds (FTP, LTHR, pace) for one sport.

    These values drive ALL future load, intensity and zone calculations across
    Intervals.icu. Do NOT call this speculatively — show the athlete the exact
    old→new values and get their explicit approval first.

    This is a confirmed write. On clients that support MCP elicitation you will be
    prompted to approve the change; otherwise you MUST pass ``confirm=True`` after the
    athlete has agreed. Without confirmation the tool refuses and returns the diff.

    Args:
        settings_id: The sport-settings record ID (from get_sport_settings).
        ftp: New FTP in watts.
        indoor_ftp: New indoor FTP in watts.
        w_prime: New W' in joules.
        lthr: New lactate-threshold HR in bpm.
        max_hr: New max HR in bpm.
        threshold_pace: New threshold pace (in the sport's pace units).
        recalc_hr_zones: If True, ask Intervals.icu to recompute HR zones from the new LTHR/max HR.
        confirm: Set True to confirm the change on clients without elicitation support.
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    proposed = {
        "ftp": ftp,
        "indoor_ftp": indoor_ftp,
        "w_prime": w_prime,
        "lthr": lthr,
        "max_hr": max_hr,
        "threshold_pace": threshold_pace,
    }
    if all(v is None for v in proposed.values()):
        return "No settings provided. Pass at least one threshold to change."

    current_list = await make_intervals_request(
        url=f"/athlete/{athlete_id}/sport-settings", api_key=api_key
    )
    if isinstance(current_list, dict) and "error" in current_list:
        return f"Error fetching current sport settings: {current_list.get('message')}"
    records = [r for r in current_list if isinstance(r, dict)] if isinstance(current_list, list) else []
    current = next((r for r in records if r.get("id") == settings_id), None)
    if current is None:
        return (
            f"No sport settings found with ID {settings_id}. "
            "Use get_sport_settings to list valid IDs."
        )

    changed: dict[str, Any] = {}
    diff_lines: list[str] = []
    for key, value in proposed.items():
        if value is not None and current.get(key) != value:
            changed[key] = value
            diff_lines.append(f"  {key}: {current.get(key)} -> {value}")
    if not changed:
        return "No changes — the provided values already match the current settings."

    sport = ", ".join(str(t) for t in (current.get("types") or [])) or f"settings {settings_id}"
    diff = "\n".join(diff_lines)

    approved = False
    if ctx is not None:
        try:
            elicited = await ctx.elicit(
                message=f"Update {sport} thresholds?\n{diff}", schema=_ConfirmThresholdChange
            )
            action = getattr(elicited, "action", None)
            if action in ("decline", "cancel"):
                return "Sport settings unchanged — you declined."
            data = getattr(elicited, "data", None)
            approved = action == "accept" and bool(getattr(data, "confirm", False))
        except Exception:  # noqa: BLE001 - client without elicitation capability falls through
            approved = False

    if not approved and not confirm:
        return (
            f"⚠️ This will change your {sport} thresholds:\n{diff}\n\n"
            "These drive ALL future load / intensity / zone calculations. "
            "If the athlete confirms, re-run with confirm=true."
        )

    updated = dict(current)
    updated.update(changed)
    result = await make_intervals_request(
        url=f"/athlete/{athlete_id}/sport-settings/{settings_id}",
        api_key=api_key,
        method="PUT",
        params={"recalcHrZones": recalc_hr_zones},
        data=updated,
    )
    if isinstance(result, dict) and "error" in result:
        return f"Error updating sport settings: {result.get('message')}"

    body = result if isinstance(result, dict) else updated
    return f"Updated {sport} settings:\n\n" + format_sport_settings(body)
