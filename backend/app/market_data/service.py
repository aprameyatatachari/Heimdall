"""Market-data use cases: cache-first retrieval and idempotent ingestion.

The ingestion path is fixed and documented:

1. Look at what is already stored.
2. Work out which expected trading days are missing.
3. Ask the provider only for the missing ranges.
4. Normalize what comes back into domain objects.
5. Validate it, rejecting unusable bars and flagging suspicious ones.
6. Store it idempotently, keyed by (asset, date, source).
7. Return provider-independent results.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType
from app.assets.repository import AssetRepository
from app.assets.symbols import InvalidSymbolError, normalize_symbol
from app.common.clock import Clock
from app.common.errors import NotFoundError, ServiceUnavailableError, ValidationError
from app.common.logging import get_logger
from app.market_data.calendar import DateRange, find_missing_ranges, trading_days_between
from app.market_data.models import PriceBar, PriceSource
from app.market_data.provider import (
    AssetSearchResult,
    MarketDataProvider,
    PriceObservation,
    ProviderError,
    SymbolNotFoundError,
)
from app.market_data.repository import PriceBarRepository
from app.market_data.validation import ObservationProblem, validate_observations
from app.portfolios.models import SUPPORTED_BASE_CURRENCIES

logger = get_logger(__name__)

# A gap of one expected trading day is tolerated rather than refetched forever:
# under Heimdall's weekday calendar an exchange holiday looks exactly like one
# missing day, and no provider will ever return it.
HOLIDAY_TOLERANCE_DAYS = 1

# Ingestion never asks for a window longer than this in one provider call.
MAX_INGEST_WINDOW_DAYS = 365 * 25

# Default history fetched when a caller does not specify a start date.
DEFAULT_HISTORY_DAYS = 365 * 3


class AssetNotFoundError(NotFoundError):
    """No asset with that symbol is known to Heimdall or to its provider."""

    code = "asset_not_found"
    message = "No asset was found for that symbol."


class MarketDataUnavailableError(ServiceUnavailableError):
    """The market-data provider could not be reached."""

    code = "market_data_unavailable"
    message = "Market data is temporarily unavailable. Please try again."


class UnsupportedCurrencyError(ValidationError):
    """The provider reports a currency Heimdall cannot combine."""

    code = "unsupported_currency"


@dataclass(frozen=True, slots=True)
class IngestResult:
    """What an ingestion run did for one asset."""

    symbol: str
    asset_id: uuid.UUID
    requested: DateRange
    ranges_fetched: list[DateRange]
    observations_received: int
    bars_written: int
    rejected: int
    flagged: int
    problems: list[ObservationProblem]
    latest_stored_date: date | None
    # Expected trading days between the newest stored bar and the as-of date.
    staleness_trading_days: int | None

    @property
    def was_up_to_date(self) -> bool:
        """True when nothing had to be fetched."""
        return not self.ranges_fetched


@dataclass(slots=True)
class RefreshSummary:
    """Aggregate outcome of refreshing every asset in a portfolio."""

    data_as_of: date
    results: list[IngestResult] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def bars_written(self) -> int:
        """Total bars inserted or updated."""
        return sum(result.bars_written for result in self.results)


class MarketDataService:
    """Cache-first market data, backed by a pluggable provider."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        assets: AssetRepository,
        price_bars: PriceBarRepository,
        provider: MarketDataProvider,
        clock: Clock,
    ) -> None:
        self._session = session
        self._assets = assets
        self._price_bars = price_bars
        self._provider = provider
        self._clock = clock

    @property
    def source(self) -> PriceSource:
        """The source value recorded on bars this service writes."""
        return PriceSource(self._provider.name)

    # --- Search and metadata -------------------------------------------------

    async def search(self, query: str, *, limit: int = 10) -> list[AssetSearchResult]:
        """Search the provider for instruments."""
        try:
            return await self._provider.search_assets(query, limit=limit)
        except ProviderError as exc:
            logger.warning("market_data_search_failed", error=str(exc))
            raise MarketDataUnavailableError() from exc

    async def resolve_asset(self, raw_symbol: str, *, enrich: bool = True) -> Asset:
        """Return the stored asset for a symbol, creating and enriching it if needed.

        Metadata comes from the provider, so an asset first created by a CSV import
        with `asset_type=unknown` gains its real name, type, and sector the first
        time market data is requested for it.
        """
        try:
            symbol = normalize_symbol(raw_symbol)
        except InvalidSymbolError as exc:
            raise ValidationError(str(exc), code="invalid_symbol") from exc

        asset = await self._assets.get_by_symbol(symbol)

        if asset is not None and not (enrich and self._needs_enrichment(asset)):
            return asset

        try:
            metadata = await self._provider.get_asset_metadata(symbol)
        except SymbolNotFoundError as exc:
            if asset is not None:
                # Heimdall knows the asset even though the provider does not. Keep
                # what is stored rather than discarding a user's holding.
                return asset
            raise AssetNotFoundError(f"No asset was found for symbol {symbol}.") from exc
        except ProviderError as exc:
            if asset is not None:
                return asset
            raise MarketDataUnavailableError() from exc

        currency = metadata.currency.upper()
        if currency not in SUPPORTED_BASE_CURRENCIES:
            raise UnsupportedCurrencyError(
                f"{symbol} is denominated in {currency}. Heimdall does not convert "
                f"between currencies, so only {', '.join(SUPPORTED_BASE_CURRENCIES)} "
                "instruments can be analyzed."
            )

        if asset is None:
            asset = Asset(symbol=symbol, currency=currency, asset_type=metadata.asset_type)
            self._assets.add(asset)
        elif asset.currency != currency:
            raise UnsupportedCurrencyError(
                f"{symbol} is stored as {asset.currency} but the data provider reports "
                f"{currency}. Heimdall does not convert between currencies."
            )

        asset.name = metadata.name or asset.name
        asset.asset_type = metadata.asset_type
        asset.exchange = metadata.exchange or asset.exchange
        asset.sector = metadata.sector or asset.sector
        asset.industry = metadata.industry or asset.industry

        await self._session.flush()
        return asset

    @staticmethod
    def _needs_enrichment(asset: Asset) -> bool:
        """True when an asset is still a placeholder created by an import."""
        # `==`, not `is`: a reloaded row holds a plain string, not the member.
        return asset.asset_type == AssetType.UNKNOWN or asset.name is None

    # --- Prices --------------------------------------------------------------

    async def get_prices(
        self,
        *,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        ensure_fresh: bool = True,
    ) -> tuple[Asset, list[PriceBar]]:
        """Return stored bars for a symbol, ingesting anything missing first."""
        asset = await self.resolve_asset(symbol)
        window = self.resolve_window(start, end)

        if ensure_fresh:
            await self.ingest(asset=asset, window=window)

        bars = await self._price_bars.list_for_asset(
            asset.id,
            start=window.start,
            end=window.end,
            source=self.source,
        )
        return asset, bars

    async def ingest(self, *, asset: Asset, window: DateRange) -> IngestResult:
        """Fill in any missing bars for one asset inside a window."""
        stored = await self._price_bars.stored_dates(
            asset.id,
            start=window.start,
            end=window.end,
            source=self.source,
        )
        missing = find_missing_ranges(
            requested=window,
            stored_dates=stored,
            tolerance_days=HOLIDAY_TOLERANCE_DAYS,
        )

        received = 0
        written = 0
        rejected = 0
        flagged = 0
        problems: list[ObservationProblem] = []

        for missing_range in missing:
            observations = await self._fetch(asset.symbol, missing_range)
            received += len(observations)

            validated = validate_observations(observations, today=self._clock.now().date())
            problems.extend(validated.problems)
            rejected += validated.rejected_count
            flagged += validated.flagged_count

            written += await self._store(asset=asset, observations=validated.observations)

        latest = await self._price_bars.latest_date(asset.id, source=self.source)
        as_of = min(self._clock.now().date(), window.end)

        result = IngestResult(
            symbol=asset.symbol,
            asset_id=asset.id,
            requested=window,
            ranges_fetched=missing,
            observations_received=received,
            bars_written=written,
            rejected=rejected,
            flagged=flagged,
            problems=problems,
            latest_stored_date=latest,
            staleness_trading_days=(
                trading_days_between(latest, as_of) if latest is not None else None
            ),
        )

        logger.info(
            "market_data_ingested",
            symbol=asset.symbol,
            ranges=len(missing),
            written=written,
            rejected=rejected,
            flagged=flagged,
        )
        return result

    async def refresh_assets(
        self,
        assets: list[Asset],
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> RefreshSummary:
        """Refresh several assets, recording per-asset failures without aborting.

        One unavailable symbol must not prevent the rest of a portfolio from being
        updated, so each failure is captured and reported.
        """
        window = self.resolve_window(start, end)
        summary = RefreshSummary(data_as_of=min(self._clock.now().date(), window.end))

        for asset in assets:
            try:
                summary.results.append(await self.ingest(asset=asset, window=window))
            except (ProviderError, ValidationError) as exc:
                logger.warning(
                    "market_data_refresh_failed",
                    symbol=asset.symbol,
                    error=type(exc).__name__,
                )
                summary.failures.append((asset.symbol, str(exc)))

        return summary

    # --- Internals -----------------------------------------------------------

    def resolve_window(self, start: date | None, end: date | None) -> DateRange:
        """Resolve an optional window into a concrete, bounded range."""
        today = self._clock.now().date()
        resolved_end = min(end or today, today)
        resolved_start = start or resolved_end - timedelta(days=DEFAULT_HISTORY_DAYS)

        if resolved_start > resolved_end:
            raise ValidationError(
                "The start date must be on or before the end date.",
                code="invalid_date_range",
            )
        if (resolved_end - resolved_start).days > MAX_INGEST_WINDOW_DAYS:
            raise ValidationError(
                f"The requested window exceeds the maximum of {MAX_INGEST_WINDOW_DAYS} days.",
                code="window_too_large",
            )

        return DateRange(resolved_start, resolved_end)

    async def _fetch(self, symbol: str, window: DateRange) -> list[PriceObservation]:
        """Ask the provider for one range, translating provider failures."""
        try:
            return await self._provider.get_daily_prices(
                symbol,
                start=window.start,
                end=window.end,
            )
        except SymbolNotFoundError:
            # The symbol is stored but the provider has no series for it. That is
            # a data-quality condition, not a crash: report zero observations.
            logger.info("market_data_symbol_missing", symbol=symbol)
            return []
        except ProviderError as exc:
            logger.warning("market_data_fetch_failed", symbol=symbol, error=str(exc))
            raise MarketDataUnavailableError() from exc

    async def _store(self, *, asset: Asset, observations: list[PriceObservation]) -> int:
        """Write validated observations idempotently."""
        if not observations:
            return 0

        rows = [
            {
                "id": uuid.uuid4(),
                "asset_id": asset.id,
                "date": observation.date,
                "open": observation.open,
                "high": observation.high,
                "low": observation.low,
                "close": observation.close,
                "adjusted_close": observation.adjusted_close,
                "volume": observation.volume,
                "currency": asset.currency,
                "source": self.source,
            }
            for observation in observations
        ]
        return await self._price_bars.upsert_many(rows)
