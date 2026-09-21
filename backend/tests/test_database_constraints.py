"""Integration tests asserting that the database itself protects invariants.

These bypass the service layer on purpose: a bug in application code must not be
able to persist nonsense.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType
from app.auth.models import RefreshToken, User
from app.portfolios.models import Portfolio, Position
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]


async def _user(session: AsyncSession) -> User:
    user = User(
        email=f"constraints-{uuid.uuid4().hex[:12]}@example.com",
        password_hash="$argon2id$fake",
    )
    session.add(user)
    await session.flush()
    return user


async def _asset(session: AsyncSession, symbol: str | None = None) -> Asset:
    asset = Asset(
        symbol=symbol or f"SYM{uuid.uuid4().hex[:6].upper()}",
        currency="USD",
        asset_type=AssetType.UNKNOWN,
    )
    session.add(asset)
    await session.flush()
    return asset


async def _portfolio(session: AsyncSession, user: User, name: str = "Core") -> Portfolio:
    portfolio = Portfolio(user_id=user.id, name=name, base_currency="USD")
    session.add(portfolio)
    await session.flush()
    return portfolio


# --- Users -------------------------------------------------------------------


async def test_duplicate_email_is_rejected(db_session):
    user = await _user(db_session)

    db_session.add(User(email=user.email, password_hash="$argon2id$other"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_email_uniqueness_is_case_insensitive_at_the_database_level(db_session):
    """A bug that skipped normalization still cannot create a duplicate."""
    user = await _user(db_session)

    db_session.add(User(email=user.email.upper(), password_hash="$argon2id$other"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


# --- Portfolios --------------------------------------------------------------


async def test_a_portfolio_requires_an_existing_user(db_session):
    db_session.add(Portfolio(user_id=uuid.uuid4(), name="Orphan", base_currency="USD"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_duplicate_portfolio_name_per_user_is_rejected(db_session):
    user = await _user(db_session)
    await _portfolio(db_session, user, name="Core")

    db_session.add(Portfolio(user_id=user.id, name="Core", base_currency="USD"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_blank_portfolio_name_is_rejected(db_session):
    user = await _user(db_session)

    db_session.add(Portfolio(user_id=user.id, name="   ", base_currency="USD"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_lower_case_base_currency_is_rejected(db_session):
    user = await _user(db_session)

    db_session.add(Portfolio(user_id=user.id, name="Lower", base_currency="usd"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_a_user_cascades_to_portfolios_and_positions(db_session):
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("1"),
            average_cost=Decimal("1"),
        )
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})

    portfolios = await db_session.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    positions = await db_session.execute(
        select(Position).where(Position.portfolio_id == portfolio.id)
    )
    assert portfolios.scalars().all() == []
    assert positions.scalars().all() == []


# --- Positions ---------------------------------------------------------------


async def test_a_portfolio_holds_at_most_one_position_per_asset(db_session):
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)

    for _ in range(2):
        db_session.add(
            Position(
                portfolio_id=portfolio.id,
                asset_id=asset.id,
                quantity=Decimal("1"),
                average_cost=Decimal("1"),
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize("quantity", ["0", "-1"])
async def test_non_positive_quantity_is_rejected(db_session, quantity):
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)

    db_session.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal(quantity),
            average_cost=Decimal("1"),
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_negative_average_cost_is_rejected(db_session):
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)

    db_session.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("1"),
            average_cost=Decimal("-0.01"),
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_an_asset_that_is_held_cannot_be_deleted(db_session):
    """Assets are shared reference data, so deletion is restricted."""
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("1"),
            average_cost=Decimal("1"),
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await db_session.execute(text("DELETE FROM assets WHERE id = :id"), {"id": asset.id})


async def test_quantities_keep_eight_decimal_places(db_session):
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)
    position = Position(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        quantity=Decimal("0.00000001"),
        average_cost=Decimal("12345.6789"),
    )
    db_session.add(position)
    await db_session.flush()
    position_id = position.id
    db_session.expire(position)

    reloaded = await db_session.get(Position, position_id)
    assert reloaded is not None
    assert reloaded.quantity == Decimal("0.00000001")
    assert reloaded.average_cost == Decimal("12345.6789")


async def test_monetary_columns_are_exact_not_floating_point(db_session):
    """Sum a value that binary floating point cannot represent exactly."""
    user = await _user(db_session)
    portfolio = await _portfolio(db_session, user)
    asset = await _asset(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("3"),
            average_cost=Decimal("0.1"),
        )
    )
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT quantity * average_cost FROM positions WHERE portfolio_id = :id"),
        {"id": portfolio.id},
    )
    assert result.scalar_one() == Decimal("0.3")


# --- Assets ------------------------------------------------------------------


async def test_a_duplicate_symbol_is_rejected(db_session):
    asset = await _asset(db_session, symbol="AAPL")

    db_session.add(Asset(symbol=asset.symbol, currency="USD", asset_type=AssetType.UNKNOWN))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_lower_case_symbol_is_rejected(db_session):
    db_session.add(Asset(symbol="aapl", currency="USD", asset_type=AssetType.UNKNOWN))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_malformed_currency_is_rejected(db_session):
    db_session.add(Asset(symbol="TEST1", currency="DOLLAR", asset_type=AssetType.UNKNOWN))

    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.flush()


# --- Refresh tokens ----------------------------------------------------------


async def test_a_duplicate_refresh_token_hash_is_rejected(db_session):
    user = await _user(db_session)
    expiry = datetime.now(UTC) + timedelta(days=1)
    digest = "a" * 64

    db_session.add(RefreshToken(user_id=user.id, token_hash=digest, expires_at=expiry))
    await db_session.flush()
    db_session.add(RefreshToken(user_id=user.id, token_hash=digest, expires_at=expiry))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_a_user_cascades_to_refresh_tokens(db_session):
    user = await _user(db_session)
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})

    remaining = await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    assert remaining.scalars().all() == []
