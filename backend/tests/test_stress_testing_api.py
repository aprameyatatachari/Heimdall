"""Integration tests for the stress-testing endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
# Covers the 2015, 2018, 2020, and 2022 scenario windows.
DATA_WINDOW = {"start": "2015-01-01", "end": "2023-12-29"}


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"st-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio(api, headers, holdings, *, refresh: bool = True) -> str:
    created = await api.post(
        PORTFOLIOS, json={"name": f"Portfolio {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert created.status_code == 201, created.text
    portfolio_id = str(created.json()["id"])

    for symbol, quantity, cost in holdings:
        added = await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/positions",
            json={"symbol": symbol, "quantity": quantity, "average_cost": cost},
            headers=headers,
        )
        assert added.status_code == 201, added.text

    if refresh:
        refreshed = await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh",
            params=DATA_WINDOW,
            headers=headers,
        )
        assert refreshed.status_code == 200, refreshed.text

    return portfolio_id


async def _stress(api, headers, portfolio_id, payload):
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/stress-tests", json=payload, headers=headers
    )


TECH_AND_HEALTH = [("AAPL", "100", "50"), ("MSFT", "50", "100"), ("JNJ", "50", "100")]


# --- Catalogue ---------------------------------------------------------------


async def test_the_scenario_catalogue_is_returned(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/stress-scenarios", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) >= 4
    assert body["limitations"]
    keys = {item["key"] for item in body["items"]}
    assert "covid_19_crash_2020" in keys
    assert "global_financial_crisis_2007_2009" in keys


async def test_every_catalogue_entry_states_its_exact_dates(api):
    headers = await _signed_in_user(api)

    body = (await api.get("/api/v1/stress-scenarios", headers=headers)).json()

    for item in body["items"]:
        assert item["start"] < item["end"]
        assert item["window"] == f"{item['start']} to {item['end']}"
        assert item["description"]


async def test_the_catalogue_requires_authentication(api):
    response = await api.get("/api/v1/stress-scenarios")

    assert response.status_code == 401


# --- Historical scenarios ----------------------------------------------------


async def test_a_historical_scenario_produces_a_loss_and_a_breakdown(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    response = await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scenario_type"] == "historical"
    assert body["scenario_name"] == "COVID-19 crash"
    assert Decimal(body["starting_value"]) > 0
    assert Decimal(body["total_impact"]) < 0
    assert Decimal(body["total_impact_percent"]) < 0
    assert len(body["positions"]) == 3
    assert body["reconciles"] is True


async def test_the_scenario_definition_is_stored_with_the_run(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    definition = body["scenario_definition"]
    assert definition["start"] == "2020-02-19"
    assert definition["end"] == "2020-03-23"
    assert definition["key"] == "covid_19_crash_2020"
    assert body["data_as_of"] == "2023-12-29"


async def test_position_impacts_reconcile_with_the_portfolio_impact(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (await _stress(api, headers, portfolio_id, {"scenario_key": "rate_rises_2022"})).json()

    summed = sum(Decimal(position["impact"]) for position in body["positions"])
    assert summed == pytest.approx(Decimal(body["total_impact"]), abs=Decimal("0.01"))
    assert Decimal(body["ending_value"]) == pytest.approx(
        Decimal(body["starting_value"]) + Decimal(body["total_impact"]),
        abs=Decimal("0.01"),
    )


async def test_contributions_to_loss_sum_to_one(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    shares = [Decimal(position["contribution_to_loss"]) for position in body["positions"]]
    assert sum(shares) == pytest.approx(Decimal("1"), abs=Decimal("0.0001"))


async def test_each_position_records_where_its_return_came_from(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    for position in body["positions"]:
        assert "observed return from" in position["return_source"]


async def test_limitations_and_the_disclaimer_are_returned(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    assert len(body["limitations"]) >= 4
    assert any("not a forecast" in item for item in body["limitations"])
    assert body["disclaimer"].startswith("Heimdall is an educational")


async def test_a_holding_without_scenario_data_is_excluded(api):
    """A symbol the provider does not know cannot be given a return."""
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS, json={"name": f"Mixed {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    portfolio_id = str(created.json()["id"])
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        files={
            "file": (
                "h.csv",
                b"symbol,quantity,average_cost\nAAPL,100,50\nZZZZ,10,10\n",
                "text/csv",
            )
        },
        headers=headers,
    )
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh", params=DATA_WINDOW, headers=headers
    )

    body = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    assert body["excluded_symbols"] == ["ZZZZ"]
    assert body["status"] == "partial"
    assert {position["symbol"] for position in body["positions"]} == {"AAPL"}


async def test_an_unknown_scenario_key_returns_404(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")])

    response = await _stress(api, headers, portfolio_id, {"scenario_key": "no_such_scenario"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "scenario_not_found"


async def test_a_scenario_with_no_stored_data_is_reported(api):
    """The GFC window predates the refresh above, so nothing is cached for it."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "100", "50")])

    response = await _stress(
        api, headers, portfolio_id, {"scenario_key": "global_financial_crisis_2007_2009"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "scenario_data_unavailable"


# --- Hypothetical scenarios --------------------------------------------------


async def test_a_portfolio_wide_shock_is_applied(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {
            "custom": {
                "name": "Broad market decline",
                "shocks": [{"target_type": "portfolio", "value": "-0.20"}],
            }
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scenario_type"] == "hypothetical"
    assert Decimal(body["total_impact_percent"]) == pytest.approx(
        Decimal("-0.20"), abs=Decimal("0.0001")
    )
    assert all(
        Decimal(position["applied_return"]) == Decimal("-0.20") for position in body["positions"]
    )


async def test_an_asset_shock_overrides_a_sector_shock_end_to_end(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(
            api,
            headers,
            portfolio_id,
            {
                "custom": {
                    "name": "Technology sell-off",
                    "shocks": [
                        {"target_type": "sector", "target": "Technology", "value": "-0.20"},
                        {"target_type": "symbol", "target": "AAPL", "value": "-0.30"},
                    ],
                }
            },
        )
    ).json()

    positions = {position["symbol"]: position for position in body["positions"]}
    assert Decimal(positions["AAPL"]["applied_return"]) == Decimal("-0.30")
    assert Decimal(positions["MSFT"]["applied_return"]) == Decimal("-0.20")
    assert Decimal(positions["JNJ"]["applied_return"]) == Decimal("0")
    assert "symbol shock on AAPL" in positions["AAPL"]["return_source"]
    assert "sector shock on Technology" in positions["MSFT"]["return_source"]


async def test_the_precedence_rule_is_stated_in_the_stored_definition(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(
            api,
            headers,
            portfolio_id,
            {
                "custom": {
                    "name": "Mixed",
                    "shocks": [{"target_type": "portfolio", "value": "-0.10"}],
                }
            },
        )
    ).json()

    assert "overrides" in body["scenario_definition"]["precedence"]
    assert body["scenario_definition"]["shocks"][0]["value"] == "-0.10"


async def test_a_positive_shock_produces_a_gain(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)

    body = (
        await _stress(
            api,
            headers,
            portfolio_id,
            {
                "custom": {
                    "name": "Rally",
                    "shocks": [{"target_type": "portfolio", "value": "0.15"}],
                }
            },
        )
    ).json()

    assert Decimal(body["total_impact"]) > 0
    assert all(position["contribution_to_loss"] is None for position in body["positions"])


@pytest.mark.parametrize("value", ["-1.5", "6.0", "-1.0"])
async def test_an_out_of_range_shock_is_rejected(api, value):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {"custom": {"name": "Extreme", "shocks": [{"target_type": "portfolio", "value": value}]}},
    )

    assert response.status_code == 422


async def test_a_symbol_shock_without_a_target_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {"custom": {"name": "Bad", "shocks": [{"target_type": "symbol", "value": "-0.1"}]}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_an_invalid_symbol_target_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {
            "custom": {
                "name": "Bad",
                "shocks": [{"target_type": "symbol", "target": "=1+1", "value": "-0.1"}],
            }
        },
    )

    assert response.status_code == 422


async def test_duplicate_shock_targets_are_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {
            "custom": {
                "name": "Ambiguous",
                "shocks": [
                    {"target_type": "symbol", "target": "AAPL", "value": "-0.1"},
                    {"target_type": "symbol", "target": "AAPL", "value": "-0.5"},
                ],
            }
        },
    )

    assert response.status_code == 422


async def test_an_empty_shock_list_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api, headers, portfolio_id, {"custom": {"name": "Nothing", "shocks": []}}
    )

    assert response.status_code == 422


async def test_supplying_both_scenario_kinds_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(
        api,
        headers,
        portfolio_id,
        {
            "scenario_key": "covid_19_crash_2020",
            "custom": {
                "name": "Both",
                "shocks": [{"target_type": "portfolio", "value": "-0.1"}],
            },
        },
    )

    assert response.status_code == 422


async def test_supplying_neither_scenario_kind_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(api, headers, portfolio_id, {})

    assert response.status_code == 422


# --- Edge cases and access ---------------------------------------------------


async def test_stressing_an_empty_portfolio_is_rejected(api):
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS, json={"name": f"Empty {uuid.uuid4().hex[:8]}"}, headers=headers
    )

    response = await _stress(
        api, headers, str(created.json()["id"]), {"scenario_key": "covid_19_crash_2020"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "portfolio_empty"


async def test_stressing_an_unpriced_portfolio_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_market_data"


async def test_a_run_can_be_read_back(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)
    created = (
        await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    fetched = await api.get(f"/api/v1/stress-tests/{created['id']}", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["total_impact"] == created["total_impact"]
    assert len(fetched.json()["positions"]) == len(created["positions"])


async def test_runs_are_listed_newest_first(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, TECH_AND_HEALTH)
    await _stress(api, headers, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    await _stress(api, headers, portfolio_id, {"scenario_key": "rate_rises_2022"})

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/stress-tests", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]


async def test_another_user_cannot_read_a_run(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, TECH_AND_HEALTH)
    created = (
        await _stress(api, owner, portfolio_id, {"scenario_key": "covid_19_crash_2020"})
    ).json()

    response = await api.get(f"/api/v1/stress-tests/{created['id']}", headers=intruder)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stress_test_run_not_found"


async def test_another_user_cannot_run_a_stress_test(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, [("AAPL", "10", "50")], refresh=False)

    response = await _stress(api, intruder, portfolio_id, {"scenario_key": "covid_19_crash_2020"})

    assert response.status_code == 404


async def test_running_a_stress_test_requires_authentication(api):
    response = await api.post(
        f"{PORTFOLIOS}/{uuid.uuid4()}/stress-tests",
        json={"scenario_key": "covid_19_crash_2020"},
    )

    assert response.status_code == 401
