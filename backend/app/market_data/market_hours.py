"""Regular trading sessions, for deciding when a live check is worth making.

Pure functions of an instant: no clock, no network, no database.

This follows the same convention as `calendar.py`: Monday to Friday, with no
exchange holidays modelled. On a holiday the market reads as open, a refresh
finds nothing new, and nothing is lost but one request. Replacing this with a
real exchange calendar would change only this module.

A portfolio's market is taken from its base currency, which is also what decides
the instruments it can hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from app.market_data.calendar import is_expected_trading_day

# Free quotes trail the exchange by about a quarter of an hour, so the last
# price of the session arrives after the bell. Checking a little past the close
# is what lets a monitoring run see the day's final figure.
CLOSE_GRACE_MINUTES: Final = 30


@dataclass(frozen=True, slots=True)
class TradingSession:
    """One exchange's regular hours, in its own local time."""

    exchange: str
    timezone: str
    opens: time
    closes: time


SESSIONS: Final[dict[str, TradingSession]] = {
    "USD": TradingSession("NYSE", "America/New_York", time(9, 30), time(16, 0)),
    "INR": TradingSession("NSE", "Asia/Kolkata", time(9, 15), time(15, 30)),
}


def session_for(currency: str) -> TradingSession | None:
    """The trading session for a base currency, or None when it is not known."""
    return SESSIONS.get(currency.upper())


def is_market_open(
    currency: str,
    moment: datetime,
    *,
    grace_minutes: int = CLOSE_GRACE_MINUTES,
) -> bool:
    """Whether prices in this currency's market could still be changing.

    An unknown currency reads as open. Not knowing a market's hours is a reason
    to keep checking it, not a reason to stop.
    """
    if moment.tzinfo is None:
        raise ValueError("is_market_open requires a timezone-aware datetime")

    session = session_for(currency)
    if session is None:
        return True

    local = moment.astimezone(ZoneInfo(session.timezone))
    if not is_expected_trading_day(local.date()):
        return False

    opens = datetime.combine(local.date(), session.opens, tzinfo=local.tzinfo)
    closes = datetime.combine(local.date(), session.closes, tzinfo=local.tzinfo)
    return opens <= local <= closes + timedelta(minutes=grace_minutes)


__all__ = [
    "CLOSE_GRACE_MINUTES",
    "SESSIONS",
    "TradingSession",
    "is_market_open",
    "session_for",
]
