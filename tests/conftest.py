"""Shared test fixtures."""

import pytest

from intervals_mcp_server import credentials


@pytest.fixture(autouse=True)
def _default_caller_credentials(monkeypatch):
    """Run tool tests as an enabled user with fixed credentials.

    Tools resolve the caller via ``credentials.resolve_caller_credentials()``;
    patching the module attribute covers every tool at once. A test can override
    this (e.g. patch it to raise ``CredentialError``) to exercise the not-approved
    path. Tests that exercise the resolver itself import the function directly and
    are unaffected.
    """

    async def _creds():
        return ("i1", "testkey")

    monkeypatch.setattr(credentials, "resolve_caller_credentials", _creds)
