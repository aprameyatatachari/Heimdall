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
| 8-11 | Frontend | Not started |
| 12 | Vercel deployment and final quality | Not started |

The backend is feature-complete. The frontend begins at Phase 8.

What exists today:

- **Accounts and portfolios** — registration, sessions, portfolios, positions, and
  ownership authorization enforced as a query predicate.
- **CSV import** — full-file validation with row-and-column error reporting, and
  merge, replace, or reject modes. A rejected file changes nothing.
- **Market data** — a vendor-neutral provider interface, an offline fixture
  provider, local caching with gap detection, and idempotent ingestion.
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

There is **no frontend yet**. Everything above is reachable through the API and its
interactive documentation.

## Technology

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg),
Alembic, PostgreSQL 17, NumPy, pandas, SciPy, ReportLab, structlog, Argon2id,
PyJWT. Tooling: uv, Ruff, mypy (strict), pytest, pip-audit.

**Frontend** (from Phase 8) — React, TypeScript, Vite, Tailwind CSS, TanStack
Query, React Router, Recharts, Vitest, Playwright.

**Infrastructure** — Docker and Docker Compose for local development, GitHub
Actions for CI, Vercel plus managed PostgreSQL for production.

## Quick start

Requirements: [Docker Desktop](https://docs.docker.com/desktop/),
[uv](https://docs.astral.sh/uv/), Python 3.12.

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

### Stopping

```bash
docker compose down            # keep data
docker compose down -v         # also delete the database volume
```

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
- [Contributor and agent guide](CLAUDE.md)

## Still to come

- Frontend: authentication, portfolio management, analytics dashboard, stress
  testing, reports, and the Gjallarhorn signal interface (Phases 8-11)
- Vercel deployment, a scheduled monitoring cron job, and end-to-end tests
  (Phase 12)

## Limitations

Stated plainly, because a risk tool that hides its own limits is not much use.

- **Fixed-weight reconstruction.** Historical portfolio returns apply *today's*
  weights to each asset's past returns. They do not reconstruct what the portfolio
  actually held. Every affected figure says so.
- **Estimates, not forecasts.** VaR at 95% is a loss exceeded 5% of the time in the
  measured window, not a maximum possible loss. Stress tests measure sensitivity to
  stated price changes, not likelihood.
- **One base currency per portfolio**, currently `USD` only. An asset in another
  currency is rejected rather than silently combined.
- **Market data is synthetic.** The committed fixtures are shaped to resemble real
  equity behaviour but are generated, not real. See
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
- Analytics are estimates derived from historical data and stated model
  assumptions.
- Heimdall does not execute trades, make recommendations, or predict returns.

## License

MIT.
