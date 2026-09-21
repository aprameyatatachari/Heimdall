"""The rule-engine contract.

A rule evaluator receives a prepared context and returns a structured outcome. It
does no database access, no HTTP, and no scheduling: everything it needs is in the
context, which the service assembles once per monitoring run.

An evaluator returns one of three things:

* **Triggered** — the condition holds, with severity, observed value, threshold,
  a plain-language explanation, and structured context.
* **Not triggered** — the condition does not hold. Any open signal for it resolves.
* **Not evaluated** — the rule could not run (insufficient history, missing
  metadata). No signal fires and no signal resolves, because the absence of
  evidence is not evidence that the condition cleared.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.analytics.snapshot import PortfolioSnapshot
from app.early_warning.models import AlertRule
from app.early_warning.rule_types import (
    BaseRuleParameters,
    RuleType,
    SeverityThresholds,
    SignalSeverity,
)


class OutcomeKind(StrEnum):
    """What an evaluation concluded."""

    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True, slots=True)
class PriceSeries:
    """One asset's adjusted-close history, ascending by date."""

    symbol: str
    observations: list[tuple[date, float]]

    @property
    def latest_date(self) -> date | None:
        """Date of the newest observation."""
        return self.observations[-1][0] if self.observations else None

    def values(self) -> list[float]:
        """The prices alone."""
        return [price for _, price in self.observations]


class ScenarioRunner(Protocol):
    """Runs a stored stress scenario. Injected so the rule engine stays pure."""

    async def __call__(self, scenario_key: str) -> tuple[Decimal, Decimal, str]:
        """Return (loss fraction, loss amount, scenario name) for a scenario."""
        ...


@dataclass(slots=True)
class RuleContext:
    """Everything a rule needs, prepared once per monitoring run."""

    snapshot: PortfolioSnapshot
    # Full price history available for the run's longest window, per symbol.
    history: dict[str, PriceSeries]
    # The instant the run is evaluating at, from the injectable clock.
    evaluated_at: datetime
    # Newest market-data date across the portfolio.
    data_as_of: date | None
    # Set for rules that need stress results. None when unavailable.
    scenario_runner: ScenarioRunner | None = None

    def series(self, symbol: str) -> PriceSeries | None:
        """History for one symbol, if any is loaded."""
        return self.history.get(symbol)


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """What a rule concluded, in a form the lifecycle layer can act on."""

    kind: OutcomeKind
    # Set for TRIGGERED.
    severity: SignalSeverity | None = None
    observed_value: Decimal | None = None
    threshold_value: Decimal | None = None
    title: str = ""
    explanation: str = ""
    suggested_action: str = ""
    # Identifies the affected asset, sector, or scenario. Part of the fingerprint.
    subject: str | None = None
    unit: str = ""
    analysis_period: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    # Why the rule could not run, for NOT_EVALUATED.
    reason: str = ""
    # Data-quality caveats that apply to a triggered signal.
    limitations: list[str] = field(default_factory=list)

    @property
    def triggered(self) -> bool:
        """True when the condition holds."""
        return self.kind is OutcomeKind.TRIGGERED

    @staticmethod
    def clear() -> RuleOutcome:
        """The condition does not hold."""
        return RuleOutcome(kind=OutcomeKind.NOT_TRIGGERED)

    @staticmethod
    def skipped(reason: str) -> RuleOutcome:
        """The rule could not be evaluated. No signal fires, none resolves."""
        return RuleOutcome(kind=OutcomeKind.NOT_EVALUATED, reason=reason)


class RuleEvaluator(ABC):
    """One rule type's evaluation logic.

    Each evaluator is independently testable: build a context, call `evaluate`,
    inspect the outcome.
    """

    rule_type: RuleType
    # The unit the observed value and thresholds are expressed in.
    unit: str
    # Default name and description used when provisioning the rule.
    default_name: str
    default_description: str
    default_thresholds: SeverityThresholds
    default_cooldown_hours: int = 24

    @abstractmethod
    def parse_parameters(self, payload: dict[str, Any]) -> BaseRuleParameters:
        """Validate this rule's stored parameters."""

    @abstractmethod
    async def evaluate(
        self,
        *,
        rule: AlertRule,
        context: RuleContext,
    ) -> list[RuleOutcome]:
        """Evaluate the rule.

        Returns a list because one rule can produce several independent conditions —
        two over-concentrated positions are two separate signals with two separate
        fingerprints. An empty list means nothing triggered.
        """

    def thresholds(self, rule: AlertRule) -> SeverityThresholds:
        """The rule's configured thresholds."""
        return SeverityThresholds.model_validate(rule.severity_configuration)


def format_percent(value: float) -> str:
    """Format a fraction as a percentage, to one decimal place."""
    return f"{value * 100:.1f}%"


def format_currency(value: float, currency: str) -> str:
    """Format a monetary amount with thousands separators."""
    return f"{value:,.2f} {currency}"
