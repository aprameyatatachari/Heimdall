"""Asset ORM model.

An asset is a tradable instrument shared across every portfolio. Assets are
reference data: they are created on demand when a position needs one, and their
metadata is enriched by the market-data subsystem in a later phase.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import TimestampMixin, UUIDPrimaryKey
from app.database import Base

SYMBOL_MAX_LENGTH = 24


class AssetType(StrEnum):
    """Instrument classification.

    `UNKNOWN` is the honest value for an asset created from a position before any
    market-data provider has described it. It is never presented as a fact.
    """

    EQUITY = "equity"
    ETF = "etf"
    UNKNOWN = "unknown"


class Asset(TimestampMixin, Base):
    """A tradable instrument."""

    __tablename__ = "assets"

    id: Mapped[UUIDPrimaryKey]
    # Normalized to upper case by `normalize_symbol`.
    symbol: Mapped[str] = mapped_column(String(SYMBOL_MAX_LENGTH), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    asset_type: Mapped[AssetType] = mapped_column(
        String(16),
        nullable=False,
        default=AssetType.UNKNOWN,
    )
    exchange: Mapped[str | None] = mapped_column(String(32), default=None)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64), default=None)
    industry: Mapped[str | None] = mapped_column(String(64), default=None)

    __table_args__ = (
        CheckConstraint("symbol = upper(symbol)", name="ck_assets_symbol_upper"),
        CheckConstraint("length(symbol) > 0", name="ck_assets_symbol_not_empty"),
        CheckConstraint("currency = upper(currency)", name="ck_assets_currency_upper"),
        CheckConstraint("length(currency) = 3", name="ck_assets_currency_length"),
    )

    def __repr__(self) -> str:
        return f"<Asset symbol={self.symbol}>"
