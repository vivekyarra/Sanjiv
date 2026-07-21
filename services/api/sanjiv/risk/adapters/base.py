from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from sanjiv.contracts import FreshnessStatus, SourceState, TruthClass
from sanjiv.risk.contracts import RiskFeatureType, RiskSourceFailure


class AdapterPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timeout_seconds: float = Field(gt=0, le=60, allow_inf_nan=False)
    max_retries: int = Field(ge=0, le=5)
    backoff_seconds: float = Field(ge=0, le=30, allow_inf_nan=False)
    expected_cadence_seconds: int = Field(gt=0)
    stale_after_seconds: int = Field(gt=0)
    rate_limit_per_minute: int = Field(gt=0)


class RawRiskSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corridor_id: UUID
    feature_type: RiskFeatureType
    raw_value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=50)
    source_id: str = Field(min_length=1, max_length=100)
    source_state: SourceState
    freshness: FreshnessStatus
    truth_class: TruthClass
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    effective_at: AwareDatetime
    fetched_at: AwareDatetime
    evidence_ids: list[UUID]


class RiskAdapterResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    signals: list[RawRiskSignal]
    failures: list[RiskSourceFailure]


class RiskSourceAdapter(Protocol):
    @property
    def source_id(self) -> str: ...

    @property
    def policy(self) -> AdapterPolicy: ...

    async def fetch(self, case_id: str) -> RiskAdapterResult: ...
