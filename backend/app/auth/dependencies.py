"""Authentication dependencies: service wiring and the current-user guard."""

from __future__ import annotations

from typing import Annotated

from argon2 import PasswordHasher
from fastapi import Depends, Request

from app.auth.models import User
from app.auth.repository import RefreshTokenRepository, UserRepository
from app.auth.security import TokenError, build_password_hasher, decode_access_token
from app.auth.service import AuthService
from app.common.dependencies import ClockDep, SessionDep, SettingsDep
from app.common.errors import AuthenticationError

# Building an Argon2 hasher is cheap, but caching one per configuration avoids
# rebuilding it on every request.
_hasher_cache: dict[tuple[int, int, int], PasswordHasher] = {}


def get_password_hasher(settings: SettingsDep) -> PasswordHasher:
    """Return the Argon2id hasher configured for this deployment."""
    key = (settings.argon2_time_cost, settings.argon2_memory_cost_kib, settings.argon2_parallelism)
    hasher = _hasher_cache.get(key)
    if hasher is None:
        hasher = build_password_hasher(
            time_cost=settings.argon2_time_cost,
            memory_cost_kib=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        )
        _hasher_cache[key] = hasher
    return hasher


HasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]


def get_auth_service(
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
    hasher: HasherDep,
) -> AuthService:
    """Build the authentication service for this request."""
    return AuthService(
        session=session,
        users=UserRepository(session),
        refresh_tokens=RefreshTokenRepository(session),
        hasher=hasher,
        settings=settings,
        clock=clock,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


class MissingAccessTokenError(AuthenticationError):
    """No bearer token was presented."""

    code = "not_authenticated"
    message = "Authentication is required."


class InvalidAccessTokenError(AuthenticationError):
    """The bearer token is malformed, expired, or not trusted."""

    code = "invalid_access_token"
    message = "Your session is no longer valid. Please sign in again."


def _bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise MissingAccessTokenError()
    return token.strip()


async def get_current_user(
    request: Request,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> User:
    """Resolve the authenticated user, or reject the request.

    Every failure mode returns the same generic message: the API never reveals
    whether a token was forged, expired, or belongs to a deleted account.
    """
    token = _bearer_token(request)

    try:
        claims = decode_access_token(token, secret=settings.auth_secret.get_secret_value())
    except TokenError as exc:
        raise InvalidAccessTokenError() from exc

    user = await service.get_user(claims.user_id)
    if user is None:
        raise InvalidAccessTokenError()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
