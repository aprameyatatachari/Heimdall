"""Daily price bars.

Creates `price_bars`, the local cache of daily market data.

* Uniqueness on (asset_id, date, source) is what makes ingestion idempotent:
  re-fetching a window updates the existing rows instead of duplicating them.
* `source` records provenance, so fixture-seeded data is never mistaken for
  live data.
* Deleting an asset cascades to its bars: cached prices for an instrument nobody
  references are worthless.

Revision ID: 0003_price_bars
Revises: 
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_price_bars"
down_revision: str | None = "0002_auth_portfolio_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_bars",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("high", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("low", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("close", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("volume", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("adjusted_close > 0", name="ck_price_bars_adjusted_positive"),
        sa.CheckConstraint("close > 0", name="ck_price_bars_close_positive"),
        sa.CheckConstraint("currency = upper(currency)", name="ck_price_bars_currency_upper"),
        sa.CheckConstraint("length(currency) = 3", name="ck_price_bars_currency_length"),
        sa.CheckConstraint(
            "volume IS NULL OR volume >= 0", name="ck_price_bars_volume_non_negative"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "date", "source", name="uq_price_bars_asset_date_source"),
    )
    op.create_index("ix_price_bars_asset_id_date", "price_bars", ["asset_id", "date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_price_bars_asset_id_date", table_name="price_bars")
    op.drop_table("price_bars")
