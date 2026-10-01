# Heimdall

**See risk before it arrives.**

Heimdall is a portfolio risk-intelligence platform for measuring exposure,
analyzing performance, and testing how investments respond to adverse market
scenarios.

Named after the vigilant watchman of Norse mythology, Heimdall is designed to
make approaching portfolio risks easier to see and understand. Its **Gjallarhorn
Early Warning System** monitors defined portfolio conditions and raises clear,
explainable signals when risk or data-quality thresholds are crossed.

> **Educational use only.** Heimdall is an educational portfolio-analysis tool.
> Its calculations are estimates based on historical data and model assumptions
> and do not constitute financial advice or guarantee future results.

---

## Project status

Under active development, phase by phase.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repository design and scaffolding | **Complete** |
| 1 | Authentication and core portfolio domain | **Complete** |
| 2 | CSV portfolio import | **Complete** |
| 3 | Market-data subsystem | **Complete** |
| 4 | Financial analytics engine | **Complete** |
| 5 | Stress-testing engine | **Complete** |
| 6 | Gjallarhorn Early Warning System backend | **Complete** |
| 7 | Backend hardening and report generation | **Complete** |
| 8-11 | Frontend | **Complete** |
| 12 | Vercel deployment and final quality | Configured, not yet deployed |

Backend and frontend are both feature-complete. Phase 12's configuration,
pipeline and documentation are in place; **no deployment has been run against
Vercel yet**, so treat the first one as a preview and work through
[deployment.md](docs/deployment.md) section 8.

What exists today:

- **Accounts and portfolios** — registration, sessions, portfolios, positions, and
  ownership authorization enforced as a query predicate.
- **CSV import** — full-file validation with row-and-column error reporting, and
  merge, replace, or reject modes. A rejected file changes nothing.
- **Market data** — a vendor-neutral provider interface with two adapters, live
  Yahoo Finance and committed offline fixtures, plus local caching with gap
  detection and idempotent ingestion.
- **Analytics** — returns, volatility, Sharpe ratio, drawdown, historical and
  parametric VaR, Expected Shortfall, correlation, risk attribution, and benchmark
  comparison, validated against an independently computed golden portfolio.
- **Stress testing** — a historical scenario catalogue and custom hypothetical
  shocks with documented precedence and position-level attribution.
- **Gjallarhorn Early Warning System** — nine deterministic rules, explainable
  signals, a full lifecycle with an audit trail, deduplication, cooldowns, and a
  protected scheduled endpoint.
- **Reports** — reproducible PDF risk reports built from stored analysis inputs.
- **Hardening** — rate limiting, security headers, and container and dependency
  scanning in CI.

- **The application** — a React single-page application covering the whole of the
  above: portfolios and holdings, the analytics dashboard, stress testing, the
  Gjallarhorn signal interface, and report generation. Every metric carries its
  unit and its basis, every chart carries the numbers behind it, and a figure
  that could not be computed shows the reason rather than a zero.

Everything is also reachable directly through the API and its interactive
documentation.

## Architecture

```mermaid
flowchart TB
    subgraph browser["Browser"]
        spa["React SPA<br/>routing, TanStack Query, in-memory access token"]
    end

    subgraph vercel["Vercel, one project"]
        static["Static files<br/>frontend/dist"]
        fn["Python function<br/>api/index.py → FastAPI"]
        cron["Cron 06:00 UTC<br/>api/cron/monitoring.py"]
    end

    subgraph api["FastAPI, a modular monolith"]
        direction LR
        auth["auth"]
        portfolios["portfolios"]
        market["market_data"]
        analytics["analytics"]
        stress["stress_testing"]
        ews["early_warning"]
        reports["reports"]
    end

    db[("PostgreSQL<br/>Neon in production")]
    fixtures[["fixtures/market_data<br/>committed price series"]]

    spa -->|"/api/v1/*, same origin"| fn
    spa --> static
    cron -->|"shared secret"| fn
    fn --> api
    api --> db
    market --> fixtures

    portfolios --> analytics
    market --> analytics
    analytics --> stress
    analytics --> ews
    stress --> ews
    analytics --> reports
    stress --> reports
    ews --> reports
```

One FastAPI application split by business capability, not microservices. Each
capability owns its router, service, repository, models and schemas; routes
validate and authorize, services own use cases and transactions, repositories own
queries, and financial calculations are pure functions with no HTTP, database or
clock dependency. [architecture.md](docs/architecture.md) has the detail.

The frontend and the API share an origin in production, which is what keeps the
refresh cookie first-party. [deployment.md](docs/deployment.md) explains the
choice.

## Technology

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg),
Alembic, PostgreSQL 17, NumPy, pandas, SciPy, ReportLab, structlog, Argon2id,
PyJWT. Tooling: uv, Ruff, mypy (strict), pytest, pip-audit.

**Frontend** — React 18, TypeScript (strict), Vite 6, Tailwind CSS v4, TanStack
Query, React Router, React Hook Form with Zod, Vitest with Testing Library and
MSW, Playwright, ESLint and Prettier. Charts are hand-drawn SVG rather than a
charting library: the table alternative has to read the same numbers the chart
drew, a gap in the data has to stay a gap, and most libraries interpolate across
one by default.

**Infrastructure** — Docker and Docker Compose for local development, GitHub
Actions for CI, Vercel plus managed PostgreSQL for production.

## Quick start

Requirements: [Docker Desktop](https://docs.docker.com/desktop/),
[uv](https://docs.astral.sh/uv/), Python 3.12, Node 20.19 or newer.

### Windows: one command

`start.bat` brings up PostgreSQL, applies migrations, and starts the API and the
web application in their own windows. `stop.bat` shuts everything down and frees
the ports, and is safe to run at any time.

```bat
start.bat
stop.bat
```

| | |
| --- | --- |
| Web | <http://localhost:5173> |
| API | <http://127.0.0.1:8000> |
| API docs | <http://127.0.0.1:8000/docs> |
| Database | `localhost:5433` |

`start.bat` refuses to run if either port is already taken and names the process
holding it, because Windows reports that case only as `WinError 10013`.

`stop.bat -KeepDatabase` leaves PostgreSQL running. `stop.bat` stops only
processes whose command line identifies them as part of this project; if a port
is held by something else it says so and leaves it alone, and `stop.bat -Force`
overrides that.

### Everything in containers

```bash
cp .env.example .env
docker compose up --build -d
docker compose --profile tools run --rm migrate
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Interactive API docs: <http://localhost:8000/docs>

### Database in Docker, API on the host

Preferred while developing, because reloads are instant.

```bash
cp .env.example .env
docker compose up -d db

cd backend
cp ../.env.example .env        # defaults already point at localhost:5433
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### The frontend

```bash
cd frontend
npm install
npm run dev
```

Served at <http://localhost:5173>, proxying `/api` to the backend so the refresh
cookie stays first-party. See [`frontend/README.md`](frontend/README.md).

### Stopping

```bash
docker compose down            # keep data
docker compose down -v         # also delete the database volume
```

On Windows, `stop.bat` does all of this and frees the application ports too.

## Tests and checks

Run from `backend/`:

```bash
uv run ruff format --check .   # formatting
uv run ruff check .            # linting
uv run mypy app                # type checking
uv run pytest                  # unit tests, no database required
```

The default run covers everything hermetic: hashing, tokens, symbol
normalization, schema validation, CSV parsing, the trading calendar, provider-data
validation, every financial calculation, the golden portfolio, the stress engine,
all nine early-warning rules, PDF rendering, rate limiting, and security headers.

Everything that touches the database is an integration test, because Heimdall does
not substitute SQLite for PostgreSQL.

Integration tests need a live PostgreSQL database and are skipped otherwise:

```bash
docker compose up -d db
cd backend
DATABASE_URL=postgresql+asyncpg://heimdall:heimdall@localhost:5433/heimdall_test uv run alembic upgrade head
RUN_INTEGRATION_TESTS=1 uv run pytest -m integration
```

### The frontend's own checks

Run from `frontend/`:

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test              # Vitest, against MSW handlers typed from the real schema
npm run build
```

### The end-to-end journey

Playwright drives a real browser against a **real API and a real database** —
register, create a portfolio, add holdings, fetch prices, analyse, stress test,
monitor, generate and download a report, sign out. It is the one suite that
proves the contract rather than a fixture of it.

```bash
# once
cd frontend && npm run e2e:install

# with PostgreSQL up, migrations applied, and the API running
cd backend && RATE_LIMIT_ENABLED=false uv run uvicorn app.main:app
cd frontend && npm run e2e
```

Rate limiting is a production guard, not a property under test; left on, the
journey trips it on its own speed.

## Deployment

Vercel, as a single project: the built application is served as static files and
everything under `/api` is a Python function running the same FastAPI
application that runs locally.

```bash
npm i -g vercel
vercel link
vercel          # preview
vercel --prod   # production
```

**Read [deployment.md](docs/deployment.md) first.** It covers the layout decision
and the fallback, every environment variable and which of them must never be
`VITE_`-prefixed, Neon's pooled and direct endpoints and why migrations need the
direct one, the migration workflow, the scheduled monitoring job and how to turn
it off, the post-deployment checks, and rollback.

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Financial methodology](docs/financial-methodology.md)
- [Authentication](docs/authentication.md)
- [CSV import](docs/csv-import.md)
- [Market data](docs/market-data.md)
- [Stress testing](docs/stress-testing.md)
- [Gjallarhorn Early Warning System](docs/early-warning.md)
- [Reports](docs/reports.md)
- [Security](docs/security.md)
- [Environment variables](docs/environment.md)
- [Deployment](docs/deployment.md)
- [Contributor and agent guide](CLAUDE.md)

## Still to come

- A first deployment. Every piece of configuration is written and documented;
  none of it has been exercised against a live Vercel build.
- A real market-data provider. The interface is vendor-neutral and the only
  implementation is the offline fixture provider.
- Notification delivery for signals. The interface exists; no channel does.

## Limitations

Stated plainly, because a risk tool that hides its own limits is not much use.

- **Fixed-weight reconstruction.** Historical portfolio returns apply *today's*
  weights to each asset's past returns. They do not reconstruct what the portfolio
  actually held. Every affected figure says so.
- **Estimates, not forecasts.** VaR at 95% is a loss exceeded 5% of the time in the
  measured window, not a maximum possible loss. Stress tests measure sensitivity to
  stated price changes, not likelihood.
- **One base currency per portfolio**, `USD` or `INR`. Heimdall does not convert
  between currencies, so a portfolio accepts only instruments priced in its own:
  a rupee instrument in a dollar portfolio is rejected rather than silently
  combined. Adding a currency means adding instruments the provider can price in
  it, not just widening a list.
- **Market data comes from Yahoo Finance**, which is not an official API: it is
  unversioned, rate-limits without documenting it, and can change shape without
  notice. The committed fixtures remain the offline alternative and are
  **synthetic** — shaped to resemble real equity behaviour, but generated. The
  test suite always uses them, so no test depends on a third party. See
  [market-data.md](docs/market-data.md).
- **Weekday trading calendar.** Exchange holidays are not modelled.
- **Equities and ETFs only.** No bond, option, or futures modelling, so a price
  shock applied to a bond fund is a crude approximation.
- **No dividends, fees, or taxes** beyond what adjusted closing prices reflect.
- **Access tokens cannot be revoked** before they expire, at most 15 minutes. See
  [authentication.md](docs/authentication.md#known-limitations).
- **Rate limiting is per-process**, so under several concurrent instances the
  effective limit multiplies. See [security.md](docs/security.md#rate-limiting).
- **No external notification delivery** for signals. The interface exists; no
  channel is implemented.
- **Signals only appear when a monitoring run executes.** Between runs a condition
  can appear and disappear unobserved.

Heimdall does not execute trades, recommend buying, selling, or holding, or claim
to predict future returns.

## License

MIT.
