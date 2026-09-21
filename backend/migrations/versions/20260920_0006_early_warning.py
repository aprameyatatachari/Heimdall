"""Gjallarhorn Early Warning System.

Creates `alert_rules`, `monitoring_runs`, `warning_signals`, and `signal_events`.

Design decisions enforced here rather than only in application code:

* `uq_alert_rules_portfolio_rule_type` — one rule per type per portfolio, which is
  what makes default-rule provisioning idempotent.
* `uq_monitoring_runs_portfolio_idempotency` — a scheduled run for the same
  portfolio and evaluation period cannot happen twice, even if the scheduler
  retries or two invocations overlap.
* `uq_warning_signals_open_fingerprint` — a **partial** unique index over
  `(portfolio_id, fingerprint)` where the signal is neither resolved nor
  dismissed. At most one open occurrence of a condition can exist, so two
  concurrent monitoring runs cannot create duplicate signals. Resolved and
  dismissed rows are excluded, which is what allows a condition to reoccur as a
  new occurrence later.
* `signal_events` is append-only by convention; nothing updates or deletes it.

Cascades: deleting a portfolio removes its rules, runs, signals, and their audit
trail. Deleting a rule removes its signals, because a signal cannot be explained
without the rule that produced it. A deleted monitoring run leaves its signals in
place with a null reference, since the signals themselves remain valid history.

Revision ID: 0006_early_warning
Revises: 0005_stress_test_runs
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_early_warning"
down_revision: str | None = "0005_stress_test_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("rule_type", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "parameters",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "severity_configuration",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("cooldown_hours", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("cooldown_hours >= 0", name="ck_alert_rules_cooldown_non_negative"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_alert_rules_name_not_blank"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "rule_type",
            name="uq_alert_rules_portfolio_rule_type",
        ),
    )
    op.create_index(op.f("ix_alert_rules_portfolio_id"), "alert_rules", ["portfolio_id"])

    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column("rules_evaluated", sa.Integer(), nullable=False),
        sa.Column("rules_failed", sa.Integer(), nullable=False),
        sa.Column("signals_created", sa.Integer(), nullable=False),
        sa.Column("signals_updated", sa.Integer(), nullable=False),
        sa.Column("signals_resolved", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "rule_results",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="uq_monitoring_runs_portfolio_idempotency",
        ),
    )
    op.create_index(op.f("ix_monitoring_runs_portfolio_id"), "monitoring_runs", ["portfolio_id"])
    op.create_index(
        "ix_monitoring_runs_portfolio_started",
        "monitoring_runs",
        ["portfolio_id", "started_at"],
    )

    op.create_table(
        "warning_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("alert_rule_id", sa.UUID(), nullable=False),
        sa.Column("monitoring_run_id", sa.UUID(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.String(length=200), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("unit", sa.String(length=48), nullable=False),
        sa.Column("analysis_period", sa.String(length=120), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=True),
        sa.Column(
            "context",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("first_triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["monitoring_run_id"],
            ["monitoring_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_warning_signals_portfolio_id"), "warning_signals", ["portfolio_id"])
    op.create_index(
        op.f("ix_warning_signals_alert_rule_id"),
        "warning_signals",
        ["alert_rule_id"],
    )
    op.create_index(
        "ix_warning_signals_portfolio_status",
        "warning_signals",
        ["portfolio_id", "status"],
    )
    op.create_index(
        "ix_warning_signals_portfolio_created",
        "warning_signals",
        ["portfolio_id", "created_at"],
    )
    # The duplicate-suppression guarantee: at most one OPEN occurrence per condition.
    op.create_index(
        "uq_warning_signals_open_fingerprint",
        "warning_signals",
        ["portfolio_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL AND dismissed_at IS NULL"),
    )

    op.create_table(
        "signal_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("signal_id", sa.UUID(), nullable=False),
        sa.Column("monitoring_run_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_severity", sa.String(length=16), nullable=True),
        sa.Column("to_severity", sa.String(length=16), nullable=True),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("observed_value", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["monitoring_run_id"],
            ["monitoring_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["warning_signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signal_events_signal_id"), "signal_events", ["signal_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_signal_events_signal_id"), table_name="signal_events")
    op.drop_table("signal_events")

    op.drop_index("uq_warning_signals_open_fingerprint", table_name="warning_signals")
    op.drop_index("ix_warning_signals_portfolio_created", table_name="warning_signals")
    op.drop_index("ix_warning_signals_portfolio_status", table_name="warning_signals")
    op.drop_index(op.f("ix_warning_signals_alert_rule_id"), table_name="warning_signals")
    op.drop_index(op.f("ix_warning_signals_portfolio_id"), table_name="warning_signals")
    op.drop_table("warning_signals")

    op.drop_index("ix_monitoring_runs_portfolio_started", table_name="monitoring_runs")
    op.drop_index(op.f("ix_monitoring_runs_portfolio_id"), table_name="monitoring_runs")
    op.drop_table("monitoring_runs")

    op.drop_index(op.f("ix_alert_rules_portfolio_id"), table_name="alert_rules")
    op.drop_table("alert_rules")
