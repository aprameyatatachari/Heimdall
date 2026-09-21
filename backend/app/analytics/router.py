"""Analytics endpoints: portfolio summary and analysis runs."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Path, Query, status

from app.analytics.dependencies import AnalyticsServiceDep
from app.analytics.models import AnalysisRun
from app.analytics.schemas import (
    AnalysisRunRequest,
    AnalysisRunResponse,
    AnalysisRunSummary,
    HoldingSummaryResponse,
    PortfolioSummaryResponse,
    RiskResultResponse,
)
from app.analytics.snapshot import PortfolioSnapshot
from app.auth.dependencies import CurrentUser
from app.common.disclaimer import DISCLAIMER
from app.common.schemas import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.portfolios.dependencies import PortfolioServiceDep

portfolio_router = APIRouter(prefix="/portfolios", tags=["analytics"])
runs_router = APIRouter(prefix="/analysis-runs", tags=["analytics"])

PortfolioIdPath = Path(description="Portfolio identifier.")
RunIdPath = Path(description="Analysis run identifier.")
PageLimit = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
PageOffset = Query(default=0, ge=0)


def _summary_response(snapshot: PortfolioSnapshot) -> PortfolioSummaryResponse:
    """Map a snapshot into its API representation."""
    total_value = snapshot.total_value
    cost_basis = snapshot.total_cost_basis
    weights = snapshot.weights()

    holdings = [
        HoldingSummaryResponse(
            symbol=holding.symbol,
            name=holding.name,
            sector=holding.sector,
            quantity=holding.quantity,
            average_cost=holding.average_cost,
            cost_basis=holding.cost_basis,
            latest_price=holding.latest_price,
            latest_price_date=holding.latest_price_date,
            market_value=holding.market_value,
            weight=weights.get(holding.symbol),
            unrealized_profit_loss=(
                None if holding.market_value is None else holding.market_value - holding.cost_basis
            ),
        )
        for holding in snapshot.holdings
    ]

    return PortfolioSummaryResponse(
        portfolio_id=snapshot.portfolio_id,
        name=snapshot.portfolio_name,
        base_currency=snapshot.base_currency,
        benchmark_symbol=snapshot.benchmark_symbol,
        data_as_of=snapshot.data_as_of,
        holdings_count=len(snapshot.holdings),
        priced_holdings_count=len(snapshot.priced_holdings),
        unpriced_symbols=snapshot.unpriced_symbols,
        total_market_value=total_value,
        total_cost_basis=cost_basis,
        unrealized_profit_loss=total_value - cost_basis,
        unrealized_profit_loss_percent=(
            float((total_value - cost_basis) / cost_basis) if cost_basis > 0 else None
        ),
        largest_position_weight=max(weights.values(), default=None),
        sector_weights=snapshot.sector_weights(),
        unknown_sector_weight=snapshot.unknown_sector_weight,
        holdings=sorted(holdings, key=lambda item: item.symbol),
        disclaimer=DISCLAIMER,
    )


@portfolio_router.get(
    "/{portfolio_id}/summary",
    response_model=PortfolioSummaryResponse,
    summary="Portfolio valuation summary",
    description=(
        "Values every holding at its newest stored price. Holdings with no stored "
        "price are listed under `unpriced_symbols` and excluded from the total and "
        "the weights, rather than being counted as zero. `data_as_of` is the newest "
        "price date actually used, which may be older than today."
    ),
)
async def get_portfolio_summary(
    current_user: CurrentUser,
    service: AnalyticsServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> PortfolioSummaryResponse:
    """Return the current valuation of a portfolio."""
    snapshot = await service.get_snapshot(portfolio_id=portfolio_id, user_id=current_user.id)
    return _summary_response(snapshot)


@portfolio_router.post(
    "/{portfolio_id}/analysis-runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a risk analysis",
    description=(
        "Computes performance and risk metrics over a window and stores the result "
        "with its parameters, so it can be explained and reproduced later.\n\n"
        "A metric that cannot be computed is returned with a null value and a reason, "
        "and the run's status becomes `partial`. Missing data is never reported as zero.\n\n"
        "Portfolio returns use **today's weights applied to historical asset returns**. "
        "That assumption is stated in the run's `notes` and on each affected metric."
    ),
)
async def create_analysis_run(
    payload: AnalysisRunRequest,
    current_user: CurrentUser,
    service: AnalyticsServiceDep,
    portfolio_service: PortfolioServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> AnalysisRunResponse:
    """Run and store an analysis."""
    entry = await portfolio_service.get(portfolio_id=portfolio_id, user_id=current_user.id)

    parameters = service.resolve_parameters(
        start=payload.start,
        end=payload.end,
        confidence=payload.confidence,
        var_method=payload.var_method,
        frequency=payload.frequency,
        annual_risk_free_rate=payload.annual_risk_free_rate,
        benchmark_symbol=payload.benchmark_symbol,
        minimum_observations=payload.minimum_observations,
        portfolio_benchmark=entry.portfolio.benchmark_symbol,
    )

    run = await service.run_analysis(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        parameters=parameters,
    )
    return _run_response(run)


@portfolio_router.get(
    "/{portfolio_id}/analysis-runs",
    response_model=Page[AnalysisRunSummary],
    summary="List analysis runs",
    description="Returns a portfolio's stored analysis runs, newest first.",
)
async def list_analysis_runs(
    current_user: CurrentUser,
    service: AnalyticsServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[AnalysisRunSummary]:
    """List a portfolio's analysis runs."""
    runs, total = await service.list_runs(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return Page[AnalysisRunSummary](
        items=[
            AnalysisRunSummary(
                id=run.id,
                portfolio_id=run.portfolio_id,
                analysis_type=run.analysis_type,
                status=run.status,
                data_as_of=run.data_as_of,
                created_at=run.created_at,
                completed_at=run.completed_at,
                result_count=len(run.results),
            )
            for run in runs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@runs_router.get(
    "/{run_id}",
    response_model=AnalysisRunResponse,
    summary="Get an analysis run",
    description="Returns a stored run with every metric, its unit, and its assumptions.",
)
async def get_analysis_run(
    current_user: CurrentUser,
    service: AnalyticsServiceDep,
    run_id: uuid.UUID = RunIdPath,
) -> AnalysisRunResponse:
    """Return one stored analysis run."""
    run = await service.get_run(run_id=run_id, user_id=current_user.id)
    return _run_response(run)


def _run_response(run: AnalysisRun) -> AnalysisRunResponse:
    return AnalysisRunResponse(
        id=run.id,
        portfolio_id=run.portfolio_id,
        analysis_type=run.analysis_type,
        status=run.status,
        parameters=run.parameters,
        data_as_of=run.data_as_of,
        notes=run.notes,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
        results=[
            RiskResultResponse(
                metric=result.metric,
                value=_clean(result.value),
                unit=result.unit,
                metadata=result.result_metadata,
                unavailable_reason=result.unavailable_reason,
            )
            for result in run.results
        ],
    )


def _clean(value: Decimal | None) -> Decimal | None:
    """Drop trailing zeros so stored values read naturally."""
    if value is None:
        return None
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    # `normalize` can render an integer in scientific notation; undo that.
    if isinstance(exponent, int) and exponent > 0:
        return normalized.quantize(Decimal(1))
    return normalized
