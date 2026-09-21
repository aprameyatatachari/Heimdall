"""Analytics service wiring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.analytics.repository import AnalysisRunRepository
from app.analytics.service import AnalyticsService
from app.analytics.snapshot import SnapshotBuilder
from app.common.dependencies import ClockDep, SessionDep
from app.market_data.dependencies import MarketDataServiceDep
from app.market_data.repository import PriceBarRepository
from app.portfolios.repository import PortfolioRepository, PositionRepository


def get_snapshot_builder(
    session: SessionDep,
    market_data: MarketDataServiceDep,
) -> SnapshotBuilder:
    """Build the snapshot builder, bound to the configured price source."""
    return SnapshotBuilder(
        session=session,
        positions=PositionRepository(session),
        price_bars=PriceBarRepository(session),
        source=market_data.source,
    )


SnapshotBuilderDep = Annotated[SnapshotBuilder, Depends(get_snapshot_builder)]


def get_analytics_service(
    session: SessionDep,
    snapshots: SnapshotBuilderDep,
    market_data: MarketDataServiceDep,
    clock: ClockDep,
) -> AnalyticsService:
    """Build the analytics service for this request."""
    return AnalyticsService(
        session=session,
        portfolios=PortfolioRepository(session),
        runs=AnalysisRunRepository(session),
        snapshots=snapshots,
        market_data=market_data,
        clock=clock,
    )


AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
