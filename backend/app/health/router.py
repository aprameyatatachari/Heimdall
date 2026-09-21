"""Liveness and readiness endpoints.

`/health` answers "is the process running?" and must not touch any dependency.
`/ready` answers "can this instance serve traffic?" and verifies the database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import check_database_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: Literal["ok"] = "ok"
    service: str = Field(description="Service name.")
    version: str = Field(description="Application version.")
    environment: str = Field(description="Deployment environment.")
    timestamp: datetime = Field(description="Server time in UTC.")


class DependencyStatus(BaseModel):
    """Status of a single dependency checked during readiness."""

    name: str
    status: Literal["ok", "unavailable"]


class ReadinessResponse(BaseModel):
    """Readiness payload."""

    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyStatus]
    timestamp: datetime


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns successfully whenever the API process is running.",
)
async def health() -> HealthResponse:
    """Report that the process is alive."""
    settings = get_settings()
    return HealthResponse(
        service="heimdall-api",
        version=settings.version,
        environment=str(settings.environment),
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Verifies that required dependencies are reachable. "
        "Returns 503 when the database cannot be queried."
    ),
    responses={503: {"model": ReadinessResponse, "description": "Not ready"}},
)
async def ready(response: Response) -> ReadinessResponse:
    """Report whether this instance can serve traffic."""
    database_ok = await check_database_connection()
    dependencies = [
        DependencyStatus(name="database", status="ok" if database_ok else "unavailable")
    ]

    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if database_ok else "not_ready",
        dependencies=dependencies,
        timestamp=datetime.now(UTC),
    )
