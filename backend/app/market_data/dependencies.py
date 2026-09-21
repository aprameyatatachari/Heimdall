"""Market-data provider selection and service wiring.

The provider is chosen by configuration. Tests and local development use the
committed offline fixtures, so no test result depends on a third party.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from app.assets.repository import AssetRepository
from app.common.dependencies import ClockDep, SessionDep, SettingsDep
from app.market_data.fixture_provider import FixtureMarketDataProvider
from app.market_data.provider import MarketDataProvider
from app.market_data.repository import PriceBarRepository
from app.market_data.service import MarketDataService


@lru_cache(maxsize=4)
def _build_provider(name: str, fixture_root: str | None) -> MarketDataProvider:
    """Build and cache the configured provider."""
    if name == "fixture":
        return FixtureMarketDataProvider(Path(fixture_root) if fixture_root else None)
    raise ValueError(f"Unknown market-data provider {name!r}. Supported providers: fixture.")


def get_market_data_provider(settings: SettingsDep) -> MarketDataProvider:
    """Return the configured market-data provider."""
    return _build_provider(settings.market_data_provider, settings.market_data_fixture_root)


ProviderDep = Annotated[MarketDataProvider, Depends(get_market_data_provider)]


def get_market_data_service(
    session: SessionDep,
    provider: ProviderDep,
    clock: ClockDep,
) -> MarketDataService:
    """Build the market-data service for this request."""
    return MarketDataService(
        session=session,
        assets=AssetRepository(session),
        price_bars=PriceBarRepository(session),
        provider=provider,
        clock=clock,
    )


MarketDataServiceDep = Annotated[MarketDataService, Depends(get_market_data_service)]
