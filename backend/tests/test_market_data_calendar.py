"""Unit tests for the trading calendar and missing-range detection."""

from __future__ import annotations

from datetime import date

import pytest

from app.market_data.calendar import (
    DateRange,
    count_expected_trading_days,
    expected_trading_days,
    find_missing_ranges,
    is_expected_trading_day,
    previous_trading_day,
    trading_days_between,
)

# 2024-03-11 is a Monday; 2024-03-16 and 17 are the weekend.
MONDAY = date(2024, 3, 11)
FRIDAY = date(2024, 3, 15)
SATURDAY = date(2024, 3, 16)
SUNDAY = date(2024, 3, 17)
NEXT_MONDAY = date(2024, 3, 18)


def test_weekdays_are_expected_trading_days():
    assert is_expected_trading_day(MONDAY) is True
    assert is_expected_trading_day(FRIDAY) is True


def test_weekends_are_not_expected_trading_days():
    assert is_expected_trading_day(SATURDAY) is False
    assert is_expected_trading_day(SUNDAY) is False


def test_expected_trading_days_skips_the_weekend():
    days = expected_trading_days(MONDAY, NEXT_MONDAY)

    assert SATURDAY not in days
    assert SUNDAY not in days
    assert len(days) == 6


def test_a_full_week_has_five_trading_days():
    assert count_expected_trading_days(MONDAY, SUNDAY) == 5


def test_an_inverted_range_has_no_trading_days():
    assert expected_trading_days(FRIDAY, MONDAY) == []


def test_previous_trading_day_walks_back_over_a_weekend():
    assert previous_trading_day(SUNDAY) == FRIDAY
    assert previous_trading_day(SATURDAY) == FRIDAY
    assert previous_trading_day(FRIDAY) == FRIDAY


def test_a_friday_close_is_one_trading_day_old_on_monday():
    """The central staleness case: a weekend must not look like stale data."""
    assert trading_days_between(FRIDAY, NEXT_MONDAY) == 1


def test_a_friday_close_is_not_stale_on_saturday_or_sunday():
    assert trading_days_between(FRIDAY, SATURDAY) == 0
    assert trading_days_between(FRIDAY, SUNDAY) == 0


def test_staleness_over_a_longer_gap():
    assert trading_days_between(MONDAY, NEXT_MONDAY) == 5


def test_staleness_is_zero_for_the_same_day():
    assert trading_days_between(FRIDAY, FRIDAY) == 0


def test_a_date_range_must_not_be_inverted():
    with pytest.raises(ValueError, match="end on or after"):
        DateRange(FRIDAY, MONDAY)


# --- Missing-range detection --------------------------------------------------


def test_nothing_is_missing_when_every_trading_day_is_stored():
    stored = set(expected_trading_days(MONDAY, FRIDAY))

    assert find_missing_ranges(requested=DateRange(MONDAY, FRIDAY), stored_dates=stored) == []


def test_a_weekend_is_never_reported_as_missing():
    stored = set(expected_trading_days(MONDAY, NEXT_MONDAY))

    missing = find_missing_ranges(
        requested=DateRange(MONDAY, NEXT_MONDAY),
        stored_dates=stored,
    )

    assert missing == []


def test_an_empty_cache_reports_the_whole_window():
    missing = find_missing_ranges(requested=DateRange(MONDAY, FRIDAY), stored_dates=set())

    assert missing == [DateRange(MONDAY, FRIDAY)]


def test_contiguous_missing_days_merge_into_one_range():
    stored = {MONDAY, FRIDAY}

    missing = find_missing_ranges(requested=DateRange(MONDAY, FRIDAY), stored_dates=stored)

    assert missing == [DateRange(date(2024, 3, 12), date(2024, 3, 14))]


def test_separate_gaps_are_reported_separately():
    stored = {date(2024, 3, 12), date(2024, 3, 14)}

    missing = find_missing_ranges(requested=DateRange(MONDAY, FRIDAY), stored_dates=stored)

    assert missing == [
        DateRange(MONDAY, MONDAY),
        DateRange(date(2024, 3, 13), date(2024, 3, 13)),
        DateRange(FRIDAY, FRIDAY),
    ]


def test_a_gap_spanning_a_weekend_is_one_range():
    """Friday and the following Monday are consecutive in trading-day terms."""
    stored = {date(2024, 3, 14), date(2024, 3, 19)}

    missing = find_missing_ranges(
        requested=DateRange(date(2024, 3, 14), date(2024, 3, 19)),
        stored_dates=stored,
    )

    assert missing == [DateRange(FRIDAY, NEXT_MONDAY)]


def test_a_single_day_gap_is_ignored_within_tolerance():
    """A market holiday looks exactly like one missing weekday."""
    stored = set(expected_trading_days(MONDAY, FRIDAY)) - {date(2024, 3, 13)}

    missing = find_missing_ranges(
        requested=DateRange(MONDAY, FRIDAY),
        stored_dates=stored,
        tolerance_days=1,
    )

    assert missing == []


def test_a_two_day_gap_exceeds_the_holiday_tolerance():
    stored = set(expected_trading_days(MONDAY, FRIDAY)) - {
        date(2024, 3, 13),
        date(2024, 3, 14),
    }

    missing = find_missing_ranges(
        requested=DateRange(MONDAY, FRIDAY),
        stored_dates=stored,
        tolerance_days=1,
    )

    assert missing == [DateRange(date(2024, 3, 13), date(2024, 3, 14))]


def test_a_weekend_only_window_is_never_missing():
    missing = find_missing_ranges(
        requested=DateRange(SATURDAY, SUNDAY),
        stored_dates=set(),
    )

    assert missing == []
