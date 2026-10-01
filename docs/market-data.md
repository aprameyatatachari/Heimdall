# Market data

## The provider interface

Every vendor sits behind one internal interface, `MarketDataProvider`:

```python
async def search_assets(query, *, limit) -> list[AssetSearchResult]
async def get_asset_metadata(symbol) -> AssetMetadata
async def get_daily_prices(symbol, *, start, end) -> list[PriceObservation]
```

Vendor response shapes stop at the adapter. What leaves a provider is always the
domain objects in `app/market_data/provider.py`, so no part of the application
depends on a particular data source. Swapping vendors means writing one adapter.

Prices are `Decimal`, not `float`: they are stored and summed.

## The ingestion path

Fixed and documented:

1. Look at what is already stored.
2. Work out which expected trading days are missing.
3. Ask the provider **only** for the missing ranges.
4. Normalize the response into domain objects.
5. Validate it, rejecting unusable bars and flagging suspicious ones.
6. Store it idempotently, keyed by `(asset, date, source)`.
7. Return provider-independent results.

### Idempotency

A unique constraint on `(asset_id, date, source)` plus an upsert makes repeated
ingestion safe: re-fetching a window that is already stored refreshes the values
instead of duplicating them. A provider may legitimately revise a bar — a late
split adjustment, a corrected close — so the newer values win.

### Missing-range detection

Only **expected trading days** count, so a weekend between two stored bars is never
a gap. Contiguous missing days merge into one range, and a gap of one trading day
is tolerated rather than refetched forever: under a weekday calendar an exchange
holiday looks exactly like one missing weekday, and no provider will ever return it.

## Validation

A provider's output is never trusted. Observations are sorted, deduplicated, and
checked.

**Rejected** — the bar is not stored, and the reason is reported:

| Issue | Why |
| --- | --- |
| `duplicate_date` | The first occurrence is kept |
| `non_positive_price` | No return can be computed from it |
| `implausible_price` | Above 1e9, which no supported instrument reaches |
| `invalid_ohlc` | `low > high`, or a close outside the range |
| `negative_volume` | Not physically meaningful |
| `future_date` | Dated after the as-of date |

**Flagged** — the bar is stored and the caller is told:

| Issue | Why it is not rejected |
| --- | --- |
| `extreme_return` | A single-day move of 60% or more usually means an unadjusted corporate action — but some real moves are that large, so the data is reported rather than removed |

Every refresh response carries these notes per asset, with counts of rejected and
flagged observations. Nothing is silently dropped.

## Trading calendar

**The documented convention:** Monday to Friday are expected trading days.
Exchange holidays are **not** modelled.

Consequences, stated because they matter for staleness:

- A weekend never counts as missing or stale data.
- A market holiday looks like one missing expected trading day. Staleness
  thresholds therefore carry a one-day tolerance.
- A Friday close read on the following Monday is **one** trading day old.

Replacing this with a real exchange calendar would change only
`app/market_data/calendar.py`.

`TRADING_DAYS_PER_YEAR = 252` lives in the same module and is the annualization
factor used throughout.

## Currency

One base currency per portfolio. `USD` and `INR` are supported. An asset whose
provider currency differs from the portfolio's base currency is **rejected** with
`unsupported_currency` or `currency_mismatch`.

Heimdall does not convert between currencies, so combining them would silently
produce meaningless totals. Adding conversion means dated FX rates and an explicit
conversion step, not a spot rate applied retroactively. A reader who wants both
markets keeps two portfolios, each measured in its own currency, which is also the
only arrangement in which a volatility or a Sharpe ratio means anything.

Supporting a currency takes more than adding it to `SUPPORTED_BASE_CURRENCIES`:
the provider has to be able to price instruments in it, or every holding comes
back unpriced and every metric comes back unavailable.

## Asset enrichment

An asset first created by a CSV import is a placeholder: symbol and currency only,
with `asset_type` literally `unknown` and a null name and sector. Nothing about the
instrument is invented.

The first time market data is requested for it, the provider's metadata fills in
its name, type, exchange, sector, and industry. A provider that does not recognise
a stored symbol leaves the record alone rather than discarding a user's holding.

## The providers

Two, chosen by `MARKET_DATA_PROVIDER`:

| | `yahoo` | `fixture` |
| --- | --- | --- |
| Source | Yahoo Finance | committed CSV files |
| Prices | live, including today's bar while a market is open | 2007-01-01 to 2024-12-31 |
| Instruments | everything Yahoo lists on a mapped exchange | fourteen |
| Needs a network | yes | no |
| Used by the test suite | never | always |

`yahoo` is the default for local development and deployment; `fixture` is the
default in configuration, so a process started with no environment at all runs
offline rather than reaching for a third party.

### The Yahoo adapter

Nothing about `yfinance` leaves `app/market_data/yahoo_provider.py`. Three things
it has to get right:

- **Threads.** `yfinance` is synchronous and does network I/O. Called directly
  from a handler it would block the event loop for every other request in the
  process, so every call goes through `asyncio.to_thread` with a deadline.
- **Dates.** Yahoo indexes daily bars by a timestamp in the *exchange's*
  timezone. An NSE bar for the 1st is `2026-10-01 00:00:00+05:30`; converting
  that to UTC moves it to the 30th of September, and every Indian price lands
  under the previous day. The local date is taken as-is.
- **Decimals.** Prices arrive as float64 and are rendered through `repr` before
  being parsed as `Decimal`, so what is stored is the shortest decimal that
  round-trips the float rather than its binary expansion.

Yahoo is not an official API: unversioned, rate-limited without documenting it,
and free to change shape. Its search results carry no currency, so the adapter
maps Yahoo's exchange codes to one and **drops any exchange it cannot map** —
offering an instrument whose currency is unknown would offer a holding the API
refuses on arrival.

Every bar it writes is stored with `source = "yahoo"`, so live data and fixture
data can never be mistaken for one another in the same database.

### The fixture provider

Reads committed CSV files from
`fixtures/market_data/`, so **every test and local development run is hermetic** —
no network, no third-party uptime, no API key.

```text
fixtures/market_data/
  assets.json     metadata for each symbol

  SPY.csv  AAPL.csv  MSFT.csv  NVDA.csv       United States, USD
  JPM.csv  XOM.csv   JNJ.csv   TLT.csv

  NIFTYBEES.NS.csv  RELIANCE.NS.csv           India, INR
  TCS.NS.csv        INFY.NS.csv
  HDFCBANK.NS.csv   ITC.NS.csv
```

Fourteen instruments, 4,697 weekdays from 2007-01-01 to 2024-12-31: eight in
dollars across five sectors plus a bond ETF, and six in rupees across four.

**Two market factors, not one.** SPY drives the US names and NIFTYBEES.NS drives
the Indian ones, each on its own random stream. A single factor would have made
every Indian holding correlate with the S&P by construction, and the correlation
heatmap would then be showing an artefact of the generator rather than anything
about the instruments.

### The data is synthetic

Generated by `scripts/generate_market_fixtures.py` from a fixed seed. It is shaped
to resemble real equity behaviour — a drift, Student-t tails, a market factor with
per-name betas, and drawdowns during the windows the shipped stress scenarios
cover — so analytics and stress tests exercise realistic numbers.

It is **not real market data** and must never be presented as such. Measured
characteristics:

| Symbol | CAGR | Annualized volatility | Maximum drawdown |
| --- | --- | --- | --- |
| SPY | 5.94% | 20.82% | -56.58% |
| AAPL | 9.16% | 35.13% | -72.58% |
| JNJ | 3.93% | 15.48% | -38.14% |
| TLT | 3.52% | 13.09% | -26.88% |

The Indian series are drawn the same way from their own factor. They are not
calibrated to the real Nifty: NIFTYBEES.NS compounds more slowly here than the
index did over the same years, because it is one path of a random process rather
than a record of one. Nothing in the product depends on the level.

TLT carries a negative market beta, so it diversifies — which is what makes the
correlation rule and risk attribution worth testing.

Regenerating is deterministic:

```bash
cd backend && uv run python ../scripts/generate_market_fixtures.py
```

### Golden fixtures

`fixtures/market_data_golden/` is separate and smaller: two instruments over 60
weekdays with returns from a short repeating cycle, used to validate the
calculations against an independent implementation. See
[financial-methodology.md](./financial-methodology.md#the-golden-portfolio).

## Licensing and reliability

No third-party data is committed, so there is nothing to license. That is one
reason the fixtures are synthetic.

A real provider brings constraints that belong in this document when one is added:
its terms of use and redistribution rules, its rate limits, its history depth, its
adjustment policy, and its uptime. The provider interface exists so that switching
vendors — or running two — does not touch the domain.

**Do not make the system depend on one vendor.** The interface, the `source` column
on every bar, and the configuration switch all exist for that reason.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/assets/search?query=` | Search instruments through the provider |
| GET | `/api/v1/assets/search?currency=` | Browse the largest instruments in a market |
| GET | `/api/v1/assets/{symbol}/prices` | Daily bars, fetching missing days first |
| POST | `/api/v1/portfolios/{id}/market-data/refresh` | Refresh every holding |

A refresh reports per asset: whether it was already up to date, how many ranges
were fetched, how many observations arrived, how many bars were written, how many
were rejected or flagged, the newest stored date, and the staleness in expected
trading days.

**One unavailable symbol does not abort the refresh.** Failures are collected under
`failures` and the remaining assets still update.

**`data_as_of` is the date the data reaches, not the date that was asked for.**
Those are different facts and the response carries both: `requested_end` is the
window's end, and `data_as_of` is the newest price now stored across the assets
refreshed — older than `requested_end` whenever the provider has nothing newer,
and null when nothing is stored at all. The field once reported the requested
date, which told a caller prices were current to today when the newest
observation was a year old; that is the one thing this product must never do, so
the name now means what it means everywhere else.

## Limitations

- **Daily closes only.** No intraday data.
- **Weekday calendar.** No exchange holidays, in either market. The Indian
  calendar has more of them than the US one, so an NSE series overstates its
  expected trading days by more.
- **USD and INR only**, and no conversion between them.
- **Synthetic fixture data.** Realistic in shape, not real.
- **No corporate-action detail.** Only what the adjusted close already reflects;
  an unadjusted split shows up as a flagged extreme return.
- **No delisting handling.** A symbol the provider stops serving keeps its stored
  history and starts producing stale-data signals.
- **25-year maximum window** per ingestion request.
