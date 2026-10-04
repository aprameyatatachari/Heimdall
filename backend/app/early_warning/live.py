"""Refresh, then monitor: the operation that makes the Early Warning System live.

A monitoring run evaluates stored prices. On its own it says nothing about how
old those prices are, so a run made on a timer without reading the market first
would re-examine yesterday's close every five minutes and report, each time,
that nothing had changed.

`LiveMonitor.check` is the pair in the right order. It is what a scheduler calls,
whether that is the in-process one in `scheduler.py` or a cron reaching the
protected endpoint. It acts for no signed-in user, so it performs no ownership
check: only callers that have already been authorized as a scheduler may use it.

A price that could not be read does not stop the run. The holdings that were
reached are evaluated on their new prices, and the one that was not is exactly
what the stale-data rule exists to report.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.snapshot import SnapshotBuilder
from app.assets.repository import AssetRepository
from app.common.clock import Clock
from app.config import Settings
from app.early_warning.notifications import NullNotifier
from app.early_warning.repository import (
    AlertRuleRepository,
    MonitoringRunRepository,
    WarningSignalRepository,
)
from app.early_warning.rule_types import MonitoringTriggerType
from app.early_warning.service import EarlyWarningService, MonitoringOutcome
from app.market_data.dependencies import get_market_data_provider
from app.market_data.repository import PriceBarRepository
from app.market_data.service import MarketDataService, RefreshSummary
from app.portfolios.repository import PortfolioRepository, PositionRepository
from app.stress_testing.service import StressTestingService


class LiveMonitor:
    """Reads the newest prices for a portfolio, then evaluates its rules."""

    def __init__(
        self,
        *,
        positions: PositionRepository,
        market_data: MarketDataService,
        early_warning: EarlyWarningService,
    ) -> None:
        self._positions = positions
        self._market_data = market_data
        self._early_warning = early_warning

    async def refresh_prices(self, portfolio_id: uuid.UUID) -> RefreshSummary:
        """Bring every holding's newest price up to date."""
        positions = await self._positions.list_for_portfolio(portfolio_id)
        return await self._market_data.refresh_latest_prices(
            [position.asset for position in positions]
        )

    async def check(
        self,
        portfolio_id: uuid.UUID,
        *,
        idempotency_key: str | None = None,
        record_reobservations: bool = False,
    ) -> MonitoringOutcome:
        """Refresh the portfolio's prices and run monitoring against them."""
        await self.refresh_prices(portfolio_id)
        return await self._early_warning.run_monitoring(
            portfolio_id=portfolio_id,
            user_id=None,
            trigger_type=MonitoringTriggerType.SCHEDULED,
            idempotency_key=idempotency_key,
            record_reobservations=record_reobservations,
        )


def build_live_monitor(session: AsyncSession, *, settings: Settings, clock: Clock) -> LiveMonitor:
    """Assemble a `LiveMonitor` outside a request, where nothing is injected."""
    market_data = MarketDataService(
        session=session,
        assets=AssetRepository(session),
        price_bars=PriceBarRepository(session),
        provider=get_market_data_provider(settings),
        clock=clock,
    )
    positions = PositionRepository(session)
    snapshots = SnapshotBuilder(
        session=session,
        positions=positions,
        price_bars=PriceBarRepository(session),
        source=market_data.source,
    )
    portfolios = PortfolioRepository(session)
    early_warning = EarlyWarningService(
        session=session,
        portfolios=portfolios,
        rules=AlertRuleRepository(session),
        runs=MonitoringRunRepository(session),
        signals=WarningSignalRepository(session),
        snapshots=snapshots,
        stress_testing=StressTestingService(
            session=session,
            portfolios=portfolios,
            snapshots=snapshots,
            clock=clock,
        ),
        notifier=NullNotifier(),
        clock=clock,
    )
    return LiveMonitor(positions=positions, market_data=market_data, early_warning=early_warning)


__all__ = ["LiveMonitor", "build_live_monitor"]
