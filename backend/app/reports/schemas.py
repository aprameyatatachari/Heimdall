"""Report API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.common.schemas import ApiModel
from app.reports.models import ReportFormat, ReportStatus


class ReportCreateRequest(BaseModel):
    """What to include in a generated report."""

    model_config = {"extra": "forbid"}

    analysis_run_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Build the report from this stored analysis run. Omit to reuse the "
            "portfolio's most recent run, or to compute one if none exists."
        ),
    )
    include_stress_tests: bool = Field(
        default=True,
        description="Include the portfolio's most recent stress tests.",
    )
    include_signals: bool = Field(
        default=True,
        description="Include a Gjallarhorn Early Warning Signals subsection.",
    )
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ReportResponse(ApiModel):
    """A generated report's metadata. The bytes are fetched separately."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    title: str
    format: ReportFormat
    status: ReportStatus = Field(
        description="pending, generating, succeeded, or failed. Only succeeded can be downloaded."
    )
    error_message: str | None
    inputs: dict[str, Any] = Field(
        description=(
            "The identifiers and parameters this report was built from, so the same "
            "document can be reproduced later."
        )
    )
    size_bytes: int | None
    filename: str | None
    download_url: str | None = Field(
        description="Where to fetch the rendered document. Null until generation succeeds."
    )
    created_at: datetime
    completed_at: datetime | None
