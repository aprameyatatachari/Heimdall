"""Integration tests for report generation and download."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
# Wide enough to cover the stress scenarios these tests exercise, including
# the 2020 COVID window.
WINDOW = {"start": "2019-01-02", "end": "2023-12-29"}
HOLDINGS = [("AAPL", "100", "50"), ("MSFT", "50", "100"), ("JNJ", "50", "100")]


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"rep-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio(api, headers, *, refresh: bool = True, benchmark: str | None = "SPY") -> str:
    payload: dict[str, object] = {"name": f"Portfolio {uuid.uuid4().hex[:8]}"}
    if benchmark:
        payload["benchmark_symbol"] = benchmark

    created = await api.post(PORTFOLIOS, json=payload, headers=headers)
    assert created.status_code == 201, created.text
    portfolio_id = str(created.json()["id"])

    for symbol, quantity, cost in HOLDINGS:
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


async def _report(api, headers, portfolio_id, **body):
    return await api.post(f"{PORTFOLIOS}/{portfolio_id}/reports", json=body, headers=headers)


# --- Generation --------------------------------------------------------------


async def test_a_report_is_generated_and_downloadable(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    created = await _report(api, headers, portfolio_id)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "succeeded"
    assert body["format"] == "pdf"
    assert body["size_bytes"] > 3000
    assert body["download_url"]
    assert body["error_message"] is None

    download = await api.get(body["download_url"], headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF-")
    assert "attachment" in download.headers["content-disposition"]


async def test_a_report_records_the_inputs_it_was_built_from(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    body = (await _report(api, headers, portfolio_id)).json()

    inputs = body["inputs"]
    assert inputs["portfolio_id"] == portfolio_id
    assert inputs["analysis_run_id"] == body["analysis_run_id"]
    assert inputs["analysis_parameters"]["start"]
    assert inputs["data_as_of"] == "2023-12-29"


async def test_a_report_reuses_the_latest_analysis_run(api):
    """Reproducible: the report reflects stored analysis, not fresh numbers."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    run = (
        await api.post(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", json=WINDOW, headers=headers)
    ).json()

    body = (await _report(api, headers, portfolio_id)).json()

    assert body["analysis_run_id"] == run["id"]


async def test_a_report_can_target_an_explicit_analysis_run(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    first = (
        await api.post(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", json=WINDOW, headers=headers)
    ).json()
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", json=WINDOW, headers=headers)

    body = (await _report(api, headers, portfolio_id, analysis_run_id=first["id"])).json()

    assert body["analysis_run_id"] == first["id"]


async def test_two_reports_from_the_same_run_have_the_same_inputs(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    run = (
        await api.post(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", json=WINDOW, headers=headers)
    ).json()

    first = (await _report(api, headers, portfolio_id, analysis_run_id=run["id"])).json()
    second = (await _report(api, headers, portfolio_id, analysis_run_id=run["id"])).json()

    assert first["inputs"] == second["inputs"]
    assert first["id"] != second["id"]


async def test_an_analysis_run_is_computed_when_none_exists(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    body = (await _report(api, headers, portfolio_id)).json()

    assert body["analysis_run_id"] is not None
    runs = await api.get(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", headers=headers)
    assert runs.json()["total"] == 1


async def test_a_report_includes_stress_tests_when_they_exist(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    stress = await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/stress-tests",
        json={"scenario_key": "covid_19_crash_2020"},
        headers=headers,
    )
    assert stress.status_code == 201, stress.text

    body = (await _report(api, headers, portfolio_id, include_stress_tests=True)).json()

    assert body["status"] == "succeeded"
    assert body["inputs"]["include_stress_tests"] is True


async def test_a_report_includes_signals_when_they_exist(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)

    body = (await _report(api, headers, portfolio_id, include_signals=True)).json()

    assert body["status"] == "succeeded"
    assert body["inputs"]["include_signals"] is True


async def test_sections_can_be_excluded(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    body = (
        await _report(api, headers, portfolio_id, include_stress_tests=False, include_signals=False)
    ).json()

    assert body["status"] == "succeeded"
    assert body["inputs"]["include_stress_tests"] is False
    assert body["inputs"]["include_signals"] is False


async def test_a_custom_title_is_used(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    body = (await _report(api, headers, portfolio_id, title="Quarterly review")).json()

    assert body["title"] == "Quarterly review"


async def test_the_filename_is_safe_and_dated(api):
    headers = await _signed_in_user(api)
    created = await api.post(PORTFOLIOS, json={"name": "My / Risky: Portfolio"}, headers=headers)
    portfolio_id = str(created.json()["id"])
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/positions",
        json={"symbol": "AAPL", "quantity": "10", "average_cost": "50"},
        headers=headers,
    )
    await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh", params=WINDOW, headers=headers
    )

    body = (await _report(api, headers, portfolio_id)).json()

    assert body["filename"].startswith("heimdall-risk-report-")
    assert body["filename"].endswith(".pdf")
    assert "/" not in body["filename"]
    assert ":" not in body["filename"]


async def test_a_portfolio_with_no_market_data_cannot_be_reported(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, refresh=False)

    response = await _report(api, headers, portfolio_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_market_data"


async def test_a_failed_report_leaves_analysis_data_intact(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    run = (
        await api.post(f"{PORTFOLIOS}/{portfolio_id}/analysis-runs", json=WINDOW, headers=headers)
    ).json()

    # An analysis run from another portfolio is refused.
    other = await _portfolio(api, headers)
    response = await _report(api, headers, other, analysis_run_id=run["id"])

    assert response.status_code == 404
    still_there = await api.get(f"/api/v1/analysis-runs/{run['id']}", headers=headers)
    assert still_there.status_code == 200


async def test_an_unknown_analysis_run_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _report(api, headers, portfolio_id, analysis_run_id=str(uuid.uuid4()))

    assert response.status_code == 404


async def test_an_unknown_field_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, refresh=False)

    response = await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/reports",
        json={"nonsense": True},
        headers=headers,
    )

    assert response.status_code == 422


# --- Listing and access ------------------------------------------------------


async def test_reports_are_listed_newest_first(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _report(api, headers, portfolio_id)
    await _report(api, headers, portfolio_id)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/reports", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]


async def test_report_metadata_can_be_read_back(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    created = (await _report(api, headers, portfolio_id)).json()

    fetched = await api.get(f"/api/v1/reports/{created['id']}", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["size_bytes"] == created["size_bytes"]


async def test_the_listing_does_not_contain_the_rendered_bytes(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _report(api, headers, portfolio_id)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/reports", headers=headers)

    assert "content" not in response.text
    assert "%PDF" not in response.text


async def test_another_user_cannot_read_a_report(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner)
    created = (await _report(api, owner, portfolio_id)).json()

    metadata = await api.get(f"/api/v1/reports/{created['id']}", headers=intruder)
    download = await api.get(created["download_url"], headers=intruder)

    assert metadata.status_code == 404
    assert download.status_code == 404
    assert metadata.json()["error"]["code"] == "report_not_found"


async def test_another_user_cannot_generate_a_report_for_a_portfolio(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, refresh=False)

    response = await _report(api, intruder, portfolio_id)

    assert response.status_code == 404


async def test_downloading_requires_authentication(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    created = (await _report(api, headers, portfolio_id)).json()

    response = await api.get(created["download_url"])

    assert response.status_code == 401


async def test_an_unknown_report_returns_404(api):
    headers = await _signed_in_user(api)

    response = await api.get(f"/api/v1/reports/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_a_downloaded_report_is_not_cached_by_shared_caches(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    created = (await _report(api, headers, portfolio_id)).json()

    response = await api.get(created["download_url"], headers=headers)

    assert "no-store" in response.headers["cache-control"]
