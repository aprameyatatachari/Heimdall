"""Generate the golden-portfolio fixtures.

The golden portfolio is a small, fully deterministic dataset whose expected
analytics are calculated **independently** of Heimdall's implementation — see
`backend/tests/test_golden_portfolio.py`, which recomputes every metric with
plain Python (`decimal` and `statistics`, no NumPy, no application code) and
compares the two.

Two instruments, 60 consecutive weekdays, daily returns drawn from a short
repeating cycle. The cycle makes the series easy to reason about while still
giving both assets non-zero variance and a non-trivial correlation.

Usage::

    uv run python ../scripts/generate_golden_fixtures.py
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "fixtures" / "market_data_golden"

START = date(2024, 1, 1)
OBSERVATIONS = 60
PRICE_SCALE = Decimal("0.000001")

# Repeating daily-return cycles. Neither cycle is constant, so both assets have
# variance; they are not proportional, so the correlation is neither 0 nor 1.
SERIES: dict[str, tuple[Decimal, list[Decimal]]] = {
    "GLDA": (
        Decimal("100"),
        [Decimal(value) for value in ("0.02", "-0.01", "0.03", "-0.025", "0.005", "-0.015")],
    ),
    "GLDB": (
        Decimal("200"),
        [Decimal(value) for value in ("0.004", "0.006", "-0.002", "0.008", "-0.012", "0.002")],
    ),
}

METADATA = [
    {
        "symbol": "GLDA",
        "name": "Golden Test Instrument A",
        "asset_type": "equity",
        "exchange": "TEST",
        "currency": "USD",
        "sector": "Technology",
        "industry": "Software",
    },
    {
        "symbol": "GLDB",
        "name": "Golden Test Instrument B",
        "asset_type": "equity",
        "exchange": "TEST",
        "currency": "USD",
        "sector": "Healthcare",
        "industry": "Pharmaceuticals",
    },
]


def weekdays(start: date, count: int) -> list[date]:
    """`count` consecutive weekdays beginning at or after `start`."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def main() -> None:
    """Write the golden fixture files."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    days = weekdays(START, OBSERVATIONS)

    for symbol, (start_price, cycle) in SERIES.items():
        path = OUTPUT / f"{symbol}.csv"
        price = start_price

        with path.open("w", encoding="utf-8", newline="\n") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["date", "close", "adjusted_close"])
            # The first row is the starting price; later rows apply the cycle.
            writer.writerow([days[0].isoformat(), price, price])

            for index, day in enumerate(days[1:]):
                price = (price * (Decimal(1) + cycle[index % len(cycle)])).quantize(
                    PRICE_SCALE, rounding=ROUND_HALF_UP
                )
                writer.writerow([day.isoformat(), price, price])

        print(f"wrote {path.name}: {len(days)} rows, final close {price}")

    metadata_path = OUTPUT / "assets.json"
    metadata_path.write_text(json.dumps(METADATA, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {metadata_path.name}")


if __name__ == "__main__":
    main()
