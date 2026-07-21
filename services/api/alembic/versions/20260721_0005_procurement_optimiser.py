"""Persist immutable procurement optimiser requests and plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "procurement_plan_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"]),
        sa.CheckConstraint("request_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_procurement_request_fingerprint"),
        sa.CheckConstraint("lifecycle IN ('COMPLETED','FAILED')", name="ck_procurement_request_lifecycle"),
    )
    op.create_index("ix_procurement_request_run", "procurement_plan_requests", ["run_id", "created_at"])
    op.create_table(
        "procurement_plans",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("solver_status", sa.String(20), nullable=False),
        sa.Column("checker_passed", sa.Boolean(), nullable=False),
        sa.Column("runtime_seconds", sa.Numeric(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["procurement_plan_requests.request_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"]),
        sa.UniqueConstraint("request_id", "profile", name="uq_procurement_request_profile"),
        sa.CheckConstraint("input_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_procurement_input_fingerprint"),
        sa.CheckConstraint("plan_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_procurement_plan_fingerprint"),
        sa.CheckConstraint("runtime_seconds >= 0", name="ck_procurement_runtime"),
        sa.CheckConstraint("checker_passed", name="ck_procurement_checked"),
    )
    op.create_index("ix_procurement_plan_run_profile", "procurement_plans", ["run_id", "profile"])
    op.create_table(
        "procurement_plan_actions",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["procurement_plans.plan_id"]),
    )
    op.create_table(
        "procurement_rejected_options",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["procurement_plans.plan_id"]),
        sa.PrimaryKeyConstraint("plan_id", "option_id"),
    )
    op.execute(
        """
        CREATE FUNCTION reject_procurement_terminal_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'terminal procurement records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("procurement_plan_requests", "procurement_plans", "procurement_plan_actions", "procurement_rejected_options"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_procurement_terminal_mutation()"
        )


def downgrade() -> None:
    for table in ("procurement_rejected_options", "procurement_plan_actions", "procurement_plans", "procurement_plan_requests"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_procurement_terminal_mutation()")
    op.drop_table("procurement_rejected_options")
    op.drop_table("procurement_plan_actions")
    op.drop_index("ix_procurement_plan_run_profile", table_name="procurement_plans")
    op.drop_table("procurement_plans")
    op.drop_index("ix_procurement_request_run", table_name="procurement_plan_requests")
    op.drop_table("procurement_plan_requests")
