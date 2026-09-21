"""Trading-calendar convention and missing-range detection.

**Documented convention.** Heimdall treats Monday to Friday as expected trading
days and does not model exchange holidays. Consequences, stated plainly because
they matter for staleness checks:

* A weekend never counts as missing or stale data.
* A market holiday looks like one missing expected trading day. Staleness
  thresholds are therefore expressed in expected trading days with a tolerance
  that absorbs a single holiday.

Replacing this with a real exchange calendar would change only this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

# Trading periods per year, used to annualize daily statistics.
TRADING_DAYS_PER_YEAR: Final = 252

SATURDAY: Final = 5
SUNDAY: Final = 6


def is_expected_trading_day(day: date) -> bool:
    """True when the given date is a weekday under Heimdall's convention."""
    return day.weekday() not in (SATURDAY, SUNDAY)


def expected_trading_days(start: date, end: date) -> list[date]:
    """Every expected trading day in the inclusive range."""
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        if is_expected_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def count_expected_trading_days(start: date, end: date) -> int:
    """How many expected trading days the inclusive range contains."""
    return len(expected_trading_days(start, end))


def previous_trading_day(day: date) -> date:
    """The most recent expected trading day at or before `day`."""
    current = day
    while not is_expected_trading_day(current):
        current -= timedelta(days=1)
    return current


def trading_days_between(earlier: date, later: date) -> int:
    """Expected trading days strictly after `earlier`, up to and including `later`.

    Returns 0 when `later` is not after `earlier`. This is the measure used for
    staleness: a Friday close read on the following Monday is one trading day old.
    """
    if later <= earlier:
        return 0
    return count_expected_trading_days(earlier + timedelta(days=1), later)


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive range of dates."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("A date range must end on or after it starts.")

    @property
    def days(self) -> int:
        """Calendar days in the range, inclusive."""
        return (self.end - self.start).days + 1


def find_missing_ranges(
    *,
    requested: DateRange,
    stored_dates: set[date],
    tolerance_days: int = 0,
) -> list[DateRange]:
    """Work out which parts of a requested window are not stored yet.

    Only expected trading days count, so a weekend between two stored bars is not
    treated as a gap. Contiguous missing days are merged into one range, and a gap
    shorter than `tolerance_days` is ignored — useful for absorbing single market
    holidays that would otherwise trigger an endless refetch of a date the
    provider will never return.
    """
    missing = [
        day
        for day in expected_trading_days(requested.start, requested.end)
        if day not in stored_dates
    ]
    if not missing:
        return []

    ranges: list[DateRange] = []
    block_start = missing[0]
    previous = missing[0]

    for day in missing[1:]:
        # Consecutive in trading-day terms: nothing expected in between.
        if count_expected_trading_days(previous + timedelta(days=1), day - timedelta(days=1)) == 0:
            previous = day
            continue
        ranges.append(DateRange(block_start, previous))
        block_start = day
        previous = day

    ranges.append(DateRange(block_start, previous))

    if tolerance_days > 0:
        ranges = [
            candidate
            for candidate in ranges
            if count_expected_trading_days(candidate.start, candidate.end) > tolerance_days
        ]

    return ranges
