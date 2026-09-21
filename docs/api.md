# API

Base URL in local development: `http://localhost:8000`

Interactive documentation is served at `/docs` (Swagger UI) and `/redoc` in every
environment except production, where all three documentation routes are disabled.

The versioned API lives under `/api/v1`. Health probes are intentionally
unversioned, because platform probes should not follow API versioning.

## Conventions

- Request and response bodies are JSON.
- Every response carries an `X-Request-ID` header. Sending your own
  `X-Request-ID` (8-64 characters, alphanumerics plus `-` and `_`) makes it flow
  through the logs unchanged.
- Errors use one envelope, described in [architecture.md](./architecture.md#error-contract).
- Monetary and quantity fields are serialized as JSON strings in later phases to
  avoid binary floating-point rounding.

## Endpoints

### `GET /health` — liveness

Returns `200` whenever the process is running. Touches no dependency.

```json
{
  "status": "ok",
  "service": "heimdall-api",
  "version": "0.1.0",
  "environment": "local",
  "timestamp": "2026-09-20T10:00:00Z"
}
```

### `GET /ready` — readiness

Verifies that required dependencies respond. Returns `200` when ready and `503`
when not, so the payload shape stays identical either way.

```json
{
  "status": "ready",
  "dependencies": [{ "name": "database", "status": "ok" }],
  "timestamp": "2026-09-20T10:00:00Z"
}
```

## Authentication

See [authentication.md](./authentication.md) for the full design. Summary:
`Authorization: Bearer <access token>` on every private endpoint; the refresh
token lives in an HttpOnly cookie scoped to `/api/v1/auth`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Create an account and sign in. `201` |
| POST | `/api/v1/auth/login` | Exchange credentials for an access token |
| POST | `/api/v1/auth/refresh` | Rotate the session using the refresh cookie |
| POST | `/api/v1/auth/logout` | Revoke the refresh token. Idempotent |
| GET | `/api/v1/auth/me` | The authenticated user |

## Portfolios

All portfolio endpoints require authentication and act only on the caller's own
records. A portfolio belonging to another user is reported as `404`, identically
to one that does not exist.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/portfolios` | Create a portfolio. `201` |
| GET | `/api/v1/portfolios` | List portfolios, paginated (`limit`, `offset`), newest first |
| GET | `/api/v1/portfolios/{portfolio_id}` | Portfolio with its holdings |
| PATCH | `/api/v1/portfolios/{portfolio_id}` | Partial update. `base_currency` is immutable |
| DELETE | `/api/v1/portfolios/{portfolio_id}` | Delete the portfolio and its holdings. `204` |

### Positions

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/portfolios/{portfolio_id}/positions` | List holdings, ordered by symbol |
| POST | `/api/v1/portfolios/{portfolio_id}/positions` | Add a holding. `201` |
| PATCH | `/api/v1/portfolios/{portfolio_id}/positions/{position_id}` | Update quantity, cost, or purchase date |
| DELETE | `/api/v1/portfolios/{portfolio_id}/positions/{position_id}` | Remove a holding. `204` |

A portfolio holds **at most one position per asset**. `on_duplicate` controls the
behaviour when the asset is already held:

* `reject` (default) — `409 position_already_exists`, nothing is changed.
* `merge` — quantities add and the average cost becomes the cost-weighted mean,
  `(q1*c1 + q2*c2) / (q1+q2)`, rounded to four decimal places. The earlier of the
  two purchase dates is kept.

Adding a position for an unknown symbol creates the asset record on demand with
only its symbol and currency. Its `asset_type` is `unknown` and its `name`,
`sector`, `exchange`, and `industry` are `null` until the market-data subsystem
describes it. Nothing about an instrument is invented.

`cost_basis` and `total_cost_basis` are **acquisition cost**, not market value.
Valuation requires prices, which arrive in Phase 3.

Decimal amounts are serialized as JSON **strings** at a fixed scale — quantities
with 8 decimal places, monetary values with 4 — so the same amount always looks
identical on the wire and no client loses precision to binary floating point.

### Limits

| Limit | Value |
| --- | --- |
| Portfolios per account | 50 |
| Positions per portfolio | 200 |
| Page size | 1–200, default 50 |
| Portfolio name | 1–120 characters, unique per user, case-insensitive |
| Quantity | greater than 0, up to 8 decimal places |
| Average cost | 0 or greater, up to 4 decimal places |

## Currency limitation

A portfolio has one `base_currency`, and only `USD` is supported at present.
Adding an asset denominated in another currency is rejected with
`422 currency_mismatch`. Heimdall does not convert between currencies, so
combining them would silently produce meaningless totals.

## Market data

See [market-data.md](./market-data.md).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/assets/search?query=` | Search instruments through the provider |
| GET | `/api/v1/assets/{symbol}/prices` | Daily bars, fetching missing trading days first |
| POST | `/api/v1/portfolios/{id}/market-data/refresh` | Refresh every holding. Idempotent |

## Analytics

See [financial-methodology.md](./financial-methodology.md).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/portfolios/{id}/summary` | Current valuation. No historical statistics |
| POST | `/api/v1/portfolios/{id}/analysis-runs` | Run and store a risk analysis. `201` |
| GET | `/api/v1/portfolios/{id}/analysis-runs` | Analysis history |
| GET | `/api/v1/analysis-runs/{run_id}` | One run with every metric |

Every metric carries its `unit`, its analysis period, whether it is annualized, its
confidence level where relevant, and its calculation assumptions. A metric that
could not be computed has a `null` value and an `unavailable_reason`; the run's
status is then `partial`. Missing data is never reported as zero.

Analysis parameters: `start`, `end`, `confidence`, `var_method`, `frequency`,
`annual_risk_free_rate`, `benchmark_symbol`, `minimum_observations`.

## Stress testing

See [stress-testing.md](./stress-testing.md).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/stress-scenarios` | Historical scenario catalogue with exact dates |
| POST | `/api/v1/portfolios/{id}/stress-tests` | Run one scenario. `201` |
| GET | `/api/v1/portfolios/{id}/stress-tests` | Stress-test history |
| GET | `/api/v1/stress-tests/{run_id}` | One result with its position breakdown |

Provide exactly one of `scenario_key` or `custom`. Shock precedence: symbol over
sector over portfolio.

## Early Warning System

See [early-warning.md](./early-warning.md). User-facing copy calls these
**Gjallarhorn Signals**; the API keeps technical names.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/alert-rule-types` | Rule catalogue with units and documented defaults |
| GET | `/api/v1/portfolios/{id}/alert-rules` | List rules |
| POST | `/api/v1/portfolios/{id}/alert-rules` | Create a rule. `201` |
| GET | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Get a rule |
| PATCH | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Update, enable, or disable |
| DELETE | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Delete a rule and its history. `204` |
| POST | `/api/v1/portfolios/{id}/alert-rules/defaults` | Provision or restore defaults |
| POST | `/api/v1/portfolios/{id}/monitoring-runs` | Run monitoring now. `201` |
| GET | `/api/v1/portfolios/{id}/monitoring-runs` | Monitoring history |
| GET | `/api/v1/monitoring-runs/{run_id}` | One run with per-rule outcome |
| GET | `/api/v1/portfolios/{id}/signals` | A portfolio's signals, filtered |
| GET | `/api/v1/portfolios/{id}/signals/summary` | Open counts by severity |
| GET | `/api/v1/signals` | Signals across the caller's portfolios |
| GET | `/api/v1/signals/{signal_id}` | One signal with its audit trail |
| POST | `/api/v1/signals/{signal_id}/acknowledge` | Mark as seen. Does **not** resolve it |
| POST | `/api/v1/signals/{signal_id}/dismiss` | Hide without resolving |
| POST | `/api/v1/internal/monitoring/run` | Scheduled monitoring. Requires `CRON_SECRET` |

There is deliberately **no** endpoint to resolve a signal. Only the rule engine
resolves one, when it observes that the condition has cleared.

## Reports

See [reports.md](./reports.md).

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/portfolios/{id}/reports` | Generate a PDF risk report. `201` |
| GET | `/api/v1/portfolios/{id}/reports` | List reports |
| GET | `/api/v1/reports/{report_id}` | Report metadata |
| GET | `/api/v1/reports/{report_id}/download` | The PDF |

## Rate limits

See [security.md](./security.md#rate-limiting). Limited endpoints return `429` with
`Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining`.

| Endpoint | Limit |
| --- | --- |
| `POST /api/v1/auth/login` | 10 per 5 minutes |
| `POST /api/v1/auth/register` | 5 per hour |
| `POST /api/v1/auth/refresh` | 60 per 5 minutes |
| `GET /api/v1/assets/*` | 120 per minute |

## Error codes

| Code | Status | Meaning |
| --- | --- | --- |
| `validation_error` | 422 | Request schema validation failed; see `details` |
| `not_authenticated`, `invalid_access_token` | 401 | Missing or unusable bearer token |
| `invalid_credentials`, `invalid_refresh_token` | 401 | Authentication failed |
| `permission_denied` | 403 | Authenticated but not allowed |
| `portfolio_not_found`, `position_not_found`, `asset_not_found` | 404 | Not found, or not yours |
| `analysis_run_not_found`, `stress_test_run_not_found` | 404 | Not found, or not yours |
| `alert_rule_not_found`, `signal_not_found`, `monitoring_run_not_found` | 404 | Not found, or not yours |
| `report_not_found`, `scenario_not_found` | 404 | Not found, or not yours |
| `email_already_registered`, `portfolio_name_taken` | 409 | Duplicate |
| `position_already_exists`, `alert_rule_exists` | 409 | Duplicate |
| `monitoring_already_running`, `signal_not_open` | 409 | Conflicting state |
| `portfolio_limit_reached`, `position_limit_reached` | 409 | Over a documented limit |
| `csv_import_failed`, `csv_import_conflict` | 422 | See [csv-import.md](./csv-import.md) |
| `portfolio_empty`, `no_market_data`, `portfolio_zero_value` | 422 | Nothing to analyze |
| `invalid_date_range`, `window_too_large` | 422 | Bad analysis window |
| `currency_mismatch`, `unsupported_currency` | 422 | Currency not supported |
| `invalid_rule_configuration` | 422 | Rule parameters or thresholds invalid |
| `scenario_data_unavailable` | 422 | No stored data for a scenario window |
| `report_generation_failed`, `report_not_ready` | 422 | Report problem |
| `payload_too_large` | 413 | Body over the limit |
| `rate_limited` | 429 | Over a rate limit |
| `scheduler_not_authorized` | 401 | Wrong or missing scheduler secret |
| `scheduler_not_configured` | 503 | No `CRON_SECRET` set |
| `market_data_unavailable`, `service_unavailable` | 503 | A dependency is down |
| `internal_error` | 500 | Unexpected failure. Never carries detail |

## Security headers

Every response carries `X-Content-Type-Options`, `X-Frame-Options`,
`Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`, and
`Cache-Control: no-store`, plus `Strict-Transport-Security` in deployed
environments. See [security.md](./security.md#response-headers).

## Not yet implemented

| Phase | Scope |
| --- | --- |
| 8-11 | Frontend |
| 12 | Vercel deployment, cron configuration, end-to-end tests |

## Disclaimer

Heimdall is an educational portfolio-analysis tool. Its calculations are
estimates based on historical data and model assumptions and do not constitute
financial advice or guarantee future results.
