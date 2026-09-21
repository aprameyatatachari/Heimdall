"""Stress-testing service wiring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.analytics.dependencies import SnapshotBuilderDep
from app.common.dependencies import ClockDep, SessionDep
from app.portfolios.repository import PortfolioRepository
from app.stress_testing.service import StressTestingService


def get_stress_testing_service(
    session: SessionDep,
    snapshots: SnapshotBuilderDep,
    clock: ClockDep,
) -> StressTestingService:
    """Build the stress-testing service for this request."""
    return StressTestingService(
        session=session,
        portfolios=PortfolioRepository(session),
        snapshots=snapshots,
        clock=clock,
    )


StressTestingServiceDep = Annotated[StressTestingService, Depends(get_stress_testing_service)]
