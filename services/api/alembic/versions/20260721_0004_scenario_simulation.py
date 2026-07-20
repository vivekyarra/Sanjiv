"""Create durable scenario and no-action simulation storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0004"
down_revision: str | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCENARIO_STATES = "'DRAFT','VALIDATED','CONFIRMED','RUNNING','COMPLETED','FAILED','CANCELLED'"
RUN_STATES = "'QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED'"


def upgrade() -> None:
    op.create_table(
        "scenario_candidates",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("twin_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_mode", sa.String(30), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["twin_snapshot_id"], ["twin_snapshots.snapshot_id"]),
        sa.CheckConstraint("scenario_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_scenario_fingerprint"),
        sa.CheckConstraint(f"lifecycle IN ({SCENARIO_STATES})", name="ck_scenario_lifecycle"),
    )
    op.create_index("ix_scenario_candidate_snapshot", "scenario_candidates", ["twin_snapshot_id", "created_at"])

    op.create_table(
        "scenario_validations",
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("scenario_fingerprint", sa.String(64), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_candidates.scenario_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scenario_validation_validated", "scenario_validations", ["valid", "validated_at"])

    op.create_table(
        "confirmed_scenarios",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_fingerprint", sa.String(64), nullable=False),
        sa.Column("twin_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_snapshot_fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmed_by", sa.String(200), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_candidates.scenario_id"]),
        sa.ForeignKeyConstraint(["twin_snapshot_id"], ["twin_snapshots.snapshot_id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"]),
    )
    op.create_index("ix_confirmed_scenario_time", "confirmed_scenarios", ["confirmed_at"])

    op.create_table(
        "simulation_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("simulation_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_ms", sa.Numeric(), nullable=True),
        sa.Column("failure_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["confirmed_scenarios.scenario_id"]),
        sa.CheckConstraint("simulation_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_simulation_fingerprint"),
        sa.CheckConstraint(f"status IN ({RUN_STATES})", name="ck_simulation_status"),
        sa.CheckConstraint("runtime_ms IS NULL OR runtime_ms >= 0", name="ck_simulation_runtime"),
    )
    op.create_index("ix_simulation_run_scenario_time", "simulation_runs", ["scenario_id", "created_at"])
    op.create_index("ix_simulation_run_status", "simulation_runs", ["status", "created_at"])

    op.create_table(
        "simulation_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("simulation_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"]),
    )

    op.create_table(
        "simulation_progress_events",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_simulation_progress_sequence"),
        sa.CheckConstraint(f"status IN ({RUN_STATES})", name="ck_simulation_progress_status"),
    )
    op.create_index("ix_simulation_progress_time", "simulation_progress_events", ["run_id", "occurred_at"])

    op.execute(
        """
        CREATE FUNCTION reject_confirmed_scenario_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'confirmed scenarios are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER confirmed_scenarios_immutable
        BEFORE UPDATE OR DELETE ON confirmed_scenarios
        FOR EACH ROW EXECUTE FUNCTION reject_confirmed_scenario_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_simulation_result_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'simulation results are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER simulation_results_immutable
        BEFORE UPDATE OR DELETE ON simulation_results
        FOR EACH ROW EXECUTE FUNCTION reject_simulation_result_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_terminal_simulation_run_update() RETURNS trigger AS $$
        BEGIN
          IF OLD.status IN ('COMPLETED', 'FAILED', 'CANCELLED') THEN
            RAISE EXCEPTION 'terminal simulation runs are immutable';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER terminal_simulation_runs_immutable
        BEFORE UPDATE ON simulation_runs
        FOR EACH ROW EXECUTE FUNCTION reject_terminal_simulation_run_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS terminal_simulation_runs_immutable ON simulation_runs")
    op.execute("DROP FUNCTION IF EXISTS reject_terminal_simulation_run_update()")
    op.execute("DROP TRIGGER IF EXISTS simulation_results_immutable ON simulation_results")
    op.execute("DROP FUNCTION IF EXISTS reject_simulation_result_mutation()")
    op.execute("DROP TRIGGER IF EXISTS confirmed_scenarios_immutable ON confirmed_scenarios")
    op.execute("DROP FUNCTION IF EXISTS reject_confirmed_scenario_mutation()")
    op.drop_index("ix_simulation_progress_time", table_name="simulation_progress_events")
    op.drop_table("simulation_progress_events")
    op.drop_table("simulation_results")
    op.drop_index("ix_simulation_run_status", table_name="simulation_runs")
    op.drop_index("ix_simulation_run_scenario_time", table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index("ix_confirmed_scenario_time", table_name="confirmed_scenarios")
    op.drop_table("confirmed_scenarios")
    op.drop_index("ix_scenario_validation_validated", table_name="scenario_validations")
    op.drop_table("scenario_validations")
    op.drop_index("ix_scenario_candidate_snapshot", table_name="scenario_candidates")
    op.drop_table("scenario_candidates")
