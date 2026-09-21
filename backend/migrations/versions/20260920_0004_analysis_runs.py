"""Analysis runs and risk results.

Creates `analysis_runs` and `risk_results`.

* A run stores its resolved parameters and `data_as_of`, so any stored number can
  be explained and reproduced later.
* A `risk_results` row holds either a value or a reason it is unavailable, never
  a zero standing in for missing data. The check constraint enforces that.
* Deleting a portfolio cascades to its runs and their results.

Revision ID: 0004_analysis_runs
Revises: 0003_price_bars
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_analysis_runs"
down_revision: str | None = "0003_price_bars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("analysis_type", sa.String(length=32), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_runs_portfolio_id_created_at",
        "analysis_runs",
        ["portfolio_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "risk_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_run_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("result_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "value IS NOT NULL OR unavailable_reason IS NOT NULL",
            name="ck_risk_results_value_or_reason",
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_results_analysis_run_id"), "risk_results", ["analysis_run_id"], unique=False
    )
    op.create_index(
        "ix_risk_results_run_metric", "risk_results", ["analysis_run_id", "metric"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_risk_results_run_metric", table_name="risk_results")
    op.drop_index(op.f("ix_risk_results_analysis_run_id"), table_name="risk_results")
    op.drop_table("risk_results")
    op.drop_index("ix_analysis_runs_portfolio_id_created_at", table_name="analysis_runs")
    op.drop_table("analysis_runs")
