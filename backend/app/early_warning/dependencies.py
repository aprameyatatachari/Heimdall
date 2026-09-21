"""Early Warning System wiring, including the scheduler guard."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Request

from app.analytics.dependencies import SnapshotBuilderDep
from app.common.dependencies import ClockDep, SessionDep, SettingsDep
from app.common.errors import AppError
from app.common.logging import get_logger
from app.early_warning.notifications import NullNotifier
from app.early_warning.repository import (
    AlertRuleRepository,
    MonitoringRunRepository,
    WarningSignalRepository,
)
from app.early_warning.service import EarlyWarningService
from app.portfolios.repository import PortfolioRepository
from app.stress_testing.dependencies import StressTestingServiceDep

logger = get_logger(__name__)

# The header a scheduler presents. Vercel Cron sends `Authorization: Bearer <secret>`;
# both forms are accepted so the endpoint works with either caller.
CRON_SECRET_HEADER = "X-Cron-Secret"  # noqa: S105 - a header name, not a secret


def get_early_warning_service(
    session: SessionDep,
    snapshots: SnapshotBuilderDep,
    stress_testing: StressTestingServiceDep,
    clock: ClockDep,
) -> EarlyWarningService:
    """Build the Early Warning Service for this request."""
    return EarlyWarningService(
        session=session,
        portfolios=PortfolioRepository(session),
        rules=AlertRuleRepository(session),
        runs=MonitoringRunRepository(session),
        signals=WarningSignalRepository(session),
        snapshots=snapshots,
        stress_testing=stress_testing,
        notifier=NullNotifier(),
        clock=clock,
    )


EarlyWarningServiceDep = Annotated[EarlyWarningService, Depends(get_early_warning_service)]


def get_signal_repository(session: SessionDep) -> WarningSignalRepository:
    """The signal repository, used directly by the filtered list endpoints."""
    return WarningSignalRepository(session)


SignalRepositoryDep = Annotated[WarningSignalRepository, Depends(get_signal_repository)]


class SchedulerNotAuthorizedError(AppError):
    """The caller did not present the configured scheduler secret."""

    code = "scheduler_not_authorized"
    status_code = 401
    message = "This endpoint requires a valid scheduler secret."


class SchedulerNotConfiguredError(AppError):
    """No scheduler secret is configured, so the endpoint refuses to run.

    Failing closed matters: an unprotected monitoring endpoint would let anyone
    trigger evaluation of every portfolio in the system.
    """

    code = "scheduler_not_configured"
    status_code = 503
    message = "Scheduled monitoring is not configured on this deployment."


async def require_scheduler_secret(request: Request, settings: SettingsDep) -> None:
    """Authorize a scheduled call.

    The comparison is constant-time, so a caller cannot discover the secret by
    measuring how long a rejection takes. Nothing about the secret, and no
    portfolio detail, is ever included in the response or the log.
    """
    if settings.cron_secret is None:
        logger.warning("scheduled_monitoring_rejected", reason="no secret configured")
        raise SchedulerNotConfiguredError()

    expected = settings.cron_secret.get_secret_value()
    presented = request.headers.get(CRON_SECRET_HEADER, "")

    if not presented:
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer":
            presented = token.strip()

    if not presented or not secrets.compare_digest(presented, expected):
        logger.warning("scheduled_monitoring_rejected", reason="invalid secret")
        raise SchedulerNotAuthorizedError()


SchedulerGuard = Depends(require_scheduler_secret)
