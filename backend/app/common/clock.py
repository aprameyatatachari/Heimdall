"""Injectable clock.

Time-dependent behaviour (token expiry, signal lifecycles, staleness checks)
must be testable without sleeping, so nothing in the application calls
`datetime.now()` directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


class FixedClock:
    """A clock frozen at a chosen instant. For tests only."""

    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._moment = moment

    def now(self) -> datetime:
        """Return the frozen instant."""
        return self._moment

    def advance(self, seconds: float) -> None:
        """Move the frozen instant forward."""
        from datetime import timedelta

        self._moment = self._moment + timedelta(seconds=seconds)


_system_clock = SystemClock()


def get_clock() -> Clock:
    """FastAPI dependency returning the application clock."""
    return _system_clock


def utcnow() -> datetime:
    """Current UTC time, for code paths that do not receive a clock."""
    return _system_clock.now()
