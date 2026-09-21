"""Ticker-symbol normalization.

A pure function, shared by the position endpoints and the CSV importer, so both
accept exactly the same inputs.
"""

from __future__ import annotations

import re

from app.assets.models import SYMBOL_MAX_LENGTH

# Upper-case letters and digits, optionally separated by a dot or hyphen, as used
# by share classes (`BRK.B`) and some non-US listings (`RDS-A`).
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+([.\-][A-Z0-9]+)*$")


class InvalidSymbolError(ValueError):
    """The supplied text is not a usable ticker symbol."""


def normalize_symbol(raw: str) -> str:
    """Normalize a ticker symbol.

    Trims surrounding whitespace, upper-cases the symbol, and validates its
    shape. Raises `InvalidSymbolError` when the input cannot be a ticker.
    """
    candidate = raw.strip().upper()

    if not candidate:
        raise InvalidSymbolError("Symbol must not be empty.")
    if len(candidate) > SYMBOL_MAX_LENGTH:
        raise InvalidSymbolError(f"Symbol must be at most {SYMBOL_MAX_LENGTH} characters.")
    if not _SYMBOL_PATTERN.match(candidate):
        raise InvalidSymbolError(
            "Symbol may contain only letters, digits, dots, and hyphens, for example AAPL or BRK.B."
        )

    return candidate
