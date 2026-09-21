# Environment variable reference

Configuration is entirely environment-based. Locally, values may be placed in
`backend/.env` (copy `.env.example`). `.env` files are never committed.

## Core

| Variable | Default | Description |
| --- | --- | --- |
| `ENVIRONMENT` | `local` | One of `local`, `test`, `preview`, `production`. |
| `DEBUG` | `false` | Must be `false` in production; startup fails otherwise. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_FORMAT` | `console` | `json` in deployed environments, `console` locally. |

## Database

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | local Compose URL | Pooled async URL used at runtime. Must use the `postgresql+asyncpg://` scheme. |
| `DATABASE_URL_DIRECT` | unset | Direct (non-pooled) URL used by Alembic. Required by Neon and similar providers. |
| `DB_ECHO` | `false` | Log every SQL statement. Development only. |
| `DB_POOL_SIZE` | `5` | Pool size for long-running processes. Ignored when `SERVERLESS=true`. |
| `DB_MAX_OVERFLOW` | `5` | Extra connections above the pool size. |
| `DB_POOL_TIMEOUT_SECONDS` | `10` | Wait time for a pooled connection. |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` | TCP/auth connect timeout. |
| `SERVERLESS` | `false` | `true` on Vercel. Switches the engine to `NullPool`. |

## HTTP

| Variable | Default | Description |
| --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | Comma-separated origin allowlist. `*` is rejected in production. |
| `MAX_REQUEST_BODY_BYTES` | `2097152` (2 MiB) | Requests declaring a larger body get `413`. |

## Docker Compose only

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_USER` | `heimdall` | Local database user. |
| `POSTGRES_PASSWORD` | `heimdall` | Local development password. Never reuse it anywhere real. |
| `POSTGRES_DB` | `heimdall` | Local database name. |
| `POSTGRES_PORT` | `5433` | Host port mapped to PostgreSQL. Defaults to 5433 so it does not collide with a PostgreSQL server already installed on the host. |
| `API_PORT` | `8000` | Host port mapped to the API. |

## Authentication

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH_SECRET` | development placeholder | Signs access tokens. Must be at least 32 characters in preview and production, where the placeholder is refused. Generate with `openssl rand -hex 32`. |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | Access-token lifetime. Access tokens are not revocable, so keep this short. |
| `REFRESH_TOKEN_TTL_DAYS` | `14` | Refresh-token lifetime. Rotated on every use. |
| `REFRESH_COOKIE_NAME` | `heimdall_refresh` | Name of the HttpOnly refresh cookie. |
| `REFRESH_COOKIE_SECURE` | `false` | Must be `true` outside local development; startup fails otherwise. |
| `REFRESH_COOKIE_SAMESITE` | `lax` | `none` is required when the frontend is on a different origin than the API, and then `SECURE` must also be true. |
| `REFRESH_COOKIE_DOMAIN` | unset | Set only when the cookie must be shared across subdomains. |
| `ARGON2_TIME_COST` | `3` | Argon2id iterations. |
| `ARGON2_MEMORY_COST_KIB` | `65536` | Argon2id memory, in KiB (64 MiB). |
| `ARGON2_PARALLELISM` | `1` | Argon2id lanes. Keep at 1 on serverless runtimes. |

## Testing

| Variable | Default | Description |
| --- | --- | --- |
| `RUN_INTEGRATION_TESTS` | unset | Set to `1` to enable tests that require a live PostgreSQL database. |
| `TEST_DATABASE_URL` | local `heimdall_test` URL | Database used by integration tests. Its contents are rewritten, so never point it at real data. |

## Market data

| Variable | Default | Description |
| --- | --- | --- |
| `MARKET_DATA_PROVIDER` | `fixture` | Only the offline fixture provider exists. Every test and local run uses it. |
| `MARKET_DATA_API_KEY` | unset | Credential for a future provider that requires one. |

## Early Warning System

| Variable | Default | Description |
| --- | --- | --- |
| `CRON_SECRET` | unset | Protects `POST /api/v1/internal/monitoring/run`. **With no value set, that endpoint returns 503 rather than running unprotected.** Generate with `openssl rand -hex 32`. |
| `MONITORING_BATCH_SIZE` | `25` | Portfolios evaluated per scheduled invocation. Bounded so a run fits inside a serverless function's duration. |

## Rate limiting

| Variable | Default | Description |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | In-process fixed-window limiting. See [security.md](./security.md#rate-limiting) for the per-instance caveat under serverless execution. |

## Reserved for later phases

| Variable | Introduced in | Description |
| --- | --- | --- |
| `FRONTEND_ORIGIN` | Phase 12 | Deployed frontend origin, added to the CORS allowlist. |
| `VITE_API_BASE_URL` | Phase 8 | Frontend-only. Exposed in the browser bundle, so it must never hold a secret. |

## Rules

- Any variable prefixed with `VITE_` is shipped to the browser. Server-only
  secrets must never use that prefix.
- Production startup fails when `DEBUG=true`, when CORS is empty, or when a
  wildcard origin is configured.
- Secrets are supplied by the platform's secret store, never committed.
