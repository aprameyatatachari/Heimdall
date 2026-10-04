"""The in-process monitoring scheduler.

On a timer, for every portfolio with an enabled rule whose market is open: read
the newest prices, then evaluate the rules. That is the whole of what makes the
Early Warning System live on a machine that stays up.

Properties, each one deliberate:

- **Opt-in.** Started only when `LIVE_MONITORING_ENABLED` is set, and never under
  `SERVERLESS`, where no process outlives a request.
- **Market hours only.** Outside a portfolio's trading session its prices cannot
  change, so a check would re-read the last close and find nothing. The session
  comes from the portfolio's base currency.
- **One transaction per portfolio.** A portfolio that fails is rolled back and
  logged, and the next one is checked in a session of its own.
- **Never fatal.** A tick that raises is logged and the loop sleeps and tries
  again. The scheduler must not be able to take the API down with it.
- **Non-overlapping.** A portfolio already being evaluated, by a person or by
  another worker, is skipped.
- **Discreet.** Log lines carry counts and identifiers, never holdings or signal
  content.

Time comes from the injected clock, so a test decides whether the market is open.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.clock import Clock
from app.common.logging import get_logger
from app.config import Settings
from app.early_warning.live import LiveMonitor, build_live_monitor
from app.early_warning.repository import AlertRuleRepository
from app.early_warning.service import MonitoringAlreadyRunningError
from app.market_data.market_hours import is_market_open

logger = get_logger(__name__)

MonitorBuilder = Callable[[AsyncSession], LiveMonitor]


@dataclass(slots=True)
class TickSummary:
    """What one pass over the monitored portfolios did."""

    checked: int = 0
    market_closed: int = 0
    already_running: int = 0
    failed: int = 0
    signals_created: int = 0
    signals_resolved: int = 0


class MonitoringScheduler:
    """Checks every monitored portfolio once per interval while its market is open."""

    def __init__(
        self,
        *,
        settings: Settings,
        clock: Clock,
        session_factory: async_sessionmaker[AsyncSession],
        build_monitor: MonitorBuilder | None = None,
    ) -> None:
        self._clock = clock
        self._session_factory = session_factory
        self._interval_seconds = settings.live_monitoring_interval_seconds
        self._build_monitor: MonitorBuilder = build_monitor or (
            lambda session: build_live_monitor(session, settings=settings, clock=clock)
        )

    async def run(self) -> None:
        """Tick until cancelled."""
        logger.info("live_monitoring_started", interval_seconds=self._interval_seconds)
        try:
            while True:
                try:
                    await self.tick()
                except Exception as exc:
                    logger.warning("live_monitoring_tick_failed", error=type(exc).__name__)
                await asyncio.sleep(self._interval_seconds)
        finally:
            logger.info("live_monitoring_stopped")

    async def tick(self) -> TickSummary:
        """Check every monitored portfolio whose market is open."""
        now = self._clock.now()
        summary = TickSummary()

        async with self._session_factory() as session:
            portfolios = await AlertRuleRepository(session).monitored_portfolios()

        for portfolio_id, currency in portfolios:
            if not is_market_open(currency, now):
                summary.market_closed += 1
                continue

            async with self._session_factory() as session:
                try:
                    outcome = await self._build_monitor(session).check(portfolio_id)
                    await session.commit()
                except MonitoringAlreadyRunningError:
                    await session.rollback()
                    summary.already_running += 1
                except Exception as exc:
                    await session.rollback()
                    summary.failed += 1
                    logger.warning(
                        "live_monitoring_portfolio_failed",
                        portfolio_id=str(portfolio_id),
                        error=type(exc).__name__,
                    )
                else:
                    summary.checked += 1
                    summary.signals_created += outcome.run.signals_created
                    summary.signals_resolved += outcome.run.signals_resolved

        logger.info(
            "live_monitoring_tick",
            checked=summary.checked,
            market_closed=summary.market_closed,
            already_running=summary.already_running,
            failed=summary.failed,
            signals_created=summary.signals_created,
            signals_resolved=summary.signals_resolved,
        )
        return summary


__all__ = ["MonitoringScheduler", "TickSummary"]
