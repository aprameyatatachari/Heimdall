"""Asset search, price, and market-data refresh endpoints."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Path, Query

from app.auth.dependencies import CurrentUser
from app.market_data.dependencies import MarketDataServiceDep
from app.market_data.schemas import (
    AssetRefreshResult,
    AssetSearchItem,
    AssetSearchResponse,
    DataQualityNote,
    MarketDataRefreshResponse,
    PriceBarResponse,
    PriceSeriesResponse,
    RefreshFailure,
)
from app.market_data.service import IngestResult
from app.market_data.validation import ObservationProblem
from app.portfolios.dependencies import PortfolioServiceDep

assets_router = APIRouter(prefix="/assets", tags=["market data"])
portfolio_market_data_router = APIRouter(prefix="/portfolios", tags=["market data"])

SymbolPath = Path(description="Ticker symbol, for example AAPL.")
PortfolioIdPath = Path(description="Portfolio identifier.")
SearchQuery = Query(min_length=1, max_length=64, description="Symbol or name fragment.")
SearchLimit = Query(default=10, ge=1, le=50)
StartDateQuery = Query(default=None, description="Inclusive start date.")
EndDateQuery = Query(default=None, description="Inclusive end date.")
RefreshFlagQuery = Query(default=True, description="Fetch missing trading days before answering.")


def _note(problem: ObservationProblem) -> DataQualityNote:
    return DataQualityNote(
        date=problem.observation_date,
        issue=str(problem.issue),
        message=problem.message,
        rejected=problem.rejected,
    )


def _refresh_result(result: IngestResult) -> AssetRefreshResult:
    return AssetRefreshResult(
        symbol=result.symbol,
        asset_id=result.asset_id,
        up_to_date=result.was_up_to_date,
        ranges_fetched=len(result.ranges_fetched),
        observations_received=result.observations_received,
        bars_written=result.bars_written,
        observations_rejected=result.rejected,
        observations_flagged=result.flagged,
        latest_date=result.latest_stored_date,
        staleness_trading_days=result.staleness_trading_days,
        notes=[_note(problem) for problem in result.problems],
    )


@assets_router.get(
    "/search",
    response_model=AssetSearchResponse,
    summary="Search instruments",
    description=(
        "Searches the configured market-data source for instruments by symbol or "
        "name. Results come from the data source, not from Heimdall's own records."
    ),
)
async def search_assets(
    current_user: CurrentUser,
    service: MarketDataServiceDep,
    query: str = SearchQuery,
    limit: int = SearchLimit,
) -> AssetSearchResponse:
    """Search for instruments."""
    del current_user  # authentication only; search is not user-specific
    items = await service.search(query, limit=limit)
    return AssetSearchResponse(
        query=query,
        source=service.source,
        items=[
            AssetSearchItem(
                symbol=item.symbol,
                name=item.name,
                asset_type=item.asset_type,
                exchange=item.exchange,
                currency=item.currency,
            )
            for item in items
        ],
    )


@assets_router.get(
    "/{symbol}/prices",
    response_model=PriceSeriesResponse,
    summary="Daily price history",
    description=(
        "Returns stored daily bars for a symbol, fetching any missing trading days "
        "from the data source first. `adjusted_close` is the series used for every "
        "return calculation. Weekends are never treated as missing data."
    ),
)
async def get_asset_prices(
    current_user: CurrentUser,
    service: MarketDataServiceDep,
    symbol: str = SymbolPath,
    start: date | None = StartDateQuery,
    end: date | None = EndDateQuery,
    refresh: bool = RefreshFlagQuery,
) -> PriceSeriesResponse:
    """Return a symbol's daily price history."""
    del current_user
    asset, bars = await service.get_prices(
        symbol=symbol,
        start=start,
        end=end,
        ensure_fresh=refresh,
    )

    latest = bars[-1].date if bars else None
    staleness = None
    if latest is not None:
        from app.market_data.calendar import trading_days_between

        staleness = trading_days_between(latest, end or date.today())

    return PriceSeriesResponse(
        symbol=asset.symbol,
        name=asset.name,
        currency=asset.currency,
        source=service.source,
        start=bars[0].date if bars else None,
        end=latest,
        observation_count=len(bars),
        staleness_trading_days=staleness,
        bars=[PriceBarResponse.model_validate(bar) for bar in bars],
    )


@portfolio_market_data_router.post(
    "/{portfolio_id}/market-data/refresh",
    response_model=MarketDataRefreshResponse,
    summary="Refresh market data for a portfolio",
    description=(
        "Fetches any missing daily bars for every holding in the portfolio. "
        "Repeating the call is safe: ingestion is idempotent, keyed by asset, date, "
        "and source. An asset that cannot be refreshed is reported under `failures` "
        "without preventing the others from updating."
    ),
)
async def refresh_portfolio_market_data(
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    service: MarketDataServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    start: date | None = StartDateQuery,
    end: date | None = EndDateQuery,
) -> MarketDataRefreshResponse:
    """Refresh every holding's price history."""
    portfolio = await portfolio_service.get_with_positions(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )

    assets = []
    for position in portfolio.positions:
        # Resolving enriches placeholder assets created by a CSV import.
        assets.append(await service.resolve_asset(position.asset.symbol))

    summary = await service.refresh_assets(assets, start=start, end=end)
    window = service.resolve_window(start, end)

    return MarketDataRefreshResponse(
        portfolio_id=portfolio.id,
        data_as_of=summary.data_as_of,
        source=service.source,
        requested_start=window.start,
        requested_end=window.end,
        assets_refreshed=len(summary.results),
        bars_written=summary.bars_written,
        results=[_refresh_result(result) for result in summary.results],
        failures=[
            RefreshFailure(symbol=symbol, message=message) for symbol, message in summary.failures
        ],
    )
