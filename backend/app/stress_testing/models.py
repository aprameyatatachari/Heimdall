"""Stress-test ORM model."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.analytics.models import RunStatus
from app.common.models import UUIDPrimaryKey
from app.database import Base


class StressTestRun(Base):
    """One stress test of one portfolio against one scenario.

    The complete scenario definition is persisted, not just its name: a stored
    result must remain explainable even after the catalogue changes.
    """

    __tablename__ = "stress_test_runs"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Historical: key, name, description, exact dates. Hypothetical: the shock list.
    scenario_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    data_as_of: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[RunStatus] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    starting_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), default=None)
    ending_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), default=None)
    total_impact: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), default=None)
    total_impact_percent: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), default=None)

    # Per-position breakdown, plus excluded symbols and the limitations text.
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("ix_stress_test_runs_portfolio_id_created_at", "portfolio_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<StressTestRun id={self.id} scenario={self.scenario_name!r}>"
