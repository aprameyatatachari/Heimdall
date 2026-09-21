"""Integration tests for the CSV import endpoint."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "csv"
PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={
            "email": f"csv-{uuid.uuid4().hex[:12]}@example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio(api, headers) -> str:
    response = await api.post(
        PORTFOLIOS,
        json={"name": f"Portfolio {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _import(api, headers, portfolio_id, content: bytes, *, mode: str | None = None):
    data = {"mode": mode} if mode else {}
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        files={"file": ("holdings.csv", content, "text/csv")},
        data=data,
        headers=headers,
    )


async def _import_fixture(api, headers, portfolio_id, name: str, *, mode: str | None = None):
    return await _import(api, headers, portfolio_id, (FIXTURES / name).read_bytes(), mode=mode)


async def _positions(api, headers, portfolio_id) -> list[dict]:
    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/positions", headers=headers)
    assert response.status_code == 200
    return list(response.json())


# --- Happy path --------------------------------------------------------------


async def test_a_valid_file_imports(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import_fixture(api, headers, portfolio_id, "valid_simple.csv")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_read"] == 3
    assert body["positions_created"] == 3
    assert body["positions_merged"] == 0
    assert body["positions_removed"] == 0
    assert body["position_count"] == 3
    assert [p["asset"]["symbol"] for p in body["positions"]] == ["AAPL", "MSFT", "SPY"]


async def test_imported_values_are_stored_exactly(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    await _import_fixture(api, headers, portfolio_id, "valid_simple.csv")
    positions = {p["asset"]["symbol"]: p for p in await _positions(api, headers, portfolio_id)}

    assert Decimal(positions["AAPL"]["quantity"]) == Decimal("10")
    assert Decimal(positions["AAPL"]["average_cost"]) == Decimal("185.20")
    assert positions["AAPL"]["purchase_date"] == "2024-03-15"
    assert Decimal(positions["SPY"]["average_cost"]) == Decimal("510")


async def test_the_total_cost_basis_is_reported(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,100.0000\nMSFT,5,200.0000\n",
    )

    assert Decimal(response.json()["total_cost_basis"]) == Decimal("2000")


async def test_assets_are_created_for_unknown_symbols(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nzzzz,1,1\n",
    )

    asset = response.json()["positions"][0]["asset"]
    assert asset["symbol"] == "ZZZZ"
    assert asset["asset_type"] == "unknown"
    assert asset["name"] is None


async def test_a_file_written_by_a_spreadsheet_imports(api):
    """UTF-8 BOM plus CRLF line endings."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import_fixture(api, headers, portfolio_id, "valid_bom_crlf.csv")

    assert response.status_code == 200, response.text
    assert response.json()["positions_created"] == 2


# --- Modes -------------------------------------------------------------------


async def test_merge_is_the_default_mode(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100.0000\n")

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,200.0000\n",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "merge"
    assert body["positions_merged"] == 1
    assert body["positions_created"] == 0
    assert body["position_count"] == 1
    # (10*100 + 10*200) / 20 = 150
    assert Decimal(body["positions"][0]["quantity"]) == Decimal("20")
    assert Decimal(body["positions"][0]["average_cost"]) == Decimal("150")


async def test_merge_keeps_holdings_absent_from_the_file(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,100\nMSFT,5,200\n",
    )

    response = await _import(
        api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n", mode="merge"
    )

    assert response.json()["position_count"] == 2


async def test_merge_keeps_the_earliest_purchase_date(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost,purchase_date\nAAPL,10,100,2024-06-01\n",
    )

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost,purchase_date\nAAPL,10,100,2024-01-15\n",
        mode="merge",
    )

    assert response.json()["positions"][0]["purchase_date"] == "2024-01-15"


async def test_replace_leaves_exactly_the_files_holdings(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,100\nMSFT,5,200\nGOOG,1,50\n",
    )

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nNVDA,3,900\n",
        mode="replace",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["positions_removed"] == 3
    assert body["positions_created"] == 1
    assert body["position_count"] == 1
    assert [p["asset"]["symbol"] for p in body["positions"]] == ["NVDA"]


async def test_replace_can_reuse_a_symbol_it_just_removed(api):
    """The delete must be flushed before the insert, or the unique index fires."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n")

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,25,150\n",
        mode="replace",
    )

    assert response.status_code == 200, response.text
    assert response.json()["position_count"] == 1
    assert Decimal(response.json()["positions"][0]["quantity"]) == Decimal("25")


async def test_reject_mode_fails_on_an_existing_holding(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n")

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,1,1\nMSFT,1,1\n",
        mode="reject",
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "csv_import_conflict"
    assert body["details"][0]["row"] == 2
    assert "AAPL" in body["details"][0]["message"]


async def test_a_failed_reject_import_changes_nothing(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n")

    await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,1,1\nMSFT,1,1\n",
        mode="reject",
    )
    positions = await _positions(api, headers, portfolio_id)

    assert [p["asset"]["symbol"] for p in positions] == ["AAPL"]
    assert Decimal(positions[0]["quantity"]) == Decimal("10")


async def test_reject_mode_succeeds_when_nothing_overlaps(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n")

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nMSFT,1,1\n",
        mode="reject",
    )

    assert response.status_code == 200
    assert response.json()["position_count"] == 2


async def test_an_unknown_mode_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,1,1\n",
        mode="overwrite",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- Failure leaves nothing behind -------------------------------------------


async def test_a_file_with_bad_rows_writes_nothing(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import_fixture(api, headers, portfolio_id, "invalid_rows.csv")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_import_failed"
    assert await _positions(api, headers, portfolio_id) == []


async def test_one_bad_row_rejects_the_whole_file(api):
    """A file is all-or-nothing: the two valid rows must not be written."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,100\nMSFT,0,200\nGOOG,1,50\n",
    )

    assert response.status_code == 422
    assert await _positions(api, headers, portfolio_id) == []


async def test_a_failed_import_does_not_disturb_existing_holdings(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100.0000\n")

    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nMSFT,0,200\n")
    positions = await _positions(api, headers, portfolio_id)

    assert len(positions) == 1
    assert Decimal(positions[0]["quantity"]) == Decimal("10")
    assert Decimal(positions[0]["average_cost"]) == Decimal("100")


async def test_a_failed_replace_does_not_delete_anything(api):
    """The delete and the insert share one transaction."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _import(api, headers, portfolio_id, b"symbol,quantity,average_cost\nAAPL,10,100\n")

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nMSFT,-1,200\n",
        mode="replace",
    )

    assert response.status_code == 422
    assert len(await _positions(api, headers, portfolio_id)) == 1


async def test_errors_identify_the_line_and_the_column(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(
        api,
        headers,
        portfolio_id,
        b"symbol,quantity,average_cost\nAAPL,10,100\nMSFT,0,200\n,1,1\n",
    )

    details = response.json()["error"]["details"]
    reported = {(detail["row"], detail.get("field")) for detail in details}
    assert (3, "quantity") in reported
    assert (4, "symbol") in reported


@pytest.mark.parametrize(
    ("fixture_name", "code"),
    [
        ("invalid_duplicate_symbol.csv", "csv_import_failed"),
        ("invalid_unexpected_column.csv", "csv_unexpected_columns"),
        ("invalid_missing_column.csv", "csv_missing_columns"),
        ("invalid_header_only.csv", "csv_no_rows"),
        ("invalid_formula_injection.csv", "csv_import_failed"),
    ],
)
async def test_malformed_files_are_rejected_safely(api, fixture_name, code):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import_fixture(api, headers, portfolio_id, fixture_name)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert await _positions(api, headers, portfolio_id) == []


async def test_an_empty_upload_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(api, headers, portfolio_id, b"")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_empty_file"


async def test_a_binary_upload_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _import(api, headers, portfolio_id, b"\x89PNG\r\n\x1a\n\x00\x00")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_not_text"


async def test_an_oversized_upload_is_rejected_without_being_parsed(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    payload = b"symbol,quantity,average_cost\n" + b"AAAA,1,1\n" * 80_000

    response = await _import(api, headers, portfolio_id, payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_file_too_large"


async def test_a_missing_file_field_is_a_validation_error(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        data={"mode": "merge"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- Authorization -----------------------------------------------------------


async def test_import_requires_authentication(api):
    response = await api.post(
        f"{PORTFOLIOS}/{uuid.uuid4()}/positions/import",
        files={"file": ("holdings.csv", b"symbol,quantity,average_cost\nAAPL,1,1\n", "text/csv")},
    )

    assert response.status_code == 401


async def test_another_user_cannot_import_into_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner)

    response = await _import(
        api, intruder, portfolio_id, b"symbol,quantity,average_cost\nAAPL,1,1\n"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"
    assert await _positions(api, owner, portfolio_id) == []


async def test_importing_into_an_unknown_portfolio_returns_404(api):
    headers = await _signed_in_user(api)

    response = await _import(
        api, headers, str(uuid.uuid4()), b"symbol,quantity,average_cost\nAAPL,1,1\n"
    )

    assert response.status_code == 404
