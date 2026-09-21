"""Unit tests for CSV parsing and validation. No database, no HTTP."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.portfolios.csv_import import (
    MAX_CELL_LENGTH,
    MAX_FILE_BYTES,
    MAX_ROWS,
    CsvStructureError,
    parse_positions_csv,
    sanitize_csv_value,
)

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "csv"
TODAY = date(2026, 9, 20)


def parse(text: str):
    return parse_positions_csv(text.encode("utf-8"), today=TODAY)


def fixture(name: str):
    return parse_positions_csv((FIXTURES / name).read_bytes(), today=TODAY)


def codes(result) -> set[str]:
    return {error.code for error in result.errors}


# --- Happy path --------------------------------------------------------------


def test_the_documented_example_parses():
    result = fixture("valid_simple.csv")

    assert result.ok
    assert [row.symbol for row in result.rows] == ["AAPL", "MSFT", "SPY"]
    assert result.rows[0].quantity == Decimal("10")
    assert result.rows[0].average_cost == Decimal("185.20")
    assert result.rows[0].purchase_date == date(2024, 3, 15)


def test_the_purchase_date_column_may_be_omitted():
    result = fixture("valid_no_dates.csv")

    assert result.ok
    assert all(row.purchase_date is None for row in result.rows)


def test_columns_may_appear_in_any_order_and_values_may_be_messy():
    result = fixture("valid_reordered_and_messy.csv")

    assert result.ok, result.errors
    assert [row.symbol for row in result.rows] == ["AAPL", "MSFT", "BRK.B"]
    assert result.rows[1].quantity == Decimal("8.5")
    assert result.rows[1].purchase_date is None
    assert result.rows[2].quantity == Decimal("0.00000001")


def test_a_bom_and_crlf_line_endings_are_accepted():
    result = fixture("valid_bom_crlf.csv")

    assert result.ok, result.errors
    assert result.rows[0].symbol == "AAPL"


def test_line_numbers_match_the_file():
    """Line 1 is the header, so the first holding is line 2."""
    result = fixture("valid_simple.csv")

    assert [row.line for row in result.rows] == [2, 3, 4]


def test_an_empty_optional_value_is_accepted():
    result = parse("symbol,quantity,average_cost,purchase_date\nAAPL,10,185.20,\n")

    assert result.ok
    assert result.rows[0].purchase_date is None


def test_a_zero_average_cost_is_accepted():
    result = parse("symbol,quantity,average_cost\nAAPL,10,0\n")

    assert result.ok
    assert result.rows[0].average_cost == Decimal("0")


def test_thousands_separators_are_accepted():
    result = parse('symbol,quantity,average_cost\nAAPL,1000,1234.56\nMSFT,2,"1,234.56"\n')

    assert result.ok, result.errors
    assert result.rows[1].average_cost == Decimal("1234.56")


# --- Structural failures ------------------------------------------------------


def test_an_empty_file_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        parse_positions_csv(b"", today=TODAY)
    assert exc.value.code == "csv_empty_file"


def test_a_file_with_only_a_header_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        fixture("invalid_header_only.csv")
    assert exc.value.code == "csv_no_rows"


def test_a_missing_required_column_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        fixture("invalid_missing_column.csv")
    assert exc.value.code == "csv_missing_columns"
    assert "symbol" in exc.value.message


def test_an_unexpected_column_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        fixture("invalid_unexpected_column.csv")
    assert exc.value.code == "csv_unexpected_columns"
    assert "cost_basis" in exc.value.message


def test_duplicate_columns_are_rejected():
    with pytest.raises(CsvStructureError) as exc:
        parse("symbol,quantity,quantity,average_cost\nAAPL,10,10,185.20\n")
    assert exc.value.code == "csv_duplicate_columns"


def test_a_file_that_is_not_utf8_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        parse_positions_csv(
            b"symbol,quantity,average_cost\n\xff\xfeAAPL,10,185.20\n",
            today=TODAY,
        )
    assert exc.value.code == "csv_invalid_encoding"


def test_a_binary_file_is_rejected():
    with pytest.raises(CsvStructureError) as exc:
        parse_positions_csv(b"\x89PNG\x00\x1a\n", today=TODAY)
    assert exc.value.code == "csv_not_text"


def test_an_oversized_file_is_rejected():
    payload = b"symbol,quantity,average_cost\n" + b"A,1,1\n" * MAX_FILE_BYTES
    with pytest.raises(CsvStructureError) as exc:
        parse_positions_csv(payload, today=TODAY)
    assert exc.value.code == "csv_file_too_large"


def test_too_many_rows_are_rejected():
    rows = "".join(f"SYM{index},1,1\n" for index in range(MAX_ROWS + 1))
    with pytest.raises(CsvStructureError) as exc:
        parse(f"symbol,quantity,average_cost\n{rows}")
    assert exc.value.code == "csv_too_many_rows"


def test_exactly_the_row_limit_is_accepted():
    rows = "".join(f"SYM{index},1,1\n" for index in range(MAX_ROWS))
    result = parse(f"symbol,quantity,average_cost\n{rows}")

    assert result.ok
    assert len(result.rows) == MAX_ROWS


def test_a_header_with_no_body_at_all_is_rejected():
    with pytest.raises(CsvStructureError):
        parse("\n")


# --- Row failures -------------------------------------------------------------


def test_every_bad_row_is_reported_with_its_line_and_column():
    result = fixture("invalid_rows.csv")

    assert not result.ok
    reported = {(error.line, error.column) for error in result.errors}
    assert (2, "quantity") in reported  # zero
    assert (3, "quantity") in reported  # negative
    assert (4, "average_cost") in reported  # negative
    assert (5, "purchase_date") in reported  # malformed
    assert (6, "symbol") in reported  # missing


def test_a_file_with_any_error_yields_no_rows():
    """Validation is all-or-nothing, which is what makes the import atomic."""
    result = fixture("invalid_rows.csv")

    assert result.rows == []


def test_a_duplicate_symbol_is_reported_against_the_later_line():
    result = fixture("invalid_duplicate_symbol.csv")

    assert not result.ok
    duplicate = next(error for error in result.errors if error.code == "duplicate_symbol")
    assert duplicate.line == 3
    assert "line 2" in duplicate.message


def test_a_formula_cell_is_rejected():
    result = fixture("invalid_formula_injection.csv")

    assert not result.ok
    assert "invalid_symbol" in codes(result)


@pytest.mark.parametrize(
    ("quantity", "code"),
    [
        ("", "required"),
        ("abc", "not_a_number"),
        ("0", "out_of_range"),
        ("-1", "out_of_range"),
        ("NaN", "not_finite"),
        ("Infinity", "not_finite"),
        ("1.123456789", "too_precise"),
        ("1e13", "out_of_range"),
    ],
)
def test_quantity_validation(quantity, code):
    result = parse(f"symbol,quantity,average_cost\nAAPL,{quantity},185.20\n")

    assert not result.ok
    assert code in codes(result)


@pytest.mark.parametrize(
    ("cost", "code"),
    [
        ("", "required"),
        ("abc", "not_a_number"),
        ("-0.01", "out_of_range"),
        ("1.12345", "too_precise"),
        ("=1+1", "not_a_number"),
    ],
)
def test_average_cost_validation(cost, code):
    result = parse(f"symbol,quantity,average_cost\nAAPL,10,{cost}\n")

    assert not result.ok
    assert code in codes(result)


@pytest.mark.parametrize(
    ("purchase_date", "code"),
    [
        ("15/03/2024", "not_a_date"),
        ("2024-13-01", "not_a_date"),
        ("2024-02-30", "not_a_date"),
        ("tomorrow", "not_a_date"),
        ("2099-01-01", "out_of_range"),
    ],
)
def test_purchase_date_validation(purchase_date, code):
    result = parse(f"symbol,quantity,average_cost,purchase_date\nAAPL,10,185.20,{purchase_date}\n")

    assert not result.ok
    assert code in codes(result)


def test_a_date_of_today_is_accepted():
    result = parse(
        f"symbol,quantity,average_cost,purchase_date\nAAPL,10,185.20,{TODAY.isoformat()}\n"
    )

    assert result.ok


@pytest.mark.parametrize(
    "symbol",
    ["", "   ", "AA PL", "=SUM(A1)", "@AAPL", "AAPL;DROP", "A" * 25],
)
def test_symbol_validation(symbol):
    result = parse(f"symbol,quantity,average_cost\n{symbol},10,185.20\n")

    assert not result.ok


def test_a_row_with_more_cells_than_the_header_is_rejected():
    result = parse("symbol,quantity,average_cost\nAAPL,10,185.20,extra\n")

    assert not result.ok
    assert "too_many_cells" in codes(result)


def test_an_over_long_cell_is_rejected():
    result = parse(f"symbol,quantity,average_cost\n{'A' * (MAX_CELL_LENGTH + 1)},10,1\n")

    assert not result.ok
    assert "too_long" in codes(result)


def test_multiple_errors_on_one_row_are_all_reported():
    result = parse("symbol,quantity,average_cost\n,0,-1\n")

    assert {error.column for error in result.errors} == {
        "symbol",
        "quantity",
        "average_cost",
    }


def test_errors_from_several_rows_are_all_reported():
    result = parse("symbol,quantity,average_cost\nAAPL,0,1\nMSFT,0,1\nGOOG,0,1\n")

    assert {error.line for error in result.errors} == {2, 3, 4}


# --- Export safety ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tTAB", "'\tTAB"),
        ("AAPL", "AAPL"),
        ("", ""),
        ("185.20", "185.20"),
    ],
)
def test_csv_values_are_made_safe_for_spreadsheets(raw, expected):
    assert sanitize_csv_value(raw) == expected
