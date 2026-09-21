# Fixtures

Deterministic offline data used by tests and local development. Tests must never
depend on a live third-party API, so every input used in automated tests is
committed here.

## `csv/`

Position-import files covering the contract in
[docs/csv-import.md](../docs/csv-import.md).

| File | What it exercises |
| --- | --- |
| `valid_simple.csv` | The documented happy path from the docs |
| `valid_no_dates.csv` | `purchase_date` column omitted entirely |
| `valid_reordered_and_messy.csv` | Any column order, lower-case and padded symbols, fractional quantity, `BRK.B` |
| `valid_bom_crlf.csv` | UTF-8 BOM and CRLF line endings, as written by spreadsheet software |
| `invalid_rows.csv` | Zero, negative, and malformed values, and a missing symbol |
| `invalid_duplicate_symbol.csv` | The same symbol on two lines |
| `invalid_unexpected_column.csv` | A column that is not part of the contract |
| `invalid_missing_column.csv` | A required column missing |
| `invalid_header_only.csv` | Header present, no holdings |
| `invalid_formula_injection.csv` | A cell that a spreadsheet would execute |

## Market data

Offline daily price series arrive with the market-data subsystem in Phase 3,
under `market_data/`.
