"""
Tests for intervals_mcp_server.api.client.make_intervals_request and helpers.

This is the single function every API call flows through, so these cover the
parts that actually matter: request construction (URL/method/auth/body),
the HTTP status-code -> friendly-message mapping, and the failure branches
(missing key, request errors, invalid JSON).
"""

import asyncio
from http import HTTPStatus

import httpx
import pytest

from intervals_mcp_server.api import client as api_client
from intervals_mcp_server.config import Config


@pytest.fixture(autouse=True)
def _stub_config(monkeypatch):
    """Give the client a deterministic config with a real API key."""
    monkeypatch.setattr(
        api_client,
        "get_config",
        lambda: Config(
            api_key="secret",
            athlete_id="i1",
            intervals_api_base_url="https://intervals.icu/api/v1",
            user_agent="test-agent",
        ),
    )


class _Resp:
    def __init__(self, *, json_data=None, content=b"{}", raise_exc=None, text=""):
        self._json = json_data if json_data is not None else {}
        self.content = content
        self._raise = raise_exc
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self._raise is not None:
            raise self._raise


class _Client:
    """Records request kwargs and returns a canned response (or raises)."""

    def __init__(self, response=None, exc=None):
        self.is_closed = False
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response

    async def aclose(self):
        self.is_closed = True


def _inject(monkeypatch, client):
    """Route make_intervals_request through our fake client."""
    import intervals_mcp_server.server as server  # noqa: PLC0415

    monkeypatch.setattr(server, "httpx_client", client, raising=False)


def _run(url, **kwargs):
    return asyncio.run(api_client.make_intervals_request(url, **kwargs))


# --------------------------------------------------------------------------- #
# Request construction
# --------------------------------------------------------------------------- #
def test_get_request_builds_url_auth_and_returns_json(monkeypatch):
    client = _Client(response=_Resp(json_data={"ok": 1}, content=b'{"ok":1}'))
    _inject(monkeypatch, client)

    result = _run("/athlete/i1/activities", params={"limit": 5})

    assert result == {"ok": 1}
    call = client.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://intervals.icu/api/v1/athlete/i1/activities"
    assert call["params"] == {"limit": 5}
    assert isinstance(call["auth"], httpx.BasicAuth)  # HTTP Basic with the API key


def test_list_response_passthrough(monkeypatch):
    client = _Client(response=_Resp(json_data=[{"a": 1}], content=b"[]"))
    _inject(monkeypatch, client)
    assert _run("/x") == [{"a": 1}]


def test_post_sends_json_body_and_content_type(monkeypatch):
    client = _Client(response=_Resp(json_data={"created": True}, content=b"{}"))
    _inject(monkeypatch, client)

    _run("/athlete/i1/events", method="POST", data={"name": "Threshold"})

    call = client.calls[0]
    assert call["method"] == "POST"
    # POST body is serialized JSON, not form params
    assert call["content"] == '{"name": "Threshold"}'
    assert call["headers"]["Content-Type"] == "application/json"


def test_empty_response_body_returns_empty_dict(monkeypatch):
    client = _Client(response=_Resp(content=b""))  # no content -> {}
    _inject(monkeypatch, client)
    assert _run("/x") == {}


# --------------------------------------------------------------------------- #
# Failure branches
# --------------------------------------------------------------------------- #
def test_missing_api_key_short_circuits(monkeypatch):
    monkeypatch.setattr(
        api_client,
        "get_config",
        lambda: Config(api_key="", athlete_id="i1", intervals_api_base_url="https://x", user_agent="t"),
    )
    client = _Client(response=_Resp())
    _inject(monkeypatch, client)

    result = _run("/x")
    assert result["error"] is True
    assert "API key is required" in result["message"]
    assert client.calls == []  # no HTTP call attempted


def test_request_error_is_wrapped(monkeypatch):
    client = _Client(exc=httpx.RequestError("connection refused"))
    _inject(monkeypatch, client)
    result = _run("/x")
    assert result["error"] is True
    assert "Request error" in result["message"]


def test_http_status_error_is_mapped(monkeypatch):
    req = httpx.Request("GET", "https://intervals.icu/api/v1/x")
    resp = httpx.Response(status_code=404, request=req, text="nope")
    err = httpx.HTTPStatusError("404", request=req, response=resp)
    client = _Client(response=_Resp(raise_exc=err))
    _inject(monkeypatch, client)

    result = _run("/x")
    assert result["error"] is True
    assert result["status_code"] == 404
    assert "doesn't exist" in result["message"]  # friendly 404 message


def test_invalid_json_returns_error(monkeypatch):
    class _BadJson(_Resp):
        def json(self):
            raise ValueError("bad json")

    client = _Client(response=_BadJson(content=b"garbage"))
    _inject(monkeypatch, client)
    # JSONDecodeError is a subclass of ValueError; _parse_response catches it
    from json import JSONDecodeError

    class _BadJson2(_Resp):
        def json(self):
            raise JSONDecodeError("x", "garbage", 0)

    client2 = _Client(response=_BadJson2(content=b"garbage"))
    _inject(monkeypatch, client2)
    result = _run("/x")
    assert result["error"] is True
    assert "Invalid JSON" in result["message"]


# --------------------------------------------------------------------------- #
# Status-code -> message mapping (pure logic)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code,needle",
    [
        (HTTPStatus.UNAUTHORIZED, "check your API key"),
        (HTTPStatus.FORBIDDEN, "permission"),
        (HTTPStatus.NOT_FOUND, "doesn't exist"),
        (HTTPStatus.UNPROCESSABLE_ENTITY, "couldn't process"),
        (HTTPStatus.TOO_MANY_REQUESTS, "Too many requests"),
        (HTTPStatus.INTERNAL_SERVER_ERROR, "internal error"),
        (HTTPStatus.SERVICE_UNAVAILABLE, "maintenance"),
    ],
)
def test_get_error_message_known_codes(code, needle):
    assert needle in api_client._get_error_message(int(code), "raw")  # noqa: SLF001


def test_get_error_message_unknown_code_falls_back_to_text():
    # a valid-but-unmapped status, and an out-of-range code, both return raw text
    assert api_client._get_error_message(418, "teapot") == "teapot"  # noqa: SLF001
    assert api_client._get_error_message(999, "weird") == "weird"  # noqa: SLF001
