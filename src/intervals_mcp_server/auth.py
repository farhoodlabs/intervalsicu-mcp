"""
Native OAuth token verification for the Intervals.icu MCP Server.

This replaces the previous runtime monkeypatch: authentication is configured
here, in code, and enabled automatically when the OAuth environment variables
(``MCP_ISSUER`` / ``MCP_RESOURCE`` / ``MCP_JWKS_URI``) are present — i.e. for
the HTTP transport running behind an OAuth authorization server (Authentik).

When those variables are absent (e.g. stdio / local development / tests) auth
is disabled and the server runs unauthenticated.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("intervals_icu_mcp_server")


class AuthentikTokenVerifier:
    """Verify RS256 Bearer JWTs against a JWKS endpoint (RFC 9068 style)."""

    def __init__(self, jwks_uri: str, issuer: str, audience: list[str]):
        import jwt  # PyJWT

        self._jwks = jwt.PyJWKClient(jwks_uri)
        self._issuer = issuer
        self._audience = audience

    async def verify_token(self, token: str):
        """Return an AccessToken if the JWT is valid, else None (unauthenticated)."""
        import jwt
        from mcp.server.auth.provider import AccessToken

        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except Exception as exc:  # noqa: BLE001 - any failure means unauthenticated
            logger.debug("Token verification failed: %s", exc)
            return None

        aud = claims.get("aud")
        resource = aud[0] if isinstance(aud, list) else aud
        return AccessToken(
            token=token,
            client_id=claims.get("azp") or resource,
            scopes=(claims.get("scope") or "").split(),
            expires_at=claims.get("exp"),
            resource=resource,
            subject=claims.get("sub"),
            claims=claims,
        )


def _audience_variants(resource: str, client_id: str | None) -> list[str]:
    """Accepted token audiences.

    RFC 8707 clients use the ``resource`` value advertised in the protected
    resource metadata, which pydantic's ``AnyHttpUrl`` normalises *with* a
    trailing slash. The raw env var is typically supplied *without* one, so we
    accept both forms (plus the OAuth client_id) to avoid audience mismatches.
    """
    base = resource.rstrip("/")
    values = [base, base + "/"]
    if client_id:
        values.append(client_id)
    # de-duplicate while preserving order
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen.keys())


def build_auth():
    """Return ``(AuthSettings, TokenVerifier)`` when OAuth is configured, else ``(None, None)``."""
    issuer = os.getenv("MCP_ISSUER")
    resource = os.getenv("MCP_RESOURCE")
    jwks_uri = os.getenv("MCP_JWKS_URI")
    client_id = os.getenv("MCP_CLIENT_ID")

    if not (issuer and resource and jwks_uri):
        return None, None

    from mcp.server.auth.settings import AuthSettings
    from pydantic import AnyHttpUrl

    settings = AuthSettings(
        issuer_url=AnyHttpUrl(issuer),
        resource_server_url=AnyHttpUrl(resource),
    )
    verifier = AuthentikTokenVerifier(jwks_uri, issuer, _audience_variants(resource, client_id))
    logger.info("Native OAuth enabled (issuer=%s, resource=%s)", issuer, resource)
    return settings, verifier
