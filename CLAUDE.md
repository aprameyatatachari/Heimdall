# CLAUDE.md

Guidance for contributors and AI agents working in this repository.

## What this is

Heimdall — a portfolio risk-intelligence platform. A **modular monolith**:
one FastAPI backend split by business capability, plus a React SPA (from Phase 8).
No microservices.

The application is educational. It must never execute trades, recommend buying,
selling, or holding, or claim to predict future returns.

## Commands

All backend commands run from `backend/`.

```bash
uv sync --all-extras           # install dependencies
uv run uvicorn app.main:app --reload
uv run ruff format .           # format
uv run ruff check . --fix      # lint
uv run mypy app                # type check (strict)
uv run pytest                  # unit tests (no database needed)
uv run alembic upgrade head    # apply migrations
uv run alembic revision --autogenerate -m "description"
```

Integration tests require PostgreSQL and `RUN_INTEGRATION_TESTS=1`:

```bash
docker compose up -d db        # from the repository root
RUN_INTEGRATION_TESTS=1 uv run pytest -m integration
```

## Layout

```text
backend/app/
  main.py          application factory; also the ASGI entrypoint
  config.py        pydantic-settings; every value comes from the environment
  database.py      async engine, session dependency, declarative Base
  common/          logging, middleware, errors, clock, rate limiting, headers
  health/          /health and /ready
  auth/            users, sessions, password hashing
  assets/          instrument reference data, symbol normalization
  portfolios/      portfolios, positions, CSV import
  market_data/     provider interface, fixture provider, ingestion, calendar
  analytics/       pure calculations, snapshots, analysis runs
  stress_testing/  scenario catalogue, shock engine
  early_warning/   rule engine, evaluators, signal lifecycle
  reports/         PDF rendering and report storage
```

Every capability package holds its own `router.py`, `service.py`, `repository.py`,
`models.py`, `schemas.py`, and `dependencies.py`. All backend capabilities are
implemented; the frontend begins at Phase 8.

## Rules

**Layering.** Routes validate, authorize, call a service, and return a schema.
Services own use cases and transactions. Repositories own queries. Financial
calculations are pure functions with no HTTP, database, or clock dependency.

**Never return ORM entities from a route.** Responses are Pydantic schemas.

**Money and quantities** use PostgreSQL `NUMERIC` and Python `Decimal`. Never
`float` for a stored monetary value.

**External vendors** sit behind an internal provider interface. Vendor response
shapes must not leak into the domain or the API.

**Errors** use the envelope in `app/common/errors.py`. Raise an `AppError`
subclass; never build an ad-hoc error dict. Internal details never reach the
client.

**Migrations never run at startup or during a request.** They are a controlled
release step.

**One transaction per request.** `get_db_session` commits on success and rolls
back on failure. Services only `flush()`; never call `commit()` in a service.

**Ownership is a query predicate.** Scope every private read by `user_id` in the
`WHERE` clause. Return the same 404 for "not yours" and "does not exist".

**Missing data is never zero.** A metric that cannot be computed is returned with a
null value and a reason, and its run's status becomes `partial`. Never substitute a
zero, an empty list, or a sentinel for an unknown value.

**Time comes from the injected clock.** Use `ClockDep` or a passed `Clock`, never
`datetime.now()` in a service or an evaluator, so time-dependent behaviour stays
testable.

**Avoid lazy loads in async code.** Async SQLAlchemy cannot lazily refresh an
attribute. Use `selectinload`, set `eager_defaults`, or add rows to the session
directly rather than appending to an unloaded relationship.

**State every assumption in the response.** Units, analysis periods, confidence
levels, whether a figure is annualized, and the fixed-weight caveat all travel with
the number they describe.

**Tests must be hermetic.** No test may depend on a live third-party API or on
network availability. Market data used in tests lives in `fixtures/`.

**Never log** passwords, tokens, authorization headers, complete uploaded files,
or any secret. `app/common/logging.py` redacts known keys; do not rely on it
alone.

**Never commit** secrets, API keys, or real financial data.

## Phase discipline

The project is built in numbered phases. Work on exactly one phase at a time,
run every check at the end of a phase, and stop for review. Do not implement
speculative features or start the next phase automatically.

The frontend does not exist before Phase 8. Do not create frontend code,
decorative assets, or logos during backend phases.

## Branding

- **Heimdall** is the product. It appears in the app name, header, logo,
  favicon, page titles, reports, and documentation.
- **Gjallarhorn** names only the Early Warning System. It never brands general
  analytics, portfolios, stress tests, reports, or authentication.
- The logo is the supplied artwork in `frontend/resources/logos/`: a horn
  fused with an open eye, above a runic wordmark. Three variants ship — mark,
  wordmark, and the lockup of both.
- **Spelling follows the alphabet.** In runes it is **HEIMDALLR**, the Old
  Norse form, which is what the wordmark artwork spells. In Latin letters it
  is **Heimdall** — page titles, prose, reports, documentation, and the `alt`
  text on the runic wordmark, which is Latin text standing in for the image
  and so takes the Latin spelling. Never write "Heimdallr" in Latin letters.
- Backend domain terms stay technical: `AlertRule`, `WarningSignal`,
  `MonitoringRun`, `SignalStatus`, `SignalSeverity`. Never rename a technical
  concept after mythology.
- A condition becomes a Gjallarhorn Signal only when an enabled EWS rule
  produces it. Form errors, auth failures, and system errors are not signals.
- Signal copy is calm, factual, and specific: describe an observed condition,
  never predict an event.

## Voice

Calm, precise, analytical, transparent about uncertainty. Prefer
"estimated portfolio loss", "based on the selected period", "historical
simulation". Avoid "guaranteed", "safe investment", "beat the market",
"AI prediction", "risk-free".

## Disclaimer

Include in the application, documentation, and generated reports:

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
