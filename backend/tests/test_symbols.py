"""Unit tests for ticker-symbol normalization."""

from __future__ import annotations

import pytest

from app.assets.symbols import InvalidSymbolError, normalize_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AAPL", "AAPL"),
        ("aapl", "AAPL"),
        ("  msft  ", "MSFT"),
        ("brk.b", "BRK.B"),
        ("rds-a", "RDS-A"),
        ("SPY", "SPY"),
        ("2330", "2330"),
        ("aapl\n", "AAPL"),  # surrounding whitespace, including newlines, is trimmed
    ],
)
def test_valid_symbols_are_normalized(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "AA PL",  # internal whitespace
        "AAPL;",  # punctuation
        "AAPL'",
        "=SUM(A1)",  # spreadsheet formula injection attempt
        "@AAPL",
        "AAPL..B",  # empty component
        ".AAPL",
        "AAPL-",
        "A" * 25,  # longer than the column allows
        "AA\tPL",
    ],
)
def test_invalid_symbols_are_rejected(raw):
    with pytest.raises(InvalidSymbolError):
        normalize_symbol(raw)


def test_the_error_message_shows_an_example():
    with pytest.raises(InvalidSymbolError, match="AAPL"):
        normalize_symbol("not a symbol!")
