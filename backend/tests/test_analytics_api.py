"""Integration tests for the portfolio summary and analysis-run endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
# Two full years inside the committed fixture range, so tail measures have data.
WINDOW = {"start": "2022-01-03", "end": "2023-12-29"}


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"an-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio(
    api,
    headers,
    holdings: list[tuple[str, str, str]],
    *,
    benchmark: str | None = None,
    refresh: bool = True,
) -> str:
    payload: dict[str, object] = {"name": f"Portfolio {uuid.uuid4().hex[:8]}"}
    if benchmark:
        payload["benchmark_symbol"] = benchmark

    created = await api.post(PORTFOLIOS, json=payload, headers=headers)
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
            params=WINDOW,
            headers=headers,
        )
        assert refreshed.status_code == 200, refreshed.text

    return portfolio_id


async def _run(api, headers, portfolio_id, **body):
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/analysis-runs",
        json={**WINDOW, **body},
        headers=headers,
    )


def _metrics(payload: dict) -> dict[str, dict]:
    return {result["metric"]: result for result in payload["results"]}


# --- Summary -----------------------------------------------------------------


async def test_summary_values_the_portfolio(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["holdings_count"] == 2
    assert body["priced_holdings_count"] == 2
    assert body["unpriced_symbols"] == []
    assert Decimal(body["total_market_value"]) > 0
    assert Decimal(body["total_cost_basis"]) == Decimal("4000")
    assert body["data_as_of"] == "2023-12-29"
    assert body["disclaimer"].startswith("Heimdall is an educational")


async def test_summary_weights_sum_to_one(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)).json()

    weights = [holding["weight"] for holding in body["holdings"]]
    assert sum(weights) == pytest.approx(1.0, abs=1e-9)


async def test_summary_reports_sector_weights(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "10", "50"), ("JNJ", "10", "100")])

    body = (await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)).json()

    assert set(body["sector_weights"]) == {"Technology", "Healthcare"}
    assert body["unknown_sector_weight"] == 0.0
    assert sum(body["sector_weights"].values()) == pytest.approx(1.0, abs=1e-9)


async def test_an_unpriced_holding_is_excluded_not_counted_as_zero(api):
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS,
        json={"name": f"Partial {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    portfolio_id = str(created.json()["id"])
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions/import",
        files={
            "file": (
                "h.csv",
                b"symbol,quantity,average_cost\nSPY,10,300\nZZZZ,5,10\n",
                "text/csv",
            )
        },
        headers=headers,
    )
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh", params=WINDOW, headers=headers
    )

    body = (await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)).json()

    assert body["unpriced_symbols"] == ["ZZZZ"]
    assert body["priced_holdings_count"] == 1
    unpriced = next(h for h in body["holdings"] if h["symbol"] == "ZZZZ")
    assert unpriced["market_value"] is None
    assert unpriced["weight"] is None
    assert unpriced["latest_price"] is None


async def test_a_portfolio_with_no_prices_reports_zero_value_and_no_weights(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")], refresh=False)

    body = (await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=headers)).json()

    assert body["data_as_of"] is None
    assert body["priced_holdings_count"] == 0
    assert body["holdings"][0]["weight"] is None
    assert body["largest_position_weight"] is None


async def test_summary_requires_ownership(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, [("SPY", "1", "300")], refresh=False)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/summary", headers=intruder)

    assert response.status_code == 404


# --- Analysis runs -----------------------------------------------------------


async def test_an_analysis_run_produces_the_documented_metrics(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(
        api,
        headers,
        [("SPY", "10", "300"), ("AAPL", "20", "50"), ("TLT", "5", "100")],
    )

    response = await _run(api, headers, portfolio_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] in {"succeeded", "partial"}
    metrics = _metrics(body)

    for expected in (
        "portfolio_value",
        "total_cost_basis",
        "unrealized_profit_loss",
        "total_return",
        "annualized_return",
        "volatility_daily",
        "volatility_annualized",
        "sharpe_ratio",
        "max_drawdown",
        "current_drawdown",
        "value_at_risk_historical",
        "value_at_risk_parametric",
        "expected_shortfall",
        "portfolio_volatility_from_covariance",
        "risk_contribution",
        "average_pairwise_correlation",
        "largest_position_weight",
        "largest_sector_weight",
    ):
        assert expected in metrics, f"{expected} missing"


async def test_every_metric_carries_a_unit(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (await _run(api, headers, portfolio_id)).json()

    for result in body["results"]:
        assert result["unit"] in {"ratio", "percent", "currency", "count", "days", "date"}


async def test_daily_and_annualized_volatility_are_reported_separately(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())

    daily = Decimal(metrics["volatility_daily"]["value"])
    annual = Decimal(metrics["volatility_annualized"]["value"])

    assert metrics["volatility_daily"]["metadata"]["annualized"] is False
    assert metrics["volatility_annualized"]["metadata"]["annualized"] is True
    assert annual > daily
    assert float(annual / daily) == pytest.approx(252**0.5, rel=1e-6)


async def test_var_is_a_positive_loss_amount_with_its_confidence_recorded(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    metrics = _metrics((await _run(api, headers, portfolio_id, confidence=0.99)).json())
    historical = metrics["value_at_risk_historical"]

    assert Decimal(historical["value"]) > 0
    assert historical["unit"] == "currency"
    assert historical["metadata"]["confidence"] == 0.99
    assert "positive estimated loss" in historical["metadata"]["sign_convention"]
    assert "not a maximum possible loss" in historical["metadata"]["assumption"].lower()


async def test_expected_shortfall_is_at_least_historical_var(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())

    assert Decimal(metrics["expected_shortfall"]["value"]) >= Decimal(
        metrics["value_at_risk_historical"]["value"]
    )


async def test_max_drawdown_is_never_positive(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())

    assert Decimal(metrics["max_drawdown"]["value"]) <= 0
    assert metrics["max_drawdown"]["metadata"]["peak_date"]
    assert metrics["max_drawdown"]["metadata"]["trough_date"]


async def test_risk_contributions_reconcile_with_total_volatility(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(
        api,
        headers,
        [("SPY", "10", "300"), ("AAPL", "20", "50"), ("XOM", "15", "80")],
    )

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())
    contribution = metrics["risk_contribution"]
    total = Decimal(metrics["portfolio_volatility_from_covariance"]["value"])

    assert contribution["metadata"]["reconciles_to_portfolio_volatility"] is True
    assert Decimal(contribution["value"]) == pytest.approx(total, abs=Decimal("0.000001"))
    shares = [asset["share_of_risk"] for asset in contribution["metadata"]["assets"]]
    assert sum(shares) == pytest.approx(1.0, abs=1e-9)


async def test_the_correlation_matrix_is_returned_with_its_symbols(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("TLT", "5", "100")])

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())
    correlation = metrics["average_pairwise_correlation"]

    assert correlation["metadata"]["excludes_diagonal"] is True
    assert correlation["metadata"]["symbols"] == ["SPY", "TLT"]
    matrix = correlation["metadata"]["matrix"]
    assert matrix[0][0] == pytest.approx(1.0)
    assert matrix[0][1] == pytest.approx(matrix[1][0])


async def test_the_fixed_weight_assumption_is_stated(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (await _run(api, headers, portfolio_id)).json()

    assert any("today's weights" in note for note in body["notes"])
    metrics = _metrics(body)
    assert "today's weights" in metrics["total_return"]["metadata"]["assumption"]


async def test_the_run_records_its_parameters_and_data_as_of(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (
        await _run(api, headers, portfolio_id, confidence=0.9, annual_risk_free_rate=0.045)
    ).json()

    assert body["parameters"]["confidence"] == 0.9
    assert body["parameters"]["annual_risk_free_rate"] == 0.045
    assert body["parameters"]["start"] == WINDOW["start"]
    assert body["parameters"]["end"] == WINDOW["end"]
    assert body["parameters"]["periods_per_year"] == 252
    assert body["data_as_of"] == "2023-12-29"


async def test_the_risk_free_rate_changes_the_sharpe_ratio(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    without = _metrics((await _run(api, headers, portfolio_id)).json())
    with_rate = _metrics(
        (await _run(api, headers, portfolio_id, annual_risk_free_rate=0.05)).json()
    )

    assert Decimal(with_rate["sharpe_ratio"]["value"]) < Decimal(without["sharpe_ratio"]["value"])


async def test_a_weekly_frequency_changes_the_annualization_factor(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (await _run(api, headers, portfolio_id, frequency="weekly")).json()

    assert body["parameters"]["periods_per_year"] == 52


# --- Edge cases --------------------------------------------------------------


async def test_analyzing_an_empty_portfolio_is_rejected(api):
    headers = await _signed_in_user(api)
    created = await api.post(
        PORTFOLIOS, json={"name": f"Empty {uuid.uuid4().hex[:8]}"}, headers=headers
    )

    response = await _run(api, headers, str(created.json()["id"]))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "portfolio_empty"


async def test_analyzing_a_portfolio_with_no_market_data_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")], refresh=False)

    response = await _run(api, headers, portfolio_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_market_data"


async def test_a_single_asset_portfolio_reports_correlation_as_unavailable(api):
    """One asset has no pairs, so the metric is unavailable rather than zero."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")])

    body = (await _run(api, headers, portfolio_id)).json()
    metrics = _metrics(body)

    assert body["status"] == "partial"
    correlation = metrics["average_pairwise_correlation"]
    assert correlation["value"] is None
    assert "2 observations" in correlation["unavailable_reason"]


async def test_a_short_window_reports_tail_measures_as_unavailable(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (
        await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/analysis-runs",
            json={"start": "2023-12-01", "end": "2023-12-29"},
            headers=headers,
        )
    ).json()

    metrics = _metrics(body)
    assert body["status"] == "partial"
    assert metrics["value_at_risk_historical"]["value"] is None
    assert "observations" in metrics["value_at_risk_historical"]["unavailable_reason"]
    # The metrics that do not need 30 observations are still reported.
    assert metrics["total_return"]["value"] is not None


async def test_an_unavailable_metric_never_reports_zero(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")])

    body = (
        await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/analysis-runs",
            json={"start": "2023-12-20", "end": "2023-12-29"},
            headers=headers,
        )
    ).json()

    for result in body["results"]:
        if result["unavailable_reason"] is not None:
            assert result["value"] is None


async def test_an_inverted_window_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")])

    response = await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/analysis-runs",
        json={"start": "2023-12-29", "end": "2023-01-03"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_date_range"


@pytest.mark.parametrize("confidence", [0.4, 1.0, 1.5])
async def test_an_invalid_confidence_is_rejected(api, confidence):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")], refresh=False)

    response = await _run(api, headers, portfolio_id, confidence=confidence)

    assert response.status_code == 422


# --- Benchmark ---------------------------------------------------------------


async def test_a_benchmark_produces_comparison_metrics(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(
        api,
        headers,
        [("AAPL", "20", "50"), ("MSFT", "10", "100")],
        benchmark="SPY",
    )

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())

    assert metrics["benchmark_beta"]["unavailable_reason"] is None, metrics["benchmark_beta"]
    assert Decimal(metrics["benchmark_beta"]["value"]) > 0
    assert metrics["benchmark_correlation"]["value"] is not None
    assert metrics["tracking_error"]["metadata"]["annualized"] is True
    assert metrics["benchmark_beta"]["metadata"]["benchmark_symbol"] == "SPY"


async def test_a_portfolio_holding_only_its_benchmark_has_beta_near_one(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300")], benchmark="SPY")

    metrics = _metrics((await _run(api, headers, portfolio_id)).json())

    assert float(metrics["benchmark_beta"]["value"]) == pytest.approx(1.0, abs=1e-6)


async def test_the_request_can_override_the_portfolio_benchmark(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("AAPL", "20", "50")], benchmark="SPY")

    body = (await _run(api, headers, portfolio_id, benchmark_symbol="TLT")).json()

    assert body["parameters"]["benchmark_symbol"] == "TLT"
    assert _metrics(body)["benchmark_beta"]["metadata"]["benchmark_symbol"] == "TLT"


async def test_an_unknown_benchmark_is_reported_not_fatal(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])

    body = (await _run(api, headers, portfolio_id, benchmark_symbol="ZZZZ")).json()
    metrics = _metrics(body)

    assert metrics["benchmark_beta"]["value"] is None
    assert metrics["benchmark_beta"]["unavailable_reason"]
    # The rest of the analysis still succeeded.
    assert metrics["volatility_annualized"]["value"] is not None


# --- Persistence and access --------------------------------------------------


async def test_a_run_can_be_read_back(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])
    created = (await _run(api, headers, portfolio_id)).json()

    fetched = await api.get(f"/api/v1/analysis-runs/{created['id']}", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert len(fetched.json()["results"]) == len(created["results"])


async def test_runs_are_listed_newest_first(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, [("SPY", "10", "300"), ("AAPL", "20", "50")])
    await _run(api, headers, portfolio_id)
    await _run(api, headers, portfolio_id)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]
    assert body["items"][0]["result_count"] > 0


async def test_another_user_cannot_read_a_run(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, [("SPY", "10", "300"), ("AAPL", "20", "50")])
    created = (await _run(api, owner, portfolio_id)).json()

    response = await api.get(f"/api/v1/analysis-runs/{created['id']}", headers=intruder)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "analysis_run_not_found"


async def test_another_user_cannot_run_an_analysis(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, [("SPY", "10", "300")], refresh=False)

    response = await _run(api, intruder, portfolio_id)

    assert response.status_code == 404


async def test_an_unknown_run_returns_404(api):
    headers = await _signed_in_user(api)

    response = await api.get(f"/api/v1/analysis-runs/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_analysis_requires_authentication(api):
    response = await api.post(f"{PORTFOLIOS}/{uuid.uuid4()}/analysis-runs", json={})

    assert response.status_code == 401
