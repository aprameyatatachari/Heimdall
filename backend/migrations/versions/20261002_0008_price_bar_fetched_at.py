"""When each price bar was last fetched.

Adds `price_bars.fetched_at`.

`created_at` records when a bar was first written and never changes. A live
provider revises today's bar many times while a market is open, so "when was
this price last read from the provider" is a different fact from "when did this
row first appear" — and it is the one a reader needs in order to judge how old a
price is.

Existing rows are backfilled from `created_at`, which is the only honest value:
nothing has re-fetched them since.

Revision ID: 0008_price_bar_fetched_at
Revises: 0007_reports
Create Date: 2026-10-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_price_bar_fetched_at"
down_revision: str | None = "0007_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable first, so the backfill can run before the constraint exists.
    op.add_column(
        "price_bars",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE price_bars SET fetched_at = created_at")
    op.alter_column(
        "price_bars",
        "fetched_at",
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.drop_column("price_bars", "fetched_at")
