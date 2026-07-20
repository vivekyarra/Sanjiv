"""Create Live Maritime Watch storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0002"
down_revision: str | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vessels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mmsi", sa.String(9), nullable=False, unique=True),
        sa.Column("imo", sa.String(7), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("ship_type", sa.SmallInteger(), nullable=True),
        sa.Column("flag", sa.String(3), nullable=True),
        sa.Column("sanctions_status", sa.String(30), nullable=False, server_default="NOT_SCREENED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mmsi ~ '^[0-9]{9}$'", name="ck_vessels_mmsi"),
        sa.CheckConstraint("imo IS NULL OR imo ~ '^[0-9]{7}$'", name="ck_vessels_imo"),
    )
    op.create_index("ix_vessels_imo", "vessels", ["imo"])

    op.create_table(
        "vessel_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", sa.String(500), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("speed_knots", sa.Float(), nullable=True),
        sa.Column("course_degrees", sa.Float(), nullable=True),
        sa.Column("heading_degrees", sa.Float(), nullable=True),
        sa.Column("navigation_status", sa.SmallInteger(), nullable=True),
        sa.Column("destination_raw", sa.String(200), nullable=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("truth_class", sa.String(20), nullable=False),
        sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("transformation", sa.String(250), nullable=False),
        sa.Column("adapter_version", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "source_timestamp"),
        sa.UniqueConstraint("source_id", "source_message_id", "source_timestamp"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_vessel_position_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_vessel_position_longitude"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_vessel_position_confidence"),
        sa.CheckConstraint(
            "source_timestamp <= fetched_at AND fetched_at <= computed_at",
            name="ck_vessel_position_timestamp_order",
        ),
    )
    op.create_index(
        "ix_vessel_positions_recent", "vessel_positions", ["vessel_id", "source_timestamp"]
    )
    op.create_index(
        "ix_vessel_positions_position_gist",
        "vessel_positions",
        ["position"],
        postgresql_using="gist",
    )
    op.execute(
        "SELECT create_hypertable('vessel_positions', by_range('source_timestamp'), "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    op.create_table(
        "vessel_track_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("end_position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=False),
        sa.Column("distance_nm", sa.Float(), nullable=False),
        sa.Column("evidence_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("transformation", sa.String(250), nullable=False),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.CheckConstraint("start_at <= end_at", name="ck_track_segment_timestamp_order"),
    )
    op.create_index(
        "ix_track_segments_vessel_end", "vessel_track_segments", ["vessel_id", "end_at"]
    )
    op.create_index(
        "ix_track_segments_path_gist",
        "vessel_track_segments",
        ["path"],
        postgresql_using="gist",
    )

    op.create_table(
        "geofences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("geometry", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("truth_class", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transformation", sa.String(250), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("authoritative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("kind IN ('CHOKEPOINT','PORT')", name="ck_geofence_kind"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_geofence_confidence"),
    )
    op.create_index(
        "ix_geofences_geometry_gist", "geofences", ["geometry"], postgresql_using="gist"
    )

    op.create_table(
        "geofence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vessel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geofence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("truth_class", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("transformation", sa.String(250), nullable=False),
        sa.ForeignKeyConstraint(["vessel_id"], ["vessels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["geofence_id"], ["geofences.id"], ondelete="CASCADE"),
        sa.CheckConstraint("event_type IN ('ENTRY','EXIT')", name="ck_geofence_event_type"),
    )
    op.create_index(
        "ix_geofence_events_asset_time",
        "geofence_events",
        ["geofence_id", "occurred_at"],
    )

    op.create_table(
        "replay_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", sa.String(200), nullable=False),
        sa.Column("manifest_version", sa.String(100), nullable=False),
        sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("object_ref", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.CheckConstraint("starts_at <= ends_at", name="ck_replay_recording_time"),
        sa.CheckConstraint("record_count > 0", name="ck_replay_recording_count"),
    )

    op.create_table(
        "operating_mode_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_mode", sa.String(20), nullable=False),
        sa.Column("to_mode", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("automatic", sa.Boolean(), nullable=False),
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"]),
        sa.CheckConstraint(
            "from_mode IN ('LIVE','DEGRADED','REPLAY') AND to_mode IN ('LIVE','DEGRADED','REPLAY')",
            name="ck_operating_mode_values",
        ),
    )
    op.create_index(
        "ix_operating_mode_transitions_time", "operating_mode_transitions", ["occurred_at"]
    )

    op.create_table(
        "ais_quarantine",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_record_id", sa.String(500), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_ais_quarantine_time", "ais_quarantine", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_ais_quarantine_time", table_name="ais_quarantine")
    op.drop_table("ais_quarantine")
    op.drop_index("ix_operating_mode_transitions_time", table_name="operating_mode_transitions")
    op.drop_table("operating_mode_transitions")
    op.drop_table("replay_recordings")
    op.drop_index("ix_geofence_events_asset_time", table_name="geofence_events")
    op.drop_table("geofence_events")
    op.drop_index("ix_geofences_geometry_gist", table_name="geofences")
    op.drop_table("geofences")
    op.drop_index("ix_track_segments_path_gist", table_name="vessel_track_segments")
    op.drop_index("ix_track_segments_vessel_end", table_name="vessel_track_segments")
    op.drop_table("vessel_track_segments")
    op.drop_index("ix_vessel_positions_position_gist", table_name="vessel_positions")
    op.drop_index("ix_vessel_positions_recent", table_name="vessel_positions")
    op.drop_table("vessel_positions")
    op.drop_index("ix_vessels_imo", table_name="vessels")
    op.drop_table("vessels")
