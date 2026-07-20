"""
Workout-library MCP tools for Intervals.icu.

Read tools exposing the athlete's reusable workout library (distinct from the
calendar *events* handled in tools/events.py).
"""

from intervals_mcp_server import credentials
from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.credentials import CredentialError
from intervals_mcp_server.utils.formatting import format_workout_details, format_workout_summary

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401


@mcp.tool()
async def get_workouts(folder_id: int | None = None, sport_type: str | None = None) -> str:
    """List the athlete's reusable workout library.

    Filtering is applied client-side (the API returns the full library).

    Args:
        folder_id: Optional folder ID to restrict results to one folder.
        sport_type: Optional sport type to filter by (e.g. "Ride", "Run").
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    result = await make_intervals_request(url=f"/athlete/{athlete_id}/workouts", api_key=api_key)

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching workouts: {result.get('message')}"

    workouts = [w for w in result if isinstance(w, dict)] if isinstance(result, list) else []
    if folder_id is not None:
        workouts = [w for w in workouts if w.get("folder_id") == folder_id]
    if sport_type:
        want = sport_type.strip().lower()
        workouts = [w for w in workouts if str(w.get("type", "")).lower() == want]

    if not workouts:
        return "No workouts found."

    lines = [f"Workout Library ({len(workouts)}):", ""]
    lines.extend(format_workout_summary(w) for w in workouts)
    return "\n".join(lines)


@mcp.tool()
async def get_workout(workout_id: int) -> str:
    """Get a single library workout's full structure (steps and targets).

    Args:
        workout_id: The Intervals.icu workout ID.
    """
    try:
        athlete_id, api_key = await credentials.resolve_caller_credentials()
    except CredentialError as exc:
        return str(exc)

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id}/workouts/{workout_id}", api_key=api_key
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error fetching workout: {result.get('message')}"
    if not isinstance(result, dict) or not result:
        return f"No workout found with ID {workout_id}."
    return format_workout_details(result)
