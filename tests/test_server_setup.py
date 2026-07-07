"""
Tests for intervals_mcp_server.server_setup — transport selection and startup.

Verifies MCP_TRANSPORT parsing (including the http -> streamable-http mapping and
the invalid-value error) and that start_server dispatches to mcp.run with the
correct transport arguments for each mode.
"""

from unittest.mock import MagicMock

import pytest

from intervals_mcp_server import server_setup
from intervals_mcp_server.utils.types import TransportAliases


# --------------------------------------------------------------------------- #
# setup_transport
# --------------------------------------------------------------------------- #
def test_default_is_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    assert server_setup.setup_transport() == TransportAliases.STDIO


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sse", TransportAliases.SSE),
        ("http", TransportAliases.STREAMABLE_HTTP),  # http is an alias for streamable-http
        ("streamable-http", TransportAliases.STREAMABLE_HTTP),
        ("STDIO", TransportAliases.STDIO),  # case-insensitive
    ],
)
def test_transport_mapping(monkeypatch, value, expected):
    monkeypatch.setenv("MCP_TRANSPORT", value)
    assert server_setup.setup_transport() == expected


def test_invalid_transport_raises(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "carrier-pigeon")
    with pytest.raises(ValueError, match="Unsupported MCP_TRANSPORT"):
        server_setup.setup_transport()


# --------------------------------------------------------------------------- #
# start_server
# --------------------------------------------------------------------------- #
def _mock_mcp():
    m = MagicMock()
    m.settings.host = "0.0.0.0"
    m.settings.port = 8080
    m.settings.sse_path = "/sse"
    m.settings.message_path = "/messages"
    m.settings.streamable_http_path = "/mcp"
    return m


def test_start_server_stdio():
    m = _mock_mcp()
    server_setup.start_server(m, TransportAliases.STDIO)
    m.run.assert_called_once_with()


def test_start_server_streamable_http(monkeypatch):
    m = _mock_mcp()
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(app=app, kw=kw))
    server_setup.start_server(m, TransportAliases.STREAMABLE_HTTP)
    # builds the app, adds CORS middleware, and serves it via uvicorn
    m.streamable_http_app.assert_called_once_with()
    m.streamable_http_app.return_value.add_middleware.assert_called_once()
    assert calls["app"] is m.streamable_http_app.return_value
    assert calls["kw"]["host"] == "0.0.0.0" and calls["kw"]["port"] == 8080


def test_start_server_sse_uses_mount_path(monkeypatch):
    monkeypatch.setenv("MCP_SSE_MOUNT_PATH", "/custom")
    m = _mock_mcp()
    server_setup.start_server(m, TransportAliases.SSE)
    m.run.assert_called_once_with(transport="sse", mount_path="/custom")
