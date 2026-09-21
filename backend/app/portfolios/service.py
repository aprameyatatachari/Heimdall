"""Portfolio and position use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.service import AssetService
from app.common.errors import ConflictError, NotFoundError, ValidationError
from app.common.logging import get_logger
from app.portfolios.models import Portfolio, Position
from app.portfolios.repository import PortfolioRepository, PositionRepository
from app.portfolios.schemas import DuplicateAssetMode

logger = get_logger(__name__)

# Bound on portfolio size, so analytics requests stay predictable.
MAX_POSITIONS_PER_PORTFOLIO = 200
MAX_PORTFOLIOS_PER_USER = 50

# Weighted-average cost is rounded to the precision of the stored column.
COST_QUANTIZE = Decimal("0.0001")


class PortfolioNotFoundError(NotFoundError):
    """The portfolio does not exist, or does not belong to the caller.

    The same error is returned in both cases, so the API cannot be used to
    discover that another user's portfolio exists.
    """

    code = "portfolio_not_found"
    message = "Portfolio not found."


class PositionNotFoundError(NotFoundError):
    """The position does not exist in this portfolio."""

    code = "position_not_found"
    message = "Position not found."


class DuplicatePortfolioNameError(ConflictError):
    """The user already has a portfolio with this name."""

    code = "portfolio_name_taken"
    message = "You already have a portfolio with this name."


class DuplicatePositionError(ConflictError):
    """The portfolio already holds this asset."""

    code = "position_already_exists"
    message = (
        "This portfolio already holds this asset. "
        "Update the existing position, or retry with on_duplicate=merge."
    )


class PortfolioLimitReachedError(ConflictError):
    """The account has reached the maximum number of portfolios."""

    code = "portfolio_limit_reached"
    message = f"An account may hold at most {MAX_PORTFOLIOS_PER_USER} portfolios."


class PositionLimitReachedError(ConflictError):
    """The portfolio has reached the maximum number of positions."""

    code = "position_limit_reached"
    message = f"A portfolio may hold at most {MAX_POSITIONS_PER_PORTFOLIO} positions."


class NoFieldsToUpdateError(ValidationError):
    """A partial update contained no fields."""

    code = "no_fields_to_update"
    message = "Provide at least one field to update."


@dataclass(frozen=True, slots=True)
class PortfolioWithCount:
    """A portfolio together with its position count."""

    portfolio: Portfolio
    position_count: int


@dataclass(frozen=True, slots=True)
class PortfolioPage:
    """One page of portfolios."""

    items: list[PortfolioWithCount]
    total: int


class PortfolioService:
    """Creates, reads, updates, and deletes portfolios."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
    ) -> None:
        self._session = session
        self._portfolios = portfolios

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        base_currency: str,
        benchmark_symbol: str | None,
    ) -> Portfolio:
        """Create a portfolio for a user."""
        if await self._portfolios.count_for_user(user_id) >= MAX_PORTFOLIOS_PER_USER:
            raise PortfolioLimitReachedError()

        if await self._portfolios.name_taken(user_id, name):
            raise DuplicatePortfolioNameError()

        portfolio = Portfolio(
            user_id=user_id,
            name=name,
            description=description,
            base_currency=base_currency,
            benchmark_symbol=benchmark_symbol,
        )
        self._portfolios.add(portfolio)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicatePortfolioNameError() from exc

        logger.info("portfolio_created", portfolio_id=str(portfolio.id))
        return portfolio

    async def get(self, *, portfolio_id: uuid.UUID, user_id: uuid.UUID) -> PortfolioWithCount:
        """Return a portfolio owned by the user."""
        portfolio = await self._require_owned(portfolio_id, user_id)
        count = await self._portfolios.count_positions(portfolio.id)
        return PortfolioWithCount(portfolio=portfolio, position_count=count)

    async def get_with_positions(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Portfolio:
        """Return a portfolio and its positions, owned by the user."""
        portfolio = await self._portfolios.get_owned_with_positions(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> PortfolioPage:
        """Return one page of the user's portfolios."""
        portfolios = await self._portfolios.list_for_user(user_id, limit=limit, offset=offset)
        total = await self._portfolios.count_for_user(user_id)
        counts = await self._portfolios.position_counts([p.id for p in portfolios])
        return PortfolioPage(
            items=[
                PortfolioWithCount(portfolio=p, position_count=counts.get(p.id, 0))
                for p in portfolios
            ],
            total=total,
        )

    async def update(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        fields: dict[str, object],
    ) -> PortfolioWithCount:
        """Apply a partial update to a portfolio.

        `fields` contains only the keys the client actually sent, so an explicit
        `null` clears a value while an omitted key leaves it unchanged.
        """
        if not fields:
            raise NoFieldsToUpdateError()

        portfolio = await self._require_owned(portfolio_id, user_id)

        new_name = fields.get("name")
        if isinstance(new_name, str) and await self._portfolios.name_taken(
            user_id, new_name, exclude_id=portfolio.id
        ):
            raise DuplicatePortfolioNameError()

        for key, value in fields.items():
            setattr(portfolio, key, value)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicatePortfolioNameError() from exc

        count = await self._portfolios.count_positions(portfolio.id)
        logger.info("portfolio_updated", portfolio_id=str(portfolio.id))
        return PortfolioWithCount(portfolio=portfolio, position_count=count)

    async def delete(self, *, portfolio_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a portfolio and, by cascade, its positions."""
        portfolio = await self._require_owned(portfolio_id, user_id)
        await self._portfolios.delete(portfolio)
        await self._session.flush()
        logger.info("portfolio_deleted", portfolio_id=str(portfolio_id))

    async def _require_owned(self, portfolio_id: uuid.UUID, user_id: uuid.UUID) -> Portfolio:
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio


class PositionService:
    """Adds, updates, and removes holdings inside a portfolio."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        positions: PositionRepository,
        assets: AssetService,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._positions = positions
        self._assets = assets

    async def add(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        symbol: str,
        quantity: Decimal,
        average_cost: Decimal,
        purchase_date: date | None,
        on_duplicate: DuplicateAssetMode,
    ) -> Position:
        """Add a position, merging into an existing holding when asked to."""
        portfolio = await self._require_owned_portfolio(portfolio_id, user_id)

        asset = await self._assets.resolve_or_create(
            raw_symbol=symbol,
            currency=portfolio.base_currency,
        )

        existing = await self._positions.get_by_asset(portfolio.id, asset.id)
        if existing is not None:
            if on_duplicate is DuplicateAssetMode.REJECT:
                raise DuplicatePositionError()
            return await self._merge_into(
                existing,
                quantity=quantity,
                average_cost=average_cost,
                purchase_date=purchase_date,
            )

        if await self._portfolios.count_positions(portfolio.id) >= MAX_POSITIONS_PER_PORTFOLIO:
            raise PositionLimitReachedError()

        position = Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=quantity,
            average_cost=average_cost,
            purchase_date=purchase_date,
        )
        self._positions.add(position)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicatePositionError() from exc

        await self._session.refresh(position, attribute_names=["asset"])
        logger.info(
            "position_added",
            portfolio_id=str(portfolio.id),
            position_id=str(position.id),
        )
        return position

    async def update(
        self,
        *,
        portfolio_id: uuid.UUID,
        position_id: uuid.UUID,
        user_id: uuid.UUID,
        fields: dict[str, object],
    ) -> Position:
        """Apply a partial update to a position."""
        if not fields:
            raise NoFieldsToUpdateError()

        await self._require_owned_portfolio(portfolio_id, user_id)
        position = await self._positions.get_in_portfolio(position_id, portfolio_id)
        if position is None:
            raise PositionNotFoundError()

        for key, value in fields.items():
            setattr(position, key, value)

        await self._session.flush()
        await self._session.refresh(position, attribute_names=["asset"])
        logger.info("position_updated", position_id=str(position.id))
        return position

    async def delete(
        self,
        *,
        portfolio_id: uuid.UUID,
        position_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Remove a position from a portfolio."""
        await self._require_owned_portfolio(portfolio_id, user_id)
        position = await self._positions.get_in_portfolio(position_id, portfolio_id)
        if position is None:
            raise PositionNotFoundError()

        await self._positions.delete(position)
        await self._session.flush()
        logger.info("position_deleted", position_id=str(position_id))

    async def list_for_portfolio(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Position]:
        """Return every position in a portfolio owned by the user."""
        await self._require_owned_portfolio(portfolio_id, user_id)
        return await self._positions.list_for_portfolio(portfolio_id)

    async def _merge_into(
        self,
        existing: Position,
        *,
        quantity: Decimal,
        average_cost: Decimal,
        purchase_date: date | None,
    ) -> Position:
        """Combine an addition into an existing position.

        Quantities add. The new average cost is the cost-weighted mean:

            (q_old * c_old + q_new * c_new) / (q_old + q_new)

        The earliest of the two purchase dates is kept, because that is when the
        holding began.
        """
        total_quantity = existing.quantity + quantity
        total_cost = existing.quantity * existing.average_cost + quantity * average_cost

        existing.quantity = total_quantity
        existing.average_cost = (total_cost / total_quantity).quantize(COST_QUANTIZE)

        if purchase_date is not None:
            existing.purchase_date = (
                purchase_date
                if existing.purchase_date is None
                else min(existing.purchase_date, purchase_date)
            )

        await self._session.flush()
        await self._session.refresh(existing, attribute_names=["asset"])
        logger.info("position_merged", position_id=str(existing.id))
        return existing

    async def _require_owned_portfolio(
        self,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Portfolio:
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio
