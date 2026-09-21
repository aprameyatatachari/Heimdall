"""CSV position import: parsing and validation.

Pure functions only. Nothing here touches the database or HTTP, so the whole
contract is testable from a string.

The file is validated **completely** before any row is accepted. A file with one
bad row produces a list of row-specific errors and no partial result, which is
what lets the service perform a single all-or-nothing transaction.

Accepted contract::

    symbol,quantity,average_cost,purchase_date
    AAPL,10,185.20,2024-03-15
    MSFT,8,402.10,2024-04-02
    SPY,12,510.00,2024-06-10

`purchase_date` is optional, both as a column and as a value.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

from app.assets.symbols import InvalidSymbolError, normalize_symbol

# --- Contract ----------------------------------------------------------------

COLUMN_SYMBOL: Final = "symbol"
COLUMN_QUANTITY: Final = "quantity"
COLUMN_AVERAGE_COST: Final = "average_cost"
COLUMN_PURCHASE_DATE: Final = "purchase_date"

REQUIRED_COLUMNS: Final = (COLUMN_SYMBOL, COLUMN_QUANTITY, COLUMN_AVERAGE_COST)
OPTIONAL_COLUMNS: Final = (COLUMN_PURCHASE_DATE,)
KNOWN_COLUMNS: Final = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# --- Limits ------------------------------------------------------------------

MAX_FILE_BYTES: Final = 512 * 1024  # 512 KiB is far more than a realistic holdings file
MAX_ROWS: Final = 1_000
MAX_CELL_LENGTH: Final = 64

QUANTITY_DECIMAL_PLACES: Final = 8
MONEY_DECIMAL_PLACES: Final = 4
MAX_QUANTITY: Final = Decimal("1e12")
MAX_AVERAGE_COST: Final = Decimal("1e12")

# Characters a spreadsheet may interpret as the start of a formula. Guarded on
# import for defence in depth, and stripped on export by `sanitize_csv_value`.
_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")


class ImportMode(StrEnum):
    """How an import interacts with holdings the portfolio already has.

    * `merge` — combine each imported row with the matching existing position:
      quantities add and the average cost becomes the cost-weighted mean.
    * `replace` — delete every existing position, then insert the file's rows.
      The portfolio ends up containing exactly what the file describes.
    * `reject` — fail if any imported symbol is already held, changing nothing.
    """

    MERGE = "merge"
    REPLACE = "replace"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RowError:
    """A problem with one cell or one row of the uploaded file."""

    # 1-based line number in the file, counting the header, so it matches what a
    # spreadsheet or text editor shows.
    line: int
    column: str | None
    message: str
    code: str


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One validated holding from the file."""

    line: int
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    purchase_date: date | None


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing a complete file."""

    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every row validated."""
        return not self.errors


class CsvStructureError(Exception):
    """The file cannot be parsed at all: bad encoding, headers, or size.

    Distinct from row errors, because there is nothing row-specific to report.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# --- Decoding ----------------------------------------------------------------


def decode_csv_bytes(payload: bytes) -> str:
    """Decode uploaded bytes as UTF-8 text.

    Accepts an optional byte-order mark, which spreadsheet software adds. Rejects
    anything that is not valid UTF-8, and rejects embedded NUL bytes, which
    indicate a binary file rather than a CSV.
    """
    if not payload:
        raise CsvStructureError("The uploaded file is empty.", code="csv_empty_file")

    if len(payload) > MAX_FILE_BYTES:
        raise CsvStructureError(
            f"The uploaded file exceeds the maximum size of {MAX_FILE_BYTES} bytes.",
            code="csv_file_too_large",
        )

    if b"\x00" in payload:
        raise CsvStructureError(
            "The uploaded file contains binary data and is not a CSV file.",
            code="csv_not_text",
        )

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvStructureError(
            "The uploaded file is not valid UTF-8 text. Save it as UTF-8 CSV and retry.",
            code="csv_invalid_encoding",
        ) from exc

    return text


# --- Header validation -------------------------------------------------------


def _normalize_header(raw: str | None) -> str:
    return (raw or "").strip().lower().replace(" ", "_")


def validate_headers(raw_headers: list[str] | None) -> None:
    """Check the header row, rejecting missing and unexpected columns."""
    if not raw_headers:
        raise CsvStructureError(
            "The file has no header row. The first line must be: " + ",".join(KNOWN_COLUMNS),
            code="csv_missing_header",
        )

    headers = [_normalize_header(header) for header in raw_headers]

    if len(set(headers)) != len(headers):
        raise CsvStructureError(
            "The header row contains duplicate column names.",
            code="csv_duplicate_columns",
        )

    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        raise CsvStructureError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(KNOWN_COLUMNS)}",
            code="csv_missing_columns",
        )

    unexpected = [header for header in headers if header not in KNOWN_COLUMNS]
    if unexpected:
        raise CsvStructureError(
            f"Unexpected column(s): {', '.join(unexpected)}. "
            f"Allowed columns are: {', '.join(KNOWN_COLUMNS)}",
            code="csv_unexpected_columns",
        )


# --- Cell validation ---------------------------------------------------------


def _looks_like_a_formula(value: str) -> bool:
    return value.startswith(_FORMULA_PREFIXES)


def _parse_decimal(
    raw: str,
    *,
    column: str,
    line: int,
    maximum: Decimal,
    decimal_places: int,
    allow_zero: bool,
) -> tuple[Decimal | None, RowError | None]:
    """Parse a decimal cell, returning either a value or an error."""
    text = raw.strip().replace(",", "")

    if not text:
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} is required.",
            code="required",
        )

    if _looks_like_a_formula(text) and not text.lstrip("-").replace(".", "", 1).isdigit():
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} must be a plain number, not a formula.",
            code="not_a_number",
        )

    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} must be a decimal number, for example 10 or 185.20.",
            code="not_a_number",
        )

    if not value.is_finite():
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} must be a finite number.",
            code="not_finite",
        )

    if value < 0 or (value == 0 and not allow_zero):
        boundary = "zero or greater" if allow_zero else "greater than zero"
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} must be {boundary}.",
            code="out_of_range",
        )

    if value >= maximum:
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} must be less than {maximum:f}.",
            code="out_of_range",
        )

    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > decimal_places:
        return None, RowError(
            line=line,
            column=column,
            message=f"{column} allows at most {decimal_places} decimal places.",
            code="too_precise",
        )

    return value, None


def _parse_purchase_date(
    raw: str,
    *,
    line: int,
    today: date,
) -> tuple[date | None, RowError | None]:
    """Parse an optional ISO date cell."""
    text = raw.strip()
    if not text:
        return None, None

    try:
        value = date.fromisoformat(text)
    except ValueError:
        return None, RowError(
            line=line,
            column=COLUMN_PURCHASE_DATE,
            message="purchase_date must be an ISO date, for example 2024-03-15.",
            code="not_a_date",
        )

    if value > today:
        return None, RowError(
            line=line,
            column=COLUMN_PURCHASE_DATE,
            message="purchase_date must not be in the future.",
            code="out_of_range",
        )

    return value, None


# --- File parsing ------------------------------------------------------------


def parse_positions_csv(payload: bytes, *, today: date | None = None) -> ParseResult:
    """Parse and validate a complete positions file.

    Raises `CsvStructureError` when the file cannot be read or its header is
    wrong. Otherwise returns every valid row together with every row error; the
    caller writes nothing unless `ParseResult.ok` is true.
    """
    reference_date = today or datetime.now(UTC).date()
    text = decode_csv_bytes(payload)

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_headers = reader.fieldnames
        validate_headers(list(raw_headers) if raw_headers else None)
        raw_rows = list(reader)
    except csv.Error as exc:
        raise CsvStructureError(
            "The file could not be parsed as CSV.", code="csv_malformed"
        ) from exc

    if not raw_rows:
        raise CsvStructureError("The file contains a header but no holdings.", code="csv_no_rows")

    if len(raw_rows) > MAX_ROWS:
        raise CsvStructureError(
            f"The file contains {len(raw_rows)} rows, more than the maximum of {MAX_ROWS}.",
            code="csv_too_many_rows",
        )

    header_map = {_normalize_header(header): header for header in raw_headers or []}
    result = ParseResult()
    seen_symbols: dict[str, int] = {}

    for index, raw_row in enumerate(raw_rows):
        # +2: one for the header line, one because lines are 1-based.
        line = index + 2
        row_errors = _validate_row(
            raw_row,
            header_map=header_map,
            line=line,
            reference_date=reference_date,
            seen_symbols=seen_symbols,
            result=result,
        )
        result.errors.extend(row_errors)

    # A file that produced errors must not contribute any rows.
    if result.errors:
        result.rows.clear()

    return result


def _validate_row(
    raw_row: dict[str, str | None],
    *,
    header_map: dict[str, str],
    line: int,
    reference_date: date,
    seen_symbols: dict[str, int],
    result: ParseResult,
) -> list[RowError]:
    """Validate one data row, appending to `result.rows` when it is clean."""
    errors: list[RowError] = []

    # `csv.DictReader` puts surplus cells under the `None` key.
    if None in raw_row:
        errors.append(
            RowError(
                line=line,
                column=None,
                message="The row has more columns than the header.",
                code="too_many_cells",
            )
        )

    def cell(column: str) -> str:
        value = raw_row.get(header_map.get(column, column))
        return value if isinstance(value, str) else ""

    for column in KNOWN_COLUMNS:
        if len(cell(column)) > MAX_CELL_LENGTH:
            errors.append(
                RowError(
                    line=line,
                    column=column,
                    message=f"{column} is longer than {MAX_CELL_LENGTH} characters.",
                    code="too_long",
                )
            )

    if errors:
        return errors

    raw_symbol = cell(COLUMN_SYMBOL)
    symbol: str | None = None
    if not raw_symbol.strip():
        errors.append(
            RowError(
                line=line, column=COLUMN_SYMBOL, message="symbol is required.", code="required"
            )
        )
    else:
        try:
            symbol = normalize_symbol(raw_symbol)
        except InvalidSymbolError as exc:
            errors.append(
                RowError(
                    line=line,
                    column=COLUMN_SYMBOL,
                    message=str(exc),
                    code="invalid_symbol",
                )
            )

    if symbol is not None:
        previous_line = seen_symbols.get(symbol)
        if previous_line is not None:
            errors.append(
                RowError(
                    line=line,
                    column=COLUMN_SYMBOL,
                    message=(
                        f"{symbol} already appears on line {previous_line}. "
                        "Combine the rows into a single holding."
                    ),
                    code="duplicate_symbol",
                )
            )
        else:
            seen_symbols[symbol] = line

    quantity, quantity_error = _parse_decimal(
        cell(COLUMN_QUANTITY),
        column=COLUMN_QUANTITY,
        line=line,
        maximum=MAX_QUANTITY,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        allow_zero=False,
    )
    if quantity_error is not None:
        errors.append(quantity_error)

    average_cost, cost_error = _parse_decimal(
        cell(COLUMN_AVERAGE_COST),
        column=COLUMN_AVERAGE_COST,
        line=line,
        maximum=MAX_AVERAGE_COST,
        decimal_places=MONEY_DECIMAL_PLACES,
        allow_zero=True,
    )
    if cost_error is not None:
        errors.append(cost_error)

    purchase_date, date_error = _parse_purchase_date(
        cell(COLUMN_PURCHASE_DATE),
        line=line,
        today=reference_date,
    )
    if date_error is not None:
        errors.append(date_error)

    if not errors and symbol is not None and quantity is not None and average_cost is not None:
        result.rows.append(
            ParsedRow(
                line=line,
                symbol=symbol,
                quantity=quantity,
                average_cost=average_cost,
                purchase_date=purchase_date,
            )
        )

    return errors


# --- Export safety -----------------------------------------------------------


def sanitize_csv_value(value: str) -> str:
    """Make a value safe to write into a CSV file.

    Spreadsheet applications execute a cell that begins with `=`, `+`, `-`, or
    `@`. Prefixing such a value with a single quote keeps it as text. Used by
    every CSV export Heimdall produces.
    """
    if value and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
