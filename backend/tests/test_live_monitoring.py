"""Integration tests for live monitoring: refresh-then-monitor and the scheduler."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import FixedClock
from app.config import Settings
from app.early_warning.live import LiveMonitor, build_live_monitor
from app.early_warning.router import _evaluation_period
from app.early_warning.scheduler import MonitoringScheduler
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
PORTFOLIOS = "/api/v1/portfolios"
DATA_WINDOW = {"start": "2022-01-03", "end": "2023-12-29"}
CRON_SECRET = "test-cron-secret-that-is-long-enough-to-be-realistic"
SINGLE = [("AAPL", "100", "50")]

# The last day the committed fixtures reach, a Friday. 15:00 UTC is 10:00 in New
# York, inside the session; 03:00 UTC is the middle of the night there.
MARKET_OPEN = datetime(2023, 12, 29, 15, 0, tzinfo=UTC)
MARKET_CLOSED = datetime(2023, 12, 29, 3, 0, tzinfo=UTC)


async def _signed_in_user(api) -> dict[str, str]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"live-{uuid.uuid4().hex[:12]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _portfolio(api, headers, *, rule: bool = True) -> str:
    created = await api.post(
        PORTFOLIOS, json={"name": f"Portfolio {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert created.status_code == 201, created.text
    portfolio_id = str(created.json()["id"])

    for symbol, quantity, cost in SINGLE:
        added = await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/positions",
            json={"symbol": symbol, "quantity": quantity, "average_cost": cost},
            headers=headers,
        )
        assert added.status_code == 201, added.text

    if rule:
        made = await api.post(
            f"{PORTFOLIOS}/{portfolio_id}/alert-rules",
            json={"rule_type": "position_concentration"},
            headers=headers,
        )
        assert made.status_code == 201, made.text

    return portfolio_id


async def _refresh(api, headers, portfolio_id, **params):
    return await api.post(
        f"{PORTFOLIOS}/{portfolio_id}/market-data/refresh",
        params={**DATA_WINDOW, **params},
        headers=headers,
    )


async def _runs(api, headers, portfolio_id) -> list[dict]:
    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _open_signals(api, headers, portfolio_id) -> list[dict]:
    response = await api.get(f"{PORTFOLIOS}/{portfolio_id}/signals", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _factory(session: AsyncSession):
    """A session factory that hands every caller the test's own session."""

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield session

    return _scope


def _scheduler(settings: Settings, session: AsyncSession, moment: datetime, build_monitor=None):
    clock = FixedClock(moment)
    return MonitoringScheduler(
        settings=settings,
        clock=clock,
        session_factory=_factory(session),  # type: ignore[arg-type]
        build_monitor=build_monitor,
    )


# --- Monitoring after a refresh ------------------------------------------------


async def test_a_refresh_can_monitor_against_the_prices_it_just_read(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _refresh(api, headers, portfolio_id, monitor="true")

    assert response.status_code == 200, response.text
    monitoring = response.json()["monitoring"]
    assert monitoring["status"] == "succeeded"
    assert monitoring["rules_evaluated"] == 1
    assert monitoring["signals_created"] == 1
    assert len(await _open_signals(api, headers, portfolio_id)) == 1


async def test_a_run_that_followed_a_refresh_says_so(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    await _refresh(api, headers, portfolio_id, monitor="true")

    runs = await _runs(api, headers, portfolio_id)
    assert [run["trigger_type"] for run in runs] == ["market_data_refresh"]


async def test_a_refresh_does_not_monitor_unless_asked(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    response = await _refresh(api, headers, portfolio_id)

    assert response.json()["monitoring"] is None
    assert await _runs(api, headers, portfolio_id) == []


async def test_a_portfolio_without_rules_is_not_monitored_on_refresh(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, rule=False)

    response = await _refresh(api, headers, portfolio_id, monitor="true")

    assert response.status_code == 200, response.text
    assert response.json()["monitoring"] is None
    # No row is written for a check that had nothing to check.
    assert await _runs(api, headers, portfolio_id) == []


async def test_repeated_live_checks_do_not_fill_the_audit_trail(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    for _ in range(4):
        await _refresh(api, headers, portfolio_id, monitor="true")

    signals = await _open_signals(api, headers, portfolio_id)
    assert len(signals) == 1
    detail = await api.get(f"/api/v1/signals/{signals[0]['id']}", headers=headers)
    # One entry for the condition appearing, and none for it still being there.
    assert [event["event_type"] for event in detail.json()["events"]] == ["created"]


async def test_a_live_check_still_brings_the_signal_up_to_date(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)

    first = await _refresh(api, headers, portfolio_id, monitor="true")
    second = await _refresh(api, headers, portfolio_id, monitor="true")

    assert second.json()["monitoring"]["signals_created"] == 0
    assert second.json()["monitoring"]["signals_updated"] == 1
    signal = (await _open_signals(api, headers, portfolio_id))[0]
    assert signal["monitoring_run_id"] == second.json()["monitoring"]["run_id"]
    assert signal["monitoring_run_id"] != first.json()["monitoring"]["run_id"]


async def test_a_manual_run_still_records_that_the_condition_persists(api):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _refresh(api, headers, portfolio_id, monitor="true")

    await api.post(f"{PORTFOLIOS}/{portfolio_id}/monitoring-runs", headers=headers)

    signal = (await _open_signals(api, headers, portfolio_id))[0]
    detail = await api.get(f"/api/v1/signals/{signal['id']}", headers=headers)
    assert [event["event_type"] for event in detail.json()["events"]] == ["created", "reobserved"]


async def test_another_user_cannot_monitor_a_portfolio_through_refresh(api):
    owner = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, owner)
    stranger = await _signed_in_user(api)

    response = await _refresh(api, stranger, portfolio_id, monitor="true")

    assert response.status_code == 404
    assert await _runs(api, owner, portfolio_id) == []


# --- The scheduled endpoint ---------------------------------------------------


def test_the_default_evaluation_period_is_one_utc_day():
    assert _evaluation_period(datetime(2026, 10, 5, 14, 37, tzinfo=UTC), None) == "2026-10-05"


def test_an_interval_period_starts_where_the_interval_does():
    moment = datetime(2026, 10, 5, 14, 37, tzinfo=UTC)

    assert _evaluation_period(moment, 15) == "2026-10-05T14:30"
    assert _evaluation_period(moment, 60) == "2026-10-05T14:00"
    # Two calls inside one interval share a period; the next interval does not.
    assert _evaluation_period(moment.replace(minute=44), 15) == "2026-10-05T14:30"
    assert _evaluation_period(moment.replace(minute=45), 15) == "2026-10-05T14:45"


async def test_a_scheduled_run_can_refresh_prices_first(api, api_with_cron_secret):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _refresh(api, headers, portfolio_id)

    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={"refresh_prices": True, "interval_minutes": 15},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "T" in body["evaluation_period"]
    assert any(str(item["portfolio_id"]) == portfolio_id for item in body["results"])
    assert len(await _open_signals(api, headers, portfolio_id)) == 1


async def test_an_interval_shorter_than_five_minutes_is_refused(api_with_cron_secret):
    response = await api_with_cron_secret.post(
        "/api/v1/internal/monitoring/run",
        json={"interval_minutes": 1},
        headers={"X-Cron-Secret": CRON_SECRET},
    )

    assert response.status_code == 422


# --- The in-process scheduler -------------------------------------------------


async def test_a_tick_checks_a_portfolio_whose_market_is_open(api, settings, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _refresh(api, headers, portfolio_id)

    summary = await _scheduler(settings, db_session, MARKET_OPEN).tick()

    assert summary.checked >= 1
    assert summary.signals_created >= 1
    runs = await _runs(api, headers, portfolio_id)
    assert [run["trigger_type"] for run in runs] == ["scheduled"]
    assert len(await _open_signals(api, headers, portfolio_id)) == 1


async def test_a_tick_leaves_a_closed_market_alone(api, settings, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _refresh(api, headers, portfolio_id)

    summary = await _scheduler(settings, db_session, MARKET_CLOSED).tick()

    assert summary.checked == 0
    assert summary.market_closed >= 1
    assert await _runs(api, headers, portfolio_id) == []


async def test_a_tick_ignores_a_portfolio_with_no_enabled_rule(api, settings, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers, rule=False)
    await _refresh(api, headers, portfolio_id)

    await _scheduler(settings, db_session, MARKET_OPEN).tick()

    assert await _runs(api, headers, portfolio_id) == []


async def test_one_failing_portfolio_does_not_stop_the_others(api, settings, db_session):
    headers = await _signed_in_user(api)
    first = await _portfolio(api, headers)
    second = await _portfolio(api, headers)
    await _refresh(api, headers, first)
    broken = uuid.UUID(min(first, second))
    clock = FixedClock(MARKET_OPEN)
    # The scheduler rolls a failed portfolio back. In production that undoes one
    # portfolio's work; here every request shares this session, so what the test
    # set up has to be committed first or the rollback would take it too.
    await db_session.commit()

    class _Failing(LiveMonitor):
        async def check(self, portfolio_id, **kwargs):
            if portfolio_id == broken:
                raise RuntimeError("the provider is down")
            return await super().check(portfolio_id, **kwargs)

    def build(session: AsyncSession) -> LiveMonitor:
        real = build_live_monitor(session, settings=settings, clock=clock)
        return _Failing(
            positions=real._positions,
            market_data=real._market_data,
            early_warning=real._early_warning,
        )

    summary = await _scheduler(settings, db_session, MARKET_OPEN, build).tick()

    assert summary.failed >= 1
    assert summary.checked >= 1
    survivor = max(first, second)
    assert len(await _runs(api, headers, survivor)) == 1


async def test_repeated_ticks_keep_one_signal_and_a_short_trail(api, settings, db_session):
    headers = await _signed_in_user(api)
    portfolio_id = await _portfolio(api, headers)
    await _refresh(api, headers, portfolio_id)
    scheduler = _scheduler(settings, db_session, MARKET_OPEN)

    for _ in range(3):
        await scheduler.tick()

    signals = await _open_signals(api, headers, portfolio_id)
    assert len(signals) == 1
    detail = await api.get(f"/api/v1/signals/{signals[0]['id']}", headers=headers)
    assert [event["event_type"] for event in detail.json()["events"]] == ["created"]
    assert len(await _runs(api, headers, portfolio_id)) == 3
