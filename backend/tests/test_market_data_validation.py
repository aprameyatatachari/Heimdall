"""Unit tests for provider-data validation and the fixture provider."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.assets.models import AssetType
from app.market_data.fixture_provider import FixtureMarketDataProvider
from app.market_data.provider import PriceObservation, SymbolNotFoundError
from app.market_data.validation import (
    DataQualityIssue,
    validate_observations,
)

TODAY = date(2026, 9, 20)


def observation(
    day: str,
    close: str = "100",
    *,
    adjusted: str | None = None,
    high: str | None = None,
    low: str | None = None,
    open_: str | None = None,
    volume: str | None = None,
) -> PriceObservation:
    return PriceObservation(
        date=date.fromisoformat(day),
        close=Decimal(close),
        adjusted_close=Decimal(adjusted or close),
        open=Decimal(open_) if open_ else None,
        high=Decimal(high) if high else None,
        low=Decimal(low) if low else None,
        volume=Decimal(volume) if volume else None,
    )


def issues(result) -> set[DataQualityIssue]:
    return {problem.issue for problem in result.problems}


# --- Ordering and deduplication ----------------------------------------------


def test_observations_are_sorted_by_date():
    result = validate_observations(
        [observation("2024-01-03"), observation("2024-01-01"), observation("2024-01-02")],
        today=TODAY,
    )

    assert [item.date.day for item in result.observations] == [1, 2, 3]


def test_reordering_the_input_does_not_change_the_output():
    forward = [observation("2024-01-01", "100"), observation("2024-01-02", "101")]
    backward = list(reversed(forward))

    assert (
        validate_observations(forward, today=TODAY).observations
        == validate_observations(backward, today=TODAY).observations
    )


def test_a_duplicate_date_is_rejected_keeping_the_first():
    result = validate_observations(
        [observation("2024-01-01", "100"), observation("2024-01-01", "999")],
        today=TODAY,
    )

    assert len(result.observations) == 1
    assert result.observations[0].close == Decimal("100")
    assert DataQualityIssue.DUPLICATE_DATE in issues(result)
    assert result.rejected_count == 1


# --- Rejections ---------------------------------------------------------------


@pytest.mark.parametrize("close", ["0", "-1"])
def test_a_non_positive_close_is_rejected(close):
    result = validate_observations([observation("2024-01-01", close)], today=TODAY)

    assert result.observations == []
    assert DataQualityIssue.NON_POSITIVE_PRICE in issues(result)


def test_a_non_positive_adjusted_close_is_rejected():
    result = validate_observations(
        [observation("2024-01-01", "100", adjusted="0")],
        today=TODAY,
    )

    assert result.observations == []
    assert DataQualityIssue.NON_POSITIVE_PRICE in issues(result)


def test_an_implausible_price_is_rejected():
    result = validate_observations([observation("2024-01-01", "1e10")], today=TODAY)

    assert result.observations == []
    assert DataQualityIssue.IMPLAUSIBLE_PRICE in issues(result)


def test_a_future_dated_observation_is_rejected():
    result = validate_observations([observation("2030-01-01")], today=TODAY)

    assert result.observations == []
    assert DataQualityIssue.FUTURE_DATE in issues(result)


def test_low_above_high_is_rejected():
    result = validate_observations(
        [observation("2024-01-01", "100", high="99", low="101")],
        today=TODAY,
    )

    assert result.observations == []
    assert DataQualityIssue.INVALID_OHLC in issues(result)


def test_a_close_outside_the_high_low_range_is_rejected():
    result = validate_observations(
        [observation("2024-01-01", "120", high="110", low="90")],
        today=TODAY,
    )

    assert result.observations == []
    assert DataQualityIssue.INVALID_OHLC in issues(result)


def test_a_consistent_ohlc_bar_is_accepted():
    result = validate_observations(
        [observation("2024-01-01", "100", open_="95", high="105", low="94")],
        today=TODAY,
    )

    assert len(result.observations) == 1
    assert result.problems == []


def test_a_bar_with_no_high_or_low_is_accepted():
    result = validate_observations([observation("2024-01-01", "100")], today=TODAY)

    assert len(result.observations) == 1


def test_negative_volume_is_rejected():
    result = validate_observations(
        [observation("2024-01-01", "100", volume="-5")],
        today=TODAY,
    )

    assert result.observations == []
    assert DataQualityIssue.NEGATIVE_VOLUME in issues(result)


def test_a_bad_bar_does_not_discard_the_good_ones():
    result = validate_observations(
        [
            observation("2024-01-01", "100"),
            observation("2024-01-02", "0"),
            observation("2024-01-03", "102"),
        ],
        today=TODAY,
    )

    assert [item.date.day for item in result.observations] == [1, 3]
    assert result.rejected_count == 1


# --- Flagging -----------------------------------------------------------------


def test_an_extreme_move_is_flagged_but_kept():
    """Some real moves are this large, so the data is reported, not removed."""
    result = validate_observations(
        [observation("2024-01-01", "100"), observation("2024-01-02", "30")],
        today=TODAY,
    )

    assert len(result.observations) == 2
    assert DataQualityIssue.EXTREME_RETURN in issues(result)
    assert result.rejected_count == 0
    assert result.flagged_count == 1


def test_an_ordinary_move_is_not_flagged():
    result = validate_observations(
        [observation("2024-01-01", "100"), observation("2024-01-02", "105")],
        today=TODAY,
    )

    assert result.problems == []


def test_an_empty_input_is_valid_and_empty():
    result = validate_observations([], today=TODAY)

    assert result.observations == []
    assert result.problems == []


# --- Fixture provider ---------------------------------------------------------


async def test_the_fixture_provider_serves_its_committed_symbols():
    provider = FixtureMarketDataProvider()

    symbols = provider.available_symbols()

    assert "SPY" in symbols
    assert "AAPL" in symbols


async def test_fixture_metadata_carries_sector_information():
    provider = FixtureMarketDataProvider()

    metadata = await provider.get_asset_metadata("aapl")

    assert metadata.symbol == "AAPL"
    assert metadata.asset_type is AssetType.EQUITY
    assert metadata.sector == "Technology"
    assert metadata.currency == "USD"


async def test_an_etf_is_typed_as_an_etf():
    provider = FixtureMarketDataProvider()

    assert (await provider.get_asset_metadata("SPY")).asset_type is AssetType.ETF


async def test_an_unknown_symbol_raises():
    provider = FixtureMarketDataProvider()

    with pytest.raises(SymbolNotFoundError):
        await provider.get_asset_metadata("NOSUCHTICKER")


async def test_search_matches_symbol_and_name():
    provider = FixtureMarketDataProvider()

    by_symbol = await provider.search_assets("aapl")
    by_name = await provider.search_assets("microsoft")

    assert by_symbol[0].symbol == "AAPL"
    assert by_name[0].symbol == "MSFT"


async def test_search_puts_an_exact_symbol_match_first():
    provider = FixtureMarketDataProvider()

    results = await provider.search_assets("spy")

    assert results[0].symbol == "SPY"


async def test_search_respects_the_limit():
    provider = FixtureMarketDataProvider()

    assert len(await provider.search_assets("a", limit=2)) <= 2


async def test_an_empty_search_returns_nothing():
    provider = FixtureMarketDataProvider()

    assert await provider.search_assets("   ") == []


async def test_prices_are_clipped_to_the_requested_window():
    provider = FixtureMarketDataProvider()

    observations = await provider.get_daily_prices(
        "SPY",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
    )

    assert observations
    assert all(date(2024, 1, 1) <= item.date <= date(2024, 1, 31) for item in observations)
    assert observations == sorted(observations, key=lambda item: item.date)


async def test_prices_are_decimals_not_floats():
    provider = FixtureMarketDataProvider()

    observations = await provider.get_daily_prices(
        "SPY",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )

    assert isinstance(observations[0].close, Decimal)
    assert isinstance(observations[0].adjusted_close, Decimal)


async def test_the_fixture_series_pass_validation():
    """The committed fixtures must themselves be clean data."""
    provider = FixtureMarketDataProvider()

    observations = await provider.get_daily_prices(
        "SPY",
        start=date(2023, 1, 1),
        end=date(2024, 12, 31),
    )
    result = validate_observations(observations, today=TODAY)

    assert result.rejected_count == 0
    assert len(result.observations) == len(observations)


async def test_asking_for_an_unknown_symbols_prices_raises():
    provider = FixtureMarketDataProvider()

    with pytest.raises(SymbolNotFoundError):
        await provider.get_daily_prices("NOSUCH", start=date(2024, 1, 1), end=date(2024, 1, 2))
