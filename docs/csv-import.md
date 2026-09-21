# CSV position import

```text
POST /api/v1/portfolios/{portfolio_id}/positions/import
Content-Type: multipart/form-data
```

| Form field | Required | Description |
| --- | --- | --- |
| `file` | yes | UTF-8 CSV file of holdings |
| `mode` | no | `merge` (default), `replace`, or `reject` |

## File contract

```csv
symbol,quantity,average_cost,purchase_date
AAPL,10,185.20,2024-03-15
MSFT,8,402.10,2024-04-02
SPY,12,510.00,2024-06-10
```

| Column | Required | Rules |
| --- | --- | --- |
| `symbol` | yes | Letters, digits, dots, and hyphens. Normalized to upper case and trimmed. `BRK.B` and `RDS-A` are valid |
| `quantity` | yes | Greater than zero, at most 8 decimal places, below 10¹² |
| `average_cost` | yes | Zero or greater, at most 4 decimal places, below 10¹². Per unit, in the portfolio's base currency |
| `purchase_date` | no | ISO `YYYY-MM-DD`, not in the future. The column and the value may both be omitted |

Accepted without complaint:

- Columns in any order, and header names with different case or spaces.
- A UTF-8 byte-order mark and CRLF line endings, as spreadsheet software writes.
- Thousands separators in numbers, when the field is quoted (`"1,234.56"`).
- Surrounding whitespace in any cell.

## Modes

| Mode | Behaviour |
| --- | --- |
| `merge` (default) | Each row is combined with the matching holding: quantities add and the average cost becomes the cost-weighted mean. Holdings absent from the file are left alone. |
| `replace` | Every existing holding is deleted, then the file's rows are inserted. The portfolio ends up containing exactly what the file describes. |
| `reject` | The import fails if any imported symbol is already held. Nothing changes. |

Merge arithmetic, identical to adding a position by hand:

```text
quantity      = q_old + q_new
average_cost  = (q_old * c_old + q_new * c_new) / (q_old + q_new)   rounded to 4 dp
purchase_date = min(existing, imported)
```

## Atomicity

The file is validated **completely** before anything is written, and the whole
import runs in the request's single transaction.

- One bad row rejects the entire file. Valid rows from that file are not written.
- A failed import leaves the portfolio byte-for-byte as it was, including a failed
  `replace`, where the deletes and inserts share one transaction.
- Symbols are resolved to assets before any position is written, so an invalid
  symbol or a currency mismatch aborts before the first change.

## Limits

| Limit | Value | Error code |
| --- | --- | --- |
| File size | 512 KiB | `csv_file_too_large` |
| Rows | 1000 | `csv_too_many_rows` |
| Cell length | 64 characters | `too_long` (row error) |
| Resulting holdings | 200 per portfolio | `csv_position_limit_exceeded` |

The upload is counted as it streams, not trusted from `Content-Length`.

## Errors

Structural problems — the file cannot be read at all — return one error with no
row detail:

| Code | Cause |
| --- | --- |
| `csv_empty_file` | Zero bytes uploaded |
| `csv_no_rows` | Header present, no holdings |
| `csv_missing_header` | No header row |
| `csv_missing_columns` | A required column is absent |
| `csv_unexpected_columns` | A column outside the contract |
| `csv_duplicate_columns` | The same column name twice |
| `csv_invalid_encoding` | Not valid UTF-8 |
| `csv_not_text` | Binary content |
| `csv_malformed` | Unparseable as CSV |
| `csv_file_too_large`, `csv_too_many_rows` | Over a limit |

Row problems return `csv_import_failed` with one detail per problem, each naming
the **line number as the file shows it** (line 1 is the header) and the column:

```json
{
  "error": {
    "code": "csv_import_failed",
    "message": "The uploaded file contains errors. No changes were made.",
    "details": [
      { "row": 3, "field": "quantity", "message": "quantity must be greater than zero.", "code": "out_of_range" },
      { "row": 4, "field": "symbol", "message": "symbol is required.", "code": "required" }
    ],
    "request_id": "6f1c..."
  }
}
```

Row error codes: `required`, `not_a_number`, `not_finite`, `out_of_range`,
`too_precise`, `not_a_date`, `invalid_symbol`, `duplicate_symbol`, `too_long`,
`too_many_cells`.

`reject` mode conflicts return `csv_import_conflict`, with one detail per
already-held symbol.

## Duplicate handling

Two senses of "duplicate", handled differently:

- **The same symbol twice in one file** is a row error (`duplicate_symbol`) on the
  later line. The file is ambiguous about what the holding should be, so Heimdall
  does not guess — it names the earlier line and asks for one row.
- **A symbol already held in the portfolio** is governed by `mode`.

## Spreadsheet formula injection

A cell beginning with `=`, `+`, `-`, `@`, a tab, or a carriage return is executed
by spreadsheet software when the file is reopened. Heimdall guards both directions:

- **On import**, such a value fails validation unless it is a plain number.
- **On export**, `sanitize_csv_value` prefixes it with a single quote so the
  spreadsheet keeps it as text. Every CSV Heimdall writes passes through it.

## Fixtures

Files covering every case above live in [`fixtures/csv/`](../fixtures/csv), and
the test suite reads them directly, so the documented contract and the tested
contract cannot drift apart.

## Limitations

- One currency per portfolio. A symbol already known in a different currency is
  rejected with `currency_mismatch`; the importer does not convert.
- No broker-specific formats. Only the contract above is accepted.
- No dry-run endpoint. A validation-only mode would be a small addition, but is
  not implemented.
