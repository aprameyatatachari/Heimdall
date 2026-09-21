"""Alembic environment.

The connection URL is taken from application settings, preferring the direct
(non-pooled) URL when one is configured: managed providers such as Neon require
a direct connection for DDL.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the model modules registers every table on Base.metadata.
# Feature models are added here as each phase introduces them.
from app.analytics import models as _analytics_models  # noqa: F401
from app.assets import models as _assets_models  # noqa: F401
from app.auth import models as _auth_models  # noqa: F401
from app.config import get_settings
from app.database import Base
from app.early_warning import models as _early_warning_models  # noqa: F401
from app.market_data import models as _market_data_models  # noqa: F401
from app.portfolios import models as _portfolio_models  # noqa: F401
from app.reports import models as _reports_models  # noqa: F401
from app.stress_testing import models as _stress_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().migration_database_url)


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against a live database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
