"""Authentication and core portfolio domain.

Creates `users`, `refresh_tokens`, `assets`, `portfolios`, and `positions`.

Cascade behaviour, chosen deliberately:

* `portfolios.user_id` and `refresh_tokens.user_id` cascade on delete. Neither
  record has meaning without its owner.
* `positions.portfolio_id` cascades on delete. A holding has no meaning without
  its portfolio.
* `positions.asset_id` uses RESTRICT. Assets are shared reference data, so a
  referenced asset must not be removable.

Revision ID: 0002_auth_portfolio_domain
Revises: 0001_baseline
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_portfolio_domain"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("currency = upper(currency)", name="ck_assets_currency_upper"),
        sa.CheckConstraint("length(currency) = 3", name="ck_assets_currency_length"),
        sa.CheckConstraint("length(symbol) > 0", name="ck_assets_symbol_not_empty"),
        sa.CheckConstraint("symbol = upper(symbol)", name="ck_assets_symbol_upper"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(
        "ix_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "portfolios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("benchmark_symbol", sa.String(length=24), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_currency = upper(base_currency)", name="ck_portfolios_currency_upper"
        ),
        sa.CheckConstraint("length(base_currency) = 3", name="ck_portfolios_currency_length"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_portfolios_name_not_blank"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_portfolios_user_id_name"),
    )
    op.create_index(op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_cost", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("average_cost >= 0", name="ck_positions_average_cost_non_negative"),
        sa.CheckConstraint("quantity > 0", name="ck_positions_quantity_positive"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "asset_id", name="uq_positions_portfolio_id_asset_id"),
    )
    op.create_index(op.f("ix_positions_asset_id"), "positions", ["asset_id"], unique=False)
    op.create_index(op.f("ix_positions_portfolio_id"), "positions", ["portfolio_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_positions_portfolio_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_asset_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_portfolios_user_id"), table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_index("ix_users_email_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("assets")
