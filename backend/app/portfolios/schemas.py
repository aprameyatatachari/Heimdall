"""Portfolio and position API schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.assets.models import AssetType
from app.assets.symbols import InvalidSymbolError, normalize_symbol
from app.common.schemas import ApiModel
from app.portfolios.models import (
    PORTFOLIO_DESCRIPTION_MAX_LENGTH,
    PORTFOLIO_NAME_MAX_LENGTH,
    SUPPORTED_BASE_CURRENCIES,
)

# Quantities and money are serialized as strings so that a JSON client cannot
# lose precision through binary floating point.
QuantityField = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]
MoneyField = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=4)]

# Scales used on the wire. A value read back from PostgreSQL carries the column's
# full scale, while one just parsed from a request carries the client's. Both are
# normalized here so the same amount always looks the same to a client.
QUANTITY_SCALE = Decimal("0.00000001")
MONEY_SCALE = Decimal("0.0001")


class DuplicateAssetMode(StrEnum):
    """What to do when the asset is already held in the portfolio.

    * `reject` — fail with a conflict, leaving the existing position untouched.
    * `merge` — combine the quantities and recompute a weighted-average cost.
    """

    REJECT = "reject"
    MERGE = "merge"


def _normalize_symbol_field(value: str) -> str:
    try:
        return normalize_symbol(value)
    except InvalidSymbolError as exc:
        raise ValueError(str(exc)) from exc


class PortfolioCreateRequest(BaseModel):
    """Payload for creating a portfolio."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=PORTFOLIO_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=PORTFOLIO_DESCRIPTION_MAX_LENGTH)
    base_currency: str = Field(
        default=SUPPORTED_BASE_CURRENCIES[0],
        description=(
            "ISO 4217 code. Heimdall does not convert between currencies, so a "
            f"portfolio accepts only assets in this currency. Supported: "
            f"{', '.join(SUPPORTED_BASE_CURRENCIES)}."
        ),
    )
    benchmark_symbol: str | None = Field(
        default=None,
        description="Optional comparison benchmark, for example SPY.",
    )

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name must not be blank.")
        return trimmed

    @field_validator("description")
    @classmethod
    def _trim_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("base_currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SUPPORTED_BASE_CURRENCIES:
            raise ValueError(
                f"Unsupported base currency. Supported: {', '.join(SUPPORTED_BASE_CURRENCIES)}."
            )
        return normalized

    @field_validator("benchmark_symbol")
    @classmethod
    def _validate_benchmark(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _normalize_symbol_field(value)


class PortfolioUpdateRequest(BaseModel):
    """Payload for a partial portfolio update.

    `base_currency` is deliberately absent: changing it would invalidate every
    stored position and analysis for the portfolio.
    """

    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=PORTFOLIO_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=PORTFOLIO_DESCRIPTION_MAX_LENGTH)
    benchmark_symbol: str | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Name must not be blank.")
        return trimmed

    @field_validator("description")
    @classmethod
    def _trim_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("benchmark_symbol")
    @classmethod
    def _validate_benchmark(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _normalize_symbol_field(value)


class AssetResponse(ApiModel):
    """Reference data for an instrument."""

    id: uuid.UUID
    symbol: str
    name: str | None
    asset_type: AssetType
    exchange: str | None
    currency: str
    sector: str | None
    industry: str | None


class PositionResponse(ApiModel):
    """A holding, as returned by the API."""

    id: uuid.UUID
    portfolio_id: uuid.UUID
    asset: AssetResponse
    quantity: Decimal
    average_cost: Decimal
    # Quantity times average cost. This is acquisition cost, not market value:
    # market value requires prices, which arrive with the market-data subsystem.
    cost_basis: Decimal
    currency: str
    purchase_date: date | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("quantity")
    def _serialize_quantity(self, value: Decimal) -> str:
        return str(value.quantize(QUANTITY_SCALE))

    @field_serializer("average_cost", "cost_basis")
    def _serialize_money(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_SCALE))


class PortfolioResponse(ApiModel):
    """A portfolio without its positions."""

    id: uuid.UUID
    name: str
    description: str | None
    base_currency: str
    benchmark_symbol: str | None
    position_count: int
    created_at: datetime
    updated_at: datetime


class PortfolioDetailResponse(PortfolioResponse):
    """A portfolio together with its positions."""

    positions: list[PositionResponse]
    # Sum of every position's cost basis. Not a market valuation.
    total_cost_basis: Decimal

    @field_serializer("total_cost_basis")
    def _serialize_total(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_SCALE))


class PositionCreateRequest(BaseModel):
    """Payload for adding a position."""

    model_config = {"extra": "forbid"}

    symbol: str = Field(description="Ticker symbol, for example AAPL.")
    quantity: QuantityField
    average_cost: MoneyField = Field(
        description="Average acquisition cost per unit, in the portfolio base currency."
    )
    purchase_date: date | None = None
    on_duplicate: DuplicateAssetMode = Field(
        default=DuplicateAssetMode.REJECT,
        description=(
            "Behaviour when the portfolio already holds this asset. "
            "`reject` fails with 409; `merge` combines quantities and recomputes "
            "the weighted-average cost."
        ),
    )

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        return _normalize_symbol_field(value)

    @field_validator("purchase_date")
    @classmethod
    def _reject_future_dates(cls, value: date | None) -> date | None:
        from datetime import UTC
        from datetime import datetime as dt

        if value is not None and value > dt.now(UTC).date():
            raise ValueError("Purchase date must not be in the future.")
        return value


class ImportSummaryResponse(BaseModel):
    """Result of a CSV import."""

    mode: str = Field(description="The import mode that was applied.")
    rows_read: int = Field(description="Number of holdings read from the file.")
    positions_created: int = Field(description="New holdings inserted.")
    positions_merged: int = Field(description="Existing holdings combined with a file row.")
    positions_removed: int = Field(description="Holdings deleted. Non-zero only in replace mode.")
    position_count: int = Field(description="Holdings in the portfolio after the import.")
    positions: list[PositionResponse] = Field(description="The portfolio's holdings afterwards.")
    total_cost_basis: Decimal = Field(
        description="Sum of every holding's acquisition cost. Not a market valuation."
    )

    @field_serializer("total_cost_basis")
    def _serialize_total(self, value: Decimal) -> str:
        return str(value.quantize(MONEY_SCALE))


class PositionUpdateRequest(BaseModel):
    """Payload for a partial position update.

    The asset cannot be changed: delete the position and add the correct one, so
    that history stays interpretable.
    """

    model_config = {"extra": "forbid"}

    quantity: QuantityField | None = None
    average_cost: MoneyField | None = None
    purchase_date: date | None = None

    @field_validator("purchase_date")
    @classmethod
    def _reject_future_dates(cls, value: date | None) -> date | None:
        from datetime import UTC
        from datetime import datetime as dt

        if value is not None and value > dt.now(UTC).date():
            raise ValueError("Purchase date must not be in the future.")
        return value
