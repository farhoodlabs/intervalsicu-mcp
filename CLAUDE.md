# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The MCP server in a self-hosted, **multi-tenant** "Intervals.icu MCP" system running on Kubernetes
(Flux GitOps) behind a single host, `https://intervalsicu.farhoodlabs.com`. This is a fork of the
upstream single-tenant project (github.com/mvilanova/intervals-mcp-server) that has been reworked for
remote, OAuth-authenticated, per-user operation.

It exposes the Intervals.icu REST API (activities, events, wellness, power curves, gear, custom items)
as MCP tools over streamable-HTTP at `/mcp`. Python 3.12+, built on FastMCP (from `mcp[cli]`) + httpx,
with SQLAlchemy/asyncpg + Alembic for the user store and PyJWT for token verification. Managed with `uv`.

Three services share one CloudNativePG Postgres database on that host:
- **intervalsicu-mcp** (this repo) — the MCP server at `/mcp`.
- **intervalsicu-mcp-ui** — a portal at `/portal` where users sign in (Google via Better Auth) and set
  their Intervals.icu credentials, and admins approve accounts.
- **intervalsicu-mcp-auth** — a TypeScript Better Auth OAuth 2.1 server at `/api/auth` (DCR per RFC 7591,
  PKCE, EdDSA-signed JWT access tokens + JWKS, Google login). Claude's connector self-registers here.

**Runtime auth flow:** Claude connector → dynamic client registration at the auth server → Google login
→ JWT access token (audience = the `/mcp` resource URL) → this server verifies the JWT against the auth
server's JWKS and resolves the caller's stored Intervals.icu credentials by the token `subject`. If the
user has no approved-and-populated credentials, tools return a friendly "account isn't ready" message.

## Commands

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv sync --all-extras            # install incl. dev extras

uv run pytest                   # run all tests (enforces a >=90% coverage gate; see pyproject)
uv run pytest tests/test_server.py::test_name   # single test
ruff check .                    # lint
mypy src tests                  # type check
```

`ruff check .`, `mypy src tests`, and `pytest` must all pass before committing. Gitea CI
(`.gitea/workflows/build.yaml`) installs with `pip install -e ".[dev]"`, runs `pytest` (which enforces
the coverage gate), then builds and pushes the image to `git.farh.net/farhoodlabs/intervalsicu-mcp`;
Flux deploys it. If you change dependencies, run `uv lock` and commit `pyproject.toml` + `uv.lock`
together. For code-only changes leave `uv.lock` untouched.

## Architecture

**Registration is import-side-effect driven.** There is no central registry call. `mcp_instance.py`
creates the single shared `FastMCP` instance; every tool module decorates its functions with
`@mcp.tool()`, so a tool only exists once its module is imported. `server.py` imports all tool modules
at module load (the `# noqa: E402` imports near the bottom) purely to trigger those decorators. If you
add a new tool module, you must import it in `server.py` or its tools silently won't register.
`register_tools()` in `tools/__init__.py` is a no-op kept for API compatibility.

**Import layering avoids cycles.** Tool modules import `mcp` from `mcp_instance.py`, never from
`server.py`. `mcp_instance.py` imports the lifespan (`setup_api_client`) from `api/client.py` and the
auth builder from `auth.py`. Keep this direction: `server.py` → tools → `mcp_instance` → `api/client`.

**All HTTP to Intervals.icu goes through one function.** `api/client.py::make_intervals_request(url,
api_key, params, method, data)` is the only path out. It uses HTTP Basic auth (username literally
`"API_KEY"`, password = the per-user key), a shared lazily-created `httpx.AsyncClient`, 30s timeout, and
returns either parsed JSON or an error dict `{"error": True, "status_code": int, "message": str}`. Tools
must check for that error shape before formatting. The shared client is closed by the FastMCP `lifespan`
(`setup_api_client`), which also handles test monkeypatching via `server.httpx_client`.

**Tools return formatted strings, not raw JSON.** Each `@mcp.tool()` is an `async def -> str`. The
per-tool pattern: resolve the caller's `(athlete_id, api_key)` via
`credentials.resolve_caller_credentials()` (catching `CredentialError` and returning its message),
validate inputs, call `make_intervals_request`, error-check, then render human-readable text via helpers
in `utils/formatting.py`. Because the return type is `str`, FastMCP auto-generates an `outputSchema`
wrapping the result — this is expected.

### Multi-tenancy: how a caller's credentials are resolved

- `credentials.py::resolve_caller_credentials()` is what tools call. It reads the OAuth access token from
  the request context (`get_access_token()`); if there is a `subject`, it looks up that user's active
  credentials in the store. With no auth context (stdio / local dev / tests) it falls back to the
  `API_KEY` / `ATHLETE_ID` env config, so single-user local runs still work. On failure it raises
  `CredentialError`, whose message is safe to show the user ("account isn't ready", or "not authenticated").
- `store.py` — async data access over the `User` model. `get_active_credentials(sub)` returns
  `(athlete_id, api_key)` only for an **enabled** user that actually has credentials, decrypting the key
  on the way out. Also has the admin/UI write helpers (`upsert_login`, `set_credentials`, `set_enabled`,
  etc.). Plaintext API keys are never persisted.
- `crypto.py` — AES-256-GCM authenticated encryption of the stored API key. Key comes from
  `INTERVALS_ENC_KEY` (base64 32 bytes, mounted from a k8s secret, shared with the UI so both read/write
  the same ciphertext). Layout: `nonce(12) || ciphertext+tag`; reversible (the server needs the key to
  call Intervals), not a hash.
- `db/models.py` — the `users` table (`sub` PK = OAuth subject, `email`, `name`, optional `athlete_id` +
  encrypted `api_key_enc`, `enabled` gate defaulting to false, timestamps). `has_credentials` property.
- `db/session.py` — lazily-created async engine/sessionmaker from `DATABASE_URL`
  (`postgresql+asyncpg://…`). Lazy so importing never requires a database (tests/stdio don't connect);
  `configure()`/`reset()` let tests point at aiosqlite.
- Schema is managed by Alembic (`alembic/`, `alembic.ini`); the deployment runs `alembic upgrade head`
  in an initContainer (Alembic is copied into the image for this).

### Auth: JWT verification

`auth.py` holds the verifier. `build_auth()` returns `(AuthSettings, TokenVerifier)` only when
`MCP_ISSUER`, `MCP_RESOURCE`, and `MCP_JWKS_URI` are all set; otherwise `(None, None)` and the server
runs unauthenticated (stdio / dev / tests). `AuthentikTokenVerifier` validates the Bearer JWT against
the JWKS (`PyJWKClient`), accepting algorithms `EdDSA`, `RS256`, `ES256` (Better Auth signs EdDSA). It
verifies signature + issuer + `exp`/`iat` strictly, but the **audience check is soft** (logged, not
rejected) because this is a single-resource server behind a dedicated auth server with dynamic
(DCR-issued) client ids. Env:
- `MCP_ISSUER` — expected token issuer (the auth server).
- `MCP_RESOURCE` — the `/mcp` resource URL; drives path-scoped RFC 9728 protected-resource metadata and
  the accepted audiences (both trailing-slash forms, plus optional `MCP_CLIENT_ID`).
- `MCP_JWKS_URI` — JWKS endpoint. In-cluster this is an internal URL so verification bypasses Cloudflare.

### Transport

`mcp_instance.py` builds the `FastMCP` instance from env; `server_setup.py` starts it.
- `MCP_TRANSPORT` — `stdio` (default), `sse`, or `http`/`streamable-http` (deployment uses HTTP).
- `MCP_STATELESS_HTTP` / `MCP_JSON_RESPONSE` — HTTP tuning (defaults false = stateful + SSE, which is
  what a single Claude Desktop session wants). **The Kubernetes deployment sets both true (stateless +
  JSON):** the distributed Claude connector can hit any replica and can't rely on `Mcp-Session-Id`
  session affinity, so stateful/SSE breaks it.
- `FASTMCP_HOST` / `FASTMCP_PORT` — bind address for HTTP/SSE.
- `server_setup.py` adds CORS middleware to the streamable-http app so browser-based connector setup can
  reach `/mcp`: `CORSMiddleware` answers the `OPTIONS` preflight directly (200) instead of the auth layer
  rejecting it (401). Bearer-token auth with no cookies, so a wildcard origin is safe; it exposes
  `Mcp-Session-Id` and `WWW-Authenticate`.

### Config

`config.py::get_config()` reads `API_KEY`, `ATHLETE_ID`, `INTERVALS_API_BASE_URL` from env
(`.env` auto-loaded) — this is only the **local/dev fallback** identity, not the multi-tenant path.
`ATHLETE_ID` must match `r"i?\d+"` (see `utils/validation.py`), validated at server startup, not import.

### Layout
- `mcp_instance.py` — the shared `FastMCP` instance; wires transport tuning + auth from env.
- `server.py` — entry point; wires config, imports tools to register them, starts transport.
- `server_setup.py` — reads `MCP_TRANSPORT`, starts the chosen transport, adds CORS for streamable-http.
- `auth.py` — JWT/JWKS verification and `AuthSettings` construction.
- `credentials.py` / `store.py` / `crypto.py` / `db/` — the multi-tenant credential store.
- `tools/` — one module per domain: `activities`, `events`, `custom_items`, `power_curves`, `gear`, `wellness`.
- `api/client.py` — Intervals.icu HTTP client, Basic auth, error mapping, lifespan.
- `utils/` — `formatting.py`, `validation.py`, `dates.py`, `types.py` (enums incl. `TransportAliases`,
  and workout `Value`/step dataclasses used by event tools).

## Deployment / connecting

This is a **remote OAuth MCP connector**, not a local stdio server. To use it, add a custom remote
connector in Claude pointing at `https://intervalsicu.farhoodlabs.com/mcp`. **Name the connector without
a dot** (use `intervals`, not `intervals.icu`) — Claude Desktop/mobile won't load the tools if the name
contains a dot. Claude then runs DCR against the auth server and Google login; the user must have been
approved in the portal and have set their Intervals.icu credentials.

## Testing conventions

Tests never hit the real API or a real database. Async tools use `@pytest.mark.asyncio`; Intervals HTTP
is stubbed with `pytest-mock` (patch `httpx.AsyncClient` or monkeypatch `server.httpx_client`); the store
is tested against aiosqlite via `db/session.py::configure`. Shared fixtures/mock payloads live in
`tests/sample_data.py`. Cover both the success path and the `{"error": True, ...}` / `CredentialError`
paths. `pytest` enforces a 90% coverage gate.

## Note on stale docs

`.cursor/rules/*.mdc` and `AGENTS.md` predate the multi-tenant refactor (they describe the upstream
single-tenant stdio server and claim all tools live in `server.py`). Trust this file and the code.
