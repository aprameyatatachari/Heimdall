"""Market-data API schemas."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.assets.models import AssetType
from app.common.schemas import ApiModel

PRICE_SCALE = Decimal("0.000001")


class AssetSearchItem(BaseModel):
    """One instrument matching a search."""

    symbol: str
    name: str | None
    asset_type: AssetType
    exchange: str | None
    currency: str


class AssetSearchResponse(BaseModel):
    """Search results, together with the data source that produced them."""

    query: str
    source: str = Field(description="Market-data source that answered the search.")
    items: list[AssetSearchItem]


class PriceBarResponse(ApiModel):
    """One daily observation.

    `adjusted_close` is the series Heimdall uses for every return calculation.
    """

    date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    adjusted_close: Decimal
    volume: Decimal | None

    @field_serializer("open", "high", "low", "close", "adjusted_close")
    def _serialize_price(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value.quantize(PRICE_SCALE))

    @field_serializer("volume")
    def _serialize_volume(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class PriceSeriesResponse(BaseModel):
    """A price series with the context needed to interpret it."""

    symbol: str
    name: str | None
    currency: str
    source: str
    start: date | None
    end: date | None
    observation_count: int
    # Expected trading days between the newest observation and today, under
    # Heimdall's weekday trading-calendar convention.
    staleness_trading_days: int | None
    bars: list[PriceBarResponse]


class DataQualityNote(BaseModel):
    """A problem found while ingesting provider data."""

    date: date | None
    issue: str
    message: str
    rejected: bool = Field(description="True when the observation was discarded.")


class AssetRefreshResult(BaseModel):
    """Ingestion outcome for one asset."""

    symbol: str
    asset_id: uuid.UUID
    up_to_date: bool = Field(description="True when nothing needed fetching.")
    ranges_fetched: int
    observations_received: int
    bars_written: int
    observations_rejected: int
    observations_flagged: int
    latest_date: date | None
    staleness_trading_days: int | None
    notes: list[DataQualityNote]


class RefreshFailure(BaseModel):
    """An asset that could not be refreshed."""

    symbol: str
    message: str


class MarketDataRefreshResponse(BaseModel):
    """Result of refreshing every holding in a portfolio."""

    portfolio_id: uuid.UUID
    data_as_of: date = Field(description="The as-of date the refresh targeted, in UTC.")
    source: str
    requested_start: date
    requested_end: date
    assets_refreshed: int
    bars_written: int
    results: list[AssetRefreshResult]
    # Present when some assets failed. Successful assets are still reported above.
    failures: list[RefreshFailure]
