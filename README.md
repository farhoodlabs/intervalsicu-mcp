# Intervals.icu MCP Server

A self-hosted, multi-tenant Model Context Protocol (MCP) server that exposes the
[Intervals.icu](https://intervals.icu) API — activities, events, wellness, power curves, gear, and
custom items — as MCP tools for Claude. It runs as a remote, OAuth-authenticated connector at
`https://intervalsicu.farhoodlabs.com/mcp`, where each user's Intervals.icu API key and athlete id are
stored encrypted and looked up per request from their OAuth identity.

This is a fork of the upstream single-tenant project
([mvilanova/intervals-mcp-server](https://github.com/mvilanova/intervals-mcp-server)), reworked for
remote multi-user operation.

## How it fits together

The system is three services on one Kubernetes host (`intervalsicu.farhoodlabs.com`), deployed via Flux
GitOps and sharing one CloudNativePG Postgres database:

| Service | Path | What it does |
| --- | --- | --- |
| **intervalsicu-mcp** (this repo) | `/mcp` | The MCP server. Verifies OAuth JWTs and serves Intervals.icu data as MCP tools over streamable-HTTP. |
| **intervalsicu-mcp-ui** | `/portal` | Portal where users sign in (Google via Better Auth) and set their Intervals.icu credentials; admins approve accounts. |
| **intervalsicu-mcp-auth** | `/api/auth` | Better Auth OAuth 2.1 server: dynamic client registration (DCR), PKCE, EdDSA-signed JWTs + JWKS, Google login. |

**Connection flow:** the Claude connector self-registers at the auth server (DCR), the user logs in with
Google, and Claude receives a JWT access token whose audience is the `/mcp` URL. This server verifies
that JWT against the auth server's JWKS and resolves the caller's stored Intervals.icu credentials by the
token subject. A user who hasn't been approved or hasn't set credentials gets a friendly "account isn't
ready" message.

## Connecting Claude

Add a **custom remote connector** in Claude pointing at:

```
https://intervalsicu.farhoodlabs.com/mcp
```

Name it **without a dot** — use `intervals`, not `intervals.icu`. Claude Desktop and mobile fail to load
the tools if the connector name contains a dot. Claude handles registration and Google login for you.
Your account must be approved in the portal and have Intervals.icu credentials set.

### Available tools

`get_activities`, `get_activity_details`, `get_activity_intervals`, `get_activity_streams`,
`get_activity_messages`, `add_activity_message`, `get_events`, `get_event_by_id`, `add_or_update_event`,
`delete_event`, `delete_events_by_date_range`, `get_wellness_data`, `get_athlete_power_curves`,
`get_gear_list`, `get_custom_items`, `get_custom_item_by_id`, `create_custom_item`, `update_custom_item`,
`delete_custom_item`.

## Local development

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv sync --all-extras        # install with dev extras

uv run pytest               # tests (enforces a >=90% coverage gate)
ruff check .                # lint
mypy src tests              # type check
```

Run locally over stdio (single-user, using the env fallback credentials below):

```bash
python -m intervals_mcp_server.server
```

For local HTTP without OAuth, set `MCP_TRANSPORT=http` and leave `MCP_ISSUER` / `MCP_RESOURCE` /
`MCP_JWKS_URI` unset — auth is disabled when those aren't all present, and tools use the `API_KEY` /
`ATHLETE_ID` env fallback.

## Environment variables

**Local / single-user fallback** (used only when there is no OAuth context):

- `API_KEY` — an Intervals.icu API key (Settings → API on intervals.icu).
- `ATHLETE_ID` — your athlete id, e.g. `i12345` (from the intervals.icu URL). Must match `i?\d+`.
- `INTERVALS_API_BASE_URL` — optional, defaults to `https://intervals.icu/api/v1`.

**Multi-tenant / deployment:**

- `DATABASE_URL` — async Postgres DSN (`postgresql+asyncpg://…`) for the shared user store.
- `INTERVALS_ENC_KEY` — base64-encoded 32-byte AES-256-GCM key used to encrypt stored API keys. Shared
  with the UI service so both read/write the same ciphertext.
- `MCP_ISSUER`, `MCP_RESOURCE`, `MCP_JWKS_URI` — OAuth: token issuer, the `/mcp` resource URL, and the
  JWKS endpoint (an internal in-cluster URL, to bypass Cloudflare). Setting all three enables auth.
- `MCP_TRANSPORT` — `stdio` (default), `sse`, or `http`/`streamable-http`. Deployment uses `http`.
- `MCP_STATELESS_HTTP`, `MCP_JSON_RESPONSE` — HTTP tuning. The deployment sets both `true` (stateless +
  JSON) so the distributed connector can hit any replica; stateful/SSE breaks it.
- `FASTMCP_HOST`, `FASTMCP_PORT`, `FASTMCP_LOG_LEVEL` — HTTP bind + logging.

## Deployment

Pushes to `main` trigger Gitea CI (`.gitea/workflows/build.yaml`): it runs the test suite with the
coverage gate, then builds and pushes a container image to
`git.farh.net/farhoodlabs/intervalsicu-mcp`. Flux reconciles the new image onto the cluster. Database
migrations run as an Alembic (`alembic upgrade head`) initContainer before the server starts.

## License

GNU General Public License v3.0 (inherited from the upstream project).
