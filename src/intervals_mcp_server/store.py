"""
Async data-access for the user store.

Read/write helpers over the :class:`User` model. Credential setters encrypt the
API key before it touches the database; the read path used by the MCP server
(:func:`get_active_credentials`) only returns credentials for an *enabled* user
that actually has them, and decrypts on the way out. Plaintext API keys never
persist and are never returned to callers other than the request that will use
them against Intervals.icu.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intervals_mcp_server import crypto
from intervals_mcp_server.db.models import User
from intervals_mcp_server.db.session import get_sessionmaker


async def get_user(session: AsyncSession, sub: str) -> User | None:
    """Fetch a single user by subject."""
    return await session.get(User, sub)


async def list_users(session: AsyncSession) -> list[User]:
    """Return all users (admin listing), newest first."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def upsert_login(session: AsyncSession, sub: str, email: str, name: str | None) -> User:
    """Record a login: create the user (disabled) on first sight, else refresh profile.

    Never flips ``enabled`` — approval is an explicit admin action.
    """
    user = await session.get(User, sub)
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(sub=sub, email=email, name=name, enabled=False, last_login_at=now)
        session.add(user)
    else:
        user.email = email
        user.name = name
        user.last_login_at = now
    await session.commit()
    return user


async def set_credentials(session: AsyncSession, sub: str, athlete_id: str, api_key: str) -> bool:
    """Store (encrypted) Intervals.icu credentials for an existing user."""
    user = await session.get(User, sub)
    if user is None:
        return False
    user.athlete_id = athlete_id
    user.api_key_enc = crypto.encrypt(api_key)
    await session.commit()
    return True


async def clear_credentials(session: AsyncSession, sub: str) -> bool:
    """Remove stored credentials for a user."""
    user = await session.get(User, sub)
    if user is None:
        return False
    user.athlete_id = None
    user.api_key_enc = None
    await session.commit()
    return True


async def set_enabled(session: AsyncSession, sub: str, enabled: bool) -> bool:
    """Enable/disable a user (admin action)."""
    user = await session.get(User, sub)
    if user is None:
        return False
    user.enabled = enabled
    await session.commit()
    return True


async def delete_user(session: AsyncSession, sub: str) -> bool:
    """Delete a user and their stored credentials (admin action)."""
    user = await session.get(User, sub)
    if user is None:
        return False
    await session.delete(user)
    await session.commit()
    return True


async def get_active_credentials(sub: str) -> tuple[str, str] | None:
    """Return ``(athlete_id, api_key)`` for an enabled user with credentials, else ``None``.

    Opens and closes its own session; used by the MCP per-request resolver.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await session.get(User, sub)
        if user is None or not user.enabled or not user.has_credentials:
            return None
        assert user.athlete_id is not None and user.api_key_enc is not None
        return user.athlete_id, crypto.decrypt(user.api_key_enc)
