"""Portfolio snapshots: the input every analysis and stress test works from.

A snapshot is a plain-data view of a portfolio at one instant — its holdings,
their latest prices, their market values, and their weights — assembled once and
then handed to pure functions. Keeping it separate means the calculation layer
never queries the database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset
from app.common.errors import ValidationError
from app.market_data.models import PriceSource
from app.market_data.repository import PriceBarRepository
from app.portfolios.models import Portfolio
from app.portfolios.repository import PositionRepository

# Sector label used when an instrument's sector is not known. Never presented as
# a real sector: exposure rules refuse to run when too much of this is present.
UNKNOWN_SECTOR = "Unknown"


class EmptyPortfolioError(ValidationError):
    """The portfolio has no holdings, so there is nothing to analyze."""

    code = "portfolio_empty"
    message = "This portfolio has no holdings. Add positions before running an analysis."


class NoMarketDataError(ValidationError):
    """No stored prices exist for any holding."""

    code = "no_market_data"
    message = (
        "No market data is stored for this portfolio's holdings. "
        "Refresh market data before running an analysis."
    )


class ZeroValuePortfolioError(ValidationError):
    """Every holding priced to zero, so weights are undefined."""

    code = "portfolio_zero_value"
    message = "This portfolio has no market value, so risk measures cannot be computed."


@dataclass(frozen=True, slots=True)
class HoldingSnapshot:
    """One holding, valued at its latest available price."""

    asset_id: uuid.UUID
    symbol: str
    name: str | None
    sector: str
    quantity: Decimal
    average_cost: Decimal
    # None when no price is stored for this asset.
    latest_price: Decimal | None
    latest_price_date: date | None
    currency: str

    @property
    def market_value(self) -> Decimal | None:
        """Quantity times latest price, or None when unpriced."""
        if self.latest_price is None:
            return None
        return self.quantity * self.latest_price

    @property
    def cost_basis(self) -> Decimal:
        """Quantity times average acquisition cost."""
        return self.quantity * self.average_cost

    @property
    def has_price(self) -> bool:
        """True when this holding could be valued."""
        return self.latest_price is not None


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """A portfolio valued at one instant, ready to be analyzed."""

    portfolio_id: uuid.UUID
    portfolio_name: str
    base_currency: str
    benchmark_symbol: str | None
    holdings: list[HoldingSnapshot]
    # Newest price date across every priced holding.
    data_as_of: date | None

    @property
    def priced_holdings(self) -> list[HoldingSnapshot]:
        """Holdings that could be valued."""
        return [holding for holding in self.holdings if holding.has_price]

    @property
    def unpriced_symbols(self) -> list[str]:
        """Symbols with no stored price."""
        return [holding.symbol for holding in self.holdings if not holding.has_price]

    @property
    def total_value(self) -> Decimal:
        """Sum of the market values that could be computed."""
        return sum(
            (holding.market_value or Decimal("0") for holding in self.holdings),
            Decimal("0"),
        )

    @property
    def total_cost_basis(self) -> Decimal:
        """Sum of every holding's acquisition cost."""
        return sum((holding.cost_basis for holding in self.holdings), Decimal("0"))

    def weights(self) -> dict[str, float]:
        """Weight of each priced holding, as a fraction of total value."""
        total = self.total_value
        if total == 0:
            return {}
        return {
            holding.symbol: float((holding.market_value or Decimal("0")) / total)
            for holding in self.priced_holdings
        }

    def sector_weights(self) -> dict[str, float]:
        """Weight by sector, with unknown sectors grouped under `Unknown`."""
        total = self.total_value
        if total == 0:
            return {}

        weights: dict[str, float] = {}
        for holding in self.priced_holdings:
            share = float((holding.market_value or Decimal("0")) / total)
            weights[holding.sector] = weights.get(holding.sector, 0.0) + share
        return weights

    @property
    def unknown_sector_weight(self) -> float:
        """Share of value whose sector is not known."""
        return self.sector_weights().get(UNKNOWN_SECTOR, 0.0)

    def require_analyzable(self) -> None:
        """Raise a specific error when the snapshot cannot support analysis."""
        if not self.holdings:
            raise EmptyPortfolioError()
        if not self.priced_holdings:
            raise NoMarketDataError()
        if self.total_value <= 0:
            raise ZeroValuePortfolioError()


class SnapshotBuilder:
    """Assembles a `PortfolioSnapshot` from stored positions and prices."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        positions: PositionRepository,
        price_bars: PriceBarRepository,
        source: PriceSource,
    ) -> None:
        self._session = session
        self._positions = positions
        self._price_bars = price_bars
        self._source = source

    async def build(
        self,
        portfolio: Portfolio,
        *,
        as_of: date | None = None,
    ) -> PortfolioSnapshot:
        """Value a portfolio using the newest stored price at or before `as_of`."""
        positions = await self._positions.list_for_portfolio(portfolio.id)

        holdings: list[HoldingSnapshot] = []
        newest: date | None = None

        for position in positions:
            asset: Asset = position.asset
            bars = await self._price_bars.list_for_asset(
                asset.id,
                end=as_of,
                source=self._source,
            )
            latest = bars[-1] if bars else None

            if latest is not None and (newest is None or latest.date > newest):
                newest = latest.date

            holdings.append(
                HoldingSnapshot(
                    asset_id=asset.id,
                    symbol=asset.symbol,
                    name=asset.name,
                    sector=asset.sector or UNKNOWN_SECTOR,
                    quantity=position.quantity,
                    average_cost=position.average_cost,
                    latest_price=latest.adjusted_close if latest is not None else None,
                    latest_price_date=latest.date if latest is not None else None,
                    currency=asset.currency,
                )
            )

        return PortfolioSnapshot(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            base_currency=portfolio.base_currency,
            benchmark_symbol=portfolio.benchmark_symbol,
            holdings=holdings,
            data_as_of=newest,
        )

    async def price_history(
        self,
        snapshot: PortfolioSnapshot,
        *,
        start: date,
        end: date,
    ) -> dict[str, list[tuple[date, float]]]:
        """Adjusted-close history for each priced holding, keyed by symbol."""
        history: dict[str, list[tuple[date, float]]] = {}

        for holding in snapshot.priced_holdings:
            bars = await self._price_bars.list_for_asset(
                holding.asset_id,
                start=start,
                end=end,
                source=self._source,
            )
            if len(bars) >= 2:
                history[holding.symbol] = [(bar.date, float(bar.adjusted_close)) for bar in bars]

        return history

    async def symbol_history(
        self,
        asset_id: uuid.UUID,
        *,
        start: date,
        end: date,
    ) -> list[tuple[date, float]]:
        """Adjusted-close history for one asset."""
        bars = await self._price_bars.list_for_asset(
            asset_id,
            start=start,
            end=end,
            source=self._source,
        )
        return [(bar.date, float(bar.adjusted_close)) for bar in bars]
