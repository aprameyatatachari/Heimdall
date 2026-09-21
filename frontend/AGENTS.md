# Heimdall Frontend — Functional Specification

How the Heimdall web application works: what every screen does, what it calls,
what it must never do.

**Read first:** `DESIGN.md` for appearance and motion, `../CLAUDE.md` for product
rules. Feature scope follows `../prompt.md` Phases 8–12; **appearance follows
`DESIGN.md`, and where `prompt.md` gives design direction it is ignored.**

---

## 1. Ground rules

These outrank every convenience.

1. **Never invent an endpoint.** The backend surface is fixed and listed in §4.
   If a screen needs data the API does not return, the screen changes — not the
   API, and never a client-side fabrication.
2. **Never return, display or infer a value the backend did not give.** A metric
   that could not be computed arrives `null` with a reason. Render the reason.
   Zero is a number, not an absence.
3. **Never present an estimate as a prediction.** No screen says what will
   happen. No screen recommends buying, selling or holding.
4. **Every figure travels with its context** — unit, period, confidence level,
   whether it is annualized, and the fixed-weight caveat when it applies. The
   backend supplies all of these; pass them through.
5. **Ownership is the server's business.** The client never filters another
   user's data out of a response. A 404 means "not yours or not there" and is
   rendered identically either way.
6. **Errors use the backend envelope.** Parse `code`, show `message`, attach
   `details` to the offending field. Never surface a stack trace or raw body.

---

## 2. Stack

| Concern       | Choice                                                     |
| ------------- | ---------------------------------------------------------- |
| Framework     | React 18 + TypeScript (strict)                             |
| Build         | Vite                                                       |
| Styling       | Tailwind CSS, configured from `DESIGN.md` tokens           |
| Routing       | React Router                                               |
| Server state  | TanStack Query                                             |
| Forms         | React Hook Form + Zod                                      |
| Charts        | Recharts or visx — must support broken lines for data gaps |
| Smooth scroll | Lenis (Outer Realm only)                                   |
| Animation     | GSAP + ScrollTrigger + SplitText (Outer Realm only)        |
| Tests         | Vitest + React Testing Library + MSW                       |
| Quality       | ESLint, Prettier, `tsc --noEmit`                           |

Types are **generated from the live OpenAPI schema** (`/openapi.json`), not
hand-written. Regenerating is part of the build, so a backend contract change
breaks the frontend at compile time rather than in production.

Local state uses React context for the session and URL search params for
everything a user might bookmark or share — selected portfolio, analysis window,
signal filters, chart range. No global store.

---

## 3. Information architecture

### Outer Realm — public

| Route                                | Screen                             |
| ------------------------------------ | ---------------------------------- |
| `/`                                  | Splash gate → landing page         |
| `/product`, `/features`, `/insights` | Marketing                          |
| `/methodology`                       | How the calculations work, plainly |
| `/limitations`                       | What the tool cannot tell you      |
| `/login`                             | Sign in                            |
| `/register`                          | Create account                     |
| `/legal/terms`, `/legal/privacy`     | Legal                              |

### Inner Realm — authenticated

| Route                           | Screen                                      |
| ------------------------------- | ------------------------------------------- |
| `/app`                          | Redirects to `/app/portfolios`              |
| `/app/portfolios`               | Portfolio list                              |
| `/app/portfolios/:id`           | Portfolio detail — overview                 |
| `/app/portfolios/:id/holdings`  | Holdings table, add/edit/delete, CSV import |
| `/app/portfolios/:id/analytics` | Analytics dashboard                         |
| `/app/portfolios/:id/stress`    | Stress testing                              |
| `/app/portfolios/:id/signals`   | Gjallarhorn signals and alert rules         |
| `/app/portfolios/:id/reports`   | Report generation and history               |
| `/app/settings`                 | Account                                     |

Unauthenticated access to `/app/*` redirects to `/login?next=<path>` and returns
there after sign-in. Authenticated access to `/login` or `/register` redirects to
`/app`.

---

## 4. API surface

Every endpoint the backend exposes. Base path `/api/v1`.

**Auth** — `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`,
`POST /auth/logout`, `GET /auth/me`

**Portfolios** — `GET|POST /portfolios`,
`GET|PATCH|DELETE /portfolios/{id}`, `GET /portfolios/{id}/summary`

**Positions** — `GET|POST /portfolios/{id}/positions`,
`PATCH|DELETE /portfolios/{id}/positions/{position_id}`,
`POST /portfolios/{id}/positions/import`

**Assets** — `GET /assets/search`, `GET /assets/{symbol}/prices`

**Market data** — `POST /portfolios/{id}/market-data/refresh`

**Analytics** — `GET|POST /portfolios/{id}/analysis-runs`,
`GET /analysis-runs/{run_id}`

**Stress testing** — `GET /stress-scenarios`,
`GET|POST /portfolios/{id}/stress-tests`, `GET /stress-tests/{run_id}`

**Gjallarhorn** — `GET /alert-rule-types`,
`GET|POST /portfolios/{id}/alert-rules`,
`POST /portfolios/{id}/alert-rules/defaults`,
`GET|PATCH|DELETE /portfolios/{id}/alert-rules/{rule_id}`,
`GET|POST /portfolios/{id}/monitoring-runs`, `GET /monitoring-runs/{run_id}`,
`GET /portfolios/{id}/signals`, `GET /portfolios/{id}/signals/summary`,
`GET /signals`, `GET /signals/{signal_id}`,
`POST /signals/{signal_id}/acknowledge`, `POST /signals/{signal_id}/dismiss`

**Reports** — `GET|POST /portfolios/{id}/reports`, `GET /reports/{report_id}`,
`GET /reports/{report_id}/download`

**Health** — `GET /health`, `GET /ready`

`POST /internal/monitoring/run` is the scheduler's endpoint. It is protected by a
shared secret, carries no portfolio detail, and **the browser never calls it.**

---

## 5. Authentication

The backend issues a short-lived **access token** (JWT, ~15 min) and a rotating
opaque **refresh token** delivered as an HTTP-only cookie scoped to
`/api/v1/auth`.

- The access token lives **in memory only**. Never `localStorage`, never
  `sessionStorage` — both are readable by any injected script.
- The refresh cookie is handled entirely by the browser. Requests to
  `/auth/refresh` and `/auth/logout` send `credentials: "include"`.
- On boot the app calls `POST /auth/refresh` once. Success hydrates the session
  and the user lands where they asked to go; failure means signed out.
- A single 401 interceptor refreshes once and replays the original request.
  Concurrent 401s share one in-flight refresh — they do not each trigger a
  rotation, which would invalidate each other.
- A failed refresh clears the query cache completely and redirects to `/login`.
  Never leave one user's cached data visible to the next.
- `logout` calls the endpoint (so the server revokes the token), then clears
  memory and cache regardless of the response.

**Registration** returns tokens directly — a new user lands in the app, not back
at a login form. Password rules come from the backend's validation error, not a
duplicated client-side list that can drift out of sync.

**Not supported:** Google and Microsoft sign-in. The mockups show these buttons;
there is no OAuth in the backend. Ship without them.

---

## 6. Screens

### 6.1 Splash gate — `/`

Full-viewport portrait plate: star, runic wordmark, `SEE FURTHER`, and
`A CLEARER TOMORROW / THROUGH A WIDER HORIZON` over the cliff-and-citadel vista.
`SLIDE UP TO ENTER` at the base.

Scrolling, swiping or the control dissolves the plate off the landing page,
which sits still behind it (`DESIGN.md` §7.4). Shown **once per session**. A
deep link to any other route never sees it. Under reduced motion, or without
WebGL, the photograph fades on the same progress instead of dissolving.

### 6.2 Landing — `/`

Hero: `See Further. Invest Smarter.` with the sub-line, `Get Started` and
`Watch Demo`, and the four capability marks — Unified Portfolio View, Advanced
Analytics, Stress Testing & Scenario Analysis, Institutional Grade Reports.

Below: how it works, a methodology teaser, the limitations teaser, and the
disclaimer. Every claim on this page must be true of the built product. There is
no demo video yet — supply one or remove the button.

### 6.3 Sign in — `/login`, Register — `/register`

Glass card over the arched-hall image (`DESIGN.md` §5.4). Fields per the
mockups, minus the OAuth buttons.

Errors: invalid credentials produce one message — _"Email or password is
incorrect."_ The client never reveals whether an email is registered. Field-level
validation errors attach to their field from the backend `details`. Rate-limit
responses (`rate_limited`) show the retry window rather than a generic failure.

The submit button enters a pending state and stays disabled until the request
settles, so a double-press cannot create two accounts.

### 6.4 Portfolio list — `/app/portfolios`

`GET /portfolios`. Each row: name, total value, holdings count, day/period
change, sparkline, overflow menu. Search filters client-side within the loaded
page; pagination follows the backend's envelope.

`+ New Portfolio` opens a dialog: name, base currency, optional benchmark symbol
(asset-search backed). Created via `POST /portfolios`, then navigate into it.

Empty state: an invitation to create the first portfolio, not an error.

Delete asks for confirmation naming the portfolio, and says the analysis history
goes with it.

### 6.5 Portfolio detail — `/app/portfolios/:id`

`GET /portfolios/{id}/summary` drives the header: total value, cost basis,
unrealized profit/loss, holdings count, **and the data-as-of date, which is
always visible.**

If market data is stale the header says so plainly — _"Prices last updated
2023-12-29. Refresh to bring this up to date."_ — with the refresh control
adjacent. Stale data is never silently presented as current.

Tabs: Overview, Holdings, Analytics, Stress Test, Signals, Reports. (No
"Transactions" tab — there is no transaction model.)

### 6.6 Holdings — `/app/portfolios/:id/holdings`

Table of positions: symbol, name, asset type, quantity, average cost, current
price, market value, weight, unrealized P/L. Sortable. Unpriced holdings are
shown with `—` and _"No price available"_, **never** zero, and never dropped
from the table.

Add position: symbol via `GET /assets/search` (debounced, keyboard navigable),
quantity and average cost as decimal strings — parsed as decimals, never floats,
never rounded in the client. Edit is inline. Delete confirms.

**CSV import** — `POST /portfolios/{id}/positions/import`:

1. Drop or choose a file. Show the expected columns before upload.
2. The response reports created, merged and skipped counts plus per-row errors.
3. Render errors as a table: **row number, column, offending value, reason.**
   A user must be able to fix the file without guessing.
4. Partial success is normal: report what was imported _and_ what was not, in
   one view. Never discard the good rows because some were bad.
5. Never log or echo the file's full contents.

**Market-data refresh** — `POST /portfolios/{id}/market-data/refresh` with a
start/end window. Shows bars ingested and the new as-of date, and invalidates
summary, analytics and signals queries on success.

### 6.7 Analytics — `/app/portfolios/:id/analytics`

`POST /portfolios/{id}/analysis-runs` creates a run; `GET` lists history;
`GET /analysis-runs/{run_id}` fetches one. The screen shows a **stored run**, so
what a user sees matches what a report would contain.

Controls: analysis window (start/end), benchmark (from the portfolio), risk-free
rate if the backend accepts one. Changing them creates a new run — it does not
silently mutate the old one.

Metrics available from the backend, each in a tile per `DESIGN.md` §6.3:

```
portfolio_value            total_cost_basis          unrealized_profit_loss
holdings_count             total_return              annualized_return
volatility_daily           volatility_annualized     sharpe_ratio
max_drawdown               current_drawdown          value_at_risk_historical
value_at_risk_parametric   expected_shortfall        benchmark_beta
benchmark_correlation      benchmark_annualized_return
benchmark_alpha_annualized tracking_error            information_ratio
average_pairwise_correlation  largest_position_weight  largest_sector_weight
risk_contribution          analysis_observations
```

There is **no Sortino ratio** and no bare "alpha" — the backend computes
`benchmark_alpha_annualized`. Label it as such.

Charts: portfolio value over time, portfolio versus benchmark, drawdown,
allocation by asset and sector, correlation heatmap, risk contribution by
holding. Each with title, labelled axes, units, legend and a **View as table**
toggle.

Run status handling:

- `succeeded` — everything computed.
- `partial` — **show the results that exist and list what failed and why, at the
  top of the screen.** A partial run is not an error page.
- `failed` — the reason, and a retry that preserves the chosen parameters.

Every screen carries the fixed-weight caveat where it applies: portfolio returns
are reconstructed by applying today's weights to historical asset returns, which
is an approximation. The backend returns this as an assumption — surface it, do
not paraphrase it away.

### 6.8 Stress testing — `/app/portfolios/:id/stress`

`GET /stress-scenarios` lists the historical catalogue; `POST
/portfolios/{id}/stress-tests` runs one; `GET` lists history.

**Before running**, the user sees the scenario's period, what it applies, its
data source, and that results are estimates of sensitivity — not forecasts.

Custom scenarios let a user specify shocks by symbol, by sector, and at market
level. **Precedence is explained on screen, not buried:** a symbol shock beats a
sector shock, which beats a market shock. Show the resolved shock that will
actually apply to each holding _before_ the run.

Results: starting value, estimated ending value, total impact in currency and
percent, and a position-level table with each holding's starting value, applied
return, impact and share of loss. Position impacts must visibly reconcile to the
total — the backend returns a reconciliation flag; if it is false, say so.

Holdings excluded for want of price data are **listed explicitly**, with the
reason. They are never silently omitted and never treated as unaffected.

A failed run preserves the user's scenario input. Re-opening the builder shows
exactly what they entered.

### 6.9 Gjallarhorn signals — `/app/portfolios/:id/signals`

The Early Warning System. This is the only place the Gjallarhorn name and the
horn mark appear.

**Summary panel** — `GET /portfolios/{id}/signals/summary`: open-signal counts by
severity, each with icon and word.

**Signal list** — `GET /portfolios/{id}/signals`, filterable by severity, status,
type and date. Each row: severity indicator, title, the plain-language
explanation, observed value versus threshold, metric name, unit, analysis period,
data-as-of.

**Signal detail** — `GET /signals/{id}`: everything above, plus context
(affected asset, sector or scenario), limitations, the suggested analytical step,
and the append-only event trail showing every severity and status change.

Observed value and threshold are **visually distinguishable** — never two
similar numbers side by side with no label.

Actions:

- **Acknowledge** — `POST /signals/{id}/acknowledge`. "I have seen this." The
  signal stays open.
- **Dismiss** — `POST /signals/{id}/dismiss`. Confirmed, and reversible only by
  the condition recurring.
- **Resolve is not a user action.** A signal resolves when the condition stops
  being true. The UI offers no control to mark an active condition resolved.

**Alert rules** — the nine rule types from `GET /alert-rule-types`:

```
position_concentration   sector_concentration   volatility_increase
portfolio_drawdown       var_threshold          correlation_increase
stress_loss              stale_market_data      missing_data
```

Each rule: enable/disable, thresholds per severity, cooldown hours. The form
validates that thresholds increase with severity and stay in range, client-side
for immediate feedback and server-side as the authority. `Restore defaults` calls
`POST /alert-rules/defaults`.

Cooldown governs **notification only** — make that explicit in the field's helper
text. A muted rule still records the current risk state.

**Manual monitoring run** — `POST /portfolios/{id}/monitoring-runs`. The button
disables while in flight so a run cannot be submitted twice. Results show rules
evaluated, rules failed, and signals created/updated/resolved. A `partial` run
lists which rules failed **without hiding the signals the others produced**.

Copy discipline: branded term beside the plain one, always.

> **Gjallarhorn Signal — High position concentration**
> AAPL represents 34.2% of this portfolio, exceeding your 30% high-severity
> threshold.

No sound. No flashing. No colour-only severity. Nothing framed as a prediction.

### 6.10 Reports — `/app/portfolios/:id/reports`

`POST /portfolios/{id}/reports` generates; `GET` lists; `GET /reports/{id}`
polls one; `GET /reports/{id}/download` returns the PDF.

Options: title, analysis run (latest or a specific one), include stress tests,
include signals. **PDF is the only format** — there is no Excel export. There is
no report scheduling.

States: pending, succeeded (download available), failed (reason, retry). Download
uses the authenticated client and streams to a blob — the URL is not a public
link and must not be shared as one. A report belonging to another user 404s, and
that is rendered as "not found", never as "forbidden".

### 6.11 Methodology and limitations — `/methodology`, `/limitations`

Public, plain-language explanations: how returns, volatility, VaR, Expected
Shortfall, drawdown, beta and risk attribution are computed; what the fixed-weight
reconstruction assumes; what historical simulation can and cannot tell you.

Linked from every metric tooltip and every signal detail. This is where the
product earns the word _transparent_.

---

## 7. Data handling

### 7.1 Money

Decimal strings from the API stay strings until formatted. **Never parse a
monetary value into a JavaScript number** — `0.1 + 0.2` is the reason. Use a
decimal library for any arithmetic, and prefer asking the backend.

Format with `Intl.NumberFormat` using the portfolio's `base_currency`. Never
hardcode a symbol. Tabular figures everywhere.

### 7.2 Missing data

The single most important display rule in the product.

| Backend gives                | Screen shows                                         |
| ---------------------------- | ---------------------------------------------------- |
| `value: null, reason: "..."` | `—  unavailable` plus the reason                     |
| Empty series                 | "No data for this period", not an empty axis         |
| `status: "partial"`          | Results **and** a list of what failed                |
| Unpriced holding             | `—  No price available`, row still visible           |
| Stale data                   | The as-of date and how stale, with a refresh control |

Never `0`. Never `N/A` with no explanation. Never an omitted row.

### 7.3 Caching

TanStack Query, 30s stale time for lists, 5 min for analysis runs (immutable once
complete). A mutation invalidates every query it could affect — importing
positions invalidates positions, summary, analytics and signals.

Analysis runs, stress runs and reports are immutable once they succeed; cache
them indefinitely and never refetch on focus.

### 7.4 Errors

The backend envelope:

```json
{ "error": { "code": "validation_error", "message": "...", "details": [...] } }
```

| Code                            | Handling                                             |
| ------------------------------- | ---------------------------------------------------- |
| `validation_error`              | Attach `details` to the fields; keep the form filled |
| `permission_denied` / not found | "Not found" — identical either way                   |
| `rate_limited`                  | Show the retry window; disable submit until then     |
| `payload_too_large`             | State the size limit and the file's size             |
| `scenario_data_unavailable`     | Explain which data is missing                        |
| `invalid_rule_configuration`    | Attach to the rule form field                        |
| `internal_error`                | Generic apology plus a retry. Never internal detail  |

Network failure is distinguished from server failure — "Could not reach Heimdall"
is different information from "Heimdall could not complete this."

---

## 8. Quality bar

**Testing.** Every screen: renders loading, error, empty and populated states.
Every form: validation and submission. Every flow in §6 as an integration test
against MSW handlers **generated from the real OpenAPI schema**, so a fixture
cannot drift from the contract. Critical paths for keyboard-only operation.

**Performance.** Route-level code splitting. GSAP and Lenis load only in the
Outer Realm. Hero images served as AVIF/WebP with explicit dimensions to prevent
layout shift. Lighthouse ≥ 90 on performance and 100 on accessibility.

**Never in the client:** secrets, API keys, the access token in storage, another
user's data, financial advice, a prediction.

**CI.** `tsc --noEmit`, ESLint, Prettier check, Vitest, production build — all in
the same workflow as the backend, all green before a phase is complete.

---

## 9. Phase order

One phase at a time. Stop at the end of each for review. Do not start the next
automatically.

| Phase  | Scope                                                                                                                                                                         |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **8**  | Foundation: Vite, Tailwind from `DESIGN.md`, routing, API client, generated types, TanStack Query, auth state, login, register, protected routes, shell, error boundaries, CI |
| **9**  | Portfolios: list, create, edit, detail, holdings, positions CRUD, asset search, CSV import with row errors, market-data refresh, all empty/partial/stale states               |
| **10** | Analytics: metric tiles, every chart, table alternatives, parameter controls, assumptions, definitions                                                                        |
| **11** | Stress testing, reports, and the full Gjallarhorn experience                                                                                                                  |
| **12** | Vercel deployment, SPA fallback, final accessibility and performance pass                                                                                                     |

Phase 8 may not build analytics screens. Phase 9 may not build charts. The
discipline is the point.

---

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
