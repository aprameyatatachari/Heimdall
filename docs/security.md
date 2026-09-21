# Security

What Heimdall does, and — just as importantly — what it does not do. Every
limitation here is deliberate and stated rather than left for a reader to discover.

## Authentication

See [authentication.md](./authentication.md) for the full design. Summary:

- Argon2id password hashing, 12-character minimum, transparent rehash on login.
- Short-lived signed access tokens (15 minutes) sent as bearer tokens.
- Opaque refresh tokens stored only as SHA-256 digests, rotated on every use.
- Replaying a rotated refresh token revokes every session of that user.
- Credential failures are indistinguishable: wrong password and unknown address
  return the same code and message, and an unknown address still costs a hash so
  response timing does not leak existence.

## Authorization

Ownership is a **query predicate**, never a check performed after loading:

```python
select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
```

Consequences, all tested:

- A resource owned by someone else and a resource that does not exist return the
  same `404` with the same message, so the API cannot be used to enumerate data.
- A nested resource reached through the wrong parent is `404`: a position under
  another portfolio, a rule under another portfolio.
- Reports carry `user_id` alongside `portfolio_id`, so a report can only ever be
  read by the account that generated it.
- Analysis runs, stress tests, monitoring runs, and signals are all scoped by
  joining through the portfolio to its owner.

## Input validation

- Every request body is a Pydantic model with `extra="forbid"`. An unrecognised
  field is rejected rather than ignored.
- Ticker symbols pass a strict pattern; `=SUM(A1)` and `AAPL;DROP` are refused.
- Monetary values and quantities are `Decimal` with bounded precision.
- Alert-rule parameters validate against a per-rule-type schema, and severity
  thresholds must increase with severity.
- Path parameters are typed as `UUID`, so a malformed id is a `422`, never a query.
- All database access goes through SQLAlchemy Core or the ORM with bound
  parameters. The handful of raw statements use named parameters.

## Upload handling

CSV import, documented in full in [csv-import.md](./csv-import.md):

- 512 KiB file limit, counted **as the upload streams**, not trusted from
  `Content-Length`.
- 1000-row limit, 64-character cell limit.
- Rejects non-UTF-8 content, embedded NUL bytes, unexpected columns, and duplicate
  columns.
- Validates the whole file before writing anything; a rejected file leaves the
  database byte-for-byte unchanged.
- Uploaded file contents are never logged.

### Spreadsheet formula injection

A cell beginning with `=`, `+`, `-`, `@`, a tab, or a carriage return is executed
by spreadsheet software. Guarded in both directions: such a value fails import
validation unless it is a plain number, and `sanitize_csv_value` prefixes it with
a single quote on export.

## Rate limiting

In-process fixed-window counters on the endpoints worth guarding:

| Endpoint | Limit |
| --- | --- |
| `POST /api/v1/auth/login` | 10 per 5 minutes |
| `POST /api/v1/auth/register` | 5 per hour |
| `POST /api/v1/auth/refresh` | 60 per 5 minutes |
| `GET /api/v1/assets/*` | 120 per minute |

A rejected request returns `429` with `Retry-After`, `X-RateLimit-Limit`, and
`X-RateLimit-Remaining`.

**Known weakness, stated plainly.** The counter store is per-process. On a
platform that runs several concurrent instances the effective limit is
`limit x instances`. This blunts credential stuffing and accidental client loops;
it is **not** a distributed quota. Making it one means moving the counter into a
shared store (Redis, or a Postgres table with a short-lived row) behind the same
`FixedWindowCounter` interface — the middleware would not change.

The client key comes from the **first** `X-Forwarded-For` entry, which is what a
trusted proxy prepends, so a client-supplied value later in the chain cannot be
used to evade the limit.

## Response headers

Applied to every response:

| Header | Value |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=(), payment=()` |
| `Cache-Control` | `no-store` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` — deployed environments only |

`default-src 'none'` is right for an API that serves no scripts, styles, or
images. The frontend, served separately, sets its own policy for HTML.

## Error handling

- One envelope for every failure: `{error: {code, message, details, request_id}}`.
- An unhandled exception is logged with a stack trace and returned as an opaque
  `500`. No exception message, no traceback, and no SQL ever reaches a client.
  This is covered by a test that raises an error containing a fake password and
  asserts the string is absent from the response.
- Documentation routes (`/docs`, `/redoc`, `/openapi.json`) are disabled in
  production.

## Logging

- Structured, JSON in deployed environments, with a request ID on every line.
- `app/common/logging.py` redacts `password`, `password_hash`, `authorization`,
  `token`, `access_token`, `refresh_token`, `secret`, `api_key`, `cookie`, and
  `set-cookie`, and the redaction is tested.
- Never logged: passwords, tokens, authorization headers, cookies, uploaded file
  contents, the scheduler secret, or a client IP on the rate-limit path.
- The scheduled monitoring response carries operational counts only — never
  portfolio names, holdings, or signal content.
- Requests slower than 3 seconds are logged at warning level, because a serverless
  function has a hard duration limit.

## Secrets

- Every secret comes from the environment. None has a usable default.
- `AUTH_SECRET` has a development placeholder that startup **refuses** in preview
  and production, along with any value shorter than 32 characters.
- Production startup also refuses `DEBUG=true`, an empty CORS allowlist, a
  wildcard CORS origin, and a non-secure refresh cookie.
- `SecretStr` keeps secrets out of `repr()` and logs.
- `.gitignore` excludes `.env` and `.env.*` while keeping `.env.example`.
- `.dockerignore` keeps `.env` files, `.git`, and caches out of the build context.

## Scheduled endpoint

`POST /api/v1/internal/monitoring/run` is the one endpoint not behind a user
session:

- Requires `CRON_SECRET` in `X-Cron-Secret` or as a bearer token.
- Compared with `secrets.compare_digest`, so a caller cannot discover the secret
  by timing rejections.
- **Fails closed**: with no secret configured it returns `503` rather than running
  unprotected.
- Bounded and resumable, so it cannot be used to force unbounded work.
- Idempotent per UTC day, so a retry storm cannot multiply work.

## Containers

- Multi-stage build; the runtime image carries only the virtual environment and
  application code.
- Runs as the non-root user `heimdall` (uid 1001). CI asserts this.
- A health check is baked into the image.
- CI builds the image, scans it with Trivy for HIGH and CRITICAL issues, and starts
  it to confirm `/health` answers and `/ready` returns `503` without a database.

## Dependencies

- `uv.lock` pins every transitive dependency; CI installs with `--frozen`.
- `pip-audit` runs in CI on every push.

Both scans use `continue-on-error`. That is deliberate: advisory databases change
without any code change here, and a new advisory in a transitive dependency should
show up in the run rather than turn an unrelated pull request red. The trade-off is
that a scan finding does not block a merge on its own — it has to be read.

## Database

- Parameterised queries throughout.
- Constraints enforce invariants independently of application code: positive
  quantities, non-negative costs, normalized symbols and currencies, unique emails
  (case-insensitively), one position per asset per portfolio, one rule per type,
  and one open signal per condition.
- Cascades are deliberate and documented in each migration. Deleting an asset that
  a position references is *restricted*, because assets are shared reference data.
- One transaction per request, committed on success and rolled back on failure.

## What is not implemented

Stated so nobody assumes otherwise:

- **No email verification, password reset, or multi-factor authentication.**
- **No access-token revocation.** A signed-out user's access token works until it
  expires, at most 15 minutes.
- **No distributed rate limiting.** See above.
- **No audit log of reads.** Writes to signals are audited; reads are not.
- **No field-level encryption.** Portfolio data is protected by access control and
  by the database's own encryption at rest, not by application-level encryption.
- **No CAPTCHA or bot detection** on registration.
- **No per-account quotas** beyond 50 portfolios and 200 positions per portfolio.
- **No signed URLs for report downloads.** A download requires a bearer token.

## Reporting a vulnerability

This is an educational portfolio project and holds no real user data. If you find
a problem, open an issue describing it.
