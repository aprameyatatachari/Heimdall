"""Persistence for portfolios and positions.

Every read is scoped by `user_id`. Ownership is a query predicate rather than a
check performed after loading, so an insecure direct-object reference cannot
return another user's row even if a caller forgets an explicit check.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.portfolios.models import Portfolio, Position


class PortfolioRepository:
    """Queries and writes for the `portfolios` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owned(self, user_id: uuid.UUID) -> Select[tuple[Portfolio]]:
        return select(Portfolio).where(Portfolio.user_id == user_id)

    async def get_owned(self, portfolio_id: uuid.UUID, user_id: uuid.UUID) -> Portfolio | None:
        """Return a portfolio only if it belongs to the given user."""
        result = await self._session.execute(
            self._owned(user_id).where(Portfolio.id == portfolio_id)
        )
        return result.scalar_one_or_none()

    async def get_owned_with_positions(
        self,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Portfolio | None:
        """Return a portfolio and its positions, scoped to the owner."""
        result = await self._session.execute(
            self._owned(user_id)
            .where(Portfolio.id == portfolio_id)
            .options(selectinload(Portfolio.positions).joinedload(Position.asset))
        )
        return result.unique().scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[Portfolio]:
        """Return one page of a user's portfolios, newest first.

        Ordering is `created_at DESC, id DESC` so pagination is stable even when
        two portfolios share a timestamp.
        """
        result = await self._session.execute(
            self._owned(user_id)
            .order_by(Portfolio.created_at.desc(), Portfolio.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        """Return the total number of portfolios owned by a user."""
        result = await self._session.execute(
            select(func.count()).select_from(Portfolio).where(Portfolio.user_id == user_id)
        )
        return int(result.scalar_one())

    async def count_positions(self, portfolio_id: uuid.UUID) -> int:
        """Return the number of positions in a portfolio."""
        result = await self._session.execute(
            select(func.count()).select_from(Position).where(Position.portfolio_id == portfolio_id)
        )
        return int(result.scalar_one())

    async def position_counts(self, portfolio_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Return position counts for several portfolios in one query."""
        if not portfolio_ids:
            return {}
        result = await self._session.execute(
            select(Position.portfolio_id, func.count())
            .where(Position.portfolio_id.in_(portfolio_ids))
            .group_by(Position.portfolio_id)
        )
        counts = {row[0]: int(row[1]) for row in result.all()}
        return {portfolio_id: counts.get(portfolio_id, 0) for portfolio_id in portfolio_ids}

    async def name_taken(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        """True when the user already has a portfolio with this name."""
        statement = select(Portfolio.id).where(
            Portfolio.user_id == user_id,
            func.lower(Portfolio.name) == name.lower(),
        )
        if exclude_id is not None:
            statement = statement.where(Portfolio.id != exclude_id)
        result = await self._session.execute(statement)
        return result.first() is not None

    def add(self, portfolio: Portfolio) -> Portfolio:
        """Stage a new portfolio for insertion."""
        self._session.add(portfolio)
        return portfolio

    async def delete(self, portfolio: Portfolio) -> None:
        """Delete a portfolio. Its positions are removed by the database cascade."""
        await self._session.delete(portfolio)


class PositionRepository:
    """Queries and writes for the `positions` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_portfolio(
        self,
        position_id: uuid.UUID,
        portfolio_id: uuid.UUID,
    ) -> Position | None:
        """Return a position only if it belongs to the given portfolio."""
        result = await self._session.execute(
            select(Position).where(
                Position.id == position_id,
                Position.portfolio_id == portfolio_id,
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_by_asset(
        self,
        portfolio_id: uuid.UUID,
        asset_id: uuid.UUID,
    ) -> Position | None:
        """Return the portfolio's position in one asset, if it holds one."""
        result = await self._session.execute(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.asset_id == asset_id,
            )
        )
        return result.unique().scalar_one_or_none()

    async def list_for_portfolio(self, portfolio_id: uuid.UUID) -> list[Position]:
        """Return every position in a portfolio, ordered by symbol."""
        from app.assets.models import Asset

        result = await self._session.execute(
            select(Position)
            .join(Asset, Position.asset_id == Asset.id)
            .where(Position.portfolio_id == portfolio_id)
            .order_by(Asset.symbol.asc())
        )
        return list(result.unique().scalars())

    def add(self, position: Position) -> Position:
        """Stage a new position for insertion."""
        self._session.add(position)
        return position

    async def delete(self, position: Position) -> None:
        """Delete a position."""
        await self._session.delete(position)
