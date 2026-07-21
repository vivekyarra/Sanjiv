"""Persist immutable evidence audits and human plan lifecycle records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0008"
down_revision: str | None = "20260721_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_audits",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("audit_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("assumption_fingerprint", sa.String(64), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("coverage_percentage", sa.Numeric(), nullable=False),
        sa.Column("audited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("plan_kind IN ('PROCUREMENT','RESERVE')", name="ck_evidence_audit_kind"),
        sa.CheckConstraint("status IN ('PASSED','FAILED')", name="ck_evidence_audit_status"),
        sa.CheckConstraint("coverage_percentage BETWEEN 0 AND 100", name="ck_evidence_audit_coverage"),
        sa.CheckConstraint("audit_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_evidence_audit_fingerprint"),
        sa.CheckConstraint("plan_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_evidence_audit_plan_fingerprint"),
        sa.CheckConstraint("assumption_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_evidence_audit_assumption_fingerprint"),
        sa.CheckConstraint("evidence_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_evidence_audit_evidence_fingerprint"),
    )
    op.create_index("ix_evidence_audits_plan_time", "evidence_audits", ["plan_id", "audited_at"])
    op.create_table(
        "plan_lifecycle_records",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_kind", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("previous_state", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("assumption_fingerprint", sa.String(64), nullable=False),
        sa.Column("audit_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("plan_kind IN ('PROCUREMENT','RESERVE')", name="ck_plan_lifecycle_kind"),
        sa.CheckConstraint("actor_role IN ('operator','reviewer','approver','administrator')", name="ck_plan_lifecycle_role"),
        sa.CheckConstraint("previous_state IN ('RECOMMENDED','UNDER_REVIEW','APPROVED','REJECTED','SUPERSEDED')", name="ck_plan_previous_state"),
        sa.CheckConstraint("state IN ('RECOMMENDED','UNDER_REVIEW','APPROVED','REJECTED','SUPERSEDED')", name="ck_plan_state"),
        sa.CheckConstraint("plan_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_lifecycle_plan_fingerprint"),
        sa.CheckConstraint("assumption_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_lifecycle_assumption_fingerprint"),
        sa.CheckConstraint("audit_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_lifecycle_audit_fingerprint"),
        sa.CheckConstraint("idempotency_fingerprint ~ '^[a-f0-9]{64}$'", name="ck_lifecycle_idempotency_fingerprint"),
    )
    op.create_index("ix_plan_lifecycle_plan_time", "plan_lifecycle_records", ["plan_id", "occurred_at"])
    op.execute(
        """CREATE FUNCTION reject_phase7_governance_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'evidence audits and lifecycle records are immutable'; END;
        $$ LANGUAGE plpgsql"""
    )
    for table in ("evidence_audits", "plan_lifecycle_records"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_phase7_governance_mutation()"
        )


def downgrade() -> None:
    for table in ("plan_lifecycle_records", "evidence_audits"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_phase7_governance_mutation()")
    op.drop_index("ix_plan_lifecycle_plan_time", table_name="plan_lifecycle_records")
    op.drop_table("plan_lifecycle_records")
    op.drop_index("ix_evidence_audits_plan_time", table_name="evidence_audits")
    op.drop_table("evidence_audits")
