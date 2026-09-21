"""Persistence for analysis runs and their results."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.models import AnalysisRun
from app.portfolios.models import Portfolio


class AnalysisRunRepository:
    """Queries and writes for `analysis_runs`.

    Ownership is enforced by joining through the portfolio, so a run belonging to
    another user is simply not found.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, run: AnalysisRun) -> AnalysisRun:
        """Stage a new run for insertion."""
        self._session.add(run)
        return run

    async def get_owned(self, run_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisRun | None:
        """Return a run with its results, only if the caller owns its portfolio."""
        result = await self._session.execute(
            select(AnalysisRun)
            .join(Portfolio, AnalysisRun.portfolio_id == Portfolio.id)
            .where(AnalysisRun.id == run_id, Portfolio.user_id == user_id)
            .options(selectinload(AnalysisRun.results))
        )
        return result.unique().scalar_one_or_none()

    async def list_for_portfolio(
        self,
        portfolio_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[AnalysisRun]:
        """Return a portfolio's runs, newest first, with a stable tiebreak."""
        result = await self._session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.portfolio_id == portfolio_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(AnalysisRun.results))
        )
        return list(result.unique().scalars())

    async def count_for_portfolio(self, portfolio_id: uuid.UUID) -> int:
        """How many runs a portfolio has."""
        result = await self._session.execute(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.portfolio_id == portfolio_id)
        )
        return int(result.scalar_one())

    async def latest_for_portfolio(self, portfolio_id: uuid.UUID) -> AnalysisRun | None:
        """The most recent run for a portfolio, if any."""
        runs = await self.list_for_portfolio(portfolio_id, limit=1, offset=0)
        return runs[0] if runs else None
