"""Report service wiring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.analytics.dependencies import AnalyticsServiceDep, SnapshotBuilderDep
from app.analytics.repository import AnalysisRunRepository
from app.common.dependencies import ClockDep, SessionDep
from app.portfolios.repository import PortfolioRepository
from app.reports.service import ReportService


def get_report_service(
    session: SessionDep,
    snapshots: SnapshotBuilderDep,
    analytics: AnalyticsServiceDep,
    clock: ClockDep,
) -> ReportService:
    """Build the report service for this request."""
    return ReportService(
        session=session,
        portfolios=PortfolioRepository(session),
        runs=AnalysisRunRepository(session),
        snapshots=snapshots,
        analytics=analytics,
        clock=clock,
    )


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
