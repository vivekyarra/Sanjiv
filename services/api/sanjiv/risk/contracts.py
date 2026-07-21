from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import to_jsonable_python

from sanjiv.contracts import FreshnessStatus, SourceState, TruthClass

SHA256_PATTERN = r"^[a-f0-9]{64}$"


class RiskFeatureType(StrEnum):
    TRANSIT_ANOMALY = "TRANSIT_ANOMALY"
    GEOPOLITICAL_SEVERITY = "GEOPOLITICAL_SEVERITY"
    AIS_BEHAVIORAL_ANOMALY = "AIS_BEHAVIORAL_ANOMALY"
    MARKET_STRESS = "MARKET_STRESS"
    SANCTIONS_EXPOSURE = "SANCTIONS_EXPOSURE"
    INFRASTRUCTURE_PHYSICAL_SIGNAL = "INFRASTRUCTURE_PHYSICAL_SIGNAL"


class RiskLifecycle(StrEnum):
    CREATED = "CREATED"
    CALCULATED = "CALCULATED"
    DEGRADED = "DEGRADED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WATCH = "WATCH"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    SUPPRESSED = "SUPPRESSED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"


class RiskSourceFailureCode(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"


class RiskSeverity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float = Field(ge=0, le=100, allow_inf_nan=False)
    unit: Literal["severity_point"] = "severity_point"


class EvidenceConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float = Field(ge=0, le=1, allow_inf_nan=False)
    unit: Literal["fraction"] = "fraction"


class DataCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float = Field(ge=0, le=1, allow_inf_nan=False)
    unit: Literal["fraction"] = "fraction"


class AnomalyBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_type: RiskFeatureType
    window_starts_at: AwareDatetime
    window_ends_at: AwareDatetime
    observations: list[float] = Field(min_length=3, max_length=10_000)
    mean: float = Field(allow_inf_nan=False)
    standard_deviation: float = Field(gt=0, allow_inf_nan=False)
    version: str = Field(min_length=1, max_length=100)
    fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_baseline(self) -> Self:
        if self.window_starts_at >= self.window_ends_at:
            raise ValueError("risk baseline window must be ordered")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != canonical_hash(payload):
            raise ValueError("risk baseline fingerprint mismatch")
        return self


class NormalizedRiskFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_id: UUID
    corridor_id: UUID
    feature_type: RiskFeatureType
    raw_value: float | None = Field(default=None, allow_inf_nan=False)
    normalized_value: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=50)
    missing: bool
    truth_class: TruthClass
    confidence: EvidenceConfidence
    source_id: str = Field(min_length=1, max_length=100)
    source_state: SourceState
    freshness: FreshnessStatus
    effective_at: AwareDatetime
    fetched_at: AwareDatetime
    evidence_ids: list[UUID]
    baseline_fingerprint: str = Field(pattern=SHA256_PATTERN)
    transformation: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_missingness(self) -> Self:
        if self.missing != (self.raw_value is None or self.normalized_value is None):
            raise ValueError("risk feature missingness does not match its values")
        if self.effective_at > self.fetched_at:
            raise ValueError("risk feature effective_at exceeds fetched_at")
        if not self.missing and not self.evidence_ids:
            raise ValueError("present risk feature requires evidence")
        return self


class FeatureContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_type: RiskFeatureType
    normalized_value: float = Field(ge=0, le=100, allow_inf_nan=False)
    weight: float = Field(ge=0, le=1, allow_inf_nan=False)
    weighted_contribution: float = Field(ge=0, le=100, allow_inf_nan=False)
    present: bool


class CorroborationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    passed: bool
    independent_source_count: int = Field(ge=0)
    corroborating_features: list[RiskFeatureType]
    disagreeing_features: list[RiskFeatureType]
    stale_or_missing_features: list[RiskFeatureType]
    explanation: str = Field(min_length=1, max_length=1000)


class RiskSourceFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str = Field(min_length=1, max_length=100)
    code: RiskSourceFailureCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    occurred_at: AwareDatetime


class CorridorRiskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    risk_id: UUID
    corridor_id: UUID
    corridor_name: str = Field(min_length=1, max_length=200)
    severity: RiskSeverity
    confidence: EvidenceConfidence
    completeness: DataCompleteness
    features: list[NormalizedRiskFeature]
    contributions: list[FeatureContribution]
    corroboration: CorroborationResult
    source_failures: list[RiskSourceFailure]
    effective_at: AwareDatetime
    calculated_at: AwareDatetime
    lifecycle: RiskLifecycle
    model_version: str = Field(min_length=1, max_length=100)
    baseline_version: str = Field(min_length=1, max_length=100)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if {item.feature_type for item in self.features} != set(RiskFeatureType):
            raise ValueError("corridor risk must report every structural feature")
        if {item.feature_type for item in self.contributions} != set(RiskFeatureType):
            raise ValueError("corridor risk must report every feature contribution")
        expected = corridor_risk_fingerprint(self)
        if self.fingerprint != expected:
            raise ValueError("corridor risk fingerprint mismatch")
        return self


class AlertRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule_id: str = Field(min_length=1, max_length=100)
    version: str
    high_threshold: float = Field(ge=0, le=100, allow_inf_nan=False)
    critical_threshold: float = Field(ge=0, le=100, allow_inf_nan=False)
    minimum_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    minimum_completeness: float = Field(ge=0, le=1, allow_inf_nan=False)
    critical_requires_corroboration: Literal[True] = True


class AlertResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alert_id: UUID
    risk_id: UUID
    corridor_id: UUID
    severity_band: AlertSeverity
    status: AlertStatus
    severity: RiskSeverity
    confidence: EvidenceConfidence
    completeness: DataCompleteness
    contributions: list[FeatureContribution]
    evidence_ids: list[UUID]
    effective_at: AwareDatetime
    created_at: AwareDatetime
    model_version: str
    rule_version: str
    explanation: str = Field(min_length=1, max_length=2000)
    recommended_analyst_action: str = Field(min_length=1, max_length=1000)
    autonomous_action: Literal[False] = False
    risk_fingerprint: str = Field(pattern=SHA256_PATTERN)


class RiskTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corridor_id: UUID
    effective_at: AwareDatetime
    severity: RiskSeverity
    confidence: EvidenceConfidence
    completeness: DataCompleteness
    risk_fingerprint: str = Field(pattern=SHA256_PATTERN)


class RiskLifecycleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    risk_id: UUID
    current: RiskLifecycle
    target: RiskLifecycle
    occurred_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        allowed = {
            RiskLifecycle.CREATED: {
                RiskLifecycle.CALCULATED,
                RiskLifecycle.DEGRADED,
                RiskLifecycle.FAILED,
            },
            RiskLifecycle.CALCULATED: {RiskLifecycle.SUPERSEDED},
            RiskLifecycle.DEGRADED: {RiskLifecycle.SUPERSEDED},
        }
        if self.target not in allowed.get(self.current, set()):
            raise ValueError("invalid risk lifecycle transition")
        return self


class BacktestCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    label: str
    expected_alert: bool
    actual_alert: bool
    severity: RiskSeverity
    confidence: EvidenceConfidence
    completeness: DataCompleteness
    lead_time_hours: float = Field(ge=0, allow_inf_nan=False)
    runtime_ms: float = Field(ge=0, allow_inf_nan=False)
    stable: bool


class BacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backtest_id: UUID
    library_id: str
    classification: Literal["SYNTHETIC_FIXTURE", "RECORDED_REAL_DATA"]
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    model_version: str
    cases: list[BacktestCaseResult] = Field(min_length=1)
    detection_lead_time_hours: float = Field(ge=0, allow_inf_nan=False)
    precision: float = Field(ge=0, le=1, allow_inf_nan=False)
    false_positives: int = Field(ge=0)
    mean_completeness: float = Field(ge=0, le=1, allow_inf_nan=False)
    source_failure_case_count: int = Field(ge=0)
    alert_stability: float = Field(ge=0, le=1, allow_inf_nan=False)
    runtime_ms: float = Field(ge=0, allow_inf_nan=False)
    fixture_evidence_only: Literal[True] = True
    fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        if self.fingerprint != backtest_fingerprint(self):
            raise ValueError("risk backtest fingerprint mismatch")
        return self


class RiskOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    risks: list[CorridorRiskResult]
    generated_at: AwareDatetime
    mode: Literal["FIXTURE", "LIVE", "DEGRADED"]


class RiskAlertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alerts: list[AlertResult]


class RiskBacktestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    results: list[BacktestResult]


def corridor_risk_fingerprint(value: CorridorRiskResult | dict[str, Any]) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else dict(to_jsonable_python(value))
    )
    payload.pop("fingerprint", None)
    return _hash(payload)


def canonical_hash(value: object) -> str:
    return _hash(value)


def backtest_fingerprint(value: BacktestResult | dict[str, Any]) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else dict(to_jsonable_python(value))
    )
    payload.pop("fingerprint", None)
    payload.pop("runtime_ms", None)
    for item in payload.get("cases", []):
        item.pop("runtime_ms", None)
    return _hash(payload)


def _hash(value: object) -> str:
    encoded = json.dumps(
        to_jsonable_python(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


RISK_OPENAPI_MODELS: tuple[type[BaseModel], ...] = (
    NormalizedRiskFeature,
    FeatureContribution,
    CorridorRiskResult,
    EvidenceConfidence,
    DataCompleteness,
    AnomalyBaseline,
    CorroborationResult,
    AlertRule,
    AlertResult,
    RiskLifecycleTransition,
    RiskSourceFailure,
    BacktestCaseResult,
    BacktestResult,
    RiskOverviewResponse,
    RiskAlertResponse,
    RiskBacktestResponse,
    RiskTimelinePoint,
)
