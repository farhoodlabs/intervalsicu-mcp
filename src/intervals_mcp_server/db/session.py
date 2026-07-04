"""
Async engine / session management.

The connection string comes from ``DATABASE_URL`` (e.g.
``postgresql+asyncpg://user:pass@host/db``). The engine and sessionmaker are
created lazily so importing this module never requires a database — tests and
stdio/local runs that don't touch the store won't connect.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker | None = None


def configure(url: str, **engine_kwargs) -> None:
    """Explicitly configure the engine (used by tests to point at aiosqlite)."""
    global _engine, _sessionmaker  # noqa: PLW0603 - module-level singletons
    _engine = create_async_engine(url, **engine_kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def get_sessionmaker() -> async_sessionmaker:
    """Return the process-wide async sessionmaker, creating it from DATABASE_URL if needed."""
    global _engine, _sessionmaker  # noqa: PLW0603
    if _sessionmaker is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        configure(url, pool_pre_ping=True)
    assert _sessionmaker is not None
    return _sessionmaker


def reset() -> None:
    """Drop the cached engine/sessionmaker (test isolation)."""
    global _engine, _sessionmaker  # noqa: PLW0603
    _engine = None
    _sessionmaker = None
