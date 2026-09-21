"""Default rule provisioning.

**The documented policy.** Default rules are **not** created automatically when a
portfolio is created. They are created by an explicit call to
`POST /api/v1/portfolios/{id}/alert-rules/defaults`.

Why explicit: a portfolio is often created empty and populated by a CSV import
minutes later. Rules provisioned at creation time would evaluate an empty
portfolio, and a "missing market data" signal on a portfolio the user is still
filling in is noise, not a warning. Making provisioning explicit also means the
same endpoint can restore defaults later, which is a documented requirement.

The operation is idempotent: calling it twice leaves one rule per type. The
unique constraint on `(portfolio_id, rule_type)` enforces that in the database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.early_warning.evaluators import EVALUATORS
from app.early_warning.models import AlertRule
from app.early_warning.rule_types import RuleType, SeverityThresholds


@dataclass(frozen=True, slots=True)
class DefaultRule:
    """The default configuration of one rule type."""

    rule_type: RuleType
    name: str
    description: str
    thresholds: SeverityThresholds
    cooldown_hours: int
    parameters: dict[str, object]


def default_rule_set() -> list[DefaultRule]:
    """The documented default rule set: every rule type, enabled.

    Thresholds come from each evaluator's own `default_thresholds`, so the
    documentation, the evaluator, and the provisioned rule cannot disagree.
    """
    return [
        DefaultRule(
            rule_type=rule_type,
            name=evaluator.default_name,
            description=evaluator.default_description,
            thresholds=evaluator.default_thresholds,
            cooldown_hours=evaluator.default_cooldown_hours,
            parameters=_default_parameters(rule_type),
        )
        for rule_type, evaluator in EVALUATORS.items()
    ]


def _default_parameters(rule_type: RuleType) -> dict[str, object]:
    """The parameter defaults for a rule type, from its own schema."""
    from app.early_warning.rule_types import RULE_PARAMETER_MODELS

    model = RULE_PARAMETER_MODELS[rule_type]
    payload = model(rule_type=rule_type).model_dump(mode="json")  # type: ignore[call-arg]
    payload.pop("rule_type", None)
    return payload


def build_default_rules(portfolio_id: uuid.UUID) -> list[AlertRule]:
    """Construct (but do not persist) the default rules for a portfolio."""
    return [
        AlertRule(
            portfolio_id=portfolio_id,
            rule_type=str(default.rule_type),
            name=default.name,
            description=default.description,
            enabled=True,
            parameters=default.parameters,
            severity_configuration=default.thresholds.as_dict(),
            cooldown_hours=default.cooldown_hours,
        )
        for default in default_rule_set()
    ]
