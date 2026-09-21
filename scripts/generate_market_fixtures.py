"""Generate the offline market-data fixtures.

The fixtures are committed, so this script exists for reproducibility and for
regenerating the series if the shape needs to change. It is deterministic: the
same seed always produces the same files, byte for byte.

The series are **synthetic**. They are shaped to resemble real equity behaviour
(a drift, fat-ish tails, sector co-movement, and drawdowns during the historical
stress windows Heimdall ships scenarios for) so that analytics and stress tests
exercise realistic numbers. They are not real market data and must never be
presented as such.

Usage::

    uv run python ../scripts/generate_market_fixtures.py
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np

SEED = 20260920
START = date(2007, 1, 1)
END = date(2024, 12, 31)

OUTPUT = Path(__file__).resolve().parent.parent / "fixtures" / "market_data"

# Windows where the generator applies a crisis regime, so the shipped historical
# stress scenarios operate on data that actually fell.
CRISIS_WINDOWS: list[tuple[date, date, float, float]] = [
    # start, end, daily drift, daily volatility
    (date(2007, 10, 9), date(2009, 3, 9), -0.0018, 0.028),  # global financial crisis
    (date(2020, 2, 19), date(2020, 3, 23), -0.0210, 0.055),  # covid-19 crash
    (date(2022, 1, 3), date(2022, 10, 14), -0.0012, 0.019),  # rate-rise drawdown
]


@dataclass(frozen=True)
class SymbolSpec:
    """How to generate one instrument."""

    symbol: str
    name: str
    asset_type: str
    exchange: str
    sector: str | None
    industry: str | None
    start_price: float
    # Drift OUTSIDE the crisis windows. The realized long-run drift is lower,
    # because the crisis regimes below subtract from it.
    annual_drift: float
    annual_volatility: float
    market_beta: float
    # Multiplies the crisis drift, so defensive names fall less.
    crisis_sensitivity: float


SPECS: list[SymbolSpec] = [
    SymbolSpec("SPY", "SPDR S&P 500 ETF Trust", "etf", "NYSE Arca", None, None,
               142.0, 0.170, 0.16, 1.00, 1.00),
    SymbolSpec("AAPL", "Apple Inc.", "equity", "NASDAQ", "Technology",
               "Consumer Electronics", 12.0, 0.300, 0.30, 1.20, 1.15),
    SymbolSpec("MSFT", "Microsoft Corporation", "equity", "NASDAQ", "Technology",
               "Software", 29.0, 0.250, 0.26, 1.05, 1.05),
    SymbolSpec("NVDA", "NVIDIA Corporation", "equity", "NASDAQ", "Technology",
               "Semiconductors", 1.10, 0.430, 0.45, 1.65, 1.45),
    SymbolSpec("JPM", "JPMorgan Chase & Co.", "equity", "NYSE", "Financials",
               "Diversified Banks", 46.0, 0.200, 0.28, 1.15, 1.60),
    SymbolSpec("XOM", "Exxon Mobil Corporation", "equity", "NYSE", "Energy",
               "Integrated Oil and Gas", 75.0, 0.130, 0.25, 0.90, 1.25),
    SymbolSpec("JNJ", "Johnson & Johnson", "equity", "NYSE", "Healthcare",
               "Pharmaceuticals", 66.0, 0.130, 0.15, 0.60, 0.55),
    SymbolSpec("TLT", "iShares 20+ Year Treasury Bond ETF", "etf", "NASDAQ", None, None,
               88.0, 0.005, 0.13, -0.25, -0.40),
]

TRADING_DAYS_PER_YEAR = 252
CENTS = Decimal("0.000001")


def trading_days(start: date, end: date) -> list[date]:
    """Weekdays in the inclusive range, matching Heimdall's calendar convention."""
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def crisis_regime(day: date) -> tuple[float, float] | None:
    """Return (drift, volatility) when the date falls inside a crisis window."""
    for window_start, window_end, drift, volatility in CRISIS_WINDOWS:
        if window_start <= day <= window_end:
            return drift, volatility
    return None


def market_returns(days: list[date], rng: np.random.Generator) -> np.ndarray:
    """Daily LOG returns for the market factor, with crisis regimes applied.

    Working in log space keeps the realized compound drift equal to the requested
    annual drift; using arithmetic returns with multiplicative compounding would
    lose sigma-squared-over-two of drift every year.
    """
    spy = SPECS[0]
    base_drift = np.log1p(spy.annual_drift) / TRADING_DAYS_PER_YEAR
    base_volatility = spy.annual_volatility / np.sqrt(TRADING_DAYS_PER_YEAR)

    returns = np.empty(len(days))
    for index, day in enumerate(days):
        regime = crisis_regime(day)
        drift, volatility = regime if regime else (base_drift, base_volatility)
        # Student-t innovations give fatter tails than a normal distribution.
        shock = rng.standard_t(df=5) / np.sqrt(5 / 3)
        returns[index] = drift + volatility * shock
    return returns


def symbol_returns(
    spec: SymbolSpec,
    days: list[date],
    market: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Daily log returns as market beta plus idiosyncratic noise."""
    if spec.symbol == "SPY":
        return market

    idiosyncratic_annual = max(
        spec.annual_volatility**2 - (spec.market_beta * SPECS[0].annual_volatility) ** 2,
        0.0004,
    )
    idiosyncratic_daily = np.sqrt(idiosyncratic_annual / TRADING_DAYS_PER_YEAR)
    alpha = (
        np.log1p(spec.annual_drift) - spec.market_beta * np.log1p(SPECS[0].annual_drift)
    ) / TRADING_DAYS_PER_YEAR

    returns = np.empty(len(days))
    for index, day in enumerate(days):
        beta = spec.market_beta
        if crisis_regime(day) is not None:
            beta *= spec.crisis_sensitivity
        shock = rng.standard_t(df=6) / np.sqrt(6 / 4)
        returns[index] = alpha + beta * market[index] + idiosyncratic_daily * shock
    return returns


def to_decimal(value: float) -> Decimal:
    """Round a price to six decimal places, matching the stored column."""
    return Decimal(repr(round(value, 6))).quantize(CENTS, rounding=ROUND_HALF_UP)


def write_series(spec: SymbolSpec, days: list[date], returns: np.ndarray, rng) -> None:
    """Write one symbol's CSV file."""
    path = OUTPUT / f"{spec.symbol}.csv"
    price = spec.start_price

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", "open", "high", "low", "close", "adjusted_close", "volume"])

        for day, log_return in zip(days, returns, strict=True):
            previous = price
            price = max(previous * float(np.exp(log_return)), 0.01)

            intraday = abs(rng.normal(0.0, 0.004))
            high = max(previous, price) * (1.0 + intraday)
            low = min(previous, price) * (1.0 - intraday)
            volume = int(rng.lognormal(mean=15.6, sigma=0.35))

            writer.writerow(
                [
                    day.isoformat(),
                    to_decimal(previous),
                    to_decimal(high),
                    to_decimal(low),
                    to_decimal(price),
                    # Synthetic series carry no distributions, so the adjusted and
                    # unadjusted closes are equal by construction.
                    to_decimal(price),
                    volume,
                ]
            )

    print(f"wrote {path.name}: {len(days)} rows, final close {price:.2f}")


def write_metadata() -> None:
    """Write the metadata file the fixture provider reads."""
    entries = [
        {
            "symbol": spec.symbol,
            "name": spec.name,
            "asset_type": spec.asset_type,
            "exchange": spec.exchange,
            "currency": "USD",
            "sector": spec.sector,
            "industry": spec.industry,
        }
        for spec in SPECS
    ]
    path = OUTPUT / "assets.json"
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {len(entries)} symbols")


def main() -> None:
    """Generate every fixture series."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    days = trading_days(START, END)

    rng = np.random.default_rng(SEED)
    market = market_returns(days, rng)

    for spec in SPECS:
        # One stream per symbol keeps each file stable when another is added.
        symbol_rng = np.random.default_rng(SEED + sum(ord(char) for char in spec.symbol))
        returns = symbol_returns(spec, days, market, symbol_rng)
        write_series(spec, days, returns, symbol_rng)

    write_metadata()


if __name__ == "__main__":
    main()
