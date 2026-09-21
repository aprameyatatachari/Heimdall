"""Portfolio and position ORM models.

**Cascade decisions.**

* Deleting a user deletes their portfolios, and deleting a portfolio deletes its
  positions. Both are enforced in the database with `ON DELETE CASCADE`: a
  portfolio has no meaning without its owner, and a position has no meaning
  without its portfolio.
* Deleting an asset is *restricted*. Assets are shared reference data, so
  removing one that a position still references would silently destroy portfolio
  history. Assets are never deleted through the API.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKey
from app.database import Base

if TYPE_CHECKING:
    from app.assets.models import Asset
    from app.auth.models import User

PORTFOLIO_NAME_MAX_LENGTH = 120
PORTFOLIO_DESCRIPTION_MAX_LENGTH = 1000

# The MVP supports one base currency per portfolio and does not convert between
# currencies. Only currencies Heimdall can price consistently are accepted.
SUPPORTED_BASE_CURRENCIES = ("USD",)
DEFAULT_BASE_CURRENCY = "USD"


class Portfolio(TimestampMixin, Base):
    """A named collection of positions belonging to one user."""

    __tablename__ = "portfolios"

    id: Mapped[UUIDPrimaryKey]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(PORTFOLIO_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(
        String(PORTFOLIO_DESCRIPTION_MAX_LENGTH),
        default=None,
    )
    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default=DEFAULT_BASE_CURRENCY,
    )
    # Symbol of the comparison benchmark, for example SPY. Optional.
    benchmark_symbol: Mapped[str | None] = mapped_column(String(24), default=None)

    user: Mapped[User] = relationship(back_populates="portfolios")
    positions: Mapped[list[Position]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # One user cannot have two portfolios with the same name.
        UniqueConstraint("user_id", "name", name="uq_portfolios_user_id_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_portfolios_name_not_blank"),
        CheckConstraint(
            "base_currency = upper(base_currency)", name="ck_portfolios_currency_upper"
        ),
        CheckConstraint("length(base_currency) = 3", name="ck_portfolios_currency_length"),
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} name={self.name!r}>"


class Position(TimestampMixin, Base):
    """A holding of one asset inside one portfolio.

    A portfolio holds at most one position per asset. Adding an asset that is
    already held either merges into the existing position or is rejected,
    depending on the caller's requested mode; see `PositionService`.
    """

    __tablename__ = "positions"

    id: Mapped[UUIDPrimaryKey]
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT: shared reference data must not be removable while referenced.
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Fractional shares are common, so quantity carries eight decimal places.
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Weighted-average acquisition cost per unit, in the portfolio base currency.
    average_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date, default=None)

    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")
    asset: Mapped[Asset] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", name="uq_positions_portfolio_id_asset_id"),
        CheckConstraint("quantity > 0", name="ck_positions_quantity_positive"),
        CheckConstraint("average_cost >= 0", name="ck_positions_average_cost_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Position id={self.id} asset_id={self.asset_id}>"
