"""Offline fixture provider.

Reads committed CSV series from `fixtures/market_data/`. This is the provider used
by every test and by local development, so nothing in the test suite depends on
network availability or on a third party's uptime.

Fixture file format, one file per symbol (`AAPL.csv`)::

    date,open,high,low,close,adjusted_close,volume
    2024-01-02,185.00,186.50,184.10,185.64,185.64,52000000

`fixtures/market_data/assets.json` carries the metadata for each symbol.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from app.assets.models import AssetType
from app.market_data.provider import (
    AssetMetadata,
    AssetSearchResult,
    MarketDataProvider,
    PriceObservation,
    ProviderError,
    SymbolNotFoundError,
)

DEFAULT_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "market_data"
METADATA_FILENAME = "assets.json"


def _decimal_or_none(raw: str | None) -> Decimal | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ProviderError(f"Fixture contains a non-numeric value: {text!r}") from exc


def _required_decimal(raw: str | None, *, column: str, symbol: str) -> Decimal:
    value = _decimal_or_none(raw)
    if value is None:
        raise ProviderError(f"Fixture for {symbol} is missing a value in column {column!r}.")
    return value


@lru_cache(maxsize=8)
def _load_metadata(root: str) -> dict[str, AssetMetadata]:
    """Read and cache the fixture metadata file."""
    path = Path(root) / METADATA_FILENAME
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, AssetMetadata] = {}
    for entry in raw:
        symbol = str(entry["symbol"]).upper()
        metadata[symbol] = AssetMetadata(
            symbol=symbol,
            name=entry.get("name"),
            asset_type=AssetType(entry.get("asset_type", AssetType.UNKNOWN)),
            exchange=entry.get("exchange"),
            currency=str(entry.get("currency", "USD")).upper(),
            sector=entry.get("sector"),
            industry=entry.get("industry"),
        )
    return metadata


@lru_cache(maxsize=64)
def _load_series(root: str, symbol: str) -> tuple[PriceObservation, ...]:
    """Read and cache one symbol's series."""
    path = Path(root) / f"{symbol}.csv"
    if not path.exists():
        raise SymbolNotFoundError(f"No fixture price series for {symbol}.")

    observations: list[PriceObservation] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observations.append(
                PriceObservation(
                    date=date.fromisoformat(str(row["date"]).strip()),
                    open=_decimal_or_none(row.get("open")),
                    high=_decimal_or_none(row.get("high")),
                    low=_decimal_or_none(row.get("low")),
                    close=_required_decimal(row.get("close"), column="close", symbol=symbol),
                    adjusted_close=_required_decimal(
                        row.get("adjusted_close"), column="adjusted_close", symbol=symbol
                    ),
                    volume=_decimal_or_none(row.get("volume")),
                )
            )

    return tuple(sorted(observations, key=lambda item: item.date))


class FixtureMarketDataProvider(MarketDataProvider):
    """Deterministic provider backed by committed CSV files."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = str(root or DEFAULT_FIXTURE_ROOT)

    @property
    def name(self) -> str:
        """Identifier recorded on stored bars."""
        return "fixture"

    def available_symbols(self) -> list[str]:
        """Every symbol this fixture set can serve."""
        return sorted(path.stem.upper() for path in Path(self._root).glob("*.csv"))

    async def search_assets(self, query: str, *, limit: int = 10) -> list[AssetSearchResult]:
        """Match the query against fixture symbols and names."""
        needle = query.strip().lower()
        if not needle:
            return []

        metadata = _load_metadata(self._root)
        matches: list[AssetSearchResult] = []

        for symbol in self.available_symbols():
            entry = metadata.get(symbol)
            name = (entry.name if entry else None) or ""
            if needle in symbol.lower() or needle in name.lower():
                matches.append(
                    AssetSearchResult(
                        symbol=symbol,
                        name=entry.name if entry else None,
                        asset_type=entry.asset_type if entry else AssetType.UNKNOWN,
                        exchange=entry.exchange if entry else None,
                        currency=entry.currency if entry else "USD",
                    )
                )

        # Exact symbol matches first, then alphabetically, so results are stable.
        matches.sort(key=lambda item: (item.symbol.lower() != needle, item.symbol))
        return matches[:limit]

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Return fixture metadata for one symbol."""
        normalized = symbol.strip().upper()
        metadata = _load_metadata(self._root).get(normalized)

        if metadata is None:
            if normalized not in self.available_symbols():
                raise SymbolNotFoundError(f"No fixture data for {normalized}.")
            # A series exists but no metadata entry: report only what is known.
            return AssetMetadata(
                symbol=normalized,
                name=None,
                asset_type=AssetType.UNKNOWN,
                exchange=None,
                currency="USD",
            )

        return metadata

    async def get_daily_prices(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[PriceObservation]:
        """Return the fixture series for a symbol, clipped to the window."""
        normalized = symbol.strip().upper()
        series = _load_series(self._root, normalized)
        return [item for item in series if start <= item.date <= end]


def clear_fixture_cache() -> None:
    """Drop cached fixture files. Used by tests that write temporary fixtures."""
    _load_metadata.cache_clear()
    _load_series.cache_clear()
