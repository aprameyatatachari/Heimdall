"""Authentication ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import TimestampMixin, UUIDPrimaryKey
from app.database import Base

if TYPE_CHECKING:
    from app.portfolios.models import Portfolio

# Emails are stored lower-cased and trimmed, so a plain unique index is enough.
EMAIL_MAX_LENGTH = 320


class User(TimestampMixin, Base):
    """A registered account."""

    __tablename__ = "users"

    id: Mapped[UUIDPrimaryKey]
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), nullable=False, unique=True)
    # Argon2id hash. Never serialized into an API response.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    portfolios: Mapped[list[Portfolio]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Reject a stored address that is not already normalized.
        Index("ix_users_email_lower", text("lower(email)"), unique=True),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id}>"


class RefreshToken(Base):
    """A refresh token issued to a user session.

    Only the SHA-256 digest of the token is stored: a database leak does not hand
    an attacker usable session credentials. Rotation replaces one row with
    another and links them through `replaced_by_id` for audit.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[UUIDPrimaryKey]
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    def is_usable(self, *, now: datetime) -> bool:
        """True when the token has neither expired nor been revoked."""
        return self.revoked_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id}>"
