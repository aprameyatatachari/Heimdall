"""Database engine, session management, and the declarative base.

Pooling is deliberately different per environment:

* Long-running processes (local, Docker, CI) use a small `QueuePool`.
* Serverless invocations use `NullPool`, because a Vercel Function may be frozen
  or discarded at any moment and must not hold a PostgreSQL connection open.

Migrations are never run from here. They run as a controlled release step.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model.

    `eager_defaults` makes SQLAlchemy fetch server-generated values (such as the
    `created_at` and `updated_at` timestamps) with RETURNING as part of the
    INSERT or UPDATE. Without it, reading one of those attributes after a write
    would trigger a lazy refresh, which is not available in async code.
    """

    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - SQLAlchemy mapper option


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(settings: Settings) -> dict[str, Any]:
    """Build engine keyword arguments appropriate for the environment."""
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "future": True,
        "pool_pre_ping": True,
        "connect_args": {
            "timeout": settings.db_connect_timeout_seconds,
            # Server-side statement caching interacts badly with connection
            # poolers such as PgBouncer in transaction mode.
            "statement_cache_size": 0,
        },
    }

    if settings.serverless:
        from sqlalchemy.pool import NullPool

        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_timeout"] = settings.db_pool_timeout_seconds
        kwargs["pool_recycle"] = 1800

    return kwargs


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create a new async engine. Callers own its lifecycle."""
    resolved = settings or get_settings()
    return create_async_engine(str(resolved.database_url), **_engine_kwargs(resolved))


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency providing one session, and one transaction, per request.

    The transaction commits when the request handler returns normally and rolls
    back when it raises. Services therefore only need to `flush()`, and a failed
    request can never leave a partial write behind.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection(engine: AsyncEngine | None = None) -> bool:
    """Return True when a trivial query succeeds against the database."""
    target = engine or get_engine()
    try:
        async with target.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def dispose_engine() -> None:
    """Dispose the process-wide engine and reset the cached factory."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
