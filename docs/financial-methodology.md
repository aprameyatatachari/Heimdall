# Financial methodology

Every convention Heimdall uses, with its formula, its assumptions, and its
limitations. Implemented in `backend/app/analytics/calculations.py` as pure
functions, and validated against an independent implementation in
`backend/tests/test_golden_portfolio.py`.

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.

## Conventions

| Convention | Value | Note |
| --- | --- | --- |
| Price series | **Adjusted closing prices** | Used for every return calculation |
| Return type | **Simple** (arithmetic) | Not log returns |
| Trading periods per year | **252** | Configurable; 52 weekly, 12 monthly |
| Storage | PostgreSQL `NUMERIC`, Python `Decimal` | Never binary floating point for a stored amount |
| VaR and Expected Shortfall | Reported as a **positive loss amount** | Documented sign convention |
| Risk-free rate | De-annualized **geometrically** | Never divided by 252 |
| Currency | One base currency per portfolio | No conversion; mixing is rejected |
| Missing data | Reported as unavailable | Never substituted with zero |

## Returns

### Asset return

```text
r(i,t) = adjusted_price(i,t) / adjusted_price(i,t-1) - 1
```

Requires two positive prices. A zero or negative price makes the return undefined,
so it is rejected rather than producing a large number.

### Position and portfolio value

```text
value(i)        = quantity(i) x current_price(i)
portfolio_value = sum of position values
weight(i)       = value(i) / portfolio_value
```

There is no cash balance in the model. A holding with no stored price is excluded
from the total and from the weights, and listed separately.

### Portfolio return

```text
portfolio_return(t) = sum over i of weight(i) x asset_return(i,t)
```

> **Fixed-weight assumption.** Heimdall applies **today's** weights to each asset's
> historical returns. This does **not** reconstruct what the portfolio actually held
> over the period. It answers "how would my current allocation have behaved?", not
> "how did my portfolio perform?".

This assumption is surfaced in three places, so it cannot be missed: in every
analysis run's `notes`, in the `assumption` field of each affected metric, and in
generated reports.

Weights are renormalized across the holdings that have both a current price and
price history, so they sum to one. A run that excludes holdings says so in its
notes.

### Alignment

Only dates present in **every** series are used, so a return is never computed
across a gap in one asset while another moved. Excluded dates are counted and
reported; a large number means the analysis covers less history than requested.

### Total and annualized return

```text
total_return = product of (1 + r) - 1
annualized   = (1 + total_return) ^ (periods_per_year / periods) - 1
```

Geometric, so it compounds correctly. A return of -100% or worse makes compounding
undefined and is rejected.

## Volatility

```text
annualized_volatility = stdev(returns) x sqrt(periods_per_year)
```

The **sample** standard deviation (`ddof=1`), because the observations are a sample
of a process rather than a whole population.

Daily and annualized values are reported as **separate metrics**
(`volatility_daily`, `volatility_annualized`), each carrying an explicit
`annualized` flag, so the two can never be confused.

Minimum 20 observations. Square-root-of-time scaling assumes returns are
independent across periods; real returns show some autocorrelation, so a scaled
figure is an approximation.

## Sharpe ratio

```text
periodic_rate = (1 + annual_rate) ^ (1 / periods_per_year) - 1
excess(t)     = return(t) - periodic_rate
Sharpe        = mean(excess) / stdev(excess) x sqrt(periods_per_year)
```

**The risk-free rate is de-annualized geometrically.** Subtracting an annual 4.5%
directly from a daily return would overstate the drag by roughly 250x. The unit
test `test_a_rate_is_deannualized_geometrically_not_by_division` pins this.

When excess returns have no variability the ratio is **undefined** and reported as
unavailable. A large sentinel would read as an excellent result.

## Drawdown

```text
drawdown(t)      = value(t) / running_peak(t) - 1
maximum_drawdown = min(drawdown series)
```

Every value is zero or negative. The response carries the peak date, the peak
value, the trough value, and the current drawdown.

The value path is reconstructed from the fixed-weight return series, so the same
caveat applies.

## Value at Risk

Both estimates are always computed. `var_method` selects which one the interface
highlights.

### Historical simulation

```text
VaR(c) = -quantile(returns, 1 - c) x portfolio_value
```

The empirical quantile of the observed distribution, with linear interpolation.
Makes no distributional assumption, but cannot produce a loss larger than the worst
day in the window.

### Parametric (variance-covariance)

```text
VaR(c) = -(mean + z(1-c) x stdev) x portfolio_value
```

Assumes normally distributed returns. Real return distributions have fatter tails,
so this usually **understates** extreme losses. Every parametric result carries that
limitation in its metadata.

### Sign convention and interpretation

Both are reported as a **positive loss amount**. A profitable tail can make the raw
quantile positive; the result is then floored at zero, because a negative "loss" is
not meaningful.

> VaR at 95% confidence is an estimate of a loss that is **exceeded 5% of the
> time** over one period. It is **not** a maximum possible loss.

That sentence, or an equivalent, appears on every VaR metric's assumptions.

Minimum 30 observations by default, configurable per run.

## Expected Shortfall

```text
threshold = quantile(returns, 1 - c)
ES(c)     = -mean(returns <= threshold) x portfolio_value
```

The average loss **given** that the VaR threshold is breached, so it is always at
least as large as the historical VaR at the same confidence. Also called
conditional VaR. It says more about the shape of the tail than VaR does, because it
averages the tail instead of reading one point from it.

## Covariance and correlation

```text
covariance         = sample covariance matrix (ddof=1)
annualized         = covariance x periods_per_year
correlation(i,j)   = covariance(i,j) / (stdev(i) x stdev(j))
```

An asset with zero variance has no correlation with anything; its row and column
are `null` in the response so the interface can say so rather than showing a fake
zero.

### Average pairwise correlation

The mean of the **off-diagonal** entries. The diagonal is excluded — it is always 1
and would bias the average upward. Undefined entries are skipped. A portfolio with
fewer than two eligible assets reports unavailable.

## Portfolio volatility from covariance

```text
portfolio_volatility = sqrt(w' x covariance x w)
```

Computed two ways that must agree: from the portfolio return series, and from the
weights and covariance matrix. The golden-portfolio test asserts they match to
within 1e-9.

## Risk attribution

```text
MRC(i) = (covariance x w)(i) / portfolio_volatility      marginal
CRC(i) = w(i) x MRC(i)                                   component
share  = CRC(i) / portfolio_volatility
```

By Euler's theorem for homogeneous functions, the component contributions sum
**exactly** to the portfolio volatility. Every analysis verifies this numerically
and reports `reconciles_to_portfolio_volatility` with the measured discrepancy.

A **negatively correlated holding gets a negative component contribution**: it
genuinely lowers portfolio volatility. Clamping contributions to be positive would
hide real diversification and break the reconciliation. The golden portfolio
includes such a pair on purpose.

## Benchmark comparison

```text
beta              = cov(portfolio, benchmark) / var(benchmark)
alpha (annual)    = (portfolio_excess - beta x benchmark_excess) x periods_per_year
tracking_error    = stdev(portfolio - benchmark) x sqrt(periods_per_year)
active_return     = mean(portfolio - benchmark) x periods_per_year
information_ratio = active_return / tracking_error
correlation       = cov(p,b) / (stdev(p) x stdev(b))
```

Alpha is Jensen's alpha: return beyond what beta alone would predict. A benchmark
with no variability over the window makes beta undefined, and it is reported as
unavailable. A zero tracking error makes the information ratio undefined.

The benchmark's price history is fetched if it is not already cached, so a
comparison does not silently require a separate refresh.

## Stress testing

See [stress-testing.md](./stress-testing.md) for the full treatment.

```text
historical:    applied_return(i) = price(i, window_end) / price(i, window_start) - 1
hypothetical:  applied_return(i) = the shock targeting i, by precedence
impact(i)      = value(i) x applied_return(i)
```

Precedence, strict: a **symbol** shock overrides a **sector** shock, which overrides
a **portfolio-wide** shock.

## Early warning rules

See [early-warning.md](./early-warning.md) for every rule's formula and defaults.

## Edge cases

Handled explicitly, never with a zero:

| Case | Behaviour |
| --- | --- |
| Empty portfolio | `422 portfolio_empty` |
| No stored prices | `422 no_market_data` |
| Zero portfolio value | `422 portfolio_zero_value` |
| Fewer observations than a metric needs | That metric is `null` with a reason; the run is `partial` |
| Zero volatility | Sharpe ratio and parametric VaR unavailable |
| Zero-variance asset | Its correlations are `null` |
| Single-asset portfolio | Correlation unavailable; concentration is 100% |
| Non-overlapping dates | Only common dates used; excluded count reported |
| Unpriced holding | Excluded from value, weights, and every risk measure; listed by symbol |
| Missing prices in a scenario window | Holding excluded from the stress test and listed |
| Non-finite or non-positive price | Rejected at ingestion with a reason |

## The golden portfolio

`fixtures/market_data_golden/` holds two instruments over 60 consecutive weekdays,
generated deterministically by `scripts/generate_golden_fixtures.py`. The portfolio
is 100 units of `GLDA` and 20 of `GLDB`.

Every metric is checked against an **independent implementation** written in plain
Python — `statistics` and `math`, no NumPy, no SciPy, no application code. For both
to agree, the same mistake would have to be made twice in two different styles.

### Reference values

Pinned by `test_documented_reference_values`. If a calculation changes, that test
fails and this table must be updated in the same commit.

| Quantity | Value |
| --- | --- |
| Weight, GLDA | 0.713699 |
| Weight, GLDB | 0.286301 |
| Total return | 0.059549 |
| Annualized return | 0.280254 |
| Volatility, daily | 0.013319 |
| Volatility, annualized | 0.211435 |
| Sharpe ratio, risk-free 0% | 1.272574 |
| Sharpe ratio, risk-free 4.5% | 1.064375 |
| Maximum drawdown | -0.025398 |
| Historical VaR, 95%, on 100,000 | 1,555.21 |
| Parametric VaR, 95%, on 100,000 | 2,084.04 |
| Expected Shortfall, 95%, on 100,000 | 1,555.21 |
| Correlation, GLDA to GLDB | -0.434755 |

Note that the parametric VaR is **larger** than the historical one here. That is
the normal assumption at work on a short, thin-tailed sample; on a fat-tailed
sample the relationship usually reverses. It is exactly why both are reported.

Expected Shortfall equals the historical VaR to the cent because, with 59
observations at 95%, only three fall at or below the threshold and their mean is
almost the threshold itself. A real portfolio over a longer window separates them.

### Tolerances

- **1e-9 relative** for comparisons against the independent implementation. The two
  differ only in floating-point ordering — NumPy's vectorized reductions against a
  Python loop. A genuine formula error would be off by percent, not by 1e-9.
- **1e-12 relative** for risk-contribution reconciliation, which is an exact
  mathematical identity and should only lose accumulation error.
- **Exact** for Decimal arithmetic in stress tests and cost bases.
- **0.01 currency units** for stress-test reconciliation, because position impacts
  are rounded to the cent before being summed, so the table a user reads adds up.

## Data sources

Daily prices come from the configured market-data provider, are validated on
ingestion, and are stored with their `source`. The committed fixture provider
serves **synthetic** series shaped to resemble real equity behaviour — a drift,
fat-ish tails, sector co-movement, and drawdowns during the historical stress
windows. They are not real market data and are never presented as such. Their
purpose is a hermetic test suite; see [market-data.md](./market-data.md).

## Known limitations

- **Fixed weights**, as described above. The largest single approximation.
- **No cash, dividends, fees, taxes, or corporate actions** beyond what the
  adjusted close already reflects. Reported profit or loss is price-only.
- **No intraday data.** Daily closes only.
- **Weekday trading calendar.** Exchange holidays are not modelled; the
  consequences are documented in `app/market_data/calendar.py`.
- **Single currency per portfolio.**
- **Equities and ETFs only.** Bonds, options, and futures are not modelled, so a
  price shock applied to a bond fund is a crude approximation.
- **Historical estimates.** Every figure describes the past under stated
  assumptions. None is a forecast.
