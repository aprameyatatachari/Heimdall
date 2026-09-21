"""Asset use cases."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType
from app.assets.repository import AssetRepository
from app.assets.symbols import InvalidSymbolError, normalize_symbol
from app.common.errors import ValidationError


class InvalidSymbolRequestError(ValidationError):
    """The submitted ticker symbol is not usable."""

    code = "invalid_symbol"


class CurrencyMismatchError(ValidationError):
    """The asset is denominated in a currency the portfolio does not use.

    Heimdall does not convert between currencies yet, so mixing them would
    silently produce meaningless portfolio totals.
    """

    code = "currency_mismatch"


class AssetService:
    """Resolves and creates reference data for instruments."""

    def __init__(self, *, session: AsyncSession, assets: AssetRepository) -> None:
        self._session = session
        self._assets = assets

    async def resolve_or_create(self, *, raw_symbol: str, currency: str) -> Asset:
        """Return the asset for a symbol, creating a placeholder when unknown.

        A newly created asset carries only its symbol and currency; its
        `asset_type` stays `unknown` until the market-data subsystem describes
        it. Nothing about the instrument is invented.

        An existing asset whose currency differs from `currency` is rejected.
        """
        try:
            symbol = normalize_symbol(raw_symbol)
        except InvalidSymbolError as exc:
            raise InvalidSymbolRequestError(str(exc)) from exc

        normalized_currency = currency.strip().upper()
        existing = await self._assets.get_by_symbol(symbol)

        if existing is not None:
            if existing.currency != normalized_currency:
                raise CurrencyMismatchError(
                    f"{symbol} is denominated in {existing.currency}, but this portfolio "
                    f"uses {normalized_currency}. Heimdall does not convert between "
                    "currencies, so the position cannot be added."
                )
            return existing

        asset = Asset(
            symbol=symbol,
            currency=normalized_currency,
            asset_type=AssetType.UNKNOWN,
        )
        self._assets.add(asset)

        try:
            await self._session.flush()
        except IntegrityError:
            # A concurrent request inserted the same symbol first.
            await self._session.rollback()
            concurrent = await self._assets.get_by_symbol(symbol)
            if concurrent is None:
                raise
            if concurrent.currency != normalized_currency:
                raise CurrencyMismatchError(
                    f"{symbol} is denominated in {concurrent.currency}, but this portfolio "
                    f"uses {normalized_currency}."
                ) from None
            return concurrent

        return asset
