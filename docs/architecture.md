# Architecture

Heimdall is a **modular monolith**: one deployable backend divided by business
capability, plus a separate single-page frontend. There are no microservices.

## Repository layout

```text
Heimdall/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI application factory
│   │   ├── config.py        environment-based settings
│   │   ├── database.py      engine, session dependency, declarative base
│   │   ├── common/          logging, middleware, errors, clock, rate limiting
│   │   ├── auth/            users, sessions, password hashing
│   │   ├── assets/          instrument reference data
│   │   ├── portfolios/      portfolios, positions, CSV import
│   │   ├── market_data/     provider interface, ingestion, trading calendar
│   │   ├── analytics/       pure calculations, snapshots, analysis runs
│   │   ├── stress_testing/  scenario catalogue and shock engine
│   │   ├── early_warning/   rule engine and signal lifecycle
│   │   ├── reports/         PDF generation and storage
│   │   └── health/          liveness and readiness endpoints
│   ├── migrations/          Alembic
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                reserved; implemented from Phase 8
├── docs/
├── fixtures/                deterministic offline data
├── scripts/
├── compose.yaml             local development and integration testing
└── .github/workflows/
```

Every business capability is its own package under `app/`: `auth`, `assets`,
`portfolios`, `market_data`, `analytics`, `stress_testing`, `early_warning`, and
`reports`. Each holds `models.py`, `schemas.py`, `repository.py`, `service.py`,
`router.py`, and `dependencies.py`.

### Where the financial logic lives

The calculation layer is deliberately separate from everything that does I/O:

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `analytics/calculations.py` | Every financial formula, as pure functions | NumPy, SciPy only |
| `analytics/snapshot.py` | Values a portfolio into plain data | Repositories |
| `analytics/service.py` | Runs an analysis, persists metrics | Snapshot plus calculations |
| `stress_testing/engine.py` | Shock precedence and impact attribution, pure | Decimal only |
| `early_warning/evaluators.py` | Nine rule evaluators, pure given a context | Calculations |
| `early_warning/service.py` | Monitoring runs and the signal lifecycle | Repositories plus evaluators |
| `reports/renderer.py` | PDF layout, pure | ReportLab only |

A rule evaluator receives a prepared `RuleContext` — snapshot, price history, the
evaluation instant, and an injected scenario runner — so it performs no queries and
can be tested by constructing a context.

### Cross-cutting middleware

Outermost first, as a request travels inward:

1. `CORSMiddleware` — origin allowlist, no wildcard in production.
2. `RequestContextMiddleware` — request id, structured access log, slow-request
   warning, `X-Response-Time-Ms`.
3. `SecurityHeadersMiddleware` — CSP, framing refusal, cache control, HSTS when
   deployed.
4. `RateLimitMiddleware` — fixed-window limits on authentication and
   provider-backed endpoints.
5. `BodySizeLimitMiddleware` — rejects oversized bodies with `413`.

## Layering

```text
HTTP route  ──►  service  ──►  repository  ──►  database
                    │
                    └──────►  pure calculation functions
```

| Layer | Responsibility | Must not |
| --- | --- | --- |
| Route | validate input, authorize, call a service, return a typed schema | contain business logic or raw SQL |
| Service | orchestrate a use case, enforce invariants, own the transaction | know about HTTP |
| Repository | persistence and queries | contain financial logic |
| Calculation | pure functions over numeric inputs | touch HTTP, the database, or the clock |
| Provider adapter | translate an external API into domain objects | leak vendor response shapes outward |

Rules enforced from Phase 0 onward:

- ORM entities are never returned from a route. Responses are Pydantic schemas.
- Financial calculations take plain data in and return plain data out, so they
  can be tested without a database.
- External market-data vendors sit behind an internal provider interface.
- The API is versioned under `/api/v1`. Health probes stay unversioned.

## Request lifecycle

1. `RequestContextMiddleware` assigns a request ID (reusing a safe inbound
   `X-Request-ID`), binds it to the structlog context, and logs the outcome.
2. `BodySizeLimitMiddleware` rejects oversized bodies with `413`.
3. `CORSMiddleware` applies the configured origin allowlist.
4. The route runs. Any `AppError` becomes a structured error response.
5. Unhandled exceptions are logged with a stack trace and returned to the client
   as an opaque `500`. Internal details never reach the client.

## Error contract

Every failure uses one envelope:

```json
{
  "error": {
    "code": "portfolio_not_found",
    "message": "Portfolio not found.",
    "details": [{ "field": "name", "message": "...", "code": "..." }],
    "request_id": "6f1c..."
  }
}
```

`code` is stable and machine-readable. `details` is present for field-level
validation failures. `request_id` matches the `X-Request-ID` response header.

## Transactions

`get_db_session` gives each request one session and one transaction. It commits
when the handler returns normally and rolls back when it raises. Services
therefore only `flush()`, which surfaces constraint violations at the point they
occur while keeping the whole request atomic: a failed request cannot leave a
partial write behind.

`Base` sets `eager_defaults=True`, so server-generated values such as
`created_at` and `updated_at` come back with the INSERT or UPDATE. Without it,
reading one of those attributes after a write would attempt a lazy refresh, which
async SQLAlchemy cannot perform.

## Ownership authorization

Ownership is a **query predicate**, never a check performed after loading:

```python
select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
```

A resource owned by another user and a resource that does not exist return the
same `404` with the same message, so the API cannot be used to enumerate other
users' data.

## Health and readiness

| Endpoint | Meaning | Dependencies checked |
| --- | --- | --- |
| `GET /health` | the process is alive | none, by design |
| `GET /ready` | this instance can serve traffic | PostgreSQL (`SELECT 1`) |

`/ready` returns `503` with `status: "not_ready"` when the database is
unreachable, so a load balancer or platform probe can route around a broken
instance.

## Database access

`app/database.py` chooses a pool strategy from configuration:

- **Long-running processes** (local, Docker, CI): small `QueuePool` with
  `pool_pre_ping` and a 30-minute recycle.
- **Serverless** (`SERVERLESS=true`, used on Vercel): `NullPool`. A function may
  be frozen or discarded between invocations and must not hold a connection.

`statement_cache_size=0` is set because server-side prepared statements break
behind transaction-mode connection poolers such as PgBouncer.

## Migrations

Alembic reads its URL from application settings and prefers
`DATABASE_URL_DIRECT` when present, because managed providers often require a
direct (non-pooled) connection for DDL.

**Migrations never run at application startup or during a request.** They are a
controlled release step. This keeps cold starts fast and prevents two concurrent
serverless instances from racing on the schema.

## Deployment shape

Local development uses Docker Compose (PostgreSQL plus the API container).
Production targets Vercel: the React frontend as a static build and FastAPI on
the Vercel Python runtime, backed by managed PostgreSQL. Docker Compose is not
used in production. Full deployment details arrive in Phase 12.
