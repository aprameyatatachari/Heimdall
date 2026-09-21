"""Tests for the centralized error envelope."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.common.errors import (
    INTERNAL_ERROR_MESSAGE,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.common.logging import REQUEST_ID_HEADER
from app.main import create_app


class _Payload(BaseModel):
    count: int


@pytest.fixture
def error_app(app: FastAPI) -> FastAPI:
    """The real application plus routes that raise each error class."""

    @app.get("/_test/not-found")
    async def _not_found() -> None:
        raise NotFoundError("Portfolio not found.", code="portfolio_not_found")

    @app.get("/_test/conflict")
    async def _conflict() -> None:
        raise ConflictError()

    @app.get("/_test/domain-validation")
    async def _domain_validation() -> None:
        raise ValidationError("Quantity must be positive.", code="invalid_quantity")

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("database password is hunter2")

    @app.post("/_test/echo")
    async def _echo(payload: _Payload) -> dict[str, int]:
        return {"count": payload.count}

    return app


@pytest.fixture
async def error_client(error_app: FastAPI):
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def test_domain_error_uses_the_standard_envelope(error_client):
    response = await error_client.get("/_test/not-found")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "portfolio_not_found"
    assert error["message"] == "Portfolio not found."
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]


async def test_error_class_defaults_are_used_when_no_message_is_given(error_client):
    response = await error_client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_domain_validation_error_reports_422(error_client):
    response = await error_client.get("/_test/domain-validation")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_quantity"


async def test_request_validation_errors_include_field_details(error_client):
    response = await error_client.post("/_test/echo", json={"count": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "count"


async def test_unknown_route_uses_the_standard_envelope(error_client):
    response = await error_client.get("/_test/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_unhandled_exception_does_not_leak_internals(error_client):
    response = await error_client.get("/_test/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == INTERNAL_ERROR_MESSAGE
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


async def test_oversized_request_body_is_rejected(settings):
    small_limit_app = create_app(settings.model_copy(update={"max_request_body_bytes": 64}))

    transport = ASGITransport(app=small_limit_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        response = await http_client.post(
            "/health",
            content=b"x" * 5000,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
