"""Persistence for price bars."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.market_data.models import PriceBar, PriceSource


class PriceBarRepository:
    """Queries and idempotent writes for the `price_bars` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_asset(
        self,
        asset_id: uuid.UUID,
        *,
        start: date | None = None,
        end: date | None = None,
        source: PriceSource | None = None,
        limit: int | None = None,
    ) -> list[PriceBar]:
        """Return an asset's bars in ascending date order."""
        statement = select(PriceBar).where(PriceBar.asset_id == asset_id)
        if start is not None:
            statement = statement.where(PriceBar.date >= start)
        if end is not None:
            statement = statement.where(PriceBar.date <= end)
        if source is not None:
            statement = statement.where(PriceBar.source == source)
        statement = statement.order_by(PriceBar.date.asc())
        if limit is not None:
            statement = statement.limit(limit)

        result = await self._session.execute(statement)
        return list(result.scalars())

    async def stored_dates(
        self,
        asset_id: uuid.UUID,
        *,
        start: date,
        end: date,
        source: PriceSource | None = None,
    ) -> set[date]:
        """Which dates are already stored for an asset in a window.

        Used for gap detection, so only the dates are fetched rather than whole rows.
        """
        statement = select(PriceBar.date).where(
            PriceBar.asset_id == asset_id,
            PriceBar.date >= start,
            PriceBar.date <= end,
        )
        if source is not None:
            statement = statement.where(PriceBar.source == source)

        result = await self._session.execute(statement)
        return set(result.scalars())

    async def latest_date(
        self,
        asset_id: uuid.UUID,
        *,
        source: PriceSource | None = None,
    ) -> date | None:
        """The most recent stored date for an asset, if any."""
        statement = select(func.max(PriceBar.date)).where(PriceBar.asset_id == asset_id)
        if source is not None:
            statement = statement.where(PriceBar.source == source)

        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def latest_dates(self, asset_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, date]:
        """The most recent stored date for several assets, in one query."""
        if not asset_ids:
            return {}
        result = await self._session.execute(
            select(PriceBar.asset_id, func.max(PriceBar.date))
            .where(PriceBar.asset_id.in_(asset_ids))
            .group_by(PriceBar.asset_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_for_asset(self, asset_id: uuid.UUID) -> int:
        """How many bars are stored for an asset."""
        result = await self._session.execute(
            select(func.count()).select_from(PriceBar).where(PriceBar.asset_id == asset_id)
        )
        return int(result.scalar_one())

    async def upsert_many(self, rows: list[dict[str, Any]]) -> int:
        """Insert or update bars, keyed by (asset_id, date, source).

        Ingestion is idempotent: re-fetching a window that is already stored
        refreshes the values instead of creating duplicates. A provider may revise
        a bar — a late split adjustment, a corrected close — so the newer values win.
        """
        if not rows:
            return 0

        statement = pg_insert(PriceBar).values(rows)
        statement = statement.on_conflict_do_update(
            constraint="uq_price_bars_asset_date_source",
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "adjusted_close": statement.excluded.adjusted_close,
                "volume": statement.excluded.volume,
                "currency": statement.excluded.currency,
            },
        )

        result = await self._session.execute(statement)
        return int(cast(CursorResult[Any], result).rowcount or 0)
