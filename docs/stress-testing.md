# Stress testing

```text
GET  /api/v1/stress-scenarios                        the catalogue
POST /api/v1/portfolios/{portfolio_id}/stress-tests  run one
GET  /api/v1/portfolios/{portfolio_id}/stress-tests  history
GET  /api/v1/stress-tests/{run_id}                   one result
```

A stress test applies price changes to the portfolio's **current** holdings and
reports what that would do to its value. It is a sensitivity estimate, not a
forecast.

## Two kinds of scenario

### Historical

Each asset's **observed** return over a stated date range is applied to what the
portfolio holds today:

```text
applied_return(i) = price(i, window_end) / price(i, window_start) - 1
```

It answers *"if those exact moves happened again to what I hold now, what would
change?"* — it does **not** reconstruct what the portfolio was worth at the time.

The catalogue lives in one place, `app/stress_testing/scenarios.py`, so a date or a
label is corrected once:

| Key | Name | Window |
| --- | --- | --- |
| `global_financial_crisis_2007_2009` | Global financial crisis | 2007-10-09 to 2009-03-09 |
| `covid_19_crash_2020` | COVID-19 crash | 2020-02-19 to 2020-03-23 |
| `rate_rises_2022` | Rapid interest-rate increases | 2022-01-03 to 2022-10-14 |
| `q4_2018_selloff` | Late-2018 technology sell-off | 2018-09-20 to 2018-12-24 |
| `china_devaluation_2015` | August 2015 volatility shock | 2015-08-10 to 2015-08-25 |
| `india_election_shock_2004` | 2004 election result sell-off (India) | 2004-05-10 to 2004-05-17 |
| `india_correction_2006` | May-June 2006 correction (India) | 2006-05-10 to 2006-06-14 |
| `india_financial_crisis_2008` | 2008 financial crisis (India) | 2008-01-08 to 2008-10-27 |
| `india_bear_market_2010_2011` | 2010-11 inflation and rate-rise decline (India) | 2010-11-05 to 2011-12-20 |
| `india_rupee_crisis_2013` | 2013 rupee crisis (India) | 2013-05-17 to 2013-08-28 |
| `india_correction_2015_2016` | 2015-16 correction (India) | 2015-03-03 to 2016-02-25 |
| `india_covid_crash_2020` | COVID-19 crash (India) | 2020-01-14 to 2020-03-23 |
| `india_correction_2021_2022` | 2021-22 correction (India) | 2021-10-18 to 2022-06-17 |
| `india_election_result_2024` | 2024 election result day (India) | 2024-06-03 to 2024-06-04 |
| `dot_com_bust_2000_2002` | Dot-com bust | 2000-03-24 to 2002-10-09 |
| `us_downgrade_euro_crisis_2011` | 2011 US downgrade and euro-area debt crisis | 2011-04-29 to 2011-10-03 |
| `taper_tantrum_2013` | Taper tantrum | 2013-05-22 to 2013-06-24 |
| `brexit_referendum_2016` | Brexit referendum | 2016-06-23 to 2016-06-27 |
| `india_demonetisation_2016` | Demonetisation sell-off (India) | 2016-11-08 to 2016-12-26 |
| `volatility_shock_feb_2018` | February 2018 volatility shock | 2018-01-26 to 2018-02-08 |
| `india_nbfc_crisis_2018` | Non-bank lender crisis (India) | 2018-08-28 to 2018-10-26 |
| `yen_carry_unwind_2024` | August 2024 carry-trade unwind | 2024-07-16 to 2024-08-05 |
| `india_correction_2024_2025` | 2024-25 equity correction (India) | 2024-09-26 to 2025-03-04 |
| `tariff_shock_2025` | 2025 tariff shock | 2025-02-19 to 2025-04-08 |
| `us_correction_early_2026` | Early 2026 correction | 2026-01-27 to 2026-03-30 |
| `india_correction_early_2026` | Early 2026 correction (India) | 2026-01-02 to 2026-03-30 |
| `technology_decline_mid_2026` | Mid-2026 technology decline | 2026-06-02 to 2026-07-29 |
| `india_decline_late_2026` | August-September 2026 decline (India) | 2026-08-03 to 2026-10-01 |
| `ai_trade_reversal_2024` | Mid-2024 AI and semiconductor sell-off | 2024-07-10 to 2024-08-07 |
| `deepseek_shock_2025` | DeepSeek shock | 2025-01-24 to 2025-01-27 |
| `india_us_tariffs_2025` | 2025 US tariffs on Indian goods (India) | 2025-06-27 to 2025-08-08 |
| `september_11_attacks_2001` | September 2001 attacks | 2001-09-10 to 2001-09-21 |
| `us_iran_tensions_january_2020` | January 2020 US-Iran escalation | 2020-01-02 to 2020-01-08 |
| `russia_ukraine_invasion_2022` | Russian invasion of Ukraine | 2022-02-09 to 2022-03-08 |
| `israel_hamas_war_2023` | October 2023 Israel-Hamas war | 2023-10-06 to 2023-10-27 |
| `iran_israel_strikes_april_2024` | April 2024 Iran-Israel strikes | 2024-04-12 to 2024-04-19 |
| `india_pakistan_conflict_2025` | May 2025 India-Pakistan conflict (India) | 2025-05-06 to 2025-05-09 |
| `israel_iran_war_june_2025` | June 2025 Israel-Iran war | 2025-06-12 to 2025-06-23 |
| `iran_war_2026` | 2026 Iran war | 2026-02-27 to 2026-03-30 |

A scenario named for a conflict replays the market's moves over those dates and
nothing else. It is not a statement about the conflict, and the returns in the
window reflect everything else that happened in those weeks too.

Windows for global episodes follow the S&P 500's peak and trough, and those marked
(India) follow the Nifty 50's, or the Sensex's for the two episodes before 2007. A
holding listed elsewhere is measured over the same dates, which may not be its own
peak or trough. The 2026 entries are dated from index closes alone and attribute no
cause; the last one ends at the lowest close when it was written, so the episode
may not have ended. An episode older than a holding's
listing has no return for it, and that holding is excluded and named.

Every run stores the full definition — key, name, description, and **exact dates** —
so a stored result stays explainable even if the catalogue changes later.

Each position records how its return was determined, for example
*"observed return from 2020-02-19 to 2020-03-23 (24 observations)"*.

### Hypothetical

An explicit set of shocks:

```json
{
  "custom": {
    "name": "Technology Sell-Off",
    "shocks": [
      { "target_type": "sector", "target": "Technology", "value": "-0.20" },
      { "target_type": "symbol", "target": "AAPL", "value": "-0.30" }
    ]
  }
}
```

| Field | Rules |
| --- | --- |
| `target_type` | `symbol`, `sector`, or `portfolio` |
| `target` | Required for `symbol` and `sector`; omitted for `portfolio` |
| `shock_type` | `relative_price` only |
| `value` | -0.99 to 5.00, as a decimal fraction |

At most 50 shocks. Two shocks on the same target are **ambiguous and rejected**
rather than silently resolved.

`relative_price` is the only shock type because it is the only one that can be
applied to an equity position without modelling something Heimdall does not model —
rate curves, credit spreads, or implied volatility.

## Shock precedence

Strict and tested:

```text
symbol  overrides  sector  overrides  portfolio
```

With the example above, in a portfolio holding AAPL, MSFT, and JNJ:

| Holding | Sector | Applied return | Why |
| --- | --- | --- | --- |
| AAPL | Technology | -30% | symbol shock wins over its sector |
| MSFT | Technology | -20% | sector shock |
| JNJ | Healthcare | 0% | no shock targets it |

Precedence does **not** depend on the order of the list. Between two shocks of the
same specificity the later one wins, so a caller can override an earlier entry
predictably.

A holding no shock targets keeps its value and is reported with a zero return and
the note *"no shock targets this holding"*. That is correct here: the caller stated
exactly what moves, so everything else is deliberately unchanged.

## What a result contains

| Field | Meaning |
| --- | --- |
| `starting_value` | Portfolio value before the scenario, over the analyzed holdings |
| `ending_value` | Estimated value afterwards |
| `total_impact` | Currency change; negative for a loss |
| `total_impact_percent` | Change as a fraction of the starting value |
| `positions[]` | Per holding: starting value, applied return, how it was determined, ending value, impact, and share of loss |
| `excluded_symbols` | Holdings with no usable price data, excluded rather than assumed flat |
| `reconciles` | Whether the position impacts sum to the portfolio impact |
| `scenario_definition` | The complete scenario as stored |
| `data_as_of` | Newest market-data date used |
| `limitations` | The caveats below |
| `status` | `succeeded`, or `partial` when holdings were excluded |

### Reconciliation

Position impacts sum **exactly** to the portfolio impact, and the check runs on the
rounded figures that are presented, so the table a user reads adds up to the
headline number. Tolerance is one cent.

### Contribution to loss

```text
contribution(i) = impact(i) / total_impact
```

Only defined when the scenario is a loss overall; otherwise `null`. A holding that
**gained** during a losing scenario gets a **negative** contribution — it offset
part of the loss. Clamping that to zero would break the reconciliation and hide a
real diversification effect.

### Exclusions

A holding with no stored price, or with fewer than two observations inside a
historical window, is **excluded** and named. It is not assumed flat: a zero would
silently understate the scenario's effect. Excluded holdings are also left out of
`starting_value`, so the percentage stays honest about what was actually analyzed.

If no holding has data for a scenario window, the run fails with
`422 scenario_data_unavailable` rather than reporting a zero impact.

## Limitations

Returned with every result:

- A stress test applies price changes to current holdings. It is an estimate of
  sensitivity, not a forecast.
- Quantities are held fixed. No trading, rebalancing, or cash flow is modelled.
- A historical scenario replays returns observed in that window. Those exact
  returns are not expected to repeat.
- A relative price shock is **not** an interest-rate, credit, liquidity, or
  macroeconomic model. Bond and derivative behaviour is not modelled.
- Holdings with no price data in the window are excluded and listed separately.
- Results depend on the stored market data and on each scenario's assumptions.

The fourth point deserves emphasis. "Rapid interest-rate increases" applies the
equity and bond-fund price moves observed in 2022. It does **not** model a yield
curve, duration, convexity, or credit spreads. For a portfolio of individual bonds
it would be a crude approximation, and Heimdall does not claim otherwise.

## Stress tests and signals

A stress-test result is **not** automatically a Gjallarhorn Signal. It becomes one
only when an enabled stress-loss early-warning rule evaluates it and its configured
threshold is crossed. See [early-warning.md](./early-warning.md).

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
