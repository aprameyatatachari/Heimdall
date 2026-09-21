"""Password hashing and access-token handling.

Pure functions only: nothing here touches the database or HTTP.

**Chosen scheme.** Short-lived signed access tokens (JWT, HS256) plus opaque
refresh tokens stored as hashes in the database:

* The access token is held by the client in memory and sent as
  `Authorization: Bearer <token>`. It is short-lived, so it needs no server-side
  revocation list.
* The refresh token is a 256-bit random string delivered in an HttpOnly cookie.
  Only its SHA-256 digest is stored, it rotates on every use, and reuse of an
  already-rotated token revokes the whole family.

This combination survives serverless execution (no server-side session state
beyond one database row) and still supports real logout.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

JWT_ALGORITHM: Final = "HS256"
TOKEN_TYPE_ACCESS: Final = "access"  # noqa: S105 - a claim name, not a credential
REFRESH_TOKEN_BYTES: Final = 32

# Argon2 rejects extremely long inputs slowly; cap the password length instead.
MIN_PASSWORD_LENGTH: Final = 12
MAX_PASSWORD_LENGTH: Final = 128


class TokenError(Exception):
    """An access token is missing, malformed, expired, or of the wrong type."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Validated claims of an access token."""

    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


def build_password_hasher(
    *,
    time_cost: int = 3,
    memory_cost_kib: int = 65536,
    parallelism: int = 1,
) -> PasswordHasher:
    """Build an Argon2id hasher with explicit work factors."""
    return PasswordHasher(
        time_cost=time_cost,
        memory_cost=memory_cost_kib,
        parallelism=parallelism,
        hash_len=32,
        salt_len=16,
    )


def hash_password(password: str, hasher: PasswordHasher) -> str:
    """Return an Argon2id hash of the password."""
    return hasher.hash(password)


def verify_password(password: str, password_hash: str, hasher: PasswordHasher) -> bool:
    """Verify a password against its hash, without raising on mismatch."""
    try:
        hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False
    return True


def needs_rehash(password_hash: str, hasher: PasswordHasher) -> bool:
    """True when the stored hash was produced with weaker parameters."""
    try:
        return hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def normalize_email(email: str) -> str:
    """Normalize an email address for storage and lookup."""
    return email.strip().lower()


def create_access_token(
    *,
    user_id: uuid.UUID,
    secret: str,
    ttl_minutes: int,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Create a signed access token. Returns the token and its expiry."""
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": TOKEN_TYPE_ACCESS,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM), expires_at


def decode_access_token(token: str, *, secret: str) -> AccessTokenClaims:
    """Validate a signed access token.

    Raises `TokenError` for every failure mode, so callers cannot accidentally
    distinguish "expired" from "forged" in a client-visible way.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("typ") != TOKEN_TYPE_ACCESS:
        raise TokenError("unexpected token type")

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenError("invalid subject") from exc

    return AccessTokenClaims(
        user_id=user_id,
        issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )


def generate_refresh_token() -> str:
    """Generate an opaque, high-entropy refresh token."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 digest stored in place of the refresh token.

    A plain digest is correct here: the token is already 256 bits of entropy, so
    it is not guessable and needs no key-stretching.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two secrets without leaking their contents through timing."""
    return secrets.compare_digest(left, right)
