"""Persist replay, LPG, sensitivity, briefing, comments, and monitoring records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0009"
down_revision: str | None = "20260721_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phase8_replay_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_phase8_replay_case_time", "phase8_replay_runs", ["case_id", "completed_at"])
    op.create_table(
        "phase8_lpg_plans",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("replay_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_phase8_lpg_replay", "phase8_lpg_plans", ["replay_run_id"])
    op.create_table(
        "phase8_sensitivity_runs",
        sa.Column("sensitivity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_phase8_sensitivity_plan", "phase8_sensitivity_runs", ["plan_id"])
    op.create_table(
        "phase8_exports",
        sa.Column("export_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_phase8_export_plan_time", "phase8_exports", ["plan_id", "created_at"])
    op.create_table(
        "phase8_plan_comments",
        sa.Column("comment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_phase8_comment_plan_time", "phase8_plan_comments", ["plan_id", "created_at"])
    op.create_table(
        "phase8_plan_monitoring",
        sa.Column("monitoring_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_phase8_monitor_plan_time", "phase8_plan_monitoring", ["plan_id", "observed_at"])
    op.execute(
        """CREATE FUNCTION reject_phase8_record_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'phase 8 replay and decision records are immutable'; END;
        $$ LANGUAGE plpgsql"""
    )
    for table in (
        "phase8_replay_runs",
        "phase8_lpg_plans",
        "phase8_sensitivity_runs",
        "phase8_exports",
        "phase8_plan_comments",
        "phase8_plan_monitoring",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_phase8_record_mutation()"
        )


def downgrade() -> None:
    tables = (
        "phase8_plan_monitoring",
        "phase8_plan_comments",
        "phase8_exports",
        "phase8_sensitivity_runs",
        "phase8_lpg_plans",
        "phase8_replay_runs",
    )
    for table in tables:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_phase8_record_mutation()")
    op.drop_index("ix_phase8_monitor_plan_time", table_name="phase8_plan_monitoring")
    op.drop_table("phase8_plan_monitoring")
    op.drop_index("ix_phase8_comment_plan_time", table_name="phase8_plan_comments")
    op.drop_table("phase8_plan_comments")
    op.drop_index("ix_phase8_export_plan_time", table_name="phase8_exports")
    op.drop_table("phase8_exports")
    op.drop_index("ix_phase8_sensitivity_plan", table_name="phase8_sensitivity_runs")
    op.drop_table("phase8_sensitivity_runs")
    op.drop_index("ix_phase8_lpg_replay", table_name="phase8_lpg_plans")
    op.drop_table("phase8_lpg_plans")
    op.drop_index("ix_phase8_replay_case_time", table_name="phase8_replay_runs")
    op.drop_table("phase8_replay_runs")
