"""Unit tests for trading sessions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.market_data.market_hours import is_market_open, session_for

# 2026-10-05 is a Monday; New York is on daylight time (UTC-4), India is UTC+5:30.


def _utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def test_new_york_is_open_during_its_session():
    # 14:00 UTC is 10:00 in New York.
    assert is_market_open("USD", _utc(5, 14)) is True


def test_new_york_is_closed_before_the_bell():
    # 13:00 UTC is 09:00 in New York, half an hour early.
    assert is_market_open("USD", _utc(5, 13)) is False


def test_india_is_open_during_its_session():
    # 05:00 UTC is 10:30 in Mumbai.
    assert is_market_open("INR", _utc(5, 5)) is True


def test_india_is_closed_while_new_york_trades():
    assert is_market_open("INR", _utc(5, 15)) is False


def test_the_close_has_a_grace_period_for_delayed_quotes():
    # 20:00 UTC is the New York close. Delayed quotes are still arriving.
    assert is_market_open("USD", _utc(5, 20, 20)) is True
    assert is_market_open("USD", _utc(5, 20, 45)) is False


def test_the_grace_period_can_be_removed():
    assert is_market_open("USD", _utc(5, 20, 20), grace_minutes=0) is False


def test_a_weekend_is_closed_in_the_markets_own_date():
    # Saturday 14:00 UTC is Saturday morning in New York.
    assert is_market_open("USD", _utc(3, 14)) is False
    # Sunday 23:00 UTC is already Monday 04:30 in Mumbai, before the open.
    assert is_market_open("INR", _utc(4, 23)) is False


def test_daylight_saving_moves_the_session_in_utc():
    # In January New York is UTC-5, so 14:00 UTC is 09:00 and the market is shut.
    assert is_market_open("USD", datetime(2026, 1, 12, 14, 0, tzinfo=UTC)) is False
    assert is_market_open("USD", datetime(2026, 1, 12, 15, 0, tzinfo=UTC)) is True


def test_an_unknown_market_is_treated_as_open():
    # Not knowing a market's hours is a reason to keep checking, not to stop.
    assert session_for("JPY") is None
    assert is_market_open("JPY", _utc(3, 3)) is True


def test_the_currency_is_matched_without_regard_to_case():
    assert is_market_open("usd", _utc(5, 14)) is True


def test_a_naive_datetime_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        is_market_open("USD", datetime(2026, 10, 5, 14, 0))
