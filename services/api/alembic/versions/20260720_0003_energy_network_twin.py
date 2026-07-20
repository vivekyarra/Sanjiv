"""Create immutable digital-twin snapshot storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0003"
down_revision: str | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "twin_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "assumption_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.CheckConstraint("fingerprint ~ '^[a-f0-9]{64}$'", name="ck_twin_fingerprint"),
        sa.UniqueConstraint("version", "fingerprint", name="uq_twin_version_fingerprint"),
    )
    op.create_index("ix_twin_snapshot_effective", "twin_snapshots", ["effective_at"])
    op.execute(
        """
        CREATE FUNCTION reject_twin_snapshot_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'twin snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER twin_snapshots_immutable
        BEFORE UPDATE OR DELETE ON twin_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_twin_snapshot_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS twin_snapshots_immutable ON twin_snapshots")
    op.execute("DROP FUNCTION IF EXISTS reject_twin_snapshot_mutation()")
    op.drop_index("ix_twin_snapshot_effective", table_name="twin_snapshots")
    op.drop_table("twin_snapshots")
