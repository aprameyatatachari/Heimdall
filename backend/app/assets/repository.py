"""Persistence for assets."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset


class AssetRepository:
    """Queries and writes for the `assets` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, asset_id: uuid.UUID) -> Asset | None:
        """Return an asset by primary key."""
        return await self._session.get(Asset, asset_id)

    async def get_by_symbol(self, symbol: str) -> Asset | None:
        """Return an asset by normalized symbol."""
        result = await self._session.execute(select(Asset).where(Asset.symbol == symbol))
        return result.scalar_one_or_none()

    async def list_by_symbols(self, symbols: Sequence[str]) -> list[Asset]:
        """Return every asset whose symbol is in the given list."""
        if not symbols:
            return []
        result = await self._session.execute(select(Asset).where(Asset.symbol.in_(symbols)))
        return list(result.scalars())

    def add(self, asset: Asset) -> Asset:
        """Stage a new asset for insertion."""
        self._session.add(asset)
        return asset
