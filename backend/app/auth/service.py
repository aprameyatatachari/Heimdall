"""Authentication use cases: registration, login, refresh, logout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken, User
from app.auth.repository import RefreshTokenRepository, UserRepository
from app.auth.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    normalize_email,
    verify_password,
)
from app.common.clock import Clock
from app.common.errors import AuthenticationError, ConflictError
from app.common.logging import get_logger
from app.config import Settings

logger = get_logger(__name__)

# One generic message for every credential failure, so the API cannot be used to
# discover which addresses are registered.
INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."


class EmailAlreadyRegisteredError(ConflictError):
    """The email address already belongs to an account."""

    code = "email_already_registered"
    message = "An account with this email address already exists."


class InvalidCredentialsError(AuthenticationError):
    """Login failed."""

    code = "invalid_credentials"
    message = INVALID_CREDENTIALS_MESSAGE


class InvalidRefreshTokenError(AuthenticationError):
    """The refresh token is missing, unknown, expired, revoked, or replayed."""

    code = "invalid_refresh_token"
    message = "The session has expired. Please sign in again."


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """An access token plus the raw refresh token to place in a cookie."""

    user: User
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime


class AuthService:
    """Orchestrates account and session lifecycles."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        hasher: PasswordHasher,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._session = session
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._hasher = hasher
        self._settings = settings
        self._clock = clock

    # --- Accounts ------------------------------------------------------------

    async def register(self, *, email: str, password: str) -> IssuedSession:
        """Create an account and sign the new user in."""
        normalized = normalize_email(email)

        if await self._users.email_exists(normalized):
            raise EmailAlreadyRegisteredError()

        user = User(
            email=normalized,
            password_hash=hash_password(password, self._hasher),
        )
        self._users.add(user)

        try:
            await self._flush()
        except IntegrityError as exc:
            # A concurrent registration won the race.
            raise EmailAlreadyRegisteredError() from exc

        logger.info("user_registered", user_id=str(user.id))
        return await self._issue_session(user)

    async def authenticate(self, *, email: str, password: str) -> IssuedSession:
        """Verify credentials and issue a session."""
        normalized = normalize_email(email)
        user = await self._users.get_by_email(normalized)

        if user is None:
            # Spend comparable time on an unknown address so response timing does
            # not reveal whether the account exists.
            self._hasher.hash(password)
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash, self._hasher):
            logger.info("login_failed", user_id=str(user.id))
            raise InvalidCredentialsError()

        # Transparently upgrade a hash produced with weaker parameters.
        if needs_rehash(user.password_hash, self._hasher):
            user.password_hash = hash_password(password, self._hasher)

        logger.info("login_succeeded", user_id=str(user.id))
        return await self._issue_session(user)

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        """Return a user by id."""
        return await self._users.get_by_id(user_id)

    # --- Sessions ------------------------------------------------------------

    async def refresh(self, raw_refresh_token: str | None) -> IssuedSession:
        """Rotate a refresh token and issue a new access token.

        Reuse of an already-rotated token revokes every active token of that
        user: the most likely explanation is that a stolen token is in play.
        """
        if not raw_refresh_token:
            raise InvalidRefreshTokenError()

        now = self._clock.now()
        stored = await self._refresh_tokens.get_by_hash(hash_refresh_token(raw_refresh_token))

        if stored is None:
            raise InvalidRefreshTokenError()

        if stored.replaced_by_id is not None or stored.revoked_at is not None:
            revoked = await self._refresh_tokens.revoke_all_for_user(stored.user_id, at=now)
            await self._flush()
            logger.warning(
                "refresh_token_reuse_detected",
                user_id=str(stored.user_id),
                tokens_revoked=revoked,
            )
            raise InvalidRefreshTokenError()

        if not stored.is_usable(now=now):
            raise InvalidRefreshTokenError()

        user = await self._users.get_by_id(stored.user_id)
        if user is None:
            raise InvalidRefreshTokenError()

        session = await self._issue_session(user)

        stored.revoked_at = now
        replacement = await self._refresh_tokens.get_by_hash(
            hash_refresh_token(session.refresh_token)
        )
        if replacement is not None:
            stored.replaced_by_id = replacement.id
        await self._flush()

        logger.info("session_refreshed", user_id=str(user.id))
        return session

    async def logout(self, raw_refresh_token: str | None) -> bool:
        """Revoke the presented refresh token.

        Logout is idempotent: an unknown or already-revoked token still returns
        success, so a client can always clear its own state.
        """
        if not raw_refresh_token:
            return False

        stored = await self._refresh_tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if stored is None or stored.revoked_at is not None:
            return False

        stored.revoked_at = self._clock.now()
        await self._flush()
        logger.info("session_revoked", user_id=str(stored.user_id))
        return True

    # --- Internals -----------------------------------------------------------

    async def _issue_session(self, user: User) -> IssuedSession:
        """Create an access token and a stored refresh token for a user."""
        now = self._clock.now()

        access_token, access_expires_at = create_access_token(
            user_id=user.id,
            secret=self._settings.auth_secret.get_secret_value(),
            ttl_minutes=self._settings.access_token_ttl_minutes,
            now=now,
        )

        raw_refresh = generate_refresh_token()
        refresh_expires_at = now + timedelta(days=self._settings.refresh_token_ttl_days)
        self._refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_refresh_token(raw_refresh),
                expires_at=refresh_expires_at,
            )
        )
        await self._flush()

        return IssuedSession(
            user=user,
            access_token=access_token,
            access_token_expires_at=access_expires_at,
            refresh_token=raw_refresh,
            refresh_token_expires_at=refresh_expires_at,
        )

    async def _flush(self) -> None:
        """Flush pending changes so database constraints are checked now."""
        await self._session.flush()


__all__ = [
    "AuthService",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InvalidRefreshTokenError",
    "IssuedSession",
]
