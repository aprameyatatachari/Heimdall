"""Integration tests for portfolio and position endpoints, including ownership."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"


async def _signed_in_user(api) -> dict[str, str]:
    """Register a fresh user and return an Authorization header for them."""
    email = f"user-{uuid.uuid4().hex[:12]}@example.com"
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_portfolio(api, headers, **overrides):
    payload = {"name": f"Portfolio {uuid.uuid4().hex[:8]}"}
    payload.update(overrides)
    response = await api.post(PORTFOLIOS, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _add_position(api, headers, portfolio_id, **overrides):
    payload = {"symbol": "AAPL", "quantity": "10", "average_cost": "185.20"}
    payload.update(overrides)
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions",
        json=payload,
        headers=headers,
    )


# --- Authentication is required ----------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", PORTFOLIOS),
        ("post", PORTFOLIOS),
        ("get", f"{PORTFOLIOS}/{uuid.uuid4()}"),
        ("patch", f"{PORTFOLIOS}/{uuid.uuid4()}"),
        ("delete", f"{PORTFOLIOS}/{uuid.uuid4()}"),
        ("get", f"{PORTFOLIOS}/{uuid.uuid4()}/positions"),
        ("post", f"{PORTFOLIOS}/{uuid.uuid4()}/positions"),
    ],
)
async def test_every_portfolio_endpoint_requires_authentication(api, method, path):
    kwargs = {"json": {}} if method in {"post", "patch"} else {}
    response = await getattr(api, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"not_authenticated", "invalid_access_token"}


# --- Portfolio CRUD ----------------------------------------------------------


async def test_create_portfolio_returns_the_created_record(api):
    headers = await _signed_in_user(api)

    portfolio = await _create_portfolio(
        api,
        headers,
        name="Retirement",
        description="Long-horizon holdings",
        benchmark_symbol="spy",
    )

    assert portfolio["name"] == "Retirement"
    assert portfolio["description"] == "Long-horizon holdings"
    assert portfolio["base_currency"] == "USD"
    assert portfolio["benchmark_symbol"] == "SPY"
    assert portfolio["position_count"] == 0


async def test_create_portfolio_does_not_expose_the_owner_id(api):
    headers = await _signed_in_user(api)

    portfolio = await _create_portfolio(api, headers)

    assert "user_id" not in portfolio


async def test_duplicate_portfolio_name_is_rejected(api):
    headers = await _signed_in_user(api)
    await _create_portfolio(api, headers, name="Core")

    response = await api.post(PORTFOLIOS, json={"name": "Core"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "portfolio_name_taken"


async def test_duplicate_name_check_ignores_case(api):
    headers = await _signed_in_user(api)
    await _create_portfolio(api, headers, name="Core")

    response = await api.post(PORTFOLIOS, json={"name": "CORE"}, headers=headers)

    assert response.status_code == 409


async def test_two_users_may_use_the_same_portfolio_name(api):
    first = await _signed_in_user(api)
    second = await _signed_in_user(api)

    await _create_portfolio(api, first, name="Core")
    response = await api.post(PORTFOLIOS, json={"name": "Core"}, headers=second)

    assert response.status_code == 201


async def test_unsupported_base_currency_is_rejected(api):
    headers = await _signed_in_user(api)

    response = await api.post(
        PORTFOLIOS,
        json={"name": "European", "base_currency": "EUR"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_list_portfolios_returns_only_the_callers_portfolios(api):
    first = await _signed_in_user(api)
    second = await _signed_in_user(api)
    await _create_portfolio(api, first, name="Mine")
    await _create_portfolio(api, second, name="Theirs")

    response = await api.get(PORTFOLIOS, headers=first)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Mine"]


async def test_list_portfolios_paginates(api):
    headers = await _signed_in_user(api)
    for index in range(3):
        await _create_portfolio(api, headers, name=f"P{index}")

    page = await api.get(PORTFOLIOS, params={"limit": 2, "offset": 0}, headers=headers)
    second_page = await api.get(PORTFOLIOS, params={"limit": 2, "offset": 2}, headers=headers)

    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1


async def test_get_portfolio_returns_positions_and_cost_basis(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    await _add_position(
        api, headers, portfolio["id"], symbol="AAPL", quantity="10", average_cost="100.0000"
    )
    await _add_position(
        api, headers, portfolio["id"], symbol="MSFT", quantity="5", average_cost="200.0000"
    )

    response = await api.get(f"{PORTFOLIOS}/{portfolio['id']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["position_count"] == 2
    assert [p["asset"]["symbol"] for p in body["positions"]] == ["AAPL", "MSFT"]
    assert Decimal(body["total_cost_basis"]) == Decimal("2000")


async def test_update_portfolio_changes_only_the_supplied_fields(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers, name="Before", description="Keep me")

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}",
        json={"name": "After"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "After"
    assert response.json()["description"] == "Keep me"


async def test_update_portfolio_can_clear_the_benchmark(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers, benchmark_symbol="SPY")

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}",
        json={"benchmark_symbol": None},
        headers=headers,
    )

    assert response.json()["benchmark_symbol"] is None


async def test_empty_update_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await api.patch(f"{PORTFOLIOS}/{portfolio['id']}", json={}, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_fields_to_update"


async def test_update_cannot_change_the_base_currency(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}",
        json={"base_currency": "EUR"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_delete_portfolio_removes_it_and_its_positions(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    await _add_position(api, headers, portfolio["id"])

    deleted = await api.delete(f"{PORTFOLIOS}/{portfolio['id']}", headers=headers)
    fetched = await api.get(f"{PORTFOLIOS}/{portfolio['id']}", headers=headers)

    assert deleted.status_code == 204
    assert fetched.status_code == 404


# --- Ownership isolation -----------------------------------------------------


async def test_another_user_cannot_read_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner, name="Private holdings")

    response = await api.get(f"{PORTFOLIOS}/{portfolio['id']}", headers=intruder)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"
    # The response must not confirm that the portfolio exists.
    assert "Private holdings" not in response.text


async def test_another_user_cannot_update_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner)

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}",
        json={"name": "Hijacked"},
        headers=intruder,
    )

    assert response.status_code == 404


async def test_another_user_cannot_delete_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner)

    response = await api.delete(f"{PORTFOLIOS}/{portfolio['id']}", headers=intruder)
    still_there = await api.get(f"{PORTFOLIOS}/{portfolio['id']}", headers=owner)

    assert response.status_code == 404
    assert still_there.status_code == 200


async def test_another_user_cannot_add_a_position(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner)

    response = await _add_position(api, intruder, portfolio["id"])

    assert response.status_code == 404


async def test_another_user_cannot_delete_a_position(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner)
    position = (await _add_position(api, owner, portfolio["id"])).json()

    response = await api.delete(
        f"{PORTFOLIOS}/{portfolio['id']}/positions/{position['id']}",
        headers=intruder,
    )

    assert response.status_code == 404


async def test_a_missing_portfolio_and_someone_elses_portfolio_look_identical(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, owner)

    theirs = await api.get(f"{PORTFOLIOS}/{portfolio['id']}", headers=intruder)
    missing = await api.get(f"{PORTFOLIOS}/{uuid.uuid4()}", headers=intruder)

    assert theirs.status_code == missing.status_code == 404
    assert theirs.json()["error"]["code"] == missing.json()["error"]["code"]
    assert theirs.json()["error"]["message"] == missing.json()["error"]["message"]


# --- Positions ---------------------------------------------------------------


async def test_add_position_creates_the_asset_on_demand(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await _add_position(api, headers, portfolio["id"], symbol="nvda")

    assert response.status_code == 201
    body = response.json()
    assert body["asset"]["symbol"] == "NVDA"
    # Nothing is invented about an instrument no provider has described yet.
    assert body["asset"]["asset_type"] == "unknown"
    assert body["asset"]["sector"] is None
    assert body["asset"]["currency"] == "USD"


async def test_position_preserves_decimal_precision(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await _add_position(
        api,
        headers,
        portfolio["id"],
        quantity="10.12345678",
        average_cost="185.2050",
    )

    body = response.json()
    assert Decimal(body["quantity"]) == Decimal("10.12345678")
    assert Decimal(body["average_cost"]) == Decimal("185.2050")
    # Cost basis is reported at monetary scale: 10.12345678 * 185.2050 = 1874.914830...
    assert Decimal(body["cost_basis"]) == Decimal("1874.9148")
    # Scales are normalized, so the same amount always looks the same on the wire.
    assert body["quantity"] == "10.12345678"
    assert body["average_cost"] == "185.2050"


async def test_cost_basis_uses_exact_decimal_arithmetic(api):
    """0.1 + 0.2 problems must not appear in monetary output."""
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await _add_position(
        api,
        headers,
        portfolio["id"],
        quantity="3",
        average_cost="0.1000",
    )

    assert Decimal(response.json()["cost_basis"]) == Decimal("0.3")


async def test_adding_a_held_asset_twice_is_rejected_by_default(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    await _add_position(api, headers, portfolio["id"], symbol="AAPL")

    response = await _add_position(api, headers, portfolio["id"], symbol="AAPL")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "position_already_exists"


async def test_merge_mode_combines_quantity_and_weighted_average_cost(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    await _add_position(
        api, headers, portfolio["id"], symbol="AAPL", quantity="10", average_cost="100.0000"
    )

    response = await _add_position(
        api,
        headers,
        portfolio["id"],
        symbol="AAPL",
        quantity="10",
        average_cost="200.0000",
        on_duplicate="merge",
    )

    assert response.status_code == 201
    body = response.json()
    assert Decimal(body["quantity"]) == Decimal("20")
    # (10*100 + 10*200) / 20 = 150
    assert Decimal(body["average_cost"]) == Decimal("150")


async def test_merge_mode_keeps_the_earliest_purchase_date(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    await _add_position(api, headers, portfolio["id"], purchase_date="2024-06-01")

    response = await _add_position(
        api,
        headers,
        portfolio["id"],
        purchase_date="2024-01-15",
        on_duplicate="merge",
    )

    assert response.json()["purchase_date"] == "2024-01-15"


async def test_merge_does_not_create_a_second_position(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    first = (await _add_position(api, headers, portfolio["id"])).json()

    merged = (await _add_position(api, headers, portfolio["id"], on_duplicate="merge")).json()
    listed = await api.get(f"{PORTFOLIOS}/{portfolio['id']}/positions", headers=headers)

    assert merged["id"] == first["id"]
    assert len(listed.json()) == 1


async def test_invalid_symbol_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await _add_position(api, headers, portfolio["id"], symbol="=1+1")

    assert response.status_code == 422


async def test_non_positive_quantity_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await _add_position(api, headers, portfolio["id"], quantity="0")

    assert response.status_code == 422


async def test_update_position_changes_quantity(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    position = (await _add_position(api, headers, portfolio["id"])).json()

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}/positions/{position['id']}",
        json={"quantity": "25.5"},
        headers=headers,
    )

    assert response.status_code == 200
    assert Decimal(response.json()["quantity"]) == Decimal("25.5")
    assert Decimal(response.json()["average_cost"]) == Decimal("185.20")


async def test_update_position_with_no_fields_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    position = (await _add_position(api, headers, portfolio["id"])).json()

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}/positions/{position['id']}",
        json={},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_fields_to_update"


async def test_updating_an_unknown_position_returns_404(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio['id']}/positions/{uuid.uuid4()}",
        json={"quantity": "1"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "position_not_found"


async def test_a_position_cannot_be_reached_through_another_portfolio(api):
    headers = await _signed_in_user(api)
    first = await _create_portfolio(api, headers, name="First")
    second = await _create_portfolio(api, headers, name="Second")
    position = (await _add_position(api, headers, first["id"])).json()

    response = await api.patch(
        f"{PORTFOLIOS}/{second['id']}/positions/{position['id']}",
        json={"quantity": "1"},
        headers=headers,
    )

    assert response.status_code == 404


async def test_delete_position_removes_it(api):
    headers = await _signed_in_user(api)
    portfolio = await _create_portfolio(api, headers)
    position = (await _add_position(api, headers, portfolio["id"])).json()

    deleted = await api.delete(
        f"{PORTFOLIOS}/{portfolio['id']}/positions/{position['id']}",
        headers=headers,
    )
    listed = await api.get(f"{PORTFOLIOS}/{portfolio['id']}/positions", headers=headers)

    assert deleted.status_code == 204
    assert listed.json() == []


async def test_the_same_asset_can_be_held_in_two_portfolios(api):
    headers = await _signed_in_user(api)
    first = await _create_portfolio(api, headers, name="First")
    second = await _create_portfolio(api, headers, name="Second")

    one = await _add_position(api, headers, first["id"], symbol="AAPL")
    two = await _add_position(api, headers, second["id"], symbol="AAPL")

    assert one.status_code == two.status_code == 201
    # One shared asset record, two positions.
    assert one.json()["asset"]["id"] == two.json()["asset"]["id"]
    assert one.json()["id"] != two.json()["id"]


async def test_a_malformed_portfolio_id_is_a_validation_error(api):
    headers = await _signed_in_user(api)

    response = await api.get(f"{PORTFOLIOS}/not-a-uuid", headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
