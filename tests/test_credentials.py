"""
Tests for the per-request credential resolver.

Identity comes from the OAuth token; credentials from the enabled store record;
with a fallback to env config only when there is no auth context (local/stdio).
"""

import asyncio
from types import SimpleNamespace

import pytest

from intervals_mcp_server import credentials
from intervals_mcp_server.config import Config
from intervals_mcp_server.credentials import CredentialError, resolve_caller_credentials


def _token(sub):
    return SimpleNamespace(subject=sub)


def test_uses_authenticated_users_stored_creds(monkeypatch):
    monkeypatch.setattr(credentials, "get_access_token", lambda: _token("sub1"))

    async def _creds(sub):
        assert sub == "sub1"
        return ("i123", "user-key")

    monkeypatch.setattr(credentials.store, "get_active_credentials", _creds)
    assert asyncio.run(resolve_caller_credentials()) == ("i123", "user-key")


def test_authenticated_but_not_set_up_raises(monkeypatch):
    monkeypatch.setattr(credentials, "get_access_token", lambda: _token("sub1"))

    async def _none(_sub):
        return None

    monkeypatch.setattr(credentials.store, "get_active_credentials", _none)
    with pytest.raises(CredentialError, match="isn't ready yet"):
        asyncio.run(resolve_caller_credentials())


def test_no_token_falls_back_to_env_config(monkeypatch):
    monkeypatch.setattr(credentials, "get_access_token", lambda: None)
    monkeypatch.setattr(
        credentials,
        "get_config",
        lambda: Config(api_key="envkey", athlete_id="i999", intervals_api_base_url="x", user_agent="t"),
    )
    assert asyncio.run(resolve_caller_credentials()) == ("i999", "envkey")


def test_no_token_no_env_raises(monkeypatch):
    monkeypatch.setattr(credentials, "get_access_token", lambda: None)
    monkeypatch.setattr(
        credentials,
        "get_config",
        lambda: Config(api_key="", athlete_id="", intervals_api_base_url="x", user_agent="t"),
    )
    with pytest.raises(CredentialError, match="Not authenticated"):
        asyncio.run(resolve_caller_credentials())
