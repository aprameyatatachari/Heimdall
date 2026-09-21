"""Shared pytest fixtures.

Two kinds of test run here:

* **Unit tests** exercise pure functions and application wiring with no database.
  They always run.
* **Integration tests** run against a real PostgreSQL database. They are marked
  `integration` and are skipped unless `RUN_INTEGRATION_TESTS=1` is set, because
  Heimdall does not substitute SQLite for PostgreSQL.

Each integration test runs inside a transaction that is rolled back afterwards,
so tests never see each other's rows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.config import Environment, Settings, reset_settings_cache
from app.database import create_engine, get_db_session
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://heimdall:heimdall@localhost:5433/heimdall_test",
)

# Tests must never inherit a developer's real environment.
_TEST_ENV = {
    "ENVIRONMENT": Environment.TEST.value,
    "DEBUG": "false",
    "LOG_LEVEL": "WARNING",
    "LOG_FORMAT": "console",
    "DATABASE_URL": TEST_DATABASE_URL,
    "CORS_ALLOW_ORIGINS": "http://localhost:5173",
    # Rate limiting is exercised by its own tests, not by every other one.
    "RATE_LIMIT_ENABLED": "false",
}


def postgres_available() -> bool:
    """True when the test suite is allowed to reach a live PostgreSQL server."""
    return os.environ.get("RUN_INTEGRATION_TESTS", "").lower() in {"1", "true", "yes"}


requires_postgres = pytest.mark.skipif(
    not postgres_available(),
    reason="Set RUN_INTEGRATION_TESTS=1 and provide a PostgreSQL database to run this test.",
)


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Apply a deterministic environment and reset the settings cache."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def settings() -> Settings:
    """Settings built from the isolated test environment.

    Argon2 work factors are reduced to the library minimum so that a suite with
    many logins stays fast. Production values live in `.env.example`.
    """
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment=Environment.TEST,
        database_url=TEST_DATABASE_URL,
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        rate_limit_enabled=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """A fresh application instance with no database override."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound directly to the ASGI app (no network, no server)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


# --- Database-backed fixtures ------------------------------------------------


@pytest.fixture(scope="session")
def _migrated_database() -> None:
    """Apply migrations to the test database once per session.

    Alembic runs in a subprocess so its own `asyncio.run` cannot collide with the
    event loop pytest-asyncio manages for the tests.
    """
    if not postgres_available():
        pytest.skip("integration tests disabled")

    environment = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "ENVIRONMENT": Environment.TEST.value,
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture
async def db_connection(
    _migrated_database: None,
    settings: Settings,
) -> AsyncIterator[AsyncConnection]:
    """An open connection inside a transaction that is always rolled back."""
    engine = create_engine(settings)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """A session joined to the rolled-back test transaction."""
    factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    async with factory() as session:
        yield session


@pytest.fixture
async def api_with_cron_secret(
    settings: Settings,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """A client whose app has a scheduler secret configured.

    The scheduled monitoring endpoint refuses to run without one, so testing its
    happy path needs an app built with the secret set.
    """
    configured = settings.model_copy(
        update={"cron_secret": SecretStr("test-cron-secret-that-is-long-enough-to-be-realistic")}
    )
    application = create_app(configured)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _override

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client

    application.dependency_overrides.clear()


@pytest.fixture
async def api(
    settings: Settings,
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose requests share the test's rolled-back session."""
    application = create_app(settings)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _override

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client

    application.dependency_overrides.clear()
