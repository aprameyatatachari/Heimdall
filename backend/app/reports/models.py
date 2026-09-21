"""Report ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import UUIDPrimaryKey
from app.database import Base


class ReportFormat(StrEnum):
    """Output format of a generated report."""

    PDF = "pdf"


class ReportStatus(StrEnum):
    """Lifecycle of a report."""

    PENDING = "pending"
    GENERATING = "generating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Report(Base):
    """A generated Heimdall Risk Report.

    **Reproducibility.** The `inputs` column stores the exact identifiers and
    parameters the report was built from — the analysis run, the stress tests, the
    data-as-of date — so the same report can be regenerated and audited later.

    **Storage.** The rendered bytes live in the database rather than on disk.
    Production runs on serverless functions with an ephemeral filesystem, so a
    file written during one request is gone by the next. A column keeps reports
    durable without adding an object-store dependency; `docs/deployment.md`
    records the size limit and the migration path to external storage.
    """

    __tablename__ = "reports"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Kept alongside the portfolio so a report cannot be read by another account
    # even if a portfolio were ever reassigned.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"),
        default=None,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(String(8), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # Everything needed to rebuild this report identically.
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    content: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="application/pdf")
    size_bytes: Mapped[int | None] = mapped_column(Integer, default=None)
    filename: Mapped[str | None] = mapped_column(String(200), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("ix_reports_portfolio_id_created_at", "portfolio_id", "created_at"),
        Index("ix_reports_user_id", "user_id"),
    )

    @property
    def is_downloadable(self) -> bool:
        """True when the rendered bytes are available."""
        # `==`, not `is`: a reloaded row holds a plain string, not the member.
        return self.status == ReportStatus.SUCCEEDED and self.content is not None

    def __repr__(self) -> str:
        return f"<Report id={self.id} status={self.status}>"
