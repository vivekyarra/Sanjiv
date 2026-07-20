from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from sanjiv.contracts.truth import DataMode, FreshnessStatus, TruthClass


class SourceState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    DISABLED = "DISABLED"


class AssumptionStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class AuditOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    source_id: str = Field(min_length=1, max_length=100)
    source_record_id: str = Field(min_length=1, max_length=500)
    source_url: AnyHttpUrl | None = None
    dataset: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=100)
    effective_at: datetime
    fetched_at: datetime
    mode: DataMode
    truth_class: TruthClass
    raw_payload_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    raw_object_ref: str | None = Field(default=None, max_length=1000)
    transformation: str = Field(min_length=1, max_length=250)
    confidence: float = Field(ge=0.0, le=1.0)
    license: str = Field(min_length=1, max_length=500)
    parent_evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "EvidenceRecord":
        if self.effective_at > self.fetched_at:
            raise ValueError("effective_at must not be after fetched_at")
        return self


class SourceHealthRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    source_id: str = Field(min_length=1, max_length=100)
    state: SourceState
    checked_at: datetime
    last_success_at: datetime | None = None
    expected_cadence_seconds: int | None = Field(default=None, gt=0)
    stale_after_seconds: int | None = Field(default=None, gt=0)
    lag_seconds: float | None = Field(default=None, ge=0)
    message_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    circuit_open: bool = False
    mode: DataMode
    freshness_status: FreshnessStatus
    error_code: str | None = Field(default=None, max_length=100)


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    key: str = Field(min_length=1, max_length=200)
    value: Any
    unit: str = Field(min_length=1, max_length=50)
    truth_class: TruthClass = TruthClass.ASSUMPTION
    rationale: str = Field(min_length=1, max_length=2000)
    source_gap: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=200)
    entered_at: datetime
    effective_at: datetime
    expires_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: str | None = Field(default=None, max_length=200)
    status: AssumptionStatus = AssumptionStatus.DRAFT
    scenario_id: UUID | None = None
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def validate_assumption(self) -> "Assumption":
        if self.truth_class is not TruthClass.ASSUMPTION:
            raise ValueError("assumptions must use truth_class ASSUMPTION")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("expires_at must be after effective_at")
        if self.status is AssumptionStatus.APPROVED and not self.approved_by:
            raise ValueError("approved assumptions require approved_by")
        return self


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime
    actor_id: str = Field(min_length=1, max_length=200)
    actor_type: str = Field(min_length=1, max_length=50)
    action: str = Field(min_length=1, max_length=200)
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=200)
    before_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    after_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    reason: str | None = Field(default=None, max_length=2000)
    correlation_id: UUID
    causation_id: UUID | None = None
    outcome: AuditOutcome
