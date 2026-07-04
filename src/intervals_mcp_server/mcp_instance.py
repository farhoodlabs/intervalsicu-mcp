"""
Shared MCP instance module.

Provides a shared FastMCP instance imported by both the server module and the
tool modules (avoiding cyclic imports). Transport and authentication are
configured here from the environment — there is no runtime monkeypatching:

- HTTP transport (``MCP_TRANSPORT=http``/``streamable-http``) is served
  statelessly with plain JSON responses (robust behind proxies / MCP
  connectors, which handle a single JSON body far better than a large SSE
  stream).
- Native OAuth (Authentik) is enabled when ``MCP_ISSUER`` / ``MCP_RESOURCE`` /
  ``MCP_JWKS_URI`` are set. See :mod:`intervals_mcp_server.auth`.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error

from intervals_mcp_server.api.client import setup_api_client
from intervals_mcp_server.auth import build_auth

_kwargs: dict[str, Any] = {"lifespan": setup_api_client}

# HTTP transport tuning: stateless + single JSON response body.
if os.getenv("MCP_TRANSPORT", "stdio").lower() in ("http", "streamable-http"):
    _kwargs["stateless_http"] = True
    _kwargs["json_response"] = True
    if os.getenv("FASTMCP_HOST"):
        _kwargs["host"] = os.environ["FASTMCP_HOST"]
    if os.getenv("FASTMCP_PORT"):
        _kwargs["port"] = int(os.environ["FASTMCP_PORT"])

# Native OAuth (Authentik) when configured via environment.
_auth_settings, _token_verifier = build_auth()
if _auth_settings is not None and _token_verifier is not None:
    _kwargs["auth"] = _auth_settings
    _kwargs["token_verifier"] = _token_verifier

mcp: FastMCP = FastMCP("intervals-icu", **_kwargs)  # pylint: disable=invalid-name
