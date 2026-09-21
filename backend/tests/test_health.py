"""Tests for the liveness and readiness endpoints."""

from __future__ import annotations

import app.health.router as health_router
from app.common.logging import REQUEST_ID_HEADER


async def test_health_reports_ok_without_touching_the_database(client, monkeypatch):
    """Liveness must not depend on the database being reachable."""

    async def _fail(*_args, **_kwargs):  # pragma: no cover - must never be called
        raise AssertionError("liveness must not query the database")

    monkeypatch.setattr(health_router, "check_database_connection", _fail)

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "heimdall-api"
    assert body["environment"] == "test"
    assert body["version"]
    assert body["timestamp"]


async def test_health_returns_a_request_id_header(client):
    response = await client.get("/health")
    assert response.headers[REQUEST_ID_HEADER]


async def test_health_echoes_a_safe_inbound_request_id(client):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc-123456"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123456"


async def test_health_replaces_an_unsafe_inbound_request_id(client):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "bad id; drop table"})
    assert response.headers[REQUEST_ID_HEADER] != "bad id; drop table"


async def test_ready_returns_200_when_the_database_answers(client, monkeypatch):
    async def _ok(*_args, **_kwargs):
        return True

    monkeypatch.setattr(health_router, "check_database_connection", _ok)

    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"] == [{"name": "database", "status": "ok"}]


async def test_ready_returns_503_when_the_database_is_unreachable(client, monkeypatch):
    async def _down(*_args, **_kwargs):
        return False

    monkeypatch.setattr(health_router, "check_database_connection", _down)

    response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["dependencies"] == [{"name": "database", "status": "unavailable"}]
