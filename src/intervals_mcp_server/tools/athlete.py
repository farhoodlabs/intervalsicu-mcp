"""
Athlete-profile and configuration MCP tools for Intervals.icu.

Read tools exposing the athlete's profile, per-sport training settings
(FTP / zones / thresholds), and training-load summaries — the context an AI
coach needs to reason about intensity and readiness.
"""

from typing import Any

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
