from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sanjiv.contracts import (
    DataMode,
    EvidenceRecord,
    FreshnessStatus,
    MetricEnvelope,
    SourceHealthRecord,
    TruthClass,
)

OperationsEventType = Literal[
    "VESSEL_POSITION",
    "GEOFENCE_EVENT",
    "MODE_TRANSITION",
    "HEARTBEAT",
    "RESYNC_REQUIRED",
    "ERROR",
]


class OperatingMode(StrEnum):
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    REPLAY = "REPLAY"


class ConnectionState(StrEnum):
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    DEGRADED = "DEGRADED"


class GeofenceEventType(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class SanctionsMatchStatus(StrEnum):
    NOT_SCREENED = "NOT_SCREENED"
    NO_MATCH = "NO_MATCH"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    EXACT_MATCH = "EXACT_MATCH"


class RawAISMessage(BaseModel):
    """Validated provider record before canonical normalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=500)
    source_timestamp: datetime
    fetched_at: datetime
    mode: DataMode
    payload: dict[str, Any]
    dataset: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=100)
    license: str = Field(min_length=1, max_length=500)
    source_url: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> "RawAISMessage":
        if self.source_timestamp.tzinfo is None or self.fetched_at.tzinfo is None:
            raise ValueError("AIS timestamps must be timezone-aware")
        if self.source_timestamp > self.fetched_at:
            raise ValueError("source_timestamp must not be after fetched_at")
        return self


class VesselPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    vessel_id: UUID
    mmsi: str = Field(pattern=r"^\d{9}$")
    imo: str | None = Field(default=None, pattern=r"^\d{7}$")
    vessel_name: str | None = Field(default=None, max_length=200)
    ship_type: int | None = Field(default=None, ge=0, le=99)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    speed_knots: float | None = Field(default=None, ge=0.0, le=102.3)
    course_degrees: float | None = Field(default=None, ge=0.0, lt=360.0)
    heading_degrees: float | None = Field(default=None, ge=0.0, le=359.0)
    navigation_status: int | None = Field(default=None, ge=0, le=15)
    destination_raw: str | None = Field(default=None, max_length=200)
    source_timestamp: datetime
    fetched_at: datetime
    computed_at: datetime
    source_id: str
    source_record_id: str
    mode: DataMode
    truth_class: TruthClass
    freshness_status: FreshnessStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(min_length=1)
    transformation: str = Field(min_length=1, max_length=250)
    adapter_version: str = Field(min_length=1, max_length=100)

    @field_validator("source_timestamp", "fetched_at", "computed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "VesselPosition":
        if not self.source_timestamp <= self.fetched_at <= self.computed_at:
            raise ValueError("expected source_timestamp <= fetched_at <= computed_at")
        return self


class VesselTrackSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    vessel_id: UUID
    start_position_id: UUID
    end_position_id: UUID
    start_at: datetime
    end_at: datetime
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=2)
    distance_nm: MetricEnvelope[float]


class Geofence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["CHOKEPOINT", "PORT"]
    coordinates: list[list[tuple[float, float]]]
    source_ref: str = Field(min_length=1, max_length=1000)
    effective_at: datetime
    truth_class: TruthClass
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_id: UUID
    transformation: str
    version: str
    authoritative: bool = False


class GeofenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    vessel_id: UUID
    geofence_id: UUID
    position_id: UUID
    event_type: GeofenceEventType
    occurred_at: datetime
    truth_class: Literal[TruthClass.DERIVED] = TruthClass.DERIVED
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(min_length=2)
    transformation: str


class InferenceContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    weight: float = Field(gt=0.0, le=1.0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    explanation: str


class IndiaBoundAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    likelihood: MetricEnvelope[float]
    completeness: float = Field(ge=0.0, le=1.0)
    contributions: list[InferenceContribution]
    disclaimer: str


class SanctionsAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SanctionsMatchStatus
    truth_class: TruthClass
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID]
    explanation: str


class VesselOperationalView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: VesselPosition
    recent_track: list[tuple[float, float]]
    india_bound: IndiaBoundAssessment
    sanctions: SanctionsAssessment


class OperatingModeTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    from_mode: OperatingMode
    to_mode: OperatingMode
    occurred_at: datetime
    reason_code: str
    explanation: str
    automatic: bool
    audit_event_id: UUID


class ReplayRecording(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    dataset_id: str
    manifest_version: str
    classification: Literal["SYNTHETIC_FIXTURE", "RECORDED_REAL_DATA"]
    object_ref: str
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    starts_at: datetime
    ends_at: datetime
    record_count: int = Field(gt=0)
    license: str


class QuarantinedAISMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    source_id: str
    source_record_id: str | None
    fetched_at: datetime
    reason_code: str
    payload_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class OperationsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    cursor: int = Field(ge=0)
    as_of: datetime
    operating_mode: OperatingMode
    mode_explanation: str
    connection_state: ConnectionState
    source_health: SourceHealthRecord
    vessel_count: MetricEnvelope[int] | None = None
    messages_per_minute: MetricEnvelope[float] | None = None
    vessels: list[VesselOperationalView]
    geofences: list[Geofence]
    latest_transition: OperatingModeTransition | None = None


class VesselHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vessel_id: UUID
    positions: list[VesselPosition]
    segments: list[VesselTrackSegment]


class OperationsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    sequence: int = Field(ge=1)
    event_type: OperationsEventType
    occurred_at: datetime
    operating_mode: OperatingMode
    payload: dict[str, Any]


class ReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    dataset_id: str
    classification: Literal["SYNTHETIC_FIXTURE", "RECORDED_REAL_DATA"]
    description: str
    source_id: str
    data_file: str
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    starts_at: datetime
    ends_at: datetime
    record_count: int = Field(gt=0)
    license: str
    redistribution: str
    transformation: str
    adapter_version: str


class ReplayFixtureMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_record_id: str = Field(min_length=1, max_length=500)
    source_timestamp: datetime
    payload: dict[str, Any]


class AdapterHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_health: SourceHealthRecord
    connection_state: ConnectionState
    detail: str


class NormalizedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: VesselPosition
    evidence: EvidenceRecord
