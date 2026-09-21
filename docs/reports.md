# Heimdall Risk Reports

```text
POST /api/v1/portfolios/{portfolio_id}/reports     generate
GET  /api/v1/portfolios/{portfolio_id}/reports     list
GET  /api/v1/reports/{report_id}                   metadata
GET  /api/v1/reports/{report_id}/download          the PDF
```

A generated document is a **Heimdall Risk Report**, never a "Gjallarhorn Report".
Early-warning results appear inside it as a subsection titled *Gjallarhorn Early
Warning Signals*, with its own disclaimer.

## What a report contains

| Section | Content |
| --- | --- |
| Header | Portfolio name, base currency, generation time, market-data as-of date, analysis period |
| Disclaimer | The educational-use disclaimer, on the first page and again at the end |
| Portfolio summary | Market value, acquisition cost, unrealized profit or loss, holdings count, largest position and sector weights |
| Holdings | Per-position quantity, average cost, market value, weight, profit or loss |
| Allocation | Weight by sector |
| Performance | Total and annualized return, and benchmark comparison when one is configured |
| Risk measures | Daily and annualized volatility, Sharpe ratio, maximum and current drawdown, historical and parametric VaR, Expected Shortfall, correlation |
| Risk attribution | Per-asset marginal and component contribution to portfolio volatility, and share of risk |
| Stress tests | Up to five recent scenarios, each with a position-level impact table |
| Gjallarhorn Early Warning Signals | Up to 25 recent signals with severity, observed value, threshold, and status |
| Unavailable measures | Anything that could not be computed, with the reason |
| Assumptions | The analysis run's recorded assumptions, including the fixed-weight caveat |
| Data sources | Where the numbers came from |
| Limitations | What the report does not model |

Every metric carries its unit and, where it matters, whether it is annualized and
at what confidence level. A value that could not be computed prints
**"unavailable"** with its reason — never a zero standing in for missing data.

## Reproducibility

A report stores the exact inputs it was built from:

```json
{
  "portfolio_id": "...",
  "analysis_run_id": "...",
  "analysis_parameters": { "start": "2022-01-03", "end": "2023-12-29", "confidence": 0.95, "...": "..." },
  "data_as_of": "2023-12-29",
  "include_stress_tests": true,
  "include_signals": true,
  "generated_by_version": "0.1.0"
}
```

Generating a report again from the same `analysis_run_id` produces the same
numbers, because it reads the **stored** analysis rather than recomputing one.

Which run is used:

1. `analysis_run_id` in the request, when given.
2. Otherwise the portfolio's most recent stored analysis run.
3. Only if none exists is a fresh analysis computed — so a report never quietly
   invents numbers that differ from what the dashboard showed.

## Formatting rules

- A negative monetary amount always carries a **minus sign**, and a signed positive
  one a plus, so meaning survives black-and-white printing and colour blindness.
  Colour reinforces the sign; it never carries it alone.
- Money is formatted with its currency code.
- Percentages come from fractions and print with two decimal places.
- Ratios (Sharpe, beta, correlation) print as plain two-decimal numbers.

## Storage

Rendered bytes are stored in the `reports.content` column.

**Why not a file:** production runs on serverless functions with an ephemeral
filesystem, so a file written during one request is gone by the next. A column
keeps reports durable without adding an object-store dependency to a project this
size.

**When to move to object storage:** a typical report is 5–20 KB, so thousands fit
comfortably. If reports grow large (many stress tests, long holdings lists) or
retention grows long, move the bytes to S3-compatible storage and keep the metadata
row, replacing `content` with a key. `ReportService.get_downloadable` is the only
code that reads the bytes.

Downloads are served with `Cache-Control: private, no-store`, because a report
contains portfolio data.

## Failure behaviour

If rendering fails, the report row is marked `failed` with its error message, and
**no analysis run, stress test, or signal is changed**. The report is a separate
record; only it is affected. The API returns `422 report_generation_failed`.

Statuses: `pending`, `generating`, `succeeded`, `failed`. Only `succeeded` has a
`download_url`.

## Access control

- Only the account that generated a report can read its metadata or download it.
- `user_id` is stored on the report alongside `portfolio_id`, so ownership holds
  independently of the portfolio row.
- Another user's report and a non-existent report both return `404 report_not_found`.
- Downloads require a bearer token; there are no signed URLs.

## Why ReportLab

Pure Python, no system libraries to install. That keeps the serverless function
bundle small and the build reproducible. A browser-based renderer (WeasyPrint,
Playwright) would need Chromium or Cairo in the image, which does not fit a
serverless function's size budget.

The trade-off: no charts in the PDF. Tables carry the numbers, which is also the
accessible presentation — a screen reader can read a table but not an image of a
chart. Charts live in the frontend, where they have accessible data-table
alternatives.

## Limitations

- **PDF only.** No CSV or XLSX export yet. When one is added it must pass every
  value through `sanitize_csv_value`.
- **No charts**, for the reason above.
- **Bounded content:** five stress tests and 25 signals, newest first, so a report
  stays readable and generation stays fast.
- **Generated synchronously.** Report generation takes well under a second for a
  normal portfolio, so a background worker would add moving parts without solving
  a real problem. If it ever grows past the function duration limit, the `Report`
  row already has the `pending`/`generating` statuses a queue would need.
- **No scheduled or emailed reports.**

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
