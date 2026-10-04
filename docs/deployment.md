# Deployment

Heimdall deploys to **Vercel** as a single project: the React application is
served as static files, and everything under `/api` is handled by a Python
function running the same FastAPI application that runs locally.

---

## 1. Why one project

Two layouts were considered.

| | One project (chosen) | Two projects |
| --- | --- | --- |
| Frontend and API share an origin | yes | no |
| Refresh cookie | first-party, `SameSite=Lax` | third-party, needs `SameSite=None; Secure` |
| CORS | not needed at all | required, and must list every frontend domain |
| Preview deployments | one URL per commit, API included | two URLs to keep in step |
| Frontend configuration | none | `VITE_API_BASE_URL` per environment |

The single project wins on the thing that matters most here: the refresh token
is an HTTP-only cookie, and a same-origin API keeps it first-party. Third-party
cookies are blocked by default in more browsers every year, and a deployment
whose sign-in silently stops working in a browser update is not a deployment.

It also matches development. `vite.config.ts` proxies `/api` to the backend for
exactly this reason, so the arrangement under test is the arrangement that ships.

**The split layout still works** if it is ever needed — nothing in the code
assumes one origin:

1. Deploy `frontend/` and `backend/` as separate Vercel projects.
2. Set `VITE_API_BASE_URL` on the frontend to the API's origin.
3. Set `CORS_ALLOW_ORIGINS` on the API to the frontend's domains, never `*`.
4. Set `REFRESH_COOKIE_SAMESITE=none` and `REFRESH_COOKIE_SECURE=true`.

> **Not verified against a live Vercel build.** The configuration here is
> written against Vercel's documented behaviour and the repository's own
> structure; the first deployment should be a preview, and section 8 says what
> to check on it.

---

## 2. What is deployed

```text
vercel.json               routing, function limits, headers, the cron schedule
api/index.py              the Vercel entrypoint; re-exports backend/app/main.py
api/requirements.txt      pinned runtime dependencies, generated from uv.lock
api/cron/monitoring.py    the scheduled-monitoring adapter (section 6)
frontend/dist             the built SPA, produced by the build command
fixtures/market_data      committed price series the fixture provider reads
```

Requests route like this:

| Path | Served by |
| --- | --- |
| `/api/*`, `/health`, `/ready`, `/openapi.json`, `/docs` | the FastAPI function |
| `/assets/*`, `/fonts/*`, `/images/*`, `/brand/*` | static files |
| everything else | `index.html`, so React Router owns the route |

That last rewrite is the SPA fallback: a direct visit to `/app/portfolios/…`
returns the application rather than a 404, and the router takes it from there.

### Regenerating the function's dependencies

`api/requirements.txt` is generated. After any change to backend dependencies:

```bash
cd backend && uv export --no-dev --no-hashes --no-emit-project \
  --no-annotate --format requirements-txt | grep -v '^#' > ../api/requirements.txt
```

---

## 3. Environment variables

Set these in Vercel, per environment. **Nothing server-side may be named
`VITE_*`** — every `VITE_` variable is inlined into the JavaScript bundle and is
public the moment it is deployed.

### Required in production

| Variable | Example | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Turns on the production safety checks in `config.py` |
| `DATABASE_URL` | `postgresql+asyncpg://…-pooler.neon.tech/heimdall?ssl=require` | The **pooled** endpoint |
| `DATABASE_URL_DIRECT` | `postgresql+asyncpg://….neon.tech/heimdall?ssl=require` | The **direct** endpoint, for migrations |
| `SERVERLESS` | `true` | Switches SQLAlchemy to `NullPool` |
| `AUTH_SECRET` | 32+ random characters | Signs access tokens; rotating it signs everyone out |
| `REFRESH_COOKIE_SECURE` | `true` | Refused otherwise outside local development |
| `CORS_ALLOW_ORIGINS` | `https://heimdall.example.com` | Never `*`; unused in the single-project layout but validated |
| `CRON_SECRET` | 32+ random characters | Guards scheduled monitoring; Vercel also sends it as a bearer token |
| `LOG_FORMAT` | `json` | Structured logs, for a log drain that can parse them |

### Optional

| Variable | Default | Notes |
| --- | --- | --- |
| `MARKET_DATA_PROVIDER` | `fixture` | **Set `yahoo` in production**; `fixture` serves committed offline series |
| `MARKET_DATA_API_KEY` | unset | Unused by Yahoo, which needs no key |
| `MONITORING_BATCH_SIZE` | `25` | Portfolios per scheduled invocation |
| `RATE_LIMIT_ENABLED` | `true` | Per-instance; see `docs/security.md` |
| `VITE_API_BASE_URL` | unset | Only for the split layout |

### Preview environments

Preview deployments must never reach production data. Give the Preview
environment its **own** `DATABASE_URL` — a Neon branch is the natural fit, and
branching is cheap — and its own `AUTH_SECRET`. Set `ENVIRONMENT=preview`, which
keeps the secret and cookie checks on while allowing a separate database.

Scheduled monitoring refuses to run anywhere but production; see section 6.

---

## 4. Database: Neon

Heimdall needs PostgreSQL 15 or newer. On Neon:

1. Create a project and a database named `heimdall`.
2. Copy **both** connection strings — the pooled one (host contains `-pooler`)
   and the direct one.
3. Rewrite the scheme for SQLAlchemy's async driver:
   `postgresql://…` → `postgresql+asyncpg://…`, and keep `?ssl=require`.
4. Put the pooled URL in `DATABASE_URL` and the direct one in
   `DATABASE_URL_DIRECT`.

**Why both.** The pooled endpoint sits behind PgBouncer in transaction mode,
which is right for short serverless requests and wrong for migrations: Alembic
takes advisory locks and runs DDL in a session, neither of which survives a
transaction pooler. `config.py` exposes `migration_database_url`, which prefers
the direct URL, and the migration step uses it.

`SERVERLESS=true` also matters here. A Vercel function may be frozen between
invocations, and a pool of open connections in a frozen function is a pool of
connections the database is still holding. `NullPool` opens one connection per
request and closes it, which is why connection counts stay flat under load
rather than climbing until Neon refuses new ones.

---

## 5. Migrations

**Migrations never run at startup or during a request.** They are a release
step, run once, against the direct URL:

```bash
cd backend
DATABASE_URL_DIRECT='postgresql+asyncpg://…' uv run alembic upgrade head
```

In the pipeline this happens after the tests pass and **before** the deploy
promotes, so the schema is always at or ahead of the code that talks to it. A
migration that is not backwards compatible with the currently deployed code
needs two releases: widen the schema, deploy the code, then narrow it.

To see what a migration would do first:

```bash
uv run alembic upgrade head --sql    # print the SQL, apply nothing
uv run alembic current               # what the database is at now
uv run alembic history --verbose     # the full chain
```

---

## 6. Scheduled monitoring

`vercel.json` schedules `/api/cron/monitoring` daily at **06:00 UTC**. Vercel
Cron schedules are always UTC; there is no timezone setting, and none is wanted
— a job that moves twice a year with daylight saving is a job that is hard to
reason about.

The path is a small adapter rather than the API endpoint itself, because Vercel
Cron issues `GET` and evaluating every portfolio is not a `GET`. The adapter:

1. Refuses unless `VERCEL_ENV=production`, so a preview deployment cannot run
   production monitoring even if it were pointed at the same database.
2. Verifies `Authorization: Bearer $CRON_SECRET` in constant time. Vercel sends
   that header automatically when `CRON_SECRET` is set. **An unset secret
   refuses rather than running unprotected.**
3. Calls `POST /api/v1/internal/monitoring/run` with the secret and
   `refresh_prices: true`, so the real request goes through the real guard and
   the rules are evaluated against prices read that morning.

This is a **daily** check, which is what Vercel's free plan allows. The
in-process scheduler that checks every few minutes (`LIVE_MONITORING_ENABLED`)
does not run here: a serverless function has no process to keep a timer in. To
check more often on a deployment, point any scheduler that can send a header at
the endpoint directly and tell it how often it calls:

```text
POST /api/v1/internal/monitoring/run
X-Cron-Secret: <secret>
{"refresh_prices": true, "interval_minutes": 15}
```

`interval_minutes` makes the evaluation period one interval instead of one day,
so each call evaluates and a retry inside the same interval is still
deduplicated. See `docs/early-warning.md`.

The work itself is idempotent and retry-safe: one evaluation period per UTC day,
so a retry after a timeout resumes rather than double-evaluating, and
`MONITORING_BATCH_SIZE` bounds a run to fit inside the function's 60-second
limit. A portfolio that fails is recorded and the batch continues.

**To disable it safely:** remove the `crons` block from `vercel.json` and
redeploy, or unset `CRON_SECRET` — the endpoint then refuses every call,
including a genuine one. Removing the schedule is the tidier of the two;
unsetting the secret is the faster. Neither loses data: monitoring records
state, it does not own it.

---

## 6a. Market data in production

Set `MARKET_DATA_PROVIDER=yahoo`. It needs no key.

Two things to watch on a serverless platform:

- **Cold starts carry pandas.** The Yahoo adapter imports `yfinance`, which
  imports pandas and numpy. The import is deferred until the provider is first
  built, so a request that never touches market data does not pay for it, but
  the first one that does will be slower.
- **Yahoo rate-limits without documenting it.** Every bar is cached in
  PostgreSQL after the first fetch, so a busy portfolio hits the provider once
  per symbol per day rather than once per view. A refresh that fails is reported
  per symbol and does not abort the others.

Falling back to `fixture` is always available and needs no network at all, but
its series end in 2024 and are synthetic — never present them as live prices.

## 7. Reports

Generated PDFs are stored as bytes in PostgreSQL, not on disk. A serverless
function's filesystem does not survive the invocation that wrote to it, so a
report written to `/tmp` would be gone before anyone could download it.

No external object storage is configured, and none is needed at this size. The
`Report` model documents the size limit and the migration path if reports ever
outgrow a database column.

---

## 8. Deploying

The pipeline is `.github/workflows/deploy.yml`. It is **manual** —
`workflow_dispatch` — until the Vercel project exists and the production
environment holds its secrets; the file says where to add the push trigger back.
The first deployment of anything should be a decision rather than a side effect
of a push.

In order:

1. Backend: format check, lint, strict type check, unit tests.
2. Frontend: format check, lint, type check, unit tests, production build.
3. Integration tests against a real PostgreSQL service container.
4. Playwright, against the built application and a live API.
5. `alembic upgrade head` against `DATABASE_URL_DIRECT`.
6. `vercel deploy --prod`.
7. Post-deployment health checks against `/health` and `/ready`.

Nothing after step 4 runs unless everything before it passed, and step 5 runs
before step 6 so the schema is never behind the code.

### By hand

```bash
npm i -g vercel
vercel link                     # once, to associate the directory with a project
vercel                          # preview deployment
vercel --prod                   # production
```

### What to check on the first preview

- `/health` returns `{"status": "ok"}` and `/ready` reports the database.
- A direct visit to `/app/portfolios` loads the application, not a 404.
- Registration works, and the refresh cookie appears as `HttpOnly`, `Secure`,
  `SameSite=Lax`, scoped to `/api/v1/auth`.
- A portfolio can be created, priced, analysed and stress-tested.
- The JavaScript bundle contains no secret: `grep -ri "secret\|password" frontend/dist/assets/*.js`
  should find nothing but the words themselves in UI copy.
- Connection count on Neon returns to baseline after traffic stops.

---

## 9. Rollback

Vercel keeps every deployment, and promoting an old one is immediate:

```bash
vercel ls                            # find the last good deployment
vercel promote <deployment-url>      # make it production again
```

Or use **Instant Rollback** in the project's dashboard.

**The schema does not roll back with it.** That asymmetry is deliberate — an
automatic `alembic downgrade` in a rollback path would be a data-loss button —
so plan for it:

- A rollback to code that predates the newest migration is safe when the
  migration was additive, which is the normal case.
- If the migration was not additive, downgrade deliberately and separately:
  `uv run alembic downgrade -1`, against the direct URL, having read what the
  downgrade does.
- Rotating `AUTH_SECRET` invalidates every access token immediately. That is the
  fastest way to sign everyone out if a token is believed compromised; refresh
  tokens are opaque and revoked server-side.

---

## 10. Demo data

```bash
cd backend
DEMO_PASSWORD='choose something long' \
  uv run python -m app.cli seed-demo --email demo@example.com
```

It creates an account, a five-holding portfolio, prices from the committed
fixtures, one analysis run, the default alert rules and one monitoring run. It
is idempotent, so running it twice does not produce two demo portfolios.

It **refuses to run against a production database** unless
`HEIMDALL_ALLOW_DEMO_SEED=true` is also set. It never generates a password:
`DEMO_PASSWORD` must be supplied, so no credential is invented, printed or
committed by the tool.
