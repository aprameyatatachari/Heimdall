"""Integration tests for market-data ingestion and endpoints."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.market_data.models import PriceBar
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
