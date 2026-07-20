"""Create evidence, source health, assumption, and audit foundations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRUTH_VALUES = "'OBSERVED','DERIVED','INFERRED','MODELED','ASSUMPTION'"
MODE_VALUES = "'LIVE','CACHED','REPLAY','FIXTURE','USER_SUPPLIED'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_record_id", sa.String(500), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("dataset", sa.String(200), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("truth_class", sa.String(20), nullable=False),
        sa.Column("raw_payload_hash", sa.String(64), nullable=False),
        sa.Column("raw_object_ref", sa.Text(), nullable=True),
        sa.Column("transformation", sa.String(250), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("license", sa.String(500), nullable=False),
        sa.Column("parent_evidence_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.CheckConstraint(f"truth_class IN ({TRUTH_VALUES})", name="ck_evidence_truth_class"),
        sa.CheckConstraint(f"mode IN ({MODE_VALUES})", name="ck_evidence_mode"),
        sa.CheckConstraint("effective_at <= fetched_at", name="ck_evidence_timestamp_order"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evidence_confidence"),
        sa.UniqueConstraint("source_id", "source_record_id", "dataset_version"),
    )
    op.create_index("ix_evidence_source_effective", "evidence_records", ["source_id", "effective_at"])

    op.create_table(
        "source_health_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_cadence_seconds", sa.Integer(), nullable=True),
        sa.Column("stale_after_seconds", sa.Integer(), nullable=True),
        sa.Column("lag_seconds", sa.Numeric(), nullable=True),
        sa.Column("message_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("circuit_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.CheckConstraint(f"mode IN ({MODE_VALUES})", name="ck_source_health_mode"),
        sa.CheckConstraint("message_count >= 0 AND error_count >= 0", name="ck_source_health_counts"),
    )
    op.create_index("ix_source_health_source_checked", "source_health_records", ["source_id", "checked_at"])

    op.create_table(
        "assumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("truth_class", sa.String(20), nullable=False, server_default="ASSUMPTION"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_gap", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(200), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("truth_class = 'ASSUMPTION'", name="ck_assumption_truth_class"),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > effective_at", name="ck_assumption_expiry"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("before_hash", sa.String(64), nullable=True),
        sa.Column("after_hash", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
    )
    op.create_index("ix_audit_resource_time", "audit_events", ["resource_type", "resource_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_resource_time", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("assumptions")
    op.drop_index("ix_source_health_source_checked", table_name="source_health_records")
    op.drop_table("source_health_records")
    op.drop_index("ix_evidence_source_effective", table_name="evidence_records")
    op.drop_table("evidence_records")
