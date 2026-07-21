"""Persist corridor risk features, alerts, timelines and replay backtests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0007"
down_revision: str | None = "20260721_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_anomaly_baselines",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("feature_type", sa.String(50), nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("fingerprint ~ '^[a-f0-9]{64}$'", name="ck_risk_baseline_fingerprint"),
    )
    op.create_table(
        "corridor_risk_results",
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("corridor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.Numeric(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("completeness", sa.Numeric(), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("severity BETWEEN 0 AND 100", name="ck_risk_severity"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_risk_confidence"),
        sa.CheckConstraint("completeness BETWEEN 0 AND 1", name="ck_risk_completeness"),
        sa.CheckConstraint("fingerprint ~ '^[a-f0-9]{64}$'", name="ck_risk_fingerprint"),
    )
    op.create_index(
        "ix_corridor_risk_current", "corridor_risk_results", ["corridor_id", "calculated_at"]
    )
    op.create_table(
        "normalized_risk_features",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corridor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["risk_id"], ["corridor_risk_results.risk_id"]),
    )
    op.create_table(
        "risk_feature_contributions",
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["risk_id"], ["corridor_risk_results.risk_id"]),
        sa.PrimaryKeyConstraint("risk_id", "feature_type"),
    )
    op.create_table(
        "risk_source_failures",
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["risk_id"], ["corridor_risk_results.risk_id"]),
        sa.PrimaryKeyConstraint("risk_id", "source_id", "code"),
    )
    op.create_table(
        "risk_alerts",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corridor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity_band", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["risk_id"], ["corridor_risk_results.risk_id"]),
    )
    op.create_table(
        "risk_timeline",
        sa.Column("corridor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("corridor_id", "effective_at", "risk_fingerprint"),
    )
    op.create_table(
        "risk_backtests",
        sa.Column("backtest_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("library_id", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "risk_lifecycle_transitions",
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_state", sa.String(20), nullable=False),
        sa.Column("target_state", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["risk_id"], ["corridor_risk_results.risk_id"]),
        sa.PrimaryKeyConstraint("risk_id", "current_state", "target_state"),
    )
    op.execute("""CREATE FUNCTION reject_risk_record_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'risk calculation records are immutable'; END;
    $$ LANGUAGE plpgsql""")
    for table in (
        "risk_anomaly_baselines",
        "corridor_risk_results",
        "normalized_risk_features",
        "risk_feature_contributions",
        "risk_source_failures",
        "risk_alerts",
        "risk_timeline",
        "risk_backtests",
        "risk_lifecycle_transitions",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_risk_record_mutation()"
        )


def downgrade() -> None:
    tables = (
        "risk_lifecycle_transitions",
        "risk_backtests",
        "risk_timeline",
        "risk_alerts",
        "risk_source_failures",
        "risk_feature_contributions",
        "normalized_risk_features",
        "corridor_risk_results",
        "risk_anomaly_baselines",
    )
    for table in tables:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_risk_record_mutation()")
    for table in tables:
        if table == "corridor_risk_results":
            op.drop_index("ix_corridor_risk_current", table_name=table)
        op.drop_table(table)
