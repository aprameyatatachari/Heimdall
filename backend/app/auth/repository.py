"""Persistence for users and refresh tokens."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken, User


class UserRepository:
    """Queries and writes for the `users` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return a user by primary key."""
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Return a user by normalized email address."""
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """True when the email address is already registered."""
        result = await self._session.execute(select(User.id).where(User.email == email))
        return result.first() is not None

    def add(self, user: User) -> User:
        """Stage a new user for insertion."""
        self._session.add(user)
        return user


class RefreshTokenRepository:
    """Queries and writes for the `refresh_tokens` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Return a refresh token row by its stored digest."""
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    def add(self, token: RefreshToken) -> RefreshToken:
        """Stage a new refresh token for insertion."""
        self._session.add(token)
        return token

    async def revoke(self, token: RefreshToken, *, at: datetime) -> None:
        """Mark a single token as revoked."""
        token.revoked_at = at

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, at: datetime) -> int:
        """Revoke every active token of a user. Returns the number revoked.

        Used when a rotated token is replayed, which suggests theft.
        """
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def delete_expired(self, *, before: datetime) -> int:
        """Delete tokens that expired before the given instant."""
        result = await self._session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < before)
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)
