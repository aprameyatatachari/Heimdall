# Gjallarhorn Early Warning System

> Gjallarhorn is Heimdall's Early Warning System. It continuously evaluates
> portfolio conditions and raises explainable signals when configured risk
> thresholds are crossed.

> **Gjallarhorn Signals identify predefined conditions in portfolio data. They are
> not predictions, guarantees, or recommendations to buy, sell, or hold an
> investment.**

## What it does, and what it cannot do

It **does**:

- Evaluate a portfolio against rules you configure.
- Raise a signal when a rule's condition is observed, with the metric, the
  threshold, the unit, the period, and the data-as-of date recorded.
- Explain every signal in plain language.
- Update a signal while its condition persists, resolve it when the condition is
  no longer observed, and create a fresh occurrence if it returns.
- Keep an append-only audit trail of every state change.

It **cannot**:

- Predict a market fall, a crash, or a recovery.
- Tell you whether an investment is safe, unsafe, cheap, or expensive.
- Recommend buying, selling, holding, or rebalancing.
- Guarantee that a signal will appear before a loss, or that no signal means no risk.

A signal is a statement about **data that already exists**, nothing more.

## Terminology

| Term | Meaning |
| --- | --- |
| Gjallarhorn Early Warning System | The whole monitoring capability |
| Gjallarhorn Signal | One detected condition that needs attention |
| Alert rule | The configuration that decides when a signal fires |
| Monitoring run | One evaluation of a portfolio against its enabled rules |
| Acknowledged | The user has seen the signal. The condition is still present |
| Resolved | The triggering condition is no longer observed |
| Dismissed | The user hid the signal without changing its condition |

Backend code uses technical names only: `AlertRule`, `MonitoringRun`,
`WarningSignal`, `SignalEvent`, `SignalStatus`, `SignalSeverity`.

**Not signals:** form validation errors, authentication failures, system errors,
and raw stress-test results. A condition becomes a signal only when an *enabled
EWS rule* produces it and it is stored through the lifecycle below.

## The rules

Nine rule types. Each has its own validated parameter schema; unknown fields and
out-of-range values are rejected when the rule is saved, not when it runs.

### Position concentration

```text
observed = position market value / total portfolio value
```

| Severity | Default |
| --- | --- |
| Elevated | 20% |
| High | 30% |
| Critical | 40% |

One signal per over-weight holding, each with its own fingerprint.

### Sector concentration

```text
observed = sum of one sector's market value / total portfolio value
```

| Severity | Default |
| --- | --- |
| Elevated | 30% |
| High | 40% |
| Critical | 50% |

**Refuses to run** when more than `max_unknown_sector_weight` (default 20%) of
portfolio value has no sector information. Presenting partial sector data as
complete exposure would be misleading, so the rule reports a data-quality reason
instead. The `Unknown` bucket never triggers a concentration signal itself.

### Volatility increase

```text
recent   = annualized volatility over recent_window_days     (default 20)
baseline = annualized volatility over baseline_window_days   (default 252)
observed = recent / baseline
```

| Severity | Default | Meaning |
| --- | --- | --- |
| Elevated | 1.25 | recent is at least 25% above baseline |
| High | 1.50 | at least 50% above |
| Critical | 2.00 | at least double |

Requires a **complete** baseline window. An incomplete window is reported as
not-evaluated; it is never silently substituted with a shorter one.

### Portfolio drawdown

```text
observed = |current value / running peak - 1|
```

| Severity | Default |
| --- | --- |
| Elevated | 5% |
| High | 10% |
| Critical | 20% |

Reported as a positive magnitude so it compares against positive thresholds. The
signal context carries the peak date, the peak value, the current value, and the
worst drawdown seen in the window.

### Value at Risk threshold

```text
observed = one-day historical VaR at `confidence` (default 0.95)
```

Expressed either as a share of portfolio value (`basis: percent_of_value`,
the default) or as a currency amount (`basis: currency`).

| Severity | Default (percent basis) |
| --- | --- |
| Elevated | 2% |
| High | 3% |
| Critical | 5% |

The confidence level and lookback window used are stored on every signal.

### Correlation increase

```text
observed = mean of the off-diagonal entries of the correlation matrix
```

| Severity | Default |
| --- | --- |
| Elevated | 0.65 |
| High | 0.75 |
| Critical | 0.85 |

The diagonal is excluded — it is always 1 and would bias the average upward.
A portfolio with fewer than two holdings that have overlapping history reports
not-evaluated rather than a fabricated number.

### Stress-test loss

Runs the configured stored scenarios and measures the estimated loss.

```text
observed = |estimated portfolio loss| / portfolio value
```

| Severity | Default |
| --- | --- |
| Elevated | 10% |
| High | 15% |
| Critical | 25% |

The signal names the scenario that triggered it. A scenario with no stored data
is reported; it does not fail the rule if another scenario could be evaluated.

**A stress-test result is not automatically a signal.** It becomes one only when
this rule is enabled and its threshold is crossed.

### Stale market data

```text
observed = expected trading days between the newest stored price and today
```

| Severity | Default |
| --- | --- |
| Elevated | more than 1 expected trading day |
| High | more than 2 |
| Critical | more than 5 |

**Weekends never count.** Staleness is measured in expected trading days under
Heimdall's documented calendar convention (Monday–Friday; exchange holidays are
not modelled). A Friday close read on the following Monday is **one** trading day
old, so the default `high` threshold of 2 does not fire over a normal weekend.

A holding with no stored price at all is not a staleness condition — that belongs
to the missing-data rule.

### Missing data

Reports three distinct conditions, each with its own fingerprint:

| Condition | What it means |
| --- | --- |
| `unpriced_holdings` | Holdings with no stored price. Excluded from value, weights, volatility, VaR, and every stress test |
| `missing_sector_metadata` | Holdings with no sector. Sector exposure is incomplete; the sector rule may refuse to run. Capped at `high` severity |
| `insufficient_history` | Fewer than `minimum_observations` (default 30) overlapping daily observations, so tail measures are unavailable |

Each signal names the calculations it affects.

## Severity

```text
Informational  Glacier Blue  #38BDF8
Elevated       Brand Gold    #D6A84B
High           Amber         #F59E0B
Critical       Muted Red     #DC5A5A
```

**Severity is never communicated by colour alone.** Every signal response carries
a severity label, a `severity_icon` name, a concise title, a plain-language
explanation, the observed metric, the triggering threshold, the unit, the analysis
period, the data-as-of date, the affected asset/sector/scenario, and an
informational next step.

A condition produces **only its highest applicable severity** — never one signal
per crossed threshold. Thresholds are validated to increase with severity; a
configuration where `high` is below `elevated` is rejected.

## Lifecycle

```text
new condition       -> active
active viewed       -> acknowledged
condition persists  -> stays active or acknowledged; values are updated
condition clears    -> resolved
condition returns   -> a NEW active occurrence
user hides signal   -> dismissed
severity increases  -> the existing occurrence is updated
```

Rules that hold without exception:

- **Acknowledgement is not resolution.** Acknowledging records that you have seen
  the signal; the condition is still there.
- **A user cannot resolve a signal.** There is no endpoint for it. Only the rule
  engine resolves a signal, and only when it observes that the condition is gone.
- **A rule that could not be evaluated resolves nothing.** Not being able to check
  a condition is not evidence that it cleared.
- **Nothing is deleted.** Resolved and dismissed signals are preserved and stay
  queryable, so history remains auditable.
- **Dismissing is not silencing.** If the same condition is observed again, a new
  occurrence is created.

Every transition is written to `signal_events`, an append-only audit table that is
never updated or deleted.

## Deduplication

Each condition has a **fingerprint**: a SHA-256 digest of

```text
portfolio id | alert rule id | signal type | affected subject
```

The subject is a symbol, a sector, a scenario key, or the literal `portfolio` for
portfolio-wide conditions.

It deliberately excludes timestamps, observed values, severities, and thresholds.
Including any of those would give the same condition a new fingerprint on every
run — which is exactly the duplicate-signal problem this prevents.

A **partial unique index** enforces the guarantee in the database:

```sql
CREATE UNIQUE INDEX uq_warning_signals_open_fingerprint
  ON warning_signals (portfolio_id, fingerprint)
  WHERE resolved_at IS NULL AND dismissed_at IS NULL;
```

So at most one *open* occurrence of a condition can exist, even if two monitoring
runs overlap. Resolved and dismissed rows are excluded from the index, which is
what allows a later reoccurrence.

**Reoccurrence policy (chosen and documented):** a condition that reappears after
being resolved creates a **new occurrence** rather than reopening the old row.
Signal history stays clear — you can see that the condition happened twice, with
the dates of each.

## Cooldowns

**Cooldowns govern notification delivery, not whether current state is recorded.**

During a cooldown Heimdall still:

- updates the signal's observed value and `last_triggered_at`,
- updates its severity if it changed,
- refrains from creating a duplicate.

It only suppresses the outbound notification. A **severity increase bypasses the
cooldown**, because a condition getting worse is new information.

External delivery (email, SMS, push, Slack) is **not implemented**. What exists is
the `Notifier` interface it will sit behind, plus `NullNotifier`, which records
that a delivery would have happened. That is enough for cooldown accounting to be
correct and tested now.

## Default rules

**The documented policy: defaults are provisioned explicitly, not automatically.**

```text
POST /api/v1/portfolios/{portfolio_id}/alert-rules/defaults
POST /api/v1/portfolios/{portfolio_id}/alert-rules/defaults?restore=true
```

Why explicit: a portfolio is usually created empty and filled by a CSV import
minutes later. Rules provisioned at creation time would evaluate an empty
portfolio, and a "missing market data" signal on a portfolio you are still filling
in is noise, not a warning. The same endpoint also restores defaults later, which
is a requirement in its own right.

The operation is **idempotent**. Without `restore`, existing rules are left exactly
as they are and only missing types are added. With `restore=true`, every rule is
reset to its documented defaults. A unique constraint on
`(portfolio_id, rule_type)` enforces one rule per type.

Users can list rules, enable or disable them, change thresholds and parameters,
restore defaults, and trigger a manual evaluation.

## Data requirements

| Rule | Needs |
| --- | --- |
| Position concentration | Current prices for the holdings |
| Sector concentration | Current prices, and sector metadata for at least 80% of value |
| Volatility increase | A complete baseline window of returns (252 by default) |
| Portfolio drawdown | At least 20 return observations |
| VaR threshold | At least 30 return observations |
| Correlation increase | Two or more holdings with overlapping history |
| Stress-test loss | Stored prices covering each scenario's date range |
| Stale market data | At least one stored price per holding |
| Missing data | Nothing; it reports the absence itself |

## Scheduling

```text
POST /api/v1/internal/monitoring/run
X-Cron-Secret: <secret>          (or: Authorization: Bearer <secret>)
```

```text
scheduler
  -> protected monitoring endpoint
  -> identify eligible portfolios (those with an enabled rule)
  -> evaluate enabled rules
  -> create, update, or resolve signals
  -> record the monitoring result
```

Properties, each one deliberate:

- **Authenticated.** Requires `CRON_SECRET`, compared in constant time. With no
  secret configured the endpoint returns `503` rather than running unprotected.
- **Idempotent** for one UTC day. A retry for the same portfolio and period returns
  the stored run instead of evaluating again.
- **Bounded.** `batch_size` (default `MONITORING_BATCH_SIZE`, 25) caps the work per
  invocation so it fits inside a serverless function's duration.
- **Resumable.** The response carries `next_cursor`; pass it back as `cursor` to
  continue. There is no unbounded loop over every portfolio.
- **Non-overlapping.** A portfolio already being evaluated is skipped, enforced by
  a unique constraint rather than only in application code.
- **Retry-safe.** A portfolio that fails is recorded and the batch continues.
- **Discreet.** The response contains operational counts only — never portfolio
  names, holdings, or signal content. The scheduler is not a user.

To disable scheduled monitoring safely: remove the cron entry from the deployment
configuration, or unset `CRON_SECRET`, which makes the endpoint refuse every call.
Disabling individual rules also stops them being evaluated.

## Partial failure

A monitoring run has three possible outcomes beyond success:

| Status | Meaning |
| --- | --- |
| `succeeded` | Every enabled rule was evaluated |
| `partial` | At least one rule raised an error. Results from the others are complete and valid |
| `skipped` | The portfolio has no enabled rules |

A failing rule is recorded in `rule_results` with its error, and **never** hides
the signals other rules produced. A rule whose status is `skipped` or `failed` is
excluded from resolution, so its open signals are left alone.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/alert-rule-types` | Rule catalogue with units and documented defaults |
| GET | `/api/v1/portfolios/{id}/alert-rules` | List rules |
| POST | `/api/v1/portfolios/{id}/alert-rules` | Create a rule |
| GET | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Get a rule |
| PATCH | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Update, enable, or disable a rule |
| DELETE | `/api/v1/portfolios/{id}/alert-rules/{rule_id}` | Delete a rule and its history |
| POST | `/api/v1/portfolios/{id}/alert-rules/defaults` | Provision or restore defaults |
| POST | `/api/v1/portfolios/{id}/monitoring-runs` | Run monitoring now |
| GET | `/api/v1/portfolios/{id}/monitoring-runs` | Monitoring history |
| GET | `/api/v1/monitoring-runs/{run_id}` | One run, with per-rule outcome |
| GET | `/api/v1/portfolios/{id}/signals` | A portfolio's signals, filtered |
| GET | `/api/v1/portfolios/{id}/signals/summary` | Open counts by severity |
| GET | `/api/v1/signals` | Signals across the caller's portfolios |
| GET | `/api/v1/signals/{signal_id}` | One signal with its audit trail |
| POST | `/api/v1/signals/{signal_id}/acknowledge` | Mark as seen |
| POST | `/api/v1/signals/{signal_id}/dismiss` | Hide without resolving |
| POST | `/api/v1/internal/monitoring/run` | Scheduled monitoring (protected) |

Signal listings support filters for status, severity, signal type, creation date
range, acknowledgement state, and portfolio, with pagination and ordering by
`created_at DESC, id DESC` so paging is stable.

## Writing style

Signal copy is calm, factual, and specific. It describes an **observed condition**.

Good:

```text
High concentration
Technology holdings represent 46.8% of portfolio value, exceeding your
configured 40% high-severity threshold.
```

```text
Stale market data
AAPL has not received a new closing price for 3 expected trading days; its
newest stored price is from 2024-03-13. Current risk estimates for this
holding may be incomplete.
```

Never:

```text
Danger is coming.  |  The market will crash.  |  Your portfolio is unsafe.
Sell your technology holdings.  |  Heimdall has predicted a loss.
```

Suggested actions are analytical: *Review position concentration*, *Inspect the
stress-test breakdown*, *Refresh market data*, *Compare recent volatility with the
historical baseline*. Never buy, sell, hold, or rebalance.

"Gjallarhorn" is never a verb. Use *Run monitoring*, *Evaluate portfolio*,
*Acknowledge signal*, *Dismiss signal*, *Edit rule*, *Restore defaults*.

## Known limitations

- **No external notification delivery.** The interface exists; no channel is
  implemented. Cooldown accounting is correct and tested, but nothing is sent.
- **No missed-signal guarantee.** Signals are produced only when a monitoring run
  executes. Between runs, a condition can appear and disappear unobserved.
- **Rules are deterministic thresholds**, not statistical models. There is no
  anomaly detection and no learning.
- **One base currency per portfolio.** Multi-currency portfolios are not evaluated.
- **The trading calendar is weekdays only.** An exchange holiday looks like one
  missing trading day, which is why staleness thresholds have a one-day tolerance.
- **Fixed-weight reconstruction.** Volatility, drawdown, VaR, and correlation rules
  use today's weights applied to historical asset returns. They do not reconstruct
  what the portfolio actually held.
- **Stress-loss rules depend on stored history** covering each scenario's window.
  Without it, the rule reports not-evaluated rather than a zero loss.
- **No per-rule schedule.** Every enabled rule is evaluated on every run.

## A signal is not financial advice

A Gjallarhorn Signal says: *this measurable condition currently holds in your
stored portfolio data, and it crosses a threshold you configured.*

It does not say what will happen next, what anything is worth, or what you should
do. Thresholds are your choices, not Heimdall's recommendations, and crossing one
is information to look into — not an instruction.

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
