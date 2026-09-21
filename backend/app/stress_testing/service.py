"""Stress-testing use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import RunStatus
from app.analytics.snapshot import PortfolioSnapshot, SnapshotBuilder
from app.common.clock import Clock
from app.common.errors import NotFoundError, ValidationError
from app.common.logging import get_logger
from app.portfolios.models import Portfolio
from app.portfolios.repository import PortfolioRepository
from app.portfolios.service import PortfolioNotFoundError
from app.stress_testing.engine import (
    HoldingInput,
    StressTestResult,
    apply_returns,
    apply_shocks,
    window_return,
)
from app.stress_testing.models import StressTestRun
from app.stress_testing.scenarios import (
    HISTORICAL_SCENARIOS,
    SCENARIOS_BY_KEY,
    STRESS_TEST_LIMITATIONS,
    HistoricalScenario,
    ScenarioType,
    Shock,
)

logger = get_logger(__name__)


class ScenarioNotFoundError(NotFoundError):
    """The requested historical scenario is not in the catalogue."""

    code = "scenario_not_found"
    message = "That stress scenario does not exist."


class StressTestRunNotFoundError(NotFoundError):
    """The stress-test run does not exist, or belongs to another user."""

    code = "stress_test_run_not_found"
    message = "Stress-test run not found."


class NoScenarioDataError(ValidationError):
    """No holding has price data inside the scenario window."""

    code = "scenario_data_unavailable"
    message = (
        "No holding has stored price data covering this scenario's date range. "
        "Refresh market data for the scenario period and try again."
    )


@dataclass(frozen=True, slots=True)
class CustomScenario:
    """A user-defined hypothetical scenario."""

    name: str
    shocks: list[Shock]

    def to_dict(self) -> dict[str, object]:
        """Serializable form, persisted with the run."""
        return {
            "scenario_type": str(ScenarioType.HYPOTHETICAL),
            "name": self.name,
            "shocks": [shock.to_dict() for shock in self.shocks],
            "precedence": (
                "A shock on a symbol overrides one on its sector, which overrides a "
                "portfolio-wide shock."
            ),
        }


class StressTestingService:
    """Runs and stores stress tests."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        snapshots: SnapshotBuilder,
        clock: Clock,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._snapshots = snapshots
        self._clock = clock

    # --- Catalogue -----------------------------------------------------------

    @staticmethod
    def list_scenarios() -> tuple[HistoricalScenario, ...]:
        """The historical scenario catalogue."""
        return HISTORICAL_SCENARIOS

    @staticmethod
    def get_scenario(key: str) -> HistoricalScenario:
        """One catalogue entry, by key."""
        scenario = SCENARIOS_BY_KEY.get(key)
        if scenario is None:
            raise ScenarioNotFoundError(
                f"Unknown scenario {key!r}. Available scenarios are listed at "
                "GET /api/v1/stress-scenarios."
            )
        return scenario

    # --- Running -------------------------------------------------------------

    async def run_historical(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        scenario_key: str,
    ) -> StressTestRun:
        """Apply the returns observed during a historical window."""
        scenario = self.get_scenario(scenario_key)
        portfolio, snapshot = await self._prepare(portfolio_id, user_id)

        returns: dict[str, Decimal] = {}
        sources: dict[str, str] = {}
        # Holdings with no stored price at all cannot be valued, let alone shocked.
        excluded: list[str] = list(snapshot.unpriced_symbols)

        for holding in snapshot.priced_holdings:
            history = await self._snapshots.symbol_history(
                holding.asset_id,
                start=scenario.start,
                end=scenario.end,
            )
            observed = window_return([(day, Decimal(str(price))) for day, price in history])

            if observed is None:
                excluded.append(holding.symbol)
                continue

            returns[holding.symbol] = observed
            sources[holding.symbol] = (
                f"observed return from {history[0][0].isoformat()} to "
                f"{history[-1][0].isoformat()} ({len(history)} observations)"
            )

        if not returns:
            raise NoScenarioDataError()

        result = apply_returns(
            self._holding_inputs(snapshot),
            returns=returns,
            sources=sources,
            excluded=excluded,
        )

        return await self._persist(
            portfolio=portfolio,
            snapshot=snapshot,
            scenario_type=ScenarioType.HISTORICAL,
            scenario_name=scenario.name,
            definition=scenario.to_dict(),
            result=result,
            user_id=user_id,
        )

    async def run_hypothetical(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        scenario: CustomScenario,
    ) -> StressTestRun:
        """Apply a user-defined shock set."""
        portfolio, snapshot = await self._prepare(portfolio_id, user_id)

        result = apply_shocks(
            self._holding_inputs(snapshot),
            shocks=scenario.shocks,
            excluded=list(snapshot.unpriced_symbols),
        )

        return await self._persist(
            portfolio=portfolio,
            snapshot=snapshot,
            scenario_type=ScenarioType.HYPOTHETICAL,
            scenario_name=scenario.name,
            definition=scenario.to_dict(),
            result=result,
            user_id=user_id,
        )

    # --- Reading -------------------------------------------------------------

    async def get_run(self, *, run_id: uuid.UUID, user_id: uuid.UUID) -> StressTestRun:
        """Return a stored run, scoped to the owner."""
        result = await self._session.execute(
            select(StressTestRun)
            .join(Portfolio, StressTestRun.portfolio_id == Portfolio.id)
            .where(StressTestRun.id == run_id, Portfolio.user_id == user_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise StressTestRunNotFoundError()
        return run

    async def list_runs(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[StressTestRun], int]:
        """List a portfolio's stress tests, newest first."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        rows = await self._session.execute(
            select(StressTestRun)
            .where(StressTestRun.portfolio_id == portfolio.id)
            .order_by(StressTestRun.created_at.desc(), StressTestRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.execute(
            select(func.count())
            .select_from(StressTestRun)
            .where(StressTestRun.portfolio_id == portfolio.id)
        )
        return list(rows.scalars()), int(total.scalar_one())

    # --- Internals -----------------------------------------------------------

    async def _prepare(
        self,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[Portfolio, PortfolioSnapshot]:
        """Load and validate the portfolio a stress test will run against."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        snapshot = await self._snapshots.build(portfolio)
        snapshot.require_analyzable()
        return portfolio, snapshot

    @staticmethod
    def _holding_inputs(snapshot: PortfolioSnapshot) -> list[HoldingInput]:
        """Map priced holdings into the engine's input shape."""
        return [
            HoldingInput(
                symbol=holding.symbol,
                sector=holding.sector,
                market_value=holding.market_value or Decimal("0"),
            )
            for holding in snapshot.priced_holdings
        ]

    async def _persist(
        self,
        *,
        portfolio: Portfolio,
        snapshot: PortfolioSnapshot,
        scenario_type: ScenarioType,
        scenario_name: str,
        definition: dict[str, object],
        result: StressTestResult,
        user_id: uuid.UUID,
    ) -> StressTestRun:
        """Store a completed stress test."""
        run = StressTestRun(
            portfolio_id=portfolio.id,
            scenario_type=str(scenario_type),
            scenario_name=scenario_name,
            scenario_definition=definition,
            data_as_of=snapshot.data_as_of,
            status=RunStatus.PARTIAL if result.excluded_symbols else RunStatus.SUCCEEDED,
            starting_value=result.starting_value,
            ending_value=result.ending_value,
            total_impact=result.total_impact,
            total_impact_percent=result.total_impact_percent,
            result=_serialize_result(result, currency=snapshot.base_currency),
            completed_at=self._clock.now(),
        )
        self._session.add(run)
        await self._session.flush()

        logger.info(
            "stress_test_completed",
            portfolio_id=str(portfolio.id),
            run_id=str(run.id),
            scenario=scenario_name,
            total_impact_percent=float(result.total_impact_percent),
            excluded=len(result.excluded_symbols),
        )
        del user_id  # ownership was checked when the portfolio was loaded
        return run


def _serialize_result(result: StressTestResult, *, currency: str) -> dict[str, object]:
    """Turn an engine result into the stored JSON payload."""
    return {
        "currency": currency,
        "reconciles": result.reconciles(),
        "excluded_symbols": result.excluded_symbols,
        "limitations": list(STRESS_TEST_LIMITATIONS),
        "positions": [
            {
                "symbol": impact.symbol,
                "sector": impact.sector,
                "starting_value": str(impact.starting_value),
                "applied_return": str(impact.applied_return),
                "return_source": impact.source,
                "ending_value": str(impact.ending_value),
                "impact": str(impact.impact),
                "impact_percent": str(impact.impact_percent),
                "contribution_to_loss": (
                    None
                    if impact.contribution_to_loss is None
                    else str(impact.contribution_to_loss)
                ),
            }
            for impact in result.impacts
        ],
    }


__all__ = [
    "CustomScenario",
    "NoScenarioDataError",
    "ScenarioNotFoundError",
    "StressTestRunNotFoundError",
    "StressTestingService",
]
