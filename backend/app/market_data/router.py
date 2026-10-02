"""Asset search, price, and market-data refresh endpoints."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Path, Query

from app.auth.dependencies import CurrentUser
from app.common.dependencies import ClockDep
from app.market_data.dependencies import MarketDataServiceDep
from app.market_data.schemas import (
    AssetRefreshResult,
    AssetSearchItem,
    AssetSearchResponse,
    CoverageResponse,
    DataQualityNote,
    HoldingCoverage,
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
SearchQuery = Query(
    default=None,
    min_length=1,
    max_length=64,
    description="Symbol or name fragment. Omit to browse the largest instruments instead.",
)
CurrencyQuery = Query(
    default=None,
    min_length=3,
    max_length=3,
    description="Restrict results to instruments priced in this currency.",
)
SearchLimit = Query(default=10, ge=1, le=50)
StartDateQuery = Query(default=None, description="Inclusive start date.")
EndDateQuery = Query(default=None, description="Inclusive end date.")
RefreshFlagQuery = Query(default=True, description="Fetch missing trading days before answering.")
QuickFlagQuery = Query(
    default=False,
    description=(
        "Only bring the newest prices up to date: a short recent window, and no "
        "re-reading of instrument metadata. What a page load or a refresh button "
        "wants, as opposed to building history."
    ),
)
CoverageStartQuery = Query(description="Inclusive start of the window.")
CoverageEndQuery = Query(description="Inclusive end of the window.")

# How far back a quick refresh reaches. Long enough to span a holiday weekend, so
# a refresh on the Tuesday after one still finds the last bar it has.
QUICK_REFRESH_DAYS = 7

# A holding whose stored prices start this many trading days into the window, or
# stop this many before its end, is reported as only partly covered. A handful
# of missing days at either edge is a holiday, not a gap.
COVERAGE_EDGE_TOLERANCE = 5


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
    summary="Search or browse instruments",
    description=(
        "Searches the configured market-data source for instruments by symbol or "
        "name. Results come from the data source, not from Heimdall's own records. "
        "With no `query`, returns the largest instruments in the market that uses "
        "`currency` - a starting point for browsing, ordered by size, which is not "
        "a recommendation. With a `query`, `currency` filters the matches."
    ),
)
async def search_assets(
    current_user: CurrentUser,
    service: MarketDataServiceDep,
    query: str | None = SearchQuery,
    currency: str | None = CurrencyQuery,
    limit: int = SearchLimit,
) -> AssetSearchResponse:
    """Search for instruments, or browse them."""
    del current_user  # authentication only; search is not user-specific
    wanted = currency.upper() if currency else None

    if query is None or not query.strip():
        items = await service.list_popular(currency=wanted or "USD", limit=limit)
    else:
        items = await service.search(query, limit=limit)
        if wanted is not None:
            items = [item for item in items if item.currency.upper() == wanted]

    return AssetSearchResponse(
        query=query or "",
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
        "Fetches any missing daily bars for every holding in the portfolio, and "
        "re-reads the newest one, which a live provider keeps revising until the "
        "close. Repeating the call is safe: ingestion is idempotent, keyed by "
        "asset, date, and source. An asset that cannot be refreshed is reported "
        "under `failures` without preventing the others from updating. "
        "`quick=true` limits the work to the last few days and skips instrument "
        "metadata, which is what a page load wants."
    ),
)
async def refresh_portfolio_market_data(
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    service: MarketDataServiceDep,
    clock: ClockDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    start: date | None = StartDateQuery,
    end: date | None = EndDateQuery,
    quick: bool = QuickFlagQuery,
) -> MarketDataRefreshResponse:
    """Refresh every holding's price history."""
    portfolio = await portfolio_service.get_with_positions(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )

    if quick and start is None:
        start = clock.now().date() - timedelta(days=QUICK_REFRESH_DAYS)

    assets = []
    for position in portfolio.positions:
        # Resolving enriches placeholder assets created by a CSV import. A quick
        # refresh skips that for an asset already described: the metadata call is
        # the slow one, and a company's sector does not change between page loads.
        described = position.asset.name is not None
        assets.append(
            await service.resolve_asset(position.asset.symbol, enrich=not (quick and described))
        )

    summary = await service.refresh_assets(assets, start=start, end=end, refresh_latest=True)
    window = service.resolve_window(start, end)

    return MarketDataRefreshResponse(
        portfolio_id=portfolio.id,
        data_as_of=summary.data_as_of,
        source=service.source,
        requested_start=window.start,
        requested_end=window.end,
        fetched_at=clock.now(),
        assets_refreshed=len(summary.results),
        bars_written=summary.bars_written,
        results=[_refresh_result(result) for result in summary.results],
        failures=[
            RefreshFailure(symbol=symbol, message=message) for symbol, message in summary.failures
        ],
    )


@portfolio_market_data_router.get(
    "/{portfolio_id}/market-data/coverage",
    response_model=CoverageResponse,
    summary="Stored price coverage of a window",
    description=(
        "Reports, for every holding, how much of a date window its stored prices "
        "cover. Fetches nothing. It exists so a screen can say which holdings have "
        "no prices for a period before an analysis or a scenario is run over it, "
        "rather than after."
    ),
)
async def get_price_coverage(
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    service: MarketDataServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    start: date = CoverageStartQuery,
    end: date = CoverageEndQuery,
) -> CoverageResponse:
    """Report stored price coverage for a window."""
    from app.market_data.calendar import count_expected_trading_days

    portfolio = await portfolio_service.get_with_positions(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )
    window = service.resolve_window(start, end)
    assets = [position.asset for position in portfolio.positions]
    stored = await service.coverage(assets, window=window)
    expected = count_expected_trading_days(window.start, window.end)

    holdings: list[HoldingCoverage] = []
    for asset in sorted(assets, key=lambda item: item.symbol):
        found = stored.get(asset.id)
        if found is None:
            holdings.append(
                HoldingCoverage(
                    symbol=asset.symbol,
                    status="none",
                    first_date=None,
                    last_date=None,
                    observations=0,
                    expected_observations=expected,
                    message=f"No prices are stored for {asset.symbol} in this period.",
                )
            )
            continue

        first, last, count = found
        late = count_expected_trading_days(window.start, first) - 1
        early = count_expected_trading_days(last, window.end) - 1
        problems: list[str] = []
        if late > COVERAGE_EDGE_TOLERANCE:
            problems.append(f"prices begin on {first.isoformat()}")
        if early > COVERAGE_EDGE_TOLERANCE:
            problems.append(f"prices end on {last.isoformat()}")

        holdings.append(
            HoldingCoverage(
                symbol=asset.symbol,
                status="partial" if problems else "full",
                first_date=first,
                last_date=last,
                observations=count,
                expected_observations=expected,
                message=(
                    f"{asset.symbol}: {' and '.join(problems)}, so it covers only part "
                    "of this period."
                    if problems
                    else None
                ),
            )
        )

    return CoverageResponse(
        portfolio_id=portfolio.id,
        start=window.start,
        end=window.end,
        source=service.source,
        complete=all(item.status == "full" for item in holdings),
        holdings=holdings,
    )
