"""Stress-test runs.

Creates `stress_test_runs`. The complete scenario definition and the
position-level breakdown are stored as JSONB, so a stored result stays
explainable even after the scenario catalogue changes.

Deleting a portfolio cascades to its stress tests.

Revision ID: 0005_stress_test_runs
Revises: 0004_analysis_runs
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_stress_test_runs"
down_revision: str | None = "0004_analysis_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stress_test_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("scenario_type", sa.String(length=16), nullable=False),
        sa.Column("scenario_name", sa.String(length=120), nullable=False),
        sa.Column("scenario_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("starting_value", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("ending_value", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("total_impact", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("total_impact_percent", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        "ix_stress_test_runs_portfolio_id_created_at",
        "stress_test_runs",
        ["portfolio_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stress_test_runs_portfolio_id_created_at", table_name="stress_test_runs")
    op.drop_table("stress_test_runs")
