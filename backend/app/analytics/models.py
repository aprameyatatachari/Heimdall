"""Analytics ORM models: analysis runs and their results."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import UUIDPrimaryKey
from app.database import Base


class AnalysisType(StrEnum):
    """What an analysis run computed."""

    RISK_SUMMARY = "risk_summary"


class RunStatus(StrEnum):
    """Lifecycle of an analysis or stress-test run.

    `partial` exists because one unavailable metric must not discard the others:
    a run that computed most of its metrics is more useful than a failed one.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class MetricUnit(StrEnum):
    """Unit of a stored metric value.

    Stored explicitly so no consumer has to guess whether 0.18 means 18% or 18.
    """

    RATIO = "ratio"
    PERCENT = "percent"
    CURRENCY = "currency"
    COUNT = "count"
    DAYS = "days"
    DATE = "date"


class AnalysisRun(Base):
    """One execution of an analysis over a portfolio and a window.

    The parameters and the data-as-of date are persisted, so a stored result can
    always be explained and reproduced.
    """

    __tablename__ = "analysis_runs"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_type: Mapped[AnalysisType] = mapped_column(String(32), nullable=False)
    # The full, resolved request: window, confidence, VaR method, risk-free rate.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Newest market-data date the run actually used.
    data_as_of: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[RunStatus] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    # Human-readable assumptions and caveats that apply to the whole run.
    notes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )

    results: Mapped[list[RiskResult]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RiskResult.metric",
    )

    __table_args__ = (
        Index("ix_analysis_runs_portfolio_id_created_at", "portfolio_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisRun id={self.id} status={self.status}>"


class RiskResult(Base):
    """One metric produced by an analysis run.

    A metric that could not be computed is stored with a null value and a reason,
    so the interface can say "insufficient data" instead of showing zero.
    """

    __tablename__ = "risk_results"

    id: Mapped[UUIDPrimaryKey]
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), default=None)
    unit: Mapped[MetricUnit] = mapped_column(String(16), nullable=False)
    # Scope, confidence level, window, per-asset detail, and assumptions.
    result_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, default=None)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="results")

    __table_args__ = (
        CheckConstraint(
            "value IS NOT NULL OR unavailable_reason IS NOT NULL",
            name="ck_risk_results_value_or_reason",
        ),
        Index("ix_risk_results_run_metric", "analysis_run_id", "metric"),
    )

    def __repr__(self) -> str:
        return f"<RiskResult metric={self.metric} value={self.value}>"
