"""Persist immutable strategic reserve requests, plans and timelines."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0006"
down_revision: str | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reserve_plan_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("procurement_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"]),
        sa.ForeignKeyConstraint(["procurement_plan_id"], ["procurement_plans.plan_id"]),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_reserve_request_fingerprint"
        ),
        sa.CheckConstraint(
            "lifecycle IN ('COMPLETED','FAILED')", name="ck_reserve_request_lifecycle"
        ),
    )
    op.create_index("ix_reserve_request_run", "reserve_plan_requests", ["run_id", "created_at"])
    op.create_table(
        "reserve_plans",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("procurement_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("solver_status", sa.String(20), nullable=False),
        sa.Column("checker_passed", sa.Boolean(), nullable=False),
        sa.Column("runtime_seconds", sa.Numeric(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["reserve_plan_requests.request_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"]),
        sa.ForeignKeyConstraint(["procurement_plan_id"], ["procurement_plans.plan_id"]),
        sa.UniqueConstraint("request_id", "profile", name="uq_reserve_request_profile"),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_reserve_input_fingerprint"
        ),
        sa.CheckConstraint(
            "plan_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_reserve_plan_fingerprint"
        ),
        sa.CheckConstraint("runtime_seconds >= 0", name="ck_reserve_runtime"),
        sa.CheckConstraint("checker_passed", name="ck_reserve_checked"),
    )
    op.create_table(
        "reserve_plan_actions",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["reserve_plans.plan_id"]),
    )
    op.create_table(
        "reserve_inventory_timeline",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["reserve_plans.plan_id"]),
        sa.PrimaryKeyConstraint("plan_id", "site_id", "effective_at"),
    )
    op.execute(
        """
        CREATE FUNCTION reject_reserve_terminal_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'terminal reserve records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "reserve_plan_requests",
        "reserve_plans",
        "reserve_plan_actions",
        "reserve_inventory_timeline",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_reserve_terminal_mutation()"
        )


def downgrade() -> None:
    for table in (
        "reserve_inventory_timeline",
        "reserve_plan_actions",
        "reserve_plans",
        "reserve_plan_requests",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_reserve_terminal_mutation()")
    op.drop_table("reserve_inventory_timeline")
    op.drop_table("reserve_plan_actions")
    op.drop_table("reserve_plans")
    op.drop_index("ix_reserve_request_run", table_name="reserve_plan_requests")
    op.drop_table("reserve_plan_requests")
