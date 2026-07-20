from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricValue = TypeVar("MetricValue", int, float, str, bool)


class TruthClass(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    MODELED = "MODELED"
    ASSUMPTION = "ASSUMPTION"


class FreshnessStatus(StrEnum):
    LIVE = "LIVE"
    RECENT = "RECENT"
    CURRENT = "CURRENT"
    STALE = "STALE"
    REPLAY = "REPLAY"
    UNAVAILABLE = "UNAVAILABLE"


class DataMode(StrEnum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    REPLAY = "REPLAY"
    FIXTURE = "FIXTURE"
    USER_SUPPLIED = "USER_SUPPLIED"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=100)
    record_id: str = Field(min_length=1, max_length=500)


class MetricEnvelope(BaseModel, Generic[MetricValue]):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: MetricValue
    unit: str = Field(min_length=1, max_length=50)
    truth_class: TruthClass
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(min_length=1)
    source_refs: list[SourceRef] = Field(min_length=1)
    effective_at: datetime
    fetched_at: datetime
    computed_at: datetime
    freshness_status: FreshnessStatus
    transformation: str = Field(min_length=1, max_length=250)
    model_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "MetricEnvelope[MetricValue]":
        if self.effective_at > self.fetched_at:
            raise ValueError("effective_at must not be after fetched_at")
        if self.fetched_at > self.computed_at:
            raise ValueError("fetched_at must not be after computed_at")
        return self
