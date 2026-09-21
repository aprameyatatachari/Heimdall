"""Generated reports.

Creates `reports`.

* `inputs` stores the identifiers and parameters a report was built from, so the
  same document can be reproduced and audited later.
* `content` holds the rendered bytes. Production runs on serverless functions with
  an ephemeral filesystem, so a file written during one request is gone by the
  next; a column keeps reports durable without adding an object-store dependency.
  See `docs/deployment.md` for the size limit and the migration path.
* `user_id` is stored alongside `portfolio_id` so a report can only ever be read
  by the account that generated it, independently of the portfolio row.
* Deleting a portfolio or a user removes their reports. Deleting the analysis run
  a report was built from leaves the report intact with a null reference, because
  the rendered document remains valid history.

Revision ID: 0007_reports
Revises: 0006_early_warning
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_reports"
down_revision: str | None = "0006_early_warning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("analysis_run_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "inputs",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_portfolio_id_created_at", "reports", ["portfolio_id", "created_at"])
    op.create_index("ix_reports_user_id", "reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_index("ix_reports_portfolio_id_created_at", table_name="reports")
    op.drop_table("reports")
