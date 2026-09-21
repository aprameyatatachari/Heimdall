"""Analytics API schemas.

Every metric carries its unit, its analysis period, and the assumptions behind it,
so no consumer has to infer whether a number is daily or annualized, a ratio or a
currency amount.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.analytics.calculations import ReturnFrequency, VarMethod
from app.analytics.models import AnalysisType, MetricUnit, RunStatus
from app.common.schemas import ApiModel

MONEY_SCALE = Decimal("0.01")


class AnalysisRunRequest(BaseModel):
    """Parameters for an analysis run. Every field has a documented default."""

    model_config = {"extra": "forbid"}

    start: date | None = Field(
        default=None,
        description="Inclusive start of the analysis window. Defaults to one year before the end.",
    )
    end: date | None = Field(
        default=None,
        description="Inclusive end of the analysis window. Defaults to today.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.5,
        lt=1.0,
        description="Confidence level for VaR and Expected Shortfall. Defaults to 0.95.",
    )
    var_method: VarMethod | None = Field(
        default=None,
        description="Which VaR estimate to highlight. Both are always computed.",
    )
    frequency: ReturnFrequency | None = Field(
        default=None,
        description="Return sampling frequency, which sets the annualization factor.",
    )
    annual_risk_free_rate: float | None = Field(
        default=None,
        ge=-0.5,
        le=1.0,
        description=(
            "Annual risk-free rate as a decimal, for example 0.045. De-annualized "
            "geometrically before use. Defaults to 0."
        ),
    )
    benchmark_symbol: str | None = Field(
        default=None,
        description="Overrides the portfolio's configured benchmark for this run.",
    )
    minimum_observations: int | None = Field(
        default=None,
        ge=2,
        le=2520,
        description="Minimum return observations required for tail measures. Defaults to 30.",
    )

    @field_validator("benchmark_symbol")
    @classmethod
    def _normalize_benchmark(cls, value: str | None) -> str | None:
        from app.assets.symbols import InvalidSymbolError, normalize_symbol

        if value is None or not value.strip():
            return None
        try:
            return normalize_symbol(value)
        except InvalidSymbolError as exc:
            raise ValueError(str(exc)) from exc


class RiskResultResponse(ApiModel):
    """One metric, with everything needed to read it correctly."""

    metric: str
    value: Decimal | None = Field(
        description="Null when the metric could not be computed; see unavailable_reason."
    )
    unit: MetricUnit
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Period, confidence, per-asset detail, and calculation assumptions.",
    )
    unavailable_reason: str | None = Field(
        default=None,
        description="Why the metric is unavailable. Never substituted with zero.",
    )


class AnalysisRunResponse(ApiModel):
    """A stored analysis run and its results."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    analysis_type: AnalysisType
    status: RunStatus = Field(
        description="`partial` means some metrics were unavailable; the rest are valid."
    )
    parameters: dict[str, Any]
    data_as_of: date | None = Field(
        description="Newest market-data date used. Null when no prices were available."
    )
    notes: list[str] = Field(description="Assumptions and caveats that apply to the whole run.")
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    results: list[RiskResultResponse]


class AnalysisRunSummary(ApiModel):
    """A run without its results, for listings."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    analysis_type: AnalysisType
    status: RunStatus
    data_as_of: date | None
    created_at: datetime
    completed_at: datetime | None
    result_count: int


class HoldingSummaryResponse(BaseModel):
    """One holding, valued at its latest stored price."""

    symbol: str
    name: str | None
    sector: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    latest_price: Decimal | None
    latest_price_date: date | None
    market_value: Decimal | None
    weight: float | None = Field(description="Share of portfolio value. Null when unpriced.")
    unrealized_profit_loss: Decimal | None

    @field_serializer(
        "average_cost",
        "cost_basis",
        "latest_price",
        "market_value",
        "unrealized_profit_loss",
    )
    def _serialize_money(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value.quantize(MONEY_SCALE))

    @field_serializer("quantity")
    def _serialize_quantity(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.00000001")))


class PortfolioSummaryResponse(BaseModel):
    """Current valuation of a portfolio. No historical statistics.

    Uses the newest stored price for each holding, which may be older than today.
    `data_as_of` and `stale_symbols` say so explicitly.
    """

    portfolio_id: uuid.UUID
    name: str
    base_currency: str
    benchmark_symbol: str | None
    data_as_of: date | None
    holdings_count: int
    priced_holdings_count: int
    unpriced_symbols: list[str] = Field(
        description="Holdings with no stored price. Excluded from value and weights."
    )
    total_market_value: Decimal
    total_cost_basis: Decimal
    unrealized_profit_loss: Decimal
    unrealized_profit_loss_percent: float | None
    largest_position_weight: float | None
    sector_weights: dict[str, float]
    unknown_sector_weight: float = Field(
        description="Share of value whose sector is unknown. Sector exposure is incomplete above 0."
    )
    holdings: list[HoldingSummaryResponse]
    disclaimer: str

    @field_serializer("total_market_value", "total_cost_basis", "unrealized_profit_loss")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_SCALE))
