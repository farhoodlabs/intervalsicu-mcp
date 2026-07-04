"""
Per-request credential resolution for multi-tenant operation.

A tool calls :func:`resolve_caller_credentials` to get the ``(athlete_id, api_key)``
for whoever made the request. Identity comes from the OAuth access token
(``get_access_token().subject``); the credentials come from that user's enabled
store record. If there is no auth context (stdio / local development) it falls back
to the ``API_KEY`` / ``ATHLETE_ID`` environment configuration, so single-user local
runs keep working.
"""

from __future__ import annotations

from mcp.server.auth.middleware.auth_context import get_access_token

from intervals_mcp_server import store
from intervals_mcp_server.config import get_config

_SETUP_HINT = (
    "Your Intervals.icu account isn't ready yet. Sign in to the Intervals.icu MCP "
    "portal, wait for an admin to approve your account, then add your athlete ID and "
    "API key there."
)


class CredentialError(Exception):
    """Raised when the caller has no usable Intervals.icu credentials.

    The message is safe to surface to the user.
    """


async def resolve_caller_credentials() -> tuple[str, str]:
    """Return ``(athlete_id, api_key)`` for the current caller or raise CredentialError."""
    try:
        token = get_access_token()
    except Exception:  # noqa: BLE001 - no auth context (stdio/local dev)
        token = None
    if token is not None and token.subject:
        creds = await store.get_active_credentials(token.subject)
        if creds is None:
            raise CredentialError(_SETUP_HINT)
        return creds

    # No authenticated context (stdio / local dev): use env config if present.
    config = get_config()
    if config.api_key and config.athlete_id:
        return config.athlete_id, config.api_key

    raise CredentialError("Not authenticated and no local credentials are configured.")
