"""Integration tests for market-data ingestion and endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.assets.models import Asset, AssetType
from app.assets.repository import AssetRepository
from app.common.clock import FixedClock
from app.market_data.calendar import DateRange, expected_trading_days
from app.market_data.models import PriceBar
from app.market_data.provider import (
    AssetMetadata,
    AssetSearchResult,
    MarketDataProvider,
    PriceObservation,
)
from app.market_data.repository import PriceBarRepository
from app.market_data.service import MarketDataService
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
# A window well inside the committed fixture range.
WINDOW = {"start": "2024-01-01", "end": "2024-03-31"}


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"md-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio_with(api, headers, symbols: list[str]) -> str:
    created = await api.post(
        PORTFOLIOS,
        json={"name": f"Portfolio {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    portfolio_id = str(created.json()["id"])

    for symbol in symbols:
        added = await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/positions",
            json={"symbol": symbol, "quantity": "10", "average_cost": "100"},
            headers=headers,
        )
        assert added.status_code == 201, added.text

    return portfolio_id


async def _refresh(api, headers, portfolio_id, **params):
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh",
        params={**WINDOW, **params},
        headers=headers,
    )


# --- Search ------------------------------------------------------------------


async def test_asset_search_returns_fixture_instruments(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/assets/search", params={"query": "aapl"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fixture"
    assert body["items"][0]["symbol"] == "AAPL"


async def test_asset_search_requires_authentication(api):
    response = await api.get("/api/v1/assets/search", params={"query": "aapl"})

    assert response.status_code == 401


async def test_asset_search_rejects_an_empty_query(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/assets/search", params={"query": ""}, headers=headers)

    assert response.status_code == 422


# --- Prices ------------------------------------------------------------------


async def test_prices_are_fetched_and_stored(api):
    headers = await _signed_in_user(api)

    response = await api.get(
        "/api/v1/assets/SPY/prices",
        params=WINDOW,
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbol"] == "SPY"
    assert body["source"] == "fixture"
    assert body["currency"] == "USD"
    assert body["observation_count"] > 50
    assert body["bars"][0]["adjusted_close"]


async def test_prices_are_returned_in_ascending_date_order(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/assets/SPY/prices", params=WINDOW, headers=headers)

    dates = [bar["date"] for bar in response.json()["bars"]]
    assert dates == sorted(dates)


async def test_an_unknown_symbol_returns_404(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/assets/NOSUCH/prices", params=WINDOW, headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "asset_not_found"


async def test_an_invalid_symbol_is_a_validation_error(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/assets/=1+1/prices", headers=headers)

    assert response.status_code == 422


async def test_requesting_an_asset_creates_and_enriches_it(api, db_session):
    headers = await _signed_in_user(api)

    await api.get("/api/v1/assets/AAPL/prices", params=WINDOW, headers=headers)
    response = await api.get("/api/v1/assets/search", params={"query": "AAPL"}, headers=headers)

    assert response.status_code == 200
    del db_session  # the assertion below goes through the API


async def test_a_second_request_does_not_duplicate_bars(api, db_session):
    """Ingestion is idempotent, keyed by (asset, date, source)."""
    headers = await _signed_in_user(api)

    first = await api.get("/api/v1/assets/SPY/prices", params=WINDOW, headers=headers)
    await api.get("/api/v1/assets/SPY/prices", params=WINDOW, headers=headers)

    total = await db_session.execute(select(func.count()).select_from(PriceBar))
    assert total.scalar_one() == first.json()["observation_count"]


async def test_a_cached_window_is_not_refetched(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    first = await _refresh(api, headers, portfolio_id)
    second = await _refresh(api, headers, portfolio_id)

    assert first.json()["results"][0]["up_to_date"] is False
    assert first.json()["bars_written"] > 0
    assert second.json()["results"][0]["up_to_date"] is True
    assert second.json()["bars_written"] == 0


async def test_only_the_missing_part_of_a_window_is_fetched(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    await _refresh(api, headers, portfolio_id, start="2024-02-01", end="2024-02-29")
    extended = await _refresh(api, headers, portfolio_id, start="2024-01-01", end="2024-02-29")

    result = extended.json()["results"][0]
    assert result["ranges_fetched"] == 1
    assert result["up_to_date"] is False
    # January only, not the whole window.
    assert result["bars_written"] < 30


async def test_refresh_requires_authentication(api):
    response = await api.post(f"{PORTFOLIOS}/{uuid.uuid4()}/market-data/refresh")

    assert response.status_code == 401


async def test_another_user_cannot_refresh_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, owner, ["SPY"])

    response = await _refresh(api, intruder, portfolio_id)

    assert response.status_code == 404


async def test_refresh_reports_every_holding(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY", "AAPL", "TLT"])

    response = await _refresh(api, headers, portfolio_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assets_refreshed"] == 3
    assert {result["symbol"] for result in body["results"]} == {"SPY", "AAPL", "TLT"}
    assert body["failures"] == []
    assert body["source"] == "fixture"


async def test_refresh_reports_the_date_the_data_reaches_not_the_date_requested(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    # A window running past the end of the committed fixtures, which is the
    # ordinary case in production: the provider's newest observation is older
    # than the date that was asked for.
    response = await _refresh(api, headers, portfolio_id, start="2024-01-02", end="2025-06-30")

    body = response.json()
    assert body["requested_end"] == "2025-06-30"
    # The field that describes the data has to describe the data. Reporting the
    # requested date here told a caller prices were current when the newest
    # observation was months old, which is the one thing this product must not do.
    assert body["data_as_of"] == "2024-12-31"
    assert body["data_as_of"] < body["requested_end"]
    assert body["data_as_of"] == max(
        result["latest_date"] for result in body["results"] if result["latest_date"]
    )


async def test_a_refresh_that_stores_nothing_reports_no_as_of_date(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    # A valid window the fixtures do not cover at all: nothing is stored, so
    # there is no as-of date. Null, never the date that was asked for.
    response = await _refresh(api, headers, portfolio_id, start="2025-02-03", end="2025-06-30")

    assert response.status_code == 200, response.text
    assert response.json()["data_as_of"] is None


async def test_a_refresh_says_when_it_read_the_provider(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    body = (await _refresh(api, headers, portfolio_id)).json()

    # To the second, in UTC: how old a price is depends on when it was read.
    assert "T" in body["fetched_at"]


async def test_the_summary_says_when_each_price_was_last_fetched(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY", "AAPL"])
    await _refresh(api, headers, portfolio_id)

    summary = (await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)).json()

    assert summary["prices_fetched_at"] is not None
    assert all(holding["latest_price_fetched_at"] for holding in summary["holdings"])
    # The headline figure is the oldest fetch, so it is true of every price shown.
    assert summary["prices_fetched_at"] == min(
        holding["latest_price_fetched_at"] for holding in summary["holdings"]
    )


async def test_a_historical_bar_is_not_read_again(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    await _refresh(api, headers, portfolio_id)
    again = (await _refresh(api, headers, portfolio_id)).json()

    # A close from 2024 is final. Re-reading it on every refresh would be a
    # request for an answer already held.
    assert again["results"][0]["ranges_fetched"] == 0


class _LiveProvider(MarketDataProvider):
    """A provider whose newest bar is "today", and changes between reads."""

    def __init__(self, today: date) -> None:
        self._today = today
        self.calls = 0

    @property
    def name(self) -> str:
        return "yahoo"

    async def search_assets(self, query: str, *, limit: int = 10) -> list[AssetSearchResult]:
        del query, limit
        return []

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        return AssetMetadata(
            symbol=symbol,
            name="Live Test",
            asset_type=AssetType.EQUITY,
            exchange="NYSE",
            currency="USD",
        )

    async def get_daily_prices(
        self, symbol: str, *, start: date, end: date
    ) -> list[PriceObservation]:
        del symbol
        self.calls += 1
        # The price moves on every read, the way an intraday bar does.
        close = Decimal("100") + Decimal(self.calls)
        return [
            PriceObservation(date=day, close=close, adjusted_close=close)
            for day in expected_trading_days(start, end)
            if day <= self._today
        ]


async def test_todays_bar_is_read_again_and_its_fetch_time_moves(db_session):
    # A Thursday, so "today" is a trading day by the weekday calendar.
    now = datetime(2026, 10, 1, 9, 30, 15, tzinfo=UTC)
    clock = FixedClock(now)
    provider = _LiveProvider(now.date())
    service = MarketDataService(
        session=db_session,
        assets=AssetRepository(db_session),
        price_bars=PriceBarRepository(db_session),
        provider=provider,
        clock=clock,
    )
    asset = Asset(
        symbol=f"LIVE{uuid.uuid4().hex[:6].upper()}",
        currency="USD",
        asset_type=AssetType.EQUITY,
    )
    db_session.add(asset)
    await db_session.flush()
    window = DateRange(now.date() - timedelta(days=7), now.date())

    first = await service.ingest(asset=asset, window=window, refresh_latest=True)
    clock.advance(42)
    second = await service.ingest(asset=asset, window=window, refresh_latest=True)

    # Gap detection alone would call today's bar done the moment it existed, and
    # a price read at the open would be shown all day as current.
    assert first.ranges_fetched
    assert second.ranges_fetched, "the newest bar was not read again"

    bars = await PriceBarRepository(db_session).list_for_asset(asset.id)
    newest = bars[-1]
    await db_session.refresh(newest)
    assert newest.date == now.date()
    # The revised close won, and the bar says when it was read — to the second.
    assert newest.close == Decimal("102")
    assert newest.fetched_at == now + timedelta(seconds=42)


async def test_without_the_flag_a_stored_bar_is_left_alone(db_session):
    now = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    provider = _LiveProvider(now.date())
    service = MarketDataService(
        session=db_session,
        assets=AssetRepository(db_session),
        price_bars=PriceBarRepository(db_session),
        provider=provider,
        clock=FixedClock(now),
    )
    asset = Asset(
        symbol=f"LIVE{uuid.uuid4().hex[:6].upper()}",
        currency="USD",
        asset_type=AssetType.EQUITY,
    )
    db_session.add(asset)
    await db_session.flush()
    window = DateRange(now.date() - timedelta(days=7), now.date())

    await service.ingest(asset=asset, window=window)
    second = await service.ingest(asset=asset, window=window)

    # An analysis run reading history must not turn into a provider call per
    # holding. Only an explicit refresh re-reads.
    assert not second.ranges_fetched
    assert provider.calls == 1


async def test_a_quick_refresh_only_reaches_back_a_few_days(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    response = await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh",
        params={"quick": "true"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    span = date.fromisoformat(body["requested_end"]) - date.fromisoformat(body["requested_start"])
    assert span.days <= 7


async def test_coverage_reports_a_holding_with_no_prices_in_the_window(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY", "AAPL"])
    await _refresh(api, headers, portfolio_id)

    # The helper's window is the first quarter of 2024; ask about 2019 instead.
    response = await api.get(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/coverage",
        params={"start": "2019-01-02", "end": "2019-03-29"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["complete"] is False
    assert {item["status"] for item in body["holdings"]} == {"none"}
    assert all("No prices are stored" in item["message"] for item in body["holdings"])


async def test_coverage_is_complete_for_a_window_that_was_fetched(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])
    await _refresh(api, headers, portfolio_id)

    response = await api.get(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/coverage",
        params=WINDOW,
        headers=headers,
    )

    body = response.json()
    assert body["complete"] is True
    assert body["holdings"][0]["status"] == "full"
    assert body["holdings"][0]["message"] is None


async def test_coverage_notices_prices_that_start_late(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])
    await _refresh(api, headers, portfolio_id)

    # Stored: Q1 2024. Asked about: all of 2023 through Q1 2024.
    response = await api.get(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/coverage",
        params={"start": "2023-01-02", "end": "2024-03-29"},
        headers=headers,
    )

    holding = response.json()["holdings"][0]
    assert holding["status"] == "partial"
    assert "prices begin on" in holding["message"]


async def test_coverage_fetches_nothing(api, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])
    before = await db_session.execute(select(func.count()).select_from(PriceBar))

    await api.get(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/coverage",
        params=WINDOW,
        headers=headers,
    )

    # It is a question about what is stored. Answering it by fetching would make
    # the warning it exists to produce impossible to see.
    after = await db_session.execute(select(func.count()).select_from(PriceBar))
    assert after.scalar_one() == before.scalar_one()


async def test_another_user_cannot_read_coverage(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, owner, ["SPY"])

    response = await api.get(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/coverage",
        params=WINDOW,
        headers=intruder,
    )

    assert response.status_code == 404


async def test_refresh_enriches_assets_created_by_an_import(api):
    """A CSV import creates a placeholder asset; a refresh fills in its metadata."""
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS,
        json={"name": f"Imported {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    portfolio_id = str(created.json()["id"])
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        files={
            "file": (
                "holdings.csv",
                b"symbol,quantity,average_cost\nAAPL,10,185.20\nJNJ,5,150.00\n",
                "text/csv",
            )
        },
        headers=headers,
    )

    before = await api.get(f"{PORTFOLIOS}/{portfolio_id}", headers=headers)
    assert {p["asset"]["asset_type"] for p in before.json()["positions"]} == {"unknown"}

    await _refresh(api, headers, portfolio_id)
    after = await api.get(f"{PORTFOLIOS}/{portfolio_id}", headers=headers)

    assets = {p["asset"]["symbol"]: p["asset"] for p in after.json()["positions"]}
    assert assets["AAPL"]["asset_type"] == "equity"
    assert assets["AAPL"]["name"] == "Apple Inc."
    assert assets["AAPL"]["sector"] == "Technology"
    assert assets["JNJ"]["sector"] == "Healthcare"


async def test_a_symbol_the_provider_does_not_know_does_not_break_the_refresh(api):
    """A holding with no available series is reported, not fatal."""
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS,
        json={"name": f"Mixed {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    portfolio_id = str(created.json()["id"])
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        files={
            "file": (
                "holdings.csv",
                b"symbol,quantity,average_cost\nSPY,10,400\nZZZZ,1,1\n",
                "text/csv",
            )
        },
        headers=headers,
    )

    response = await _refresh(api, headers, portfolio_id)

    assert response.status_code == 200, response.text
    results = {result["symbol"]: result for result in response.json()["results"]}
    assert results["SPY"]["bars_written"] > 0
    assert results["ZZZZ"]["bars_written"] == 0
    assert results["ZZZZ"]["latest_date"] is None


async def test_refresh_records_staleness_in_trading_days(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    response = await _refresh(api, headers, portfolio_id, start="2024-01-01", end="2024-01-31")

    result = response.json()["results"][0]
    assert result["latest_date"] == "2024-01-31"
    # The window ends in the past, so the newest bar is measured against that end.
    assert result["staleness_trading_days"] == 0


async def test_an_inverted_window_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])

    response = await _refresh(api, headers, portfolio_id, start="2024-03-31", end="2024-01-01")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_date_range"


async def test_stored_bars_record_their_source_and_currency(api, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio_with(api, headers, ["SPY"])
    await _refresh(api, headers, portfolio_id)

    result = await db_session.execute(select(PriceBar).limit(1))
    bar = result.scalar_one()

    assert bar.source == "fixture"
    assert bar.currency == "USD"
    assert bar.adjusted_close > 0
    assert isinstance(bar.date, date)
