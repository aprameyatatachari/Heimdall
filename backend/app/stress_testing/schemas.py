"""Stress-testing API schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.analytics.models import RunStatus
from app.assets.symbols import InvalidSymbolError, normalize_symbol
from app.common.schemas import ApiModel
from app.stress_testing.scenarios import (
    MAX_SHOCK_VALUE,
    MIN_SHOCK_VALUE,
    STRESS_TEST_LIMITATIONS,
    ShockTargetType,
    ShockType,
)

MAX_SHOCKS = 50
MAX_SCENARIO_NAME_LENGTH = 120


class ScenarioCatalogueItem(BaseModel):
    """One historical scenario in the catalogue."""

    key: str
    name: str
    description: str
    start: date
    end: date
    window: str = Field(description="Human-readable date range.")


class ScenarioCatalogueResponse(BaseModel):
    """The available historical scenarios, with shared limitations."""

    scenario_type: str = "historical"
    items: list[ScenarioCatalogueItem]
    limitations: list[str] = Field(default_factory=lambda: list(STRESS_TEST_LIMITATIONS))


class ShockRequest(BaseModel):
    """One shock in a hypothetical scenario."""

    model_config = {"extra": "forbid"}

    target_type: ShockTargetType
    target: str | None = Field(
        default=None,
        max_length=64,
        description="Symbol or sector name. Omit for a portfolio-wide shock.",
    )
    shock_type: ShockType = Field(
        default=ShockType.RELATIVE_PRICE,
        description="Only relative_price is supported.",
    )
    value: Decimal = Field(
        ge=MIN_SHOCK_VALUE,
        le=MAX_SHOCK_VALUE,
        description="Relative price change as a decimal: -0.20 is a 20% fall.",
    )

    @model_validator(mode="after")
    def _validate_target(self) -> ShockRequest:
        """A symbol or sector shock needs a target; a portfolio shock must not have one."""
        if self.target_type is ShockTargetType.PORTFOLIO:
            return self

        if not self.target or not self.target.strip():
            raise ValueError(f"A {self.target_type} shock requires a target.")

        if self.target_type is ShockTargetType.SYMBOL:
            try:
                object.__setattr__(self, "target", normalize_symbol(self.target))
            except InvalidSymbolError as exc:
                raise ValueError(str(exc)) from exc
        else:
            object.__setattr__(self, "target", self.target.strip())

        return self


class HypotheticalScenarioRequest(BaseModel):
    """A user-defined scenario."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=MAX_SCENARIO_NAME_LENGTH)
    shocks: list[ShockRequest] = Field(min_length=1, max_length=MAX_SHOCKS)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Scenario name must not be blank.")
        return trimmed

    @model_validator(mode="after")
    def _reject_duplicate_targets(self) -> HypotheticalScenarioRequest:
        """Two shocks on the same target are ambiguous, so they are refused."""
        seen: set[tuple[str, str | None]] = set()
        for shock in self.shocks:
            key = (str(shock.target_type), shock.target)
            if key in seen:
                label = shock.target or "the whole portfolio"
                raise ValueError(f"More than one {shock.target_type} shock targets {label}.")
            seen.add(key)
        return self


class StressTestRequest(BaseModel):
    """Run either a catalogue scenario or a custom one, never both."""

    model_config = {"extra": "forbid"}

    scenario_key: str | None = Field(
        default=None,
        description="Key of a historical scenario from GET /api/v1/stress-scenarios.",
    )
    custom: HypotheticalScenarioRequest | None = Field(
        default=None,
        description="A hypothetical scenario defined by explicit shocks.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> StressTestRequest:
        if (self.scenario_key is None) == (self.custom is None):
            raise ValueError("Provide exactly one of scenario_key or custom.")
        return self


class PositionImpactResponse(BaseModel):
    """The estimated effect of a scenario on one holding."""

    symbol: str
    sector: str
    starting_value: Decimal
    applied_return: Decimal = Field(description="The return applied, as a decimal fraction.")
    return_source: str = Field(description="How the applied return was determined.")
    ending_value: Decimal
    impact: Decimal = Field(description="Negative for a loss.")
    impact_percent: Decimal
    contribution_to_loss: Decimal | None = Field(
        description=(
            "Share of the portfolio's total loss. Null when the scenario is not a "
            "loss overall. Negative for a holding that offset part of the loss."
        )
    )


class StressTestRunResponse(ApiModel):
    """A completed stress test."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    scenario_type: str
    scenario_name: str
    scenario_definition: dict[str, Any] = Field(
        description="The complete scenario, stored so the result stays explainable."
    )
    status: RunStatus = Field(
        description="`partial` means some holdings were excluded for lack of data."
    )
    data_as_of: date | None
    currency: str
    starting_value: Decimal
    ending_value: Decimal
    total_impact: Decimal
    total_impact_percent: Decimal
    positions: list[PositionImpactResponse]
    excluded_symbols: list[str] = Field(
        description="Holdings with no price data for the scenario. Not counted as zero."
    )
    reconciles: bool = Field(
        description="True when the position impacts sum to the portfolio impact."
    )
    limitations: list[str]
    disclaimer: str
    created_at: datetime
    completed_at: datetime | None


class StressTestRunSummary(ApiModel):
    """A stress test without its position breakdown, for listings."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    scenario_type: str
    scenario_name: str
    status: RunStatus
    data_as_of: date | None
    total_impact: Decimal | None
    total_impact_percent: Decimal | None
    created_at: datetime
