"""Yahoo Finance, behind the provider interface.

Nothing about `yfinance` leaves this file. It returns pandas frames, numpy
scalars, tz-aware timestamps and dictionaries whose keys change between
versions; what this adapter hands back is the same domain objects the fixture
provider returns, so the rest of the application cannot tell which one answered.

Three things this adapter has to get right, and each has cost someone a bug
somewhere:

**Threads.** `yfinance` is synchronous and does network I/O. Called directly from
an async handler it would block the event loop for every other request in the
process. Every call here goes through `asyncio.to_thread`.

**Dates.** Yahoo indexes daily bars by a timestamp in the *exchange's* timezone.
An NSE bar for the 1st is `2026-10-01 00:00:00+05:30`; converting that to UTC
moves it to the 30th of September, and every Indian price would be filed under
the previous day. The local date is taken as-is, never converted.

**Decimals.** Prices arrive as float64. They are rendered through `repr` and
parsed as `Decimal`, so what gets stored is the shortest decimal that round-trips
the float rather than its binary expansion.

Yahoo is not an official API: it is unversioned, rate-limited without documenting
it, and free to change shape. That is precisely why it sits behind an interface,
and why no test depends on it.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.assets.models import AssetType
from app.common.logging import get_logger
from app.market_data.provider import (
    AssetMetadata,
    AssetSearchResult,
    MarketDataProvider,
    PriceObservation,
    ProviderUnavailableError,
    SymbolNotFoundError,
)

logger = get_logger(__name__)

# How long any one Yahoo call may take before it is treated as unavailable.
# Bounded because a request to Heimdall must not hang on a third party.
REQUEST_TIMEOUT_SECONDS = 20.0

# Yahoo's exchange codes, which search results carry instead of a currency.
# Only the exchanges Heimdall can price are mapped; anything else is left
# unknown rather than guessed at, because a wrong currency in a suggestion list
# hides a valid instrument or offers one that cannot be held.
EXCHANGE_CURRENCY: dict[str, str] = {
    "NSI": "INR",  # National Stock Exchange of India
    "BSE": "INR",  # Bombay Stock Exchange
    "NYQ": "USD",  # New York Stock Exchange
    "NMS": "USD",  # NASDAQ Global Select
    "NGM": "USD",  # NASDAQ Global Market
    "NCM": "USD",  # NASDAQ Capital Market
    "ASE": "USD",  # NYSE American
    "PCX": "USD",  # NYSE Arca
    "BTS": "USD",  # BATS
}

# Yahoo's `quoteType`, which is not Heimdall's `AssetType`.
QUOTE_TYPES: dict[str, AssetType] = {
    "EQUITY": AssetType.EQUITY,
    "ETF": AssetType.ETF,
    "MUTUALFUND": AssetType.UNKNOWN,
    "INDEX": AssetType.UNKNOWN,
    "CURRENCY": AssetType.UNKNOWN,
    "CRYPTOCURRENCY": AssetType.UNKNOWN,
}

# Yahoo's region codes for the markets Heimdall supports, by currency.
REGION_BY_CURRENCY: dict[str, str] = {"USD": "us", "INR": "in"}

# Below this market capitalization a screened result is more noise than
# suggestion. In the screened region's own currency.
MINIMUM_MARKET_CAP: dict[str, float] = {"USD": 2e10, "INR": 2e11}


def _decimal(value: Any) -> Decimal | None:
    """A float64 price as the shortest decimal that round-trips it."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric or numeric in (float("inf"), float("-inf")):  # NaN or infinite
        return None
    try:
        return Decimal(repr(numeric))
    except InvalidOperation:
        return None


def _text(value: Any) -> str | None:
    """A non-empty string, or nothing."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _asset_type(quote_type: Any) -> AssetType:
    return QUOTE_TYPES.get(str(quote_type or "").upper(), AssetType.UNKNOWN)


def existing_is_nse(existing: AssetSearchResult | None) -> bool:
    """Whether a already-kept listing is the NSE one."""
    return existing is not None and existing.symbol.upper().endswith(".NS")


# What yfinance raises when a range holds no prices for a symbol it does know.
NO_PRICES_IN_RANGE = "YFPricesMissingError"


class YahooMarketDataProvider(MarketDataProvider):
    """Daily prices and reference data from Yahoo Finance."""

    def __init__(self, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        """Recorded on every stored bar, so a series' origin is never in doubt."""
        return "yahoo"

    # --- Internals -----------------------------------------------------------

    async def _call(self, work: Any, *args: Any, **kwargs: Any) -> Any:
        """Run one blocking yfinance call off the event loop, with a deadline."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(work, *args, **kwargs),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise ProviderUnavailableError("Yahoo Finance did not respond in time.") from exc
        # Every vendor failure is one failure here: a timeout, a parse error and
        # a rate limit are all "Yahoo could not answer" to a caller.
        except Exception as exc:
            logger.warning("yahoo_call_failed", error=type(exc).__name__)
            raise ProviderUnavailableError("Yahoo Finance could not be reached.") from exc

    # --- Interface -----------------------------------------------------------

    async def search_assets(self, query: str, *, limit: int = 10) -> list[AssetSearchResult]:
        """Instruments whose symbol or name matches, as Yahoo ranks them."""
        import yfinance

        def run() -> list[dict[str, Any]]:
            search = yfinance.Search(query, max_results=max(limit * 2, limit))
            return list(search.quotes or [])

        quotes = await self._call(run)

        results: list[AssetSearchResult] = []
        for quote in quotes:
            symbol = _text(quote.get("symbol"))
            if symbol is None:
                continue
            currency = EXCHANGE_CURRENCY.get(str(quote.get("exchange") or "").upper())
            if currency is None:
                # Yahoo lists far more exchanges than Heimdall can price. An
                # instrument whose currency is unknown is left out rather than
                # offered as a holding that would be refused on arrival.
                continue
            results.append(
                AssetSearchResult(
                    symbol=symbol,
                    name=_text(quote.get("longname")) or _text(quote.get("shortname")),
                    asset_type=_asset_type(quote.get("quoteType")),
                    exchange=_text(quote.get("exchDisp")) or _text(quote.get("exchange")),
                    currency=currency,
                )
            )
            if len(results) >= limit:
                break
        return results

    async def list_popular(self, *, currency: str, limit: int = 20) -> list[AssetSearchResult]:
        """The largest instruments in the market that uses `currency`.

        This is what fills the symbol field's list before anything is typed. It
        is a starting point, not a recommendation: the ordering is market
        capitalization, which says what is big, not what is worth holding.
        """
        import yfinance

        region = REGION_BY_CURRENCY.get(currency.upper())
        if region is None:
            return []
        floor = MINIMUM_MARKET_CAP.get(currency.upper(), 0.0)

        def run() -> list[dict[str, Any]]:
            query = yfinance.EquityQuery(
                "and",
                [
                    yfinance.EquityQuery("eq", ["region", region]),
                    yfinance.EquityQuery("gt", ["intradaymarketcap", floor]),
                ],
            )
            response = yfinance.screen(
                query,
                sortField="intradaymarketcap",
                sortAsc=False,
                size=min(limit * 3, 100),
            )
            return list(response.get("quotes", []) if isinstance(response, dict) else [])

        quotes = await self._call(run)

        # Indian companies list on both the NSE and the BSE, and the two rows are
        # the same company. Keeping both fills a suggestion list with pairs that
        # help nobody choose, so one listing per name survives — the NSE one
        # where there is a choice, because it is the more liquid of the two and
        # the series behind it has fewer gaps.
        by_name: dict[str, AssetSearchResult] = {}
        for quote in quotes:
            symbol = _text(quote.get("symbol"))
            quoted_currency = _text(quote.get("currency"))
            if symbol is None or quoted_currency != currency.upper():
                continue

            name = _text(quote.get("longName")) or _text(quote.get("shortName")) or symbol
            candidate = AssetSearchResult(
                symbol=symbol,
                name=name,
                asset_type=_asset_type(quote.get("quoteType")),
                exchange=_text(quote.get("fullExchangeName")),
                currency=quoted_currency,
            )

            existing = by_name.get(name.casefold())
            prefer_nse = symbol.upper().endswith(".NS") and not existing_is_nse(existing)
            if existing is None or prefer_nse:
                by_name[name.casefold()] = candidate

            if len(by_name) >= limit and symbol.upper().endswith(".NS"):
                break

        return list(by_name.values())[:limit]

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Reference data for one instrument, from the authoritative quote."""
        import yfinance

        def run() -> dict[str, Any]:
            ticker = yfinance.Ticker(symbol)
            fast = ticker.fast_info
            detail: dict[str, Any] = {
                "currency": fast.get("currency"),
                "quoteType": fast.get("quoteType"),
                "exchange": fast.get("exchange"),
                "lastPrice": fast.get("lastPrice"),
            }
            # `info` is the slower, richer call, and the only source of sector.
            # A failure here is not fatal: a holding with no sector is honest,
            # a holding Heimdall refuses to store is not.
            try:
                info = ticker.info or {}
            # Optional enrichment only; see above.
            except Exception:
                info = {}
            detail["name"] = info.get("longName") or info.get("shortName")
            detail["sector"] = info.get("sector")
            detail["industry"] = info.get("industry")
            return detail

        detail = await self._call(run)

        currency = _text(detail.get("currency"))
        if currency is None or detail.get("lastPrice") is None:
            # Yahoo answers for an unknown symbol with an empty quote rather
            # than an error, so "no currency and no price" is how it says no.
            raise SymbolNotFoundError(f"Yahoo Finance does not know {symbol}.")

        return AssetMetadata(
            symbol=symbol,
            name=_text(detail.get("name")),
            asset_type=_asset_type(detail.get("quoteType")),
            exchange=_text(detail.get("exchange")),
            currency=currency.upper(),
            sector=_text(detail.get("sector")),
            industry=_text(detail.get("industry")),
        )

    async def get_daily_prices(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[PriceObservation]:
        """Daily bars between `start` and `end`, both inclusive."""
        import yfinance

        def run() -> list[dict[str, Any]]:
            try:
                frame = yfinance.Ticker(symbol).history(
                    start=start.isoformat(),
                    # Yahoo's `end` is exclusive; Heimdall's is inclusive.
                    end=(end + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                    raise_errors=True,
                )
            except Exception as exc:
                # Asked for dates on which the instrument did not trade, most
                # often the months before it was listed, Yahoo raises instead
                # of returning nothing. That is an answer, not an outage: there
                # are no prices in the range. Matched by name so the vendor's
                # exception types stay out of this module's imports.
                if type(exc).__name__ == NO_PRICES_IN_RANGE:
                    return []
                raise
            if frame is None or frame.empty:
                return []
            rows: list[dict[str, Any]] = []
            for timestamp, row in frame.iterrows():
                # `.date()` on the exchange-local timestamp. Converting to UTC
                # first would file every Indian bar under the previous day.
                rows.append({"date": timestamp.date(), **{str(k): v for k, v in row.items()}})
            return rows

        rows = await self._call(run)

        observations: list[PriceObservation] = []
        for row in rows:
            observed_on = row.get("date")
            close = _decimal(row.get("Close"))
            if not isinstance(observed_on, date) or close is None or close <= 0:
                # A bar with no usable close is not a bar. The validation layer
                # reports gaps; inventing one here would hide a real one.
                continue
            if observed_on < start or observed_on > end:
                continue
            adjusted = _decimal(row.get("Adj Close")) or close
            observations.append(
                PriceObservation(
                    date=observed_on,
                    close=close,
                    adjusted_close=adjusted,
                    open=_decimal(row.get("Open")),
                    high=_decimal(row.get("High")),
                    low=_decimal(row.get("Low")),
                    volume=_decimal(row.get("Volume")),
                )
            )

        observations.sort(key=lambda observation: observation.date)
        return observations
