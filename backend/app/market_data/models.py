"""Market-data ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import UUIDPrimaryKey
from app.database import Base


class PriceSource(StrEnum):
    """Where a price bar came from.

    Stored on every bar so that data of different provenance can be told apart,
    and so a fixture-seeded database is never mistaken for live data.
    """

    FIXTURE = "fixture"
    STOOQ = "stooq"
    MANUAL = "manual"


class PriceBar(Base):
    """One daily observation for one asset from one source.

    `adjusted_close` is the series used for every return calculation. `close` is
    kept for display and for validating OHLC relationships.
    """

    __tablename__ = "price_bars"

    id: Mapped[UUIDPrimaryKey]
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), default=None)
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), default=None)
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), default=None)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    adjusted_close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), default=None)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[PriceSource] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        # Idempotent ingestion depends on this: re-fetching a range updates rather
        # than duplicates.
        UniqueConstraint("asset_id", "date", "source", name="uq_price_bars_asset_date_source"),
        # The usual query is "this asset, this date range, in order".
        Index("ix_price_bars_asset_id_date", "asset_id", "date"),
        CheckConstraint("close > 0", name="ck_price_bars_close_positive"),
        CheckConstraint("adjusted_close > 0", name="ck_price_bars_adjusted_positive"),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_price_bars_volume_non_negative"),
        CheckConstraint("currency = upper(currency)", name="ck_price_bars_currency_upper"),
        CheckConstraint("length(currency) = 3", name="ck_price_bars_currency_length"),
    )

    def __repr__(self) -> str:
        return f"<PriceBar asset_id={self.asset_id} date={self.date}>"
