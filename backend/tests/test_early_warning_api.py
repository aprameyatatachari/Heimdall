"""Integration tests for the Early Warning System endpoints and lifecycle."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
DATA_WINDOW = {"start": "2022-01-03", "end": "2023-12-29"}
CRON_SECRET = "test-cron-secret-that-is-long-enough-to-be-realistic"


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"ews-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
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


async def _rule(api, headers, portfolio_id, rule_type: str, **overrides):
    payload: dict[str, object] = {"rule_type": rule_type}
    payload.update(overrides)
    return await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules", json=payload, headers=headers)


async def _monitor(api, headers, portfolio_id):
    return await api.post(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)


async def _signals(api, headers, portfolio_id, **params):
    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/signals", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# A single concentrated holding, so position concentration always fires.
SINGLE = [("AAPL", "100", "50")]


# --- Rule catalogue ----------------------------------------------------------


async def test_the_rule_type_catalogue_lists_every_rule(api):
    headers = await _signed_in_user(api)

    response = await api.get("/api/v1/alert-rule-types", headers=headers)

    assert response.status_code == 200
    body = response.json()
    types = {item["rule_type"] for item in body["items"]}
    assert types == {
        "position_concentration",
        "sector_concentration",
        "volatility_increase",
        "portfolio_drawdown",
        "var_threshold",
        "correlation_increase",
        "stress_loss",
        "stale_market_data",
        "missing_data",
    }
    assert body["disclaimer"].startswith("Gjallarhorn Signals identify")


async def test_every_catalogue_entry_documents_its_unit_and_defaults(api):
    headers = await _signed_in_user(api)

    body = (await api.get("/api/v1/alert-rule-types", headers=headers)).json()

    for item in body["items"]:
        assert item["unit"]
        assert item["default_severity_configuration"]
        assert item["default_cooldown_hours"] >= 0
        assert len(item["description"]) > 30


# --- Rule CRUD ---------------------------------------------------------------


async def test_a_rule_can_be_created_with_documented_defaults(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await _rule(api, headers, portfolio_id, "position_concentration")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rule_type"] == "position_concentration"
    assert body["enabled"] is True
    assert body["severity_configuration"] == {"elevated": 0.20, "high": 0.30, "critical": 0.40}


async def test_a_rule_accepts_custom_thresholds(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await _rule(
        api,
        headers,
        portfolio_id,
        "position_concentration",
        severity_configuration={"high": 0.5},
        cooldown_hours=6,
    )

    assert response.status_code == 201
    assert response.json()["severity_configuration"] == {"high": 0.5}
    assert response.json()["cooldown_hours"] == 6


async def test_out_of_order_thresholds_are_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await _rule(
        api,
        headers,
        portfolio_id,
        "position_concentration",
        severity_configuration={"elevated": 0.40, "high": 0.20},
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "invalid_rule_configuration"
    assert any("severity_configuration" in (detail["field"] or "") for detail in body["details"])


async def test_unknown_rule_parameters_are_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await _rule(
        api, headers, portfolio_id, "position_concentration", parameters={"nonsense": 1}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_rule_configuration"


async def test_an_invalid_window_combination_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await _rule(
        api,
        headers,
        portfolio_id,
        "volatility_increase",
        parameters={"recent_window_days": 100, "baseline_window_days": 50},
    )

    assert response.status_code == 422


async def test_a_second_rule_of_the_same_type_conflicts(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    await _rule(api, headers, portfolio_id, "position_concentration")

    response = await _rule(api, headers, portfolio_id, "position_concentration")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "alert_rule_exists"


async def test_a_rule_can_be_disabled_and_re_enabled(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    rule_id = (await _rule(api, headers, portfolio_id, "position_concentration")).json()["id"]

    disabled = await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"enabled": False},
        headers=headers,
    )
    enabled = await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"enabled": True},
        headers=headers,
    )

    assert disabled.json()["enabled"] is False
    assert enabled.json()["enabled"] is True


async def test_updating_thresholds_revalidates_their_order(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    rule_id = (await _rule(api, headers, portfolio_id, "position_concentration")).json()["id"]

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 0.9, "high": 0.1}},
        headers=headers,
    )

    assert response.status_code == 422


async def test_an_empty_update_is_rejected(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    rule_id = (await _rule(api, headers, portfolio_id, "position_concentration")).json()["id"]

    response = await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}", json={}, headers=headers
    )

    assert response.status_code == 422


async def test_a_rule_can_be_deleted(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    rule_id = (await _rule(api, headers, portfolio_id, "position_concentration")).json()["id"]

    deleted = await api.delete(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}", headers=headers
    )
    listed = await api.get(f"{PORTFOLIOS}/{portfolio_id}/alert-rules", headers=headers)

    assert deleted.status_code == 204
    assert listed.json() == []


async def test_a_rule_cannot_be_reached_through_another_portfolio(api):
    headers = await _signed_in_user(api)
    first = await _portfolio(api, headers, SINGLE, refresh=False)
    second = await _portfolio(api, headers, SINGLE, refresh=False)
    rule_id = (await _rule(api, headers, first, "position_concentration")).json()["id"]

    response = await api.get(f"{PORTFOLIOS}/{second}/alert-rules/{rule_id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "alert_rule_not_found"


# --- Default provisioning ----------------------------------------------------


async def test_defaults_provision_every_rule_type(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)

    assert response.status_code == 200, response.text
    rules = response.json()
    assert len(rules) == 9
    assert all(rule["enabled"] for rule in rules)


async def test_a_new_portfolio_has_no_rules_until_defaults_are_requested(api):
    """The documented policy: provisioning is explicit, not automatic."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/alert-rules", headers=headers)

    assert response.json() == []


async def test_provisioning_defaults_twice_is_idempotent(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)

    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    second = await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)

    assert second.status_code == 200
    assert len(second.json()) == 9


async def test_provisioning_leaves_customized_rules_alone(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    await _rule(
        api,
        headers,
        portfolio_id,
        "position_concentration",
        severity_configuration={"high": 0.9},
        enabled=False,
    )

    rules = (
        await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    ).json()

    custom = next(rule for rule in rules if rule["rule_type"] == "position_concentration")
    assert custom["severity_configuration"] == {"high": 0.9}
    assert custom["enabled"] is False


async def test_restore_resets_customized_rules_to_defaults(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE, refresh=False)
    await _rule(
        api,
        headers,
        portfolio_id,
        "position_concentration",
        severity_configuration={"high": 0.9},
        enabled=False,
    )

    rules = (
        await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults",
            params={"restore": "true"},
            headers=headers,
        )
    ).json()

    restored = next(rule for rule in rules if rule["rule_type"] == "position_concentration")
    assert restored["severity_configuration"] == {
        "elevated": 0.20,
        "high": 0.30,
        "critical": 0.40,
    }
    assert restored["enabled"] is True


# --- Monitoring runs ---------------------------------------------------------


async def test_a_monitoring_run_creates_signals(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    response = await _monitor(api, headers, portfolio_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["trigger_type"] == "manual"
    assert body["rules_evaluated"] == 1
    assert body["signals_created"] == 1
    assert body["rules_failed"] == 0
    assert body["data_as_of"] == "2023-12-29"


async def test_a_run_without_rules_is_skipped(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)

    response = await _monitor(api, headers, portfolio_id)

    assert response.status_code == 201
    assert response.json()["status"] == "skipped"
    assert "No enabled alert rules" in response.json()["error_summary"]


async def test_a_disabled_rule_is_not_evaluated(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration", enabled=False)

    response = await _monitor(api, headers, portfolio_id)

    assert response.json()["status"] == "skipped"


async def test_a_signal_carries_everything_needed_to_explain_it(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)

    signals = await _signals(api, headers, portfolio_id)
    signal = signals["items"][0]

    assert signal["signal_type"] == "position_concentration"
    assert signal["severity"] == "critical"
    assert signal["severity_icon"]
    assert signal["status"] == "active"
    assert signal["title"] == "High position concentration"
    assert "AAPL represents 100.0%" in signal["explanation"]
    assert signal["suggested_action"] == "Review position concentration"
    assert Decimal(signal["observed_value"]) == Decimal("1")
    assert Decimal(signal["threshold_value"]) == Decimal("0.4")
    assert signal["unit"] == "percent_of_portfolio_value"
    assert signal["analysis_period"]
    assert signal["data_as_of"] == "2023-12-29"
    assert signal["context"]["affected_symbol"] == "AAPL"
    assert signal["disclaimer"].startswith("Gjallarhorn Signals identify")


async def test_a_run_reports_its_per_rule_outcome(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)

    body = (await _monitor(api, headers, portfolio_id)).json()

    statuses = {item["rule_type"]: item["status"] for item in body["rule_results"]}
    assert statuses["position_concentration"] == "evaluated"
    # A single holding cannot have a pairwise correlation.
    assert statuses["correlation_increase"] == "skipped"
    assert all(item["error"] is None for item in body["rule_results"])


async def test_a_skipped_rule_does_not_fail_the_run(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)

    body = (await _monitor(api, headers, portfolio_id)).json()

    assert body["status"] == "succeeded"
    assert body["rules_failed"] == 0
    assert body["signals_created"] > 0


async def test_runs_are_listed_newest_first(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    await _monitor(api, headers, portfolio_id)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)

    assert response.json()["total"] == 2
    items = response.json()["items"]
    assert items[0]["started_at"] >= items[1]["started_at"]


async def test_a_run_can_be_read_back(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    created = (await _monitor(api, headers, portfolio_id)).json()

    fetched = await api.get(f"/api/v1/monitoring-runs/{created['id']}", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


# --- Deduplication and lifecycle ---------------------------------------------


async def test_a_repeated_run_updates_rather_than_duplicates(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    first = (await _monitor(api, headers, portfolio_id)).json()
    second = (await _monitor(api, headers, portfolio_id)).json()

    assert first["signals_created"] == 1
    assert second["signals_created"] == 0
    assert second["signals_updated"] == 1
    assert (await _signals(api, headers, portfolio_id))["total"] == 1


async def test_three_runs_still_leave_one_signal(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    for _ in range(3):
        await _monitor(api, headers, portfolio_id)

    assert (await _signals(api, headers, portfolio_id))["total"] == 1


async def test_severity_increases_update_the_same_signal(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    rule_id = (
        await _rule(
            api,
            headers,
            portfolio_id,
            "position_concentration",
            severity_configuration={"elevated": 0.5},
        )
    ).json()["id"]
    first = await _monitor(api, headers, portfolio_id)
    assert first.status_code == 201
    original = (await _signals(api, headers, portfolio_id))["items"][0]
    assert original["severity"] == "elevated"

    # Tightening the ladder makes the same condition critical.
    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 0.2, "high": 0.4, "critical": 0.8}},
        headers=headers,
    )
    await _monitor(api, headers, portfolio_id)

    signals = await _signals(api, headers, portfolio_id)
    assert signals["total"] == 1
    assert signals["items"][0]["id"] == original["id"]
    assert signals["items"][0]["severity"] == "critical"


async def test_a_severity_decrease_keeps_the_signal_open(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    rule_id = (
        await _rule(
            api,
            headers,
            portfolio_id,
            "position_concentration",
            severity_configuration={"elevated": 0.2, "high": 0.4, "critical": 0.8},
        )
    ).json()["id"]
    await _monitor(api, headers, portfolio_id)

    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 0.5}},
        headers=headers,
    )
    await _monitor(api, headers, portfolio_id)

    signals = await _signals(api, headers, portfolio_id)
    assert signals["total"] == 1
    assert signals["items"][0]["severity"] == "elevated"
    assert signals["items"][0]["status"] in {"active", "acknowledged"}
    assert signals["items"][0]["resolved_at"] is None


async def test_a_cleared_condition_resolves_its_signal(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    rule_id = (
        await _rule(
            api,
            headers,
            portfolio_id,
            "position_concentration",
            severity_configuration={"elevated": 0.5},
        )
    ).json()["id"]
    await _monitor(api, headers, portfolio_id)

    # Raising the threshold above 100% clears the condition.
    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 1.0, "high": 2.0}},
        headers=headers,
    )
    # 100% still crosses a 1.0 threshold, so push it beyond reach.
    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 2.0}},
        headers=headers,
    )
    run = (await _monitor(api, headers, portfolio_id)).json()

    assert run["signals_resolved"] == 1
    signals = await _signals(api, headers, portfolio_id, signal_status="resolved")
    assert signals["total"] == 1
    assert signals["items"][0]["resolved_at"] is not None


async def test_a_resolved_condition_reappears_as_a_new_occurrence(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    rule_id = (
        await _rule(
            api,
            headers,
            portfolio_id,
            "position_concentration",
            severity_configuration={"elevated": 0.5},
        )
    ).json()["id"]
    await _monitor(api, headers, portfolio_id)
    original = (await _signals(api, headers, portfolio_id))["items"][0]

    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 2.0}},
        headers=headers,
    )
    await _monitor(api, headers, portfolio_id)

    await api.patch(
        f"{PORTFOLIOS}/{portfolio_id}/alert-rules/{rule_id}",
        json={"severity_configuration": {"elevated": 0.5}},
        headers=headers,
    )
    await _monitor(api, headers, portfolio_id)

    all_signals = await _signals(api, headers, portfolio_id)
    assert all_signals["total"] == 2
    active = await _signals(api, headers, portfolio_id, signal_status="active")
    assert active["total"] == 1
    assert active["items"][0]["id"] != original["id"]


async def test_a_rule_that_cannot_be_evaluated_resolves_nothing(api):
    """Not being able to check a condition is not evidence that it cleared."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _rule(api, headers, portfolio_id, "correlation_increase")
    first = (await _monitor(api, headers, portfolio_id)).json()

    second = (await _monitor(api, headers, portfolio_id)).json()

    assert first["signals_created"] == 1
    assert second["signals_resolved"] == 0
    assert (await _signals(api, headers, portfolio_id, signal_status="active"))["total"] == 1


# --- Acknowledge and dismiss -------------------------------------------------


async def test_acknowledging_a_signal_does_not_resolve_it(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]

    response = await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None
    assert body["resolved_at"] is None


async def test_an_acknowledged_signal_stays_open_across_runs(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]
    await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    run = (await _monitor(api, headers, portfolio_id)).json()

    assert run["signals_updated"] == 1
    assert run["signals_resolved"] == 0
    assert (await _signals(api, headers, portfolio_id))["total"] == 1


async def test_acknowledging_twice_is_harmless(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]

    first = await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)
    second = await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["acknowledged_at"] == second.json()["acknowledged_at"]


async def test_dismissing_a_signal_hides_it_from_the_default_view(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]

    response = await api.post(f"/api/v1/signals/{signal_id}/dismiss", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    active = await _signals(api, headers, portfolio_id, signal_status="active")
    assert active["total"] == 0


async def test_a_dismissed_condition_can_signal_again(api):
    """Dismissing is not a way to silence a rule permanently."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]
    await api.post(f"/api/v1/signals/{signal_id}/dismiss", headers=headers)

    run = (await _monitor(api, headers, portfolio_id)).json()

    assert run["signals_created"] == 1
    assert (await _signals(api, headers, portfolio_id))["total"] == 2


async def test_a_dismissed_signal_cannot_be_acknowledged(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]
    await api.post(f"/api/v1/signals/{signal_id}/dismiss", headers=headers)

    response = await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "signal_not_open"


async def test_there_is_no_endpoint_to_resolve_a_signal_manually(api):
    """Only the rule engine resolves a signal."""
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]

    response = await api.post(f"/api/v1/signals/{signal_id}/resolve", headers=headers)

    assert response.status_code in {404, 405}


# --- Audit trail -------------------------------------------------------------


async def test_the_audit_trail_records_the_lifecycle(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]
    await _monitor(api, headers, portfolio_id)
    await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    response = await api.get(f"/api/v1/signals/{signal_id}", headers=headers)

    events = [event["event_type"] for event in response.json()["events"]]
    assert events[0] == "created"
    assert "reobserved" in events
    assert events[-1] == "acknowledged"


# --- Filtering and pagination ------------------------------------------------


async def test_signals_can_be_filtered_by_severity(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await _monitor(api, headers, portfolio_id)

    critical = await _signals(api, headers, portfolio_id, severity="critical")
    elevated = await _signals(api, headers, portfolio_id, severity="elevated")

    assert all(item["severity"] == "critical" for item in critical["items"])
    assert all(item["severity"] == "elevated" for item in elevated["items"])


async def test_signals_can_be_filtered_by_type(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await _monitor(api, headers, portfolio_id)

    filtered = await _signals(api, headers, portfolio_id, signal_type="position_concentration")

    assert filtered["total"] >= 1
    assert all(item["signal_type"] == "position_concentration" for item in filtered["items"])


async def test_signals_can_be_filtered_by_acknowledgement(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await _monitor(api, headers, portfolio_id)
    signal_id = (await _signals(api, headers, portfolio_id))["items"][0]["id"]
    await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=headers)

    acknowledged = await _signals(api, headers, portfolio_id, acknowledged="true")
    unacknowledged = await _signals(api, headers, portfolio_id, acknowledged="false")

    assert acknowledged["total"] == 1
    assert unacknowledged["total"] >= 1
    assert all(item["acknowledged_at"] is not None for item in acknowledged["items"])


async def test_signals_paginate_with_a_stable_order(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await _monitor(api, headers, portfolio_id)

    first = await _signals(api, headers, portfolio_id, limit=1, offset=0)
    second = await _signals(api, headers, portfolio_id, limit=1, offset=1)

    assert first["total"] == second["total"] >= 2
    assert first["items"][0]["id"] != second["items"][0]["id"]


async def test_the_severity_summary_counts_open_signals(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await api.post(f"{PORTFOLIOS}/{portfolio_id}/alert-rules/defaults", headers=headers)
    await _monitor(api, headers, portfolio_id)

    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/signals/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_open"] == sum(body["by_severity"].values())
    assert body["total_open"] >= 1


async def test_the_cross_portfolio_listing_returns_only_the_callers_signals(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, SINGLE)
    await _rule(api, owner, portfolio_id, "position_concentration")
    await _monitor(api, owner, portfolio_id)

    theirs = await api.get("/api/v1/signals", headers=intruder)
    mine = await api.get("/api/v1/signals", headers=owner)

    assert theirs.json()["total"] == 0
    assert mine.json()["total"] == 1


# --- Authorization -----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path_suffix"),
    [
        ("get", "/alert-rules"),
        ("post", "/alert-rules/defaults"),
        ("post", "/monitoring-runs"),
        ("get", "/monitoring-runs"),
        ("get", "/signals"),
        ("get", "/signals/summary"),
    ],
)
async def test_another_user_cannot_reach_a_portfolios_ews_data(api, method, path_suffix):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, SINGLE, refresh=False)

    response = await getattr(api, method)(
        f"{PORTFOLIOS}/{portfolio_id}{path_suffix}", headers=intruder
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "portfolio_not_found"


async def test_another_user_cannot_acknowledge_a_signal(api):
    owner = await _signed_in_user(api)
    intruder = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner, SINGLE)
    await _rule(api, owner, portfolio_id, "position_concentration")
    await _monitor(api, owner, portfolio_id)
    signal_id = (await _signals(api, owner, portfolio_id))["items"][0]["id"]

    response = await api.post(f"/api/v1/signals/{signal_id}/acknowledge", headers=intruder)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "signal_not_found"


async def test_ews_endpoints_require_authentication(api):
    portfolio_id = uuid.uuid4()

    assert (await api.get(f"{PORTFOLIOS}/{portfolio_id}/alert-rules")).status_code == 401
    assert (await api.post(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs")).status_code == 401
    assert (await api.get("/api/v1/signals")).status_code == 401


# --- Scheduled monitoring ----------------------------------------------------


async def test_the_scheduled_endpoint_rejects_a_missing_secret(api):
    response = await api.post("/api/v1/internal/monitoring/run", json={})

    assert response.status_code in {401, 503}


async def test_the_scheduled_endpoint_rejects_a_wrong_secret(api_with_cron_secret):
    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": "not-the-secret"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "scheduler_not_authorized"


async def test_the_scheduled_endpoint_accepts_the_configured_secret(api_with_cron_secret):
    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    assert response.status_code == 200, response.text
    assert "evaluation_period" in response.json()


async def test_the_scheduled_endpoint_accepts_a_bearer_token(api_with_cron_secret):
    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"Authorization": f"Bearer {CRON_SECRET}"},
    )

    assert response.status_code == 200


async def test_a_scheduled_run_evaluates_eligible_portfolios(api, api_with_cron_secret):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    body = response.json()
    assert body["portfolios_processed"] >= 1
    assert body["signals_created"] >= 1
    assert any(str(item["portfolio_id"]) == portfolio_id for item in body["results"])


async def test_a_scheduled_run_is_idempotent_for_its_period(api, api_with_cron_secret):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    first = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": CRON_SECRET},
    )
    second = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    assert first.json()["signals_created"] >= 1
    # The repeat returns the stored run rather than evaluating again.
    assert second.json()["signals_created"] == 0
    runs = await api.get(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)
    scheduled = [item for item in runs.json()["items"] if item["trigger_type"] == "scheduled"]
    assert len(scheduled) == 1


async def test_a_scheduled_run_is_bounded_and_resumable(api, api_with_cron_secret):
    headers = await _signed_in_user(api)
    for _ in range(3):
        portfolio_id = await _portfolio(api, headers, SINGLE)
        await _rule(api, headers, portfolio_id, "position_concentration")

    first = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={"batch_size": 2},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    body = first.json()
    assert len(body["results"]) == 2
    assert body["next_cursor"] is not None

    second = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={"batch_size": 2, "cursor": body["next_cursor"]},
        headers={"X-Cron-Secret": CRON_SECRET},
    )
    assert len(second.json()["results"]) >= 1


async def test_a_scheduled_response_carries_no_portfolio_detail(api, api_with_cron_secret):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, SINGLE)
    await _rule(api, headers, portfolio_id, "position_concentration")

    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    text = response.text
    assert "AAPL" not in text
    assert "Portfolio " not in text
    assert "explanation" not in text
    assert set(response.json()["results"][0]) == {
        "portfolio_id",
        "status",
        "signals_created",
        "signals_updated",
        "signals_resolved",
    }
