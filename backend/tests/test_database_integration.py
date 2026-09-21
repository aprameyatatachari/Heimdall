"""Integration tests that require a live PostgreSQL database.

Run them with::

    docker compose up -d db
    RUN_INTEGRATION_TESTS=1 uv run pytest -m integration

They are skipped by default so that the default test run stays hermetic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import check_database_connection, create_engine
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]


async def test_engine_connects_to_postgres(settings):
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


async def test_readiness_check_reports_true_against_a_live_database(settings):
    engine = create_engine(settings)
    try:
        assert await check_database_connection(engine) is True
    finally:
        await engine.dispose()


async def test_readiness_check_reports_false_for_an_unreachable_database(settings):
    unreachable = settings.model_copy(
        update={
            "database_url": "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/heimdall",
            "db_connect_timeout_seconds": 1,
        }
    )
    engine = create_engine(unreachable)
    try:
        assert await check_database_connection(engine) is False
    finally:
        await engine.dispose()


async def test_migrations_applied_the_alembic_version_table(settings):
    """`alembic upgrade head` must have been run against the test database."""
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT to_regclass('public.alembic_version')"))
            assert result.scalar_one() is not None, (
                "Run `uv run alembic upgrade head` against the test database first."
            )
    finally:
        await engine.dispose()
