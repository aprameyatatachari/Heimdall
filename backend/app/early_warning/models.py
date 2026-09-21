"""Early Warning System ORM models.

Backend names stay technical — `AlertRule`, `MonitoringRun`, `WarningSignal` — as
required. "Gjallarhorn" is a presentation-layer name, never a column or a class.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKey
from app.database import Base


class AlertRule(TimestampMixin, Base):
    """The configuration that decides when a signal fires.

    A rule belongs to exactly one portfolio, so a user can only ever change rules
    on portfolios they own.
    """

    __tablename__ = "alert_rules"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_type: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Validated against the rule type's own schema before it is stored.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Ordered numeric thresholds per severity.
    severity_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Governs notification delivery only, never whether current state is recorded.
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    signals: Mapped[list[WarningSignal]] = relationship(
        back_populates="alert_rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # One rule of each type per portfolio keeps the default set idempotent.
        UniqueConstraint("portfolio_id", "rule_type", name="uq_alert_rules_portfolio_rule_type"),
        CheckConstraint("cooldown_hours >= 0", name="ck_alert_rules_cooldown_non_negative"),
        CheckConstraint("length(trim(name)) > 0", name="ck_alert_rules_name_not_blank"),
    )

    def __repr__(self) -> str:
        return f"<AlertRule id={self.id} type={self.rule_type}>"


class MonitoringRun(Base):
    """One evaluation of a portfolio against its enabled rules."""

    __tablename__ = "monitoring_runs"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    data_as_of: Mapped[date | None] = mapped_column(Date, default=None)

    rules_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-rule failure detail. A failure is recorded, never swallowed.
    error_summary: Mapped[str | None] = mapped_column(Text, default=None)
    rule_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    # Deterministic key for the evaluation period, used for scheduled idempotency.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), default=None)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        # A scheduled run for the same portfolio and period must not run twice.
        UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="uq_monitoring_runs_portfolio_idempotency",
        ),
        Index("ix_monitoring_runs_portfolio_started", "portfolio_id", "started_at"),
    )

    def __repr__(self) -> str:
        return f"<MonitoringRun id={self.id} status={self.status}>"


class WarningSignal(TimestampMixin, Base):
    """A detected condition, with everything needed to explain it.

    Historical signals are preserved rather than deleted when a condition clears:
    the record becomes `resolved` and stays queryable.
    """

    __tablename__ = "warning_signals"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitoring_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Stable identity of the underlying condition. Contains no timestamps and no
    # observed values, so the same condition keeps the same fingerprint.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(200), nullable=False)

    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_value: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(48), nullable=False)
    analysis_period: Mapped[str] = mapped_column(String(120), nullable=False)
    data_as_of: Mapped[date | None] = mapped_column(Date, default=None)

    # Affected asset, sector, or scenario, plus rule-specific detail and any
    # data-quality limitations that apply to this signal.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    first_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # When the last external notification was delivered, for cooldown accounting.
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )

    alert_rule: Mapped[AlertRule] = relationship(back_populates="signals")
    events: Mapped[list[SignalEvent]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SignalEvent.occurred_at",
    )

    __table_args__ = (
        # At most one open occurrence per condition. Enforced in the database, so a
        # concurrent monitoring run cannot create a duplicate.
        Index(
            "uq_warning_signals_open_fingerprint",
            "portfolio_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("resolved_at IS NULL AND dismissed_at IS NULL"),
        ),
        Index("ix_warning_signals_portfolio_status", "portfolio_id", "status"),
        Index("ix_warning_signals_portfolio_created", "portfolio_id", "created_at"),
    )

    @property
    def is_open(self) -> bool:
        """True while the condition is still considered present."""
        return self.resolved_at is None and self.dismissed_at is None

    def __repr__(self) -> str:
        return f"<WarningSignal id={self.id} type={self.signal_type} severity={self.severity}>"


class SignalEvent(Base):
    """Append-only audit of everything that happened to a signal.

    Never updated or deleted, so the lifecycle of any signal can be reconstructed.
    """

    __tablename__ = "signal_events"

    id: Mapped[UUIDPrimaryKey]
    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warning_signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitoring_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_runs.id", ondelete="SET NULL"),
        default=None,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_severity: Mapped[str | None] = mapped_column(String(16), default=None)
    to_severity: Mapped[str | None] = mapped_column(String(16), default=None)
    from_status: Mapped[str | None] = mapped_column(String(16), default=None)
    to_status: Mapped[str | None] = mapped_column(String(16), default=None)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    signal: Mapped[WarningSignal] = relationship(back_populates="events")

    def __repr__(self) -> str:
        return f"<SignalEvent signal_id={self.signal_id} type={self.event_type}>"


class SignalEventType(StrEnum):
    """What kind of lifecycle change an audit entry records."""

    CREATED = "created"
    SEVERITY_INCREASED = "severity_increased"
    SEVERITY_DECREASED = "severity_decreased"
    REOBSERVED = "reobserved"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
