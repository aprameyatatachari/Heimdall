"""Authentication API schemas.

No schema here exposes `password_hash` or any other internal secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, normalize_email
from app.common.schemas import ApiModel

PASSWORD_DESCRIPTION = (
    f"Between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters. "
    "Stored only as an Argon2id hash."
)


class RegisterRequest(BaseModel):
    """Registration payload."""

    model_config = {"extra": "forbid"}

    email: EmailStr
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=PASSWORD_DESCRIPTION,
    )

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not consist solely of whitespace.")
        return value


class LoginRequest(BaseModel):
    """Login payload."""

    model_config = {"extra": "forbid"}

    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class UserResponse(ApiModel):
    """A user, as returned by the API."""

    id: uuid.UUID
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """An issued access token.

    The refresh token is never in the body. It is set as an HttpOnly cookie so
    that browser JavaScript cannot read it.
    """

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - an OAuth scheme name, not a secret
    expires_at: datetime = Field(description="Access-token expiry, in UTC.")
    user: UserResponse


class LogoutResponse(BaseModel):
    """Result of revoking the current session."""

    revoked: bool = True
