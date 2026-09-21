"""Early Warning System API schemas.

Every signal response carries what a reader needs to judge it without prior
knowledge: the metric, the observed value, the threshold that was crossed, the
unit, the analysis period, the data-as-of date, and an informational next step.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.disclaimer import EARLY_WARNING_DISCLAIMER
from app.common.schemas import ApiModel
from app.early_warning.rule_types import (
    MonitoringStatus,
    MonitoringTriggerType,
    RuleType,
    SeverityThresholds,
    SignalSeverity,
    SignalStatus,
)

MAX_COOLDOWN_HOURS = 24 * 30

# Icon names, so severity is never communicated by colour alone. The frontend maps
# these to shapes; the backend names them so every client agrees.
SEVERITY_ICONS: dict[str, str] = {
    "informational": "info-circle",
    "elevated": "flag",
    "high": "alert-triangle",
    "critical": "alert-octagon",
}


class AlertRuleCreateRequest(BaseModel):
    """Create one alert rule."""

    model_config = {"extra": "forbid"}

    rule_type: RuleType
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Validated against this rule type's own schema. Unknown keys are rejected.",
    )
    severity_configuration: dict[str, float] | None = Field(
        default=None,
        description=(
            "Thresholds per severity. At least one of elevated, high, critical. "
            "They must increase with severity. Omit to use the documented defaults."
        ),
    )
    cooldown_hours: int = Field(
        default=24,
        ge=0,
        le=MAX_COOLDOWN_HOURS,
        description=(
            "Minimum hours between external notifications for the same signal. "
            "Never affects whether the current risk state is recorded."
        ),
    )

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name must not be blank.")
        return trimmed


class AlertRuleUpdateRequest(BaseModel):
    """Partial update of an alert rule. The rule type cannot be changed."""

    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    parameters: dict[str, Any] | None = None
    severity_configuration: dict[str, float] | None = None
    cooldown_hours: int | None = Field(default=None, ge=0, le=MAX_COOLDOWN_HOURS)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name must not be blank.")
        return trimmed

    @model_validator(mode="after")
    def _at_least_one(self) -> AlertRuleUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class AlertRuleResponse(ApiModel):
    """One alert rule."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    rule_type: str
    name: str
    description: str
    enabled: bool
    parameters: dict[str, Any]
    severity_configuration: dict[str, float]
    cooldown_hours: int
    created_at: datetime
    updated_at: datetime


class AlertRuleCatalogueItem(BaseModel):
    """What a rule type measures, and its documented defaults."""

    rule_type: str
    name: str
    description: str
    unit: str
    default_severity_configuration: dict[str, float]
    default_cooldown_hours: int
    default_parameters: dict[str, Any]


class AlertRuleCatalogueResponse(BaseModel):
    """Every rule type Heimdall can evaluate."""

    items: list[AlertRuleCatalogueItem]
    disclaimer: str = EARLY_WARNING_DISCLAIMER


class SignalEventResponse(ApiModel):
    """One entry in a signal's append-only audit trail."""

    event_type: str
    from_severity: str | None
    to_severity: str | None
    from_status: str | None
    to_status: str | None
    observed_value: Decimal | None
    note: str | None
    occurred_at: datetime


class WarningSignalResponse(ApiModel):
    """A Gjallarhorn Signal, with everything needed to explain why it fired."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    alert_rule_id: uuid.UUID
    monitoring_run_id: uuid.UUID | None
    signal_type: str
    severity: SignalSeverity
    severity_icon: str = Field(
        description="Icon name, so severity is never conveyed by colour alone."
    )
    status: SignalStatus
    title: str
    explanation: str = Field(description="Plain-language description of the observed condition.")
    suggested_action: str = Field(
        description="An informational analytical step. Never a buy, sell, or hold instruction."
    )
    metric_name: str
    observed_value: Decimal
    threshold_value: Decimal
    unit: str
    analysis_period: str
    data_as_of: date | None
    context: dict[str, Any] = Field(
        description="Affected asset, sector, or scenario, plus rule-specific detail."
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Data-quality caveats that apply to this signal.",
    )
    first_triggered_at: datetime
    last_triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime
    events: list[SignalEventResponse] = Field(default_factory=list)
    disclaimer: str = EARLY_WARNING_DISCLAIMER


class SignalSummaryResponse(BaseModel):
    """Open-signal counts by severity, for the dashboard panel."""

    portfolio_id: uuid.UUID
    total_open: int
    by_severity: dict[str, int]
    disclaimer: str = EARLY_WARNING_DISCLAIMER


class MonitoringRuleResult(BaseModel):
    """What one rule did during a run."""

    rule_id: uuid.UUID
    rule_type: str
    status: str = Field(
        description="evaluated, clear, skipped, or failed. A failure never hides other results."
    )
    signals_created: int
    signals_updated: int
    signals_resolved: int
    skipped_reason: str | None
    error: str | None


class MonitoringRunResponse(ApiModel):
    """One monitoring run."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    trigger_type: MonitoringTriggerType
    status: MonitoringStatus = Field(
        description="`partial` means some rules failed; results from the others are complete."
    )
    data_as_of: date | None
    rules_evaluated: int
    rules_failed: int
    signals_created: int
    signals_updated: int
    signals_resolved: int
    error_summary: str | None
    rule_results: list[MonitoringRuleResult]
    started_at: datetime
    completed_at: datetime | None


class MonitoringRunSummary(ApiModel):
    """A monitoring run without its per-rule detail, for listings."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    trigger_type: MonitoringTriggerType
    status: MonitoringStatus
    data_as_of: date | None
    rules_evaluated: int
    rules_failed: int
    signals_created: int
    signals_updated: int
    signals_resolved: int
    started_at: datetime
    completed_at: datetime | None


class ScheduledMonitoringRequest(BaseModel):
    """Body of the protected scheduled-monitoring endpoint."""

    model_config = {"extra": "forbid"}

    batch_size: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Portfolios to process in this invocation. Bounded for serverless runtime.",
    )
    cursor: uuid.UUID | None = Field(
        default=None,
        description="Resume point: process portfolios with an id greater than this.",
    )


class ScheduledPortfolioResult(BaseModel):
    """Per-portfolio outcome of a scheduled run.

    Deliberately carries no portfolio names, holdings, or signal content: the
    scheduler is not a user and must not receive portfolio detail.
    """

    portfolio_id: uuid.UUID
    status: str = Field(
        description=(
            "The run's status, or `deduplicated` when an equivalent run already "
            "covered this period, `already_running` when one was in progress, or "
            "`failed`. Counts are always what THIS invocation did, so a repeat "
            "reports zeroes."
        )
    )
    signals_created: int = 0
    signals_updated: int = 0
    signals_resolved: int = 0


class ScheduledMonitoringResponse(BaseModel):
    """Operational summary of a scheduled run."""

    evaluated_at: datetime
    evaluation_period: str = Field(description="The period this invocation is idempotent for.")
    portfolios_processed: int
    portfolios_failed: int
    portfolios_skipped: int
    signals_created: int
    signals_updated: int
    signals_resolved: int
    next_cursor: uuid.UUID | None = Field(
        description="Pass as `cursor` to continue. Null when the batch reached the end."
    )
    results: list[ScheduledPortfolioResult]


def default_thresholds_for(rule_type: RuleType) -> dict[str, float]:
    """The documented default thresholds for a rule type."""
    from app.early_warning.evaluators import get_evaluator

    thresholds: SeverityThresholds = get_evaluator(rule_type).default_thresholds
    return thresholds.as_dict()
