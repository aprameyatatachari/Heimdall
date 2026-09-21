"""Baseline revision.

Establishes the Alembic version table on an empty database. Heimdall's schema is
introduced by the migrations that follow, starting with the authentication and
portfolio domain.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema objects yet; this revision only marks the starting point."""


def downgrade() -> None:
    """Nothing to undo."""
