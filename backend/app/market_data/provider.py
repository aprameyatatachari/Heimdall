"""The internal market-data provider interface.

Every vendor sits behind this interface. Vendor response shapes stop at the
adapter: what leaves a provider is always the domain objects defined here, so no
part of the application depends on a particular data source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.assets.models import AssetType


@dataclass(frozen=True, slots=True)
class AssetSearchResult:
    """One instrument matching a search, as the provider describes it."""

    symbol: str
    name: str | None
    asset_type: AssetType
    exchange: str | None
    currency: str


@dataclass(frozen=True, slots=True)
class AssetMetadata:
    """Reference data for one instrument."""

    symbol: str
    name: str | None
    asset_type: AssetType
    exchange: str | None
    currency: str
    sector: str | None = None
    industry: str | None = None


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """One daily observation, normalized and provider-independent.

    Decimals, not floats: these values are stored and summed.
    """

    date: date
    close: Decimal
    adjusted_close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None


class ProviderError(Exception):
    """A provider could not satisfy a request."""


class SymbolNotFoundError(ProviderError):
    """The provider does not know the requested symbol."""


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached, or refused the request."""


class MarketDataProvider(ABC):
    """Asynchronous source of instrument metadata and daily prices."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier recorded on every stored bar."""

    @abstractmethod
    async def search_assets(self, query: str, *, limit: int = 10) -> list[AssetSearchResult]:
        """Find instruments whose symbol or name matches `query`."""

    @abstractmethod
    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Return reference data for one instrument.

        Raises `SymbolNotFoundError` when the provider does not know the symbol.
        """

    @abstractmethod
    async def get_daily_prices(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[PriceObservation]:
        """Return daily observations for `symbol` between `start` and `end`.

        Both bounds are inclusive. The result is ascending by date and contains
        only trading days the provider has data for; gaps are not filled.
        """
