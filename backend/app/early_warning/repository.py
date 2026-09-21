"""Persistence for alert rules, monitoring runs, and warning signals."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.early_warning.models import AlertRule, MonitoringRun, SignalEvent, WarningSignal
from app.portfolios.models import Portfolio


class AlertRuleRepository:
    """Queries and writes for `alert_rules`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_portfolio(
        self,
        portfolio_id: uuid.UUID,
        *,
        enabled_only: bool = False,
    ) -> list[AlertRule]:
        """A portfolio's rules, ordered by type for a stable presentation."""
        statement = select(AlertRule).where(AlertRule.portfolio_id == portfolio_id)
        if enabled_only:
            statement = statement.where(AlertRule.enabled.is_(True))
        result = await self._session.execute(statement.order_by(AlertRule.rule_type.asc()))
        return list(result.scalars())

    async def get_owned(self, rule_id: uuid.UUID, user_id: uuid.UUID) -> AlertRule | None:
        """One rule, only if the caller owns its portfolio."""
        result = await self._session.execute(
            select(AlertRule)
            .join(Portfolio, AlertRule.portfolio_id == Portfolio.id)
            .where(AlertRule.id == rule_id, Portfolio.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_type(self, portfolio_id: uuid.UUID, rule_type: str) -> AlertRule | None:
        """A portfolio's rule of one type, if it has one."""
        result = await self._session.execute(
            select(AlertRule).where(
                AlertRule.portfolio_id == portfolio_id,
                AlertRule.rule_type == rule_type,
            )
        )
        return result.scalar_one_or_none()

    def add(self, rule: AlertRule) -> AlertRule:
        """Stage a new rule for insertion."""
        self._session.add(rule)
        return rule

    async def delete(self, rule: AlertRule) -> None:
        """Delete a rule. Its signals are removed by the database cascade."""
        await self._session.delete(rule)


class MonitoringRunRepository:
    """Queries and writes for `monitoring_runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, run: MonitoringRun) -> MonitoringRun:
        """Stage a new run for insertion."""
        self._session.add(run)
        return run

    async def get_owned(self, run_id: uuid.UUID, user_id: uuid.UUID) -> MonitoringRun | None:
        """One run, only if the caller owns its portfolio."""
        result = await self._session.execute(
            select(MonitoringRun)
            .join(Portfolio, MonitoringRun.portfolio_id == Portfolio.id)
            .where(MonitoringRun.id == run_id, Portfolio.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self,
        portfolio_id: uuid.UUID,
        key: str,
    ) -> MonitoringRun | None:
        """An existing run for the same portfolio and evaluation period."""
        result = await self._session.execute(
            select(MonitoringRun).where(
                MonitoringRun.portfolio_id == portfolio_id,
                MonitoringRun.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_portfolio(
        self,
        portfolio_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[MonitoringRun]:
        """A portfolio's runs, newest first, with a stable tiebreak."""
        result = await self._session.execute(
            select(MonitoringRun)
            .where(MonitoringRun.portfolio_id == portfolio_id)
            .order_by(MonitoringRun.started_at.desc(), MonitoringRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count_for_portfolio(self, portfolio_id: uuid.UUID) -> int:
        """How many runs a portfolio has."""
        result = await self._session.execute(
            select(func.count())
            .select_from(MonitoringRun)
            .where(MonitoringRun.portfolio_id == portfolio_id)
        )
        return int(result.scalar_one())

    async def has_running(self, portfolio_id: uuid.UUID) -> bool:
        """True when a run for this portfolio is already in progress.

        Used to prevent two monitoring runs evaluating the same portfolio at once.
        """
        result = await self._session.execute(
            select(MonitoringRun.id).where(
                MonitoringRun.portfolio_id == portfolio_id,
                MonitoringRun.status == "running",
            )
        )
        return result.first() is not None


class WarningSignalRepository:
    """Queries and writes for `warning_signals` and their audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, signal: WarningSignal) -> WarningSignal:
        """Stage a new signal for insertion."""
        self._session.add(signal)
        return signal

    def add_event(self, event: SignalEvent) -> SignalEvent:
        """Append an audit entry."""
        self._session.add(event)
        return event

    async def get_owned(self, signal_id: uuid.UUID, user_id: uuid.UUID) -> WarningSignal | None:
        """One signal with its audit trail, only if the caller owns its portfolio."""
        result = await self._session.execute(
            select(WarningSignal)
            .join(Portfolio, WarningSignal.portfolio_id == Portfolio.id)
            .where(WarningSignal.id == signal_id, Portfolio.user_id == user_id)
            .options(selectinload(WarningSignal.events))
        )
        return result.unique().scalar_one_or_none()

    async def find_open(
        self,
        portfolio_id: uuid.UUID,
        fingerprint: str,
    ) -> WarningSignal | None:
        """The open signal for a condition, if one exists.

        "Open" means neither resolved nor dismissed. A partial unique index makes
        at most one exist at a time.
        """
        result = await self._session.execute(
            select(WarningSignal).where(
                WarningSignal.portfolio_id == portfolio_id,
                WarningSignal.fingerprint == fingerprint,
                WarningSignal.resolved_at.is_(None),
                WarningSignal.dismissed_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_open_for_rules(
        self,
        portfolio_id: uuid.UUID,
        rule_ids: Sequence[uuid.UUID],
    ) -> list[WarningSignal]:
        """Every open signal belonging to the given rules."""
        if not rule_ids:
            return []
        result = await self._session.execute(
            select(WarningSignal).where(
                WarningSignal.portfolio_id == portfolio_id,
                WarningSignal.alert_rule_id.in_(rule_ids),
                WarningSignal.resolved_at.is_(None),
                WarningSignal.dismissed_at.is_(None),
            )
        )
        return list(result.scalars())

    def filtered(
        self,
        *,
        user_id: uuid.UUID,
        portfolio_id: uuid.UUID | None = None,
        statuses: Sequence[str] | None = None,
        severities: Sequence[str] | None = None,
        signal_types: Sequence[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        acknowledged: bool | None = None,
    ) -> Select[tuple[WarningSignal]]:
        """Build the filtered, owner-scoped signal query used by the list endpoint."""
        statement = (
            select(WarningSignal)
            .join(Portfolio, WarningSignal.portfolio_id == Portfolio.id)
            .where(Portfolio.user_id == user_id)
        )

        if portfolio_id is not None:
            statement = statement.where(WarningSignal.portfolio_id == portfolio_id)
        if statuses:
            statement = statement.where(WarningSignal.status.in_(statuses))
        if severities:
            statement = statement.where(WarningSignal.severity.in_(severities))
        if signal_types:
            statement = statement.where(WarningSignal.signal_type.in_(signal_types))
        if created_from is not None:
            statement = statement.where(WarningSignal.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(WarningSignal.created_at <= created_to)
        if acknowledged is True:
            statement = statement.where(WarningSignal.acknowledged_at.is_not(None))
        if acknowledged is False:
            statement = statement.where(WarningSignal.acknowledged_at.is_(None))

        return statement

    async def list_filtered(
        self,
        statement: Select[tuple[WarningSignal]],
        *,
        limit: int,
        offset: int,
    ) -> list[WarningSignal]:
        """Run a filtered query with stable ordering.

        Ordering is newest first with the id as a tiebreak, so pagination cannot
        show or skip a row when two signals share a timestamp.
        """
        result = await self._session.execute(
            statement.order_by(WarningSignal.created_at.desc(), WarningSignal.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count_filtered(self, statement: Select[tuple[WarningSignal]]) -> int:
        """Total rows the filtered query matches."""
        result = await self._session.execute(select(func.count()).select_from(statement.subquery()))
        return int(result.scalar_one())

    async def severity_counts(self, portfolio_id: uuid.UUID) -> dict[str, int]:
        """Open signal counts by severity, for the dashboard summary panel."""
        result = await self._session.execute(
            select(WarningSignal.severity, func.count())
            .where(
                WarningSignal.portfolio_id == portfolio_id,
                WarningSignal.resolved_at.is_(None),
                WarningSignal.dismissed_at.is_(None),
            )
            .group_by(WarningSignal.severity)
        )
        return {row[0]: int(row[1]) for row in result.all()}
