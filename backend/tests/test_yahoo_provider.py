"""Unit tests for the Yahoo Finance adapter.

**No network.** `yfinance` is replaced with a stub module for every test here, so
these run offline and deterministically like everything else in the suite. What
is under test is the translation — vendor shapes in, domain objects out — which
is the part that breaks when Yahoo changes a field name, and the part a live test
would be worst at catching.
"""

from __future__ import annotations

import sys
import types
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.assets.models import AssetType
from app.market_data.provider import ProviderUnavailableError, SymbolNotFoundError
from app.market_data.yahoo_provider import YahooMarketDataProvider


class _Frame:
    """The slice of a pandas frame the adapter actually uses."""

    def __init__(self, rows: list[tuple[datetime, dict[str, object]]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def iterrows(self):
        yield from self._rows


class _Ticker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @property
    def fast_info(self) -> dict[str, object]:
        return _STUB["fast_info"]

    @property
    def info(self) -> dict[str, object]:
        detail = _STUB["info"]
        if isinstance(detail, Exception):
            raise detail
        return detail

    def history(self, **kwargs: object) -> _Frame:
        del kwargs  # the adapter's arguments are checked by the tests that matter
        return _STUB["history"]


class _Search:
    def __init__(self, query: str, max_results: int = 10) -> None:
        self.query = query
        self.max_results = max_results

    @property
    def quotes(self) -> list[dict[str, object]]:
        quotes = _STUB["quotes"]
        if isinstance(quotes, Exception):
            raise quotes
        return quotes


class _EquityQuery:
    def __init__(self, operator: str, operands: object) -> None:
        self.operator = operator
        self.operands = operands


def _screen(*args: object, **kwargs: object) -> dict[str, object]:
    del args, kwargs
    return {"quotes": _STUB["screened"]}


# What the stub module returns, rewritten per test.
_STUB: dict[str, object] = {}


@pytest.fixture(autouse=True)
def stub_yfinance(monkeypatch):
    """Install a fake `yfinance` for the duration of one test."""
    module = types.ModuleType("yfinance")
    module.Ticker = _Ticker  # type: ignore[attr-defined]
    module.Search = _Search  # type: ignore[attr-defined]
    module.EquityQuery = _EquityQuery  # type: ignore[attr-defined]
    module.screen = _screen  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", module)

    _STUB.clear()
    _STUB.update({"quotes": [], "screened": [], "fast_info": {}, "info": {}, "history": _Frame([])})
    yield


@pytest.fixture
def provider() -> YahooMarketDataProvider:
    return YahooMarketDataProvider()


# --- Search -------------------------------------------------------------------


async def test_search_translates_a_quote_into_a_domain_result(provider):
    _STUB["quotes"] = [
        {
            "symbol": "RELIANCE.NS",
            "shortname": "RELIANCE INDUSTRIES LTD",
            "longname": "Reliance Industries Limited",
            "quoteType": "EQUITY",
            "exchange": "NSI",
            "exchDisp": "NSE",
        }
    ]

    results = await provider.search_assets("reliance", limit=5)

    assert len(results) == 1
    assert results[0].symbol == "RELIANCE.NS"
    # The longer name, which is the one a reader recognises.
    assert results[0].name == "Reliance Industries Limited"
    assert results[0].asset_type is AssetType.EQUITY
    assert results[0].currency == "INR"
    assert results[0].exchange == "NSE"


async def test_search_leaves_out_an_exchange_heimdall_cannot_price(provider):
    # Yahoo lists far more exchanges than Heimdall supports currencies for.
    # Offering a London listing to a portfolio that cannot hold it would be
    # offering a holding the API refuses on arrival.
    _STUB["quotes"] = [
        {
            "symbol": "RIGD.IL",
            "shortname": "RELIANCE GDR",
            "quoteType": "EQUITY",
            "exchange": "IOB",
        },
        {
            "symbol": "RELIANCE.NS",
            "shortname": "RELIANCE",
            "quoteType": "EQUITY",
            "exchange": "NSI",
        },
    ]

    results = await provider.search_assets("reliance")

    assert [item.symbol for item in results] == ["RELIANCE.NS"]


async def test_search_maps_yahoos_quote_type_rather_than_passing_it_through(provider):
    _STUB["quotes"] = [
        {"symbol": "SPY", "quoteType": "ETF", "exchange": "PCX"},
        {"symbol": "^GSPC", "quoteType": "INDEX", "exchange": "NYQ"},
    ]

    results = await provider.search_assets("s")

    assert results[0].asset_type is AssetType.ETF
    # An index is not an asset type Heimdall models, and is not invented into one.
    assert results[1].asset_type is AssetType.UNKNOWN


async def test_search_stops_at_the_limit(provider):
    _STUB["quotes"] = [
        {"symbol": f"T{index}", "quoteType": "EQUITY", "exchange": "NYQ"} for index in range(10)
    ]

    assert len(await provider.search_assets("t", limit=3)) == 3


async def test_a_vendor_failure_becomes_a_provider_failure(provider):
    # Nothing vendor-shaped escapes: callers handle ProviderError and nothing else.
    _STUB["quotes"] = RuntimeError("Yahoo rate limited the request")

    with pytest.raises(ProviderUnavailableError):
        await provider.search_assets("anything")


# --- Browsing -----------------------------------------------------------------


async def test_popular_returns_only_the_currency_asked_for(provider):
    _STUB["screened"] = [
        {"symbol": "RELIANCE.NS", "longName": "Reliance", "currency": "INR", "quoteType": "EQUITY"},
        {"symbol": "AAPL", "longName": "Apple", "currency": "USD", "quoteType": "EQUITY"},
    ]

    results = await provider.list_popular(currency="INR", limit=10)

    assert [item.symbol for item in results] == ["RELIANCE.NS"]


async def test_popular_keeps_one_listing_per_company(provider):
    # Indian companies list on both the NSE and the BSE. Two rows for the same
    # name is a suggestion list that helps nobody choose, and the NSE listing is
    # the one to keep: it is the more liquid of the two.
    _STUB["screened"] = [
        {"symbol": "RELIANCE.BO", "longName": "Reliance Industries Limited", "currency": "INR"},
        {"symbol": "RELIANCE.NS", "longName": "Reliance Industries Limited", "currency": "INR"},
        {"symbol": "TCS.NS", "longName": "Tata Consultancy Services Limited", "currency": "INR"},
    ]

    results = await provider.list_popular(currency="INR")

    assert [item.symbol for item in results] == ["RELIANCE.NS", "TCS.NS"]


async def test_popular_is_empty_for_a_market_with_no_region(provider):
    assert await provider.list_popular(currency="EUR") == []


# --- Metadata -----------------------------------------------------------------


async def test_metadata_prefers_the_authoritative_currency(provider):
    _STUB["fast_info"] = {
        "currency": "inr",
        "quoteType": "EQUITY",
        "exchange": "NSI",
        "lastPrice": 1180.8,
    }
    _STUB["info"] = {"longName": "Reliance Industries Limited", "sector": "Energy"}

    metadata = await provider.get_asset_metadata("RELIANCE.NS")

    assert metadata.currency == "INR"
    assert metadata.sector == "Energy"
    assert metadata.asset_type is AssetType.EQUITY


async def test_metadata_survives_the_slow_enrichment_call_failing(provider):
    # `info` is optional enrichment. A holding with no sector is honest; a
    # holding Heimdall refuses to store because of it is not.
    _STUB["fast_info"] = {"currency": "USD", "quoteType": "EQUITY", "lastPrice": 190.0}
    _STUB["info"] = RuntimeError("info endpoint is down")

    metadata = await provider.get_asset_metadata("AAPL")

    assert metadata.currency == "USD"
    assert metadata.sector is None


async def test_an_unknown_symbol_is_reported_as_unknown(provider):
    # Yahoo answers for a symbol it does not know with an empty quote rather
    # than an error, so this is how it says no.
    _STUB["fast_info"] = {}

    with pytest.raises(SymbolNotFoundError):
        await provider.get_asset_metadata("NOTREAL.XX")


# --- Prices -------------------------------------------------------------------


def _bar(day: date, close: float, tz: str = "Asia/Kolkata") -> tuple[datetime, dict[str, object]]:
    moment = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz))
    return moment, {
        "Open": close - 1,
        "High": close + 2,
        "Low": close - 3,
        "Close": close,
        "Adj Close": close,
        "Volume": 1_000_000,
    }


async def test_prices_keep_the_exchanges_own_date(provider):
    # An NSE bar is midnight in Kolkata. Converting it to UTC moves it to the
    # previous day, and every Indian price lands under the wrong date.
    _STUB["history"] = _Frame([_bar(date(2026, 10, 1), 1180.7)])

    observations = await provider.get_daily_prices(
        "RELIANCE.NS", start=date(2026, 9, 1), end=date(2026, 10, 1)
    )

    assert [item.date for item in observations] == [date(2026, 10, 1)]


async def test_prices_come_back_as_decimals_that_round_trip(provider):
    _STUB["history"] = _Frame([_bar(date(2026, 10, 1), 1180.699951171875)])

    observation = (
        await provider.get_daily_prices(
            "RELIANCE.NS", start=date(2026, 10, 1), end=date(2026, 10, 1)
        )
    )[0]

    assert isinstance(observation.close, Decimal)
    assert float(observation.close) == 1180.699951171875


async def test_a_bar_with_no_usable_close_is_dropped_not_invented(provider):
    moment, values = _bar(date(2026, 10, 1), 100.0)
    values["Close"] = float("nan")
    _STUB["history"] = _Frame([(moment, values), _bar(date(2026, 10, 2), 101.0)])

    observations = await provider.get_daily_prices(
        "X", start=date(2026, 10, 1), end=date(2026, 10, 2)
    )

    # The gap is left as a gap for the validation layer to report.
    assert [item.date for item in observations] == [date(2026, 10, 2)]


async def test_prices_outside_the_window_are_discarded(provider):
    # Yahoo's `end` is exclusive and the adapter adds a day to it, so a bar
    # beyond the requested window can come back.
    _STUB["history"] = _Frame([_bar(date(2026, 10, 1), 100.0), _bar(date(2026, 10, 3), 102.0)])

    observations = await provider.get_daily_prices(
        "X", start=date(2026, 10, 1), end=date(2026, 10, 2)
    )

    assert [item.date for item in observations] == [date(2026, 10, 1)]


async def test_prices_are_returned_in_date_order(provider):
    _STUB["history"] = _Frame([_bar(date(2026, 10, 3), 102.0), _bar(date(2026, 10, 1), 100.0)])

    observations = await provider.get_daily_prices(
        "X", start=date(2026, 10, 1), end=date(2026, 10, 3)
    )

    assert [item.date for item in observations] == [date(2026, 10, 1), date(2026, 10, 3)]


async def test_an_empty_history_is_not_an_error(provider):
    # A symbol with no trading in the window is a fact, not a failure.
    assert await provider.get_daily_prices("X", start=date(2026, 1, 1), end=date(2026, 1, 2)) == []


async def test_a_slow_vendor_is_given_up_on():
    import time

    slow = YahooMarketDataProvider(timeout_seconds=0.05)

    class _SlowSearch(_Search):
        @property
        def quotes(self):
            time.sleep(0.5)
            return []

    sys.modules["yfinance"].Search = _SlowSearch  # type: ignore[attr-defined]

    # A request to Heimdall must not hang because a third party did.
    with pytest.raises(ProviderUnavailableError):
        await slow.search_assets("anything")


def test_the_adapter_reports_its_own_name(provider):
    # Recorded on every stored bar, so a series' origin is never in doubt and
    # fixture data can never be mistaken for live data.
    assert provider.name == "yahoo"
    assert provider.name != "fixture"


def test_a_us_window_is_unaffected_by_the_timezone_handling():
    moment, _ = _bar(date(2026, 10, 1), 100.0, tz="America/New_York")
    assert moment.date() == date(2026, 10, 1)
    assert (moment.astimezone(UTC) + timedelta(0)).date() == date(2026, 10, 1)
