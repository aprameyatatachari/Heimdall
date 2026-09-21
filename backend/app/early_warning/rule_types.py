"""Rule types, severities, and validated rule parameters.

Every rule type has its own typed parameter schema. Arbitrary JSON is never
accepted: an unknown field or an out-of-range threshold is rejected at the API
boundary, so a stored rule can always be evaluated.

Severity thresholds are validated for ordering. A configuration where `high` is
lower than `elevated` would make the highest applicable severity meaningless, so
it is refused rather than silently reordered.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, model_validator


class RuleType(StrEnum):
    """The conditions the Early Warning System can evaluate."""

    POSITION_CONCENTRATION = "position_concentration"
    SECTOR_CONCENTRATION = "sector_concentration"
    VOLATILITY_INCREASE = "volatility_increase"
    PORTFOLIO_DRAWDOWN = "portfolio_drawdown"
    VAR_THRESHOLD = "var_threshold"
    CORRELATION_INCREASE = "correlation_increase"
    STRESS_LOSS = "stress_loss"
    STALE_MARKET_DATA = "stale_market_data"
    MISSING_DATA = "missing_data"


class SignalSeverity(StrEnum):
    """How much attention a signal warrants.

    Ordered from least to most serious. Severity is never communicated by colour
    alone: every signal carries this label, an icon name, and plain-language text.
    """

    INFORMATIONAL = "informational"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


# Rank for comparisons. Higher means more serious.
SEVERITY_RANK: Final[dict[SignalSeverity, int]] = {
    SignalSeverity.INFORMATIONAL: 0,
    SignalSeverity.ELEVATED: 1,
    SignalSeverity.HIGH: 2,
    SignalSeverity.CRITICAL: 3,
}

# Thresholds are configured for these three, in this order. `informational` is
# produced by data-quality rules, which have no numeric ladder.
CONFIGURABLE_SEVERITIES: Final[tuple[SignalSeverity, ...]] = (
    SignalSeverity.ELEVATED,
    SignalSeverity.HIGH,
    SignalSeverity.CRITICAL,
)


class SignalStatus(StrEnum):
    """Where a signal is in its lifecycle.

    `acknowledged` means the user has seen it — **not** that the condition has
    cleared. Only the rule engine may resolve a signal.
    """

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MonitoringTriggerType(StrEnum):
    """What caused a monitoring run."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    MARKET_DATA_REFRESH = "market_data_refresh"


class MonitoringStatus(StrEnum):
    """Outcome of a monitoring run.

    `partial` is a first-class outcome: one failing rule must not discard the
    results of the rules that succeeded.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- Severity configuration ---------------------------------------------------

Fraction = Annotated[float, Field(gt=0.0, le=1.0)]
Multiple = Annotated[float, Field(gt=0.0, le=20.0)]
Currency = Annotated[float, Field(gt=0.0, le=1e12)]
TradingDays = Annotated[int, Field(ge=1, le=60)]


class SeverityThresholds(BaseModel):
    """Numeric thresholds for the three configurable severities.

    At least one must be set. Any that are set must increase with severity, since
    every rule here measures a quantity where larger is worse.
    """

    model_config = {"extra": "forbid"}

    elevated: float | None = None
    high: float | None = None
    critical: float | None = None

    @model_validator(mode="after")
    def _validate_order(self) -> SeverityThresholds:
        configured = [
            (severity, getattr(self, str(severity)))
            for severity in CONFIGURABLE_SEVERITIES
            if getattr(self, str(severity)) is not None
        ]

        if not configured:
            raise ValueError("At least one severity threshold must be set.")

        for (lower_name, lower), (upper_name, upper) in pairwise(configured):
            if upper <= lower:
                raise ValueError(
                    f"The {upper_name} threshold ({upper}) must be greater than the "
                    f"{lower_name} threshold ({lower})."
                )

        return self

    def highest_crossed(self, observed: float) -> tuple[SignalSeverity, float] | None:
        """The most serious severity whose threshold `observed` reaches.

        Returns the severity and the threshold it crossed, or None when nothing is
        crossed. Only the highest applicable severity is produced — never one
        signal per crossed threshold.
        """
        crossed: tuple[SignalSeverity, float] | None = None

        for severity in CONFIGURABLE_SEVERITIES:
            threshold = getattr(self, str(severity))
            if threshold is not None and observed >= threshold:
                crossed = (severity, float(threshold))

        return crossed

    def as_dict(self) -> dict[str, float]:
        """Only the thresholds that are set."""
        return {
            str(severity): float(getattr(self, str(severity)))
            for severity in CONFIGURABLE_SEVERITIES
            if getattr(self, str(severity)) is not None
        }


# --- Per-rule parameters ------------------------------------------------------


class BaseRuleParameters(BaseModel):
    """Shared base. Unknown fields are rejected."""

    model_config = {"extra": "forbid"}


class PositionConcentrationParameters(BaseRuleParameters):
    """One holding exceeding a share of portfolio value."""

    rule_type: Literal[RuleType.POSITION_CONCENTRATION] = RuleType.POSITION_CONCENTRATION


class SectorConcentrationParameters(BaseRuleParameters):
    """One sector exceeding a share of portfolio value."""

    rule_type: Literal[RuleType.SECTOR_CONCENTRATION] = RuleType.SECTOR_CONCENTRATION
    # Above this share of unknown-sector value the rule refuses to run, because
    # partial sector data would be presented as complete exposure.
    max_unknown_sector_weight: Fraction = 0.20


class VolatilityIncreaseParameters(BaseRuleParameters):
    """Recent volatility relative to a longer baseline."""

    rule_type: Literal[RuleType.VOLATILITY_INCREASE] = RuleType.VOLATILITY_INCREASE
    recent_window_days: Annotated[int, Field(ge=5, le=252)] = 20
    baseline_window_days: Annotated[int, Field(ge=30, le=2520)] = 252

    @model_validator(mode="after")
    def _validate_windows(self) -> VolatilityIncreaseParameters:
        if self.baseline_window_days <= self.recent_window_days:
            raise ValueError("The baseline window must be longer than the recent window.")
        return self


class PortfolioDrawdownParameters(BaseRuleParameters):
    """Current decline from the running peak."""

    rule_type: Literal[RuleType.PORTFOLIO_DRAWDOWN] = RuleType.PORTFOLIO_DRAWDOWN
    lookback_days: Annotated[int, Field(ge=30, le=2520)] = 365


class VarThresholdParameters(BaseRuleParameters):
    """One-day historical Value at Risk above a limit.

    The limit may be a percentage of portfolio value, an absolute currency amount,
    or both. With both, whichever is breached more severely wins.
    """

    rule_type: Literal[RuleType.VAR_THRESHOLD] = RuleType.VAR_THRESHOLD
    confidence: Annotated[float, Field(ge=0.5, lt=1.0)] = 0.95
    lookback_days: Annotated[int, Field(ge=30, le=2520)] = 365
    # Which basis the severity thresholds are expressed in.
    basis: Literal["percent_of_value", "currency"] = "percent_of_value"


class CorrelationIncreaseParameters(BaseRuleParameters):
    """Average pairwise correlation above a limit."""

    rule_type: Literal[RuleType.CORRELATION_INCREASE] = RuleType.CORRELATION_INCREASE
    lookback_days: Annotated[int, Field(ge=30, le=2520)] = 365


class StressLossParameters(BaseRuleParameters):
    """Estimated loss under stored stress scenarios above a limit."""

    rule_type: Literal[RuleType.STRESS_LOSS] = RuleType.STRESS_LOSS
    scenario_keys: Annotated[list[str], Field(min_length=1, max_length=10)] = Field(
        default_factory=lambda: ["covid_19_crash_2020"]
    )

    @model_validator(mode="after")
    def _validate_scenarios(self) -> StressLossParameters:
        from app.stress_testing.scenarios import SCENARIOS_BY_KEY

        unknown = [key for key in self.scenario_keys if key not in SCENARIOS_BY_KEY]
        if unknown:
            raise ValueError(
                f"Unknown stress scenario(s): {', '.join(unknown)}. "
                "See GET /api/v1/stress-scenarios."
            )
        return self


class StaleMarketDataParameters(BaseRuleParameters):
    """Prices older than a number of expected trading days.

    Staleness is measured in **expected trading days** under Heimdall's weekday
    calendar convention, so a weekend never makes data look stale.
    """

    rule_type: Literal[RuleType.STALE_MARKET_DATA] = RuleType.STALE_MARKET_DATA


class MissingDataParameters(BaseRuleParameters):
    """Data gaps that prevent reliable analysis."""

    rule_type: Literal[RuleType.MISSING_DATA] = RuleType.MISSING_DATA
    # Below this many observations, risk measures are not dependable.
    minimum_observations: Annotated[int, Field(ge=2, le=2520)] = 30
    lookback_days: Annotated[int, Field(ge=30, le=2520)] = 365


RULE_PARAMETER_MODELS: Final[dict[RuleType, type[BaseRuleParameters]]] = {
    RuleType.POSITION_CONCENTRATION: PositionConcentrationParameters,
    RuleType.SECTOR_CONCENTRATION: SectorConcentrationParameters,
    RuleType.VOLATILITY_INCREASE: VolatilityIncreaseParameters,
    RuleType.PORTFOLIO_DRAWDOWN: PortfolioDrawdownParameters,
    RuleType.VAR_THRESHOLD: VarThresholdParameters,
    RuleType.CORRELATION_INCREASE: CorrelationIncreaseParameters,
    RuleType.STRESS_LOSS: StressLossParameters,
    RuleType.STALE_MARKET_DATA: StaleMarketDataParameters,
    RuleType.MISSING_DATA: MissingDataParameters,
}


def parse_parameters(rule_type: RuleType, payload: dict[str, object]) -> BaseRuleParameters:
    """Validate a rule's parameters against its own schema.

    Raises `pydantic.ValidationError` for anything the schema rejects, which the
    API surfaces as field-level detail.
    """
    model = RULE_PARAMETER_MODELS[rule_type]
    return model.model_validate({**payload, "rule_type": str(rule_type)})


# The unit each rule's observed value and thresholds are expressed in.
RULE_UNITS: Final[dict[RuleType, str]] = {
    RuleType.POSITION_CONCENTRATION: "percent_of_portfolio_value",
    RuleType.SECTOR_CONCENTRATION: "percent_of_portfolio_value",
    RuleType.VOLATILITY_INCREASE: "ratio_to_baseline",
    RuleType.PORTFOLIO_DRAWDOWN: "percent_decline_from_peak",
    RuleType.VAR_THRESHOLD: "percent_of_portfolio_value",
    RuleType.CORRELATION_INCREASE: "correlation_coefficient",
    RuleType.STRESS_LOSS: "percent_of_portfolio_value",
    RuleType.STALE_MARKET_DATA: "expected_trading_days",
    RuleType.MISSING_DATA: "count",
}
