"""
Tests for intervals_mcp_server.store against an in-memory SQLite database.

Verifies the real behaviors that matter: new users are created disabled,
credentials are stored encrypted (never plaintext), and get_active_credentials
only returns decrypted creds for an enabled user that actually has them.
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from intervals_mcp_server import crypto, store
from intervals_mcp_server.db.models import Base

KEY = crypto.generate_key_b64()


def _run_db(monkeypatch, body):
    """Run `body(sessionmaker)` against a fresh in-memory DB, all in one event loop."""

    async def go():
        monkeypatch.setenv("INTERVALS_ENC_KEY", KEY)
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(store, "get_sessionmaker", lambda: maker)
        try:
            await body(maker)
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_first_login_creates_disabled_user(monkeypatch):
    async def body(maker):
        async with maker() as s:
            user = await store.upsert_login(s, "sub1", "a@b.com", "Alice")
            assert user.enabled is False
            assert user.has_credentials is False
            assert user.last_login_at is not None

    _run_db(monkeypatch, body)


def test_repeat_login_refreshes_profile_but_not_enabled(monkeypatch):
    async def body(maker):
        async with maker() as s:
            await store.upsert_login(s, "sub1", "a@b.com", "Alice")
            await store.set_enabled(s, "sub1", True)
            # a later login must not touch the approval flag
            user = await store.upsert_login(s, "sub1", "new@b.com", "Al")
            assert user.email == "new@b.com"
            assert user.enabled is True  # unchanged by login
            assert len(await store.list_users(s)) == 1

    _run_db(monkeypatch, body)


def test_set_credentials_stores_encrypted(monkeypatch):
    async def body(maker):
        async with maker() as s:
            await store.upsert_login(s, "sub1", "a@b.com", None)
            assert await store.set_credentials(s, "sub1", "i123", "SECRET-KEY") is True
            user = await store.get_user(s, "sub1")
            assert user.athlete_id == "i123"
            assert user.api_key_enc is not None
            assert b"SECRET-KEY" not in user.api_key_enc  # not plaintext
            assert crypto.decrypt(user.api_key_enc) == "SECRET-KEY"

    _run_db(monkeypatch, body)


def test_set_credentials_unknown_user(monkeypatch):
    async def body(maker):
        async with maker() as s:
            assert await store.set_credentials(s, "ghost", "i1", "k") is False

    _run_db(monkeypatch, body)


def test_active_credentials_gated_on_enabled_and_present(monkeypatch):
    async def body(maker):
        async with maker() as s:
            await store.upsert_login(s, "sub1", "a@b.com", None)
            await store.set_credentials(s, "sub1", "i123", "KEY")
        # has creds but not enabled -> None
        assert await store.get_active_credentials("sub1") is None
        async with maker() as s:
            await store.set_enabled(s, "sub1", True)
        # enabled + creds -> decrypted tuple
        assert await store.get_active_credentials("sub1") == ("i123", "KEY")

    _run_db(monkeypatch, body)


def test_active_credentials_enabled_without_creds(monkeypatch):
    async def body(maker):
        async with maker() as s:
            await store.upsert_login(s, "sub1", "a@b.com", None)
            await store.set_enabled(s, "sub1", True)
        assert await store.get_active_credentials("sub1") is None

    _run_db(monkeypatch, body)


def test_clear_and_delete(monkeypatch):
    async def body(maker):
        async with maker() as s:
            await store.upsert_login(s, "sub1", "a@b.com", None)
            await store.set_credentials(s, "sub1", "i1", "k")
            assert await store.clear_credentials(s, "sub1") is True
            user = await store.get_user(s, "sub1")
            assert user.athlete_id is None and user.api_key_enc is None
            assert await store.delete_user(s, "sub1") is True
            assert await store.get_user(s, "sub1") is None
            assert await store.delete_user(s, "ghost") is False

    _run_db(monkeypatch, body)
