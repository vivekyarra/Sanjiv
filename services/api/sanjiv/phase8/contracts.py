from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sanjiv.audit.contracts import EvidenceAuditStatus, GovernanceRole, PlanKind
from sanjiv.contracts import Assumption, EvidenceRecord, MetricEnvelope


class DatasetClassification(StrEnum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    RECORDED_REAL_DATA = "RECORDED_REAL_DATA"


class Commodity(StrEnum):
    CRUDE_OIL = "CRUDE_OIL"
    LPG = "LPG"


class ReplayEventType(StrEnum):
    CHOKEPOINT_DISRUPTION = "CHOKEPOINT_DISRUPTION"
    SUPPLIER_OUTAGE = "SUPPLIER_OUTAGE"
    PORT_DISRUPTION = "PORT_DISRUPTION"
    REFINERY_OUTAGE = "REFINERY_OUTAGE"
    SANCTIONS_EVENT = "SANCTIONS_EVENT"
    DEMAND_SHOCK = "DEMAND_SHOCK"
    COMPOUND_DISRUPTION = "COMPOUND_DISRUPTION"
    FALSE_NEWS_SPIKE = "FALSE_NEWS_SPIKE"
    SOURCE_OUTAGE = "SOURCE_OUTAGE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    SOLVER_INFEASIBILITY = "SOLVER_INFEASIBILITY"
    EXTENDED_DISRUPTION = "EXTENDED_DISRUPTION"


class ReplayInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid_order(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("replay interval must end after it starts")
        return self


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,100}$")
    name: str = Field(min_length=1, max_length=200)
    classification: DatasetClassification
    source_or_generator: str = Field(min_length=1, max_length=300)
    original_interval: ReplayInterval
    license: str = Field(min_length=1, max_length=200)
    redistribution_status: str = Field(min_length=1, max_length=200)
    commodity: Commodity
    event_type: ReplayEventType
    disruption_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    duration_days: int = Field(ge=1, le=180)
    demand_change_percent: float = Field(ge=-50, le=100, allow_inf_nan=False)
    source_completeness: float = Field(ge=0, le=1, allow_inf_nan=False)
    assumptions: list[str] = Field(min_length=1, max_length=20)
    expected_invariants: list[str] = Field(min_length=1, max_length=30)
    expected_detection: str = Field(min_length=1, max_length=100)
    expected_plan_outcome: str = Field(min_length=1, max_length=100)


class ReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    version: str
    classification: DatasetClassification
    source_or_generator: str
    payload: str
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    license: str
    redistribution_status: str
    case_count: int = Field(ge=20)
    created_at: datetime
    warning: str


class ReplayCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: ReplayManifest
    cases: list[ReplayCase] = Field(min_length=20)


class ReplayTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day: int = Field(ge=0)
    no_action_shortage: MetricEnvelope[float]
    recommended_shortage: MetricEnvelope[float]


class ReplayRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    case_id: str
    library_id: str
    library_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    classification: DatasetClassification
    commodity: Commodity
    truth_label: Literal["FIXTURE", "REPLAY"] = "FIXTURE"
    started_at: datetime
    completed_at: datetime
    detection_lead_time: MetricEnvelope[float]
    recommendation_runtime: MetricEnvelope[float]
    evidence_coverage: MetricEnvelope[float]
    no_action_shortage: MetricEnvelope[float]
    recommended_shortage: MetricEnvelope[float]
    shortfall_reduction: MetricEnvelope[float]
    cost_increase: MetricEnvelope[float]
    timeline: list[ReplayTimelinePoint] = Field(min_length=1)
    expected_invariants: list[str]
    invariant_results: dict[str, bool]
    detection_outcome: str
    plan_outcome: str
    audit_status: EvidenceAuditStatus
    checker_passed: bool
    export_allowed: bool
    evidence_records: list[EvidenceRecord] = Field(min_length=1)
    assumptions: list[Assumption] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class LpgSupplier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    country_code: str = Field(min_length=2, max_length=2)
    capacity: float = Field(ge=0)
    sanctioned: bool


class LpgTerminal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    capacity: float = Field(ge=0)
    compatible: bool


class LpgRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    supplier_id: str
    terminal_id: str
    via: str
    capacity: float = Field(ge=0)
    baseline_flow: float = Field(ge=0)
    transit_days: float = Field(gt=0)
    cost_usd_per_tonne: float = Field(ge=0)


class LpgNetwork(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    version: str
    classification: DatasetClassification
    license: str
    redistribution_status: str
    unit: Literal["tonne_per_day"]
    effective_at: datetime
    expires_at: datetime
    suppliers: list[LpgSupplier] = Field(min_length=1)
    terminals: list[LpgTerminal] = Field(min_length=1)
    routes: list[LpgRoute] = Field(min_length=1)
    baseline_demand: float = Field(gt=0)
    public_reserve_policy: Literal["NOT_APPLICABLE"]
    assumption_notice: str

    @model_validator(mode="after")
    def physical_invariants(self) -> Self:
        suppliers = {item.id: item for item in self.suppliers}
        terminals = {item.id: item for item in self.terminals}
        if self.expires_at <= self.effective_at:
            raise ValueError("LPG fixture expiry must follow effective time")
        if len(suppliers) != len(self.suppliers) or len(terminals) != len(self.terminals):
            raise ValueError("duplicate LPG asset identifier")
        terminal_flows: dict[str, float] = {}
        supplier_flows: dict[str, float] = {}
        for route in self.routes:
            if route.supplier_id not in suppliers or route.terminal_id not in terminals:
                raise ValueError("LPG route has an unknown endpoint")
            if route.baseline_flow > route.capacity:
                raise ValueError("LPG baseline flow exceeds route capacity")
            if not terminals[route.terminal_id].compatible:
                raise ValueError("LPG route targets an incompatible terminal")
            terminal_flows[route.terminal_id] = (
                terminal_flows.get(route.terminal_id, 0.0) + route.baseline_flow
            )
            supplier_flows[route.supplier_id] = (
                supplier_flows.get(route.supplier_id, 0.0) + route.baseline_flow
            )
        if any(value > terminals[key].capacity for key, value in terminal_flows.items()):
            raise ValueError("LPG terminal baseline exceeds capacity")
        if any(value > suppliers[key].capacity for key, value in supplier_flows.items()):
            raise ValueError("LPG supplier baseline exceeds capacity")
        if abs(sum(item.baseline_flow for item in self.routes) - self.baseline_demand) > 1e-6:
            raise ValueError("LPG baseline demand does not conserve mass")
        return self


class LpgAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str
    supplier_id: str
    terminal_id: str
    volume: MetricEnvelope[float]
    arrival_days: MetricEnvelope[float]
    landed_cost: MetricEnvelope[float]


class LpgPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: UUID
    replay_run_id: UUID
    profile: Literal["LOWEST_COST", "BALANCED", "HIGHEST_RESILIENCE"]
    allocations: list[LpgAllocation] = Field(min_length=1)
    delivered_volume: MetricEnvelope[float]
    residual_shortage: MetricEnvelope[float]
    total_landed_cost: MetricEnvelope[float]
    supplier_concentration: MetricEnvelope[float]
    route_concentration: MetricEnvelope[float]
    reserve_handling: Literal["NOT_APPLICABLE"]
    solver_status: Literal["OPTIMAL"]
    checker_passed: Literal[True]
    audit_status: EvidenceAuditStatus
    evidence_coverage: MetricEnvelope[float]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class SensitivityMode(StrEnum):
    FAST = "FAST"
    DEEP = "DEEP"


class SensitivityRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    unit: str

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if self.maximum <= self.minimum:
            raise ValueError("sensitivity maximum must exceed minimum")
        return self


class SensitivityCorrelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left: str
    right: str
    coefficient: float = Field(ge=-1, le=1, allow_inf_nan=False)


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: SensitivityMode = SensitivityMode.FAST
    seed: int = Field(default=20260721, ge=0, le=2_147_483_647)
    ranges: list[SensitivityRange] = Field(default_factory=list, max_length=20)
    correlations: list[SensitivityCorrelation] = Field(default_factory=list, max_length=20)


class SensitivityDriver(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    rank: int = Field(ge=1)
    normalized_effect: MetricEnvelope[float]


class SensitivityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sensitivity_id: UUID
    plan_id: UUID
    plan_kind: PlanKind | Literal["LPG"]
    mode: SensitivityMode
    seed: int
    sample_count: int
    sampling_method: Literal["SEEDED_LATIN_HYPERCUBE_V1"]
    ranges: list[SensitivityRange]
    correlations: list[SensitivityCorrelation]
    median: MetricEnvelope[float]
    p10: MetricEnvelope[float]
    p90: MetricEnvelope[float]
    best_case: MetricEnvelope[float]
    worst_case: MetricEnvelope[float]
    drivers: list[SensitivityDriver]
    plan_stability: MetricEnvelope[float]
    stability_method_version: Literal["allocation-l1-threshold-v1"]
    probability_claimed: Literal[False] = False
    audit_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExportKind(StrEnum):
    EXECUTIVE_BRIEFING = "EXECUTIVE_BRIEFING"
    PROCUREMENT_ACTION_PACKAGE = "PROCUREMENT_ACTION_PACKAGE"
    STRATEGIC_RESERVE_GUIDANCE = "STRATEGIC_RESERVE_GUIDANCE"
    RISK_ROUTE_MAP = "RISK_ROUTE_MAP"
    SCENARIO_JSON = "SCENARIO_JSON"
    ASSUMPTIONS_SHEET = "ASSUMPTIONS_SHEET"
    EVIDENCE_APPENDIX = "EVIDENCE_APPENDIX"
    MODEL_VERSION_APPENDIX = "MODEL_VERSION_APPENDIX"
    APPROVAL_RECORD = "APPROVAL_RECORD"
    MACHINE_READABLE_JSON = "MACHINE_READABLE_JSON"
    PDF_BRIEFING = "PDF_BRIEFING"


class CreateExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ExportKind


class BriefingExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    export_id: UUID
    plan_id: UUID
    plan_kind: PlanKind | Literal["LPG"]
    kind: ExportKind
    created_at: datetime
    content_type: str
    filename: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(ge=1)
    audit_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    values_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    truth_label: Literal["AUDITED_DECISION_SUPPORT"]
    execution_authorized: Literal[False] = False


class CreateCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    comment: str = Field(min_length=1, max_length=2000)


class PlanComment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    comment_id: UUID
    plan_id: UUID
    actor_id: str
    actor_role: GovernanceRole
    comment: str
    idempotency_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    immutable: Literal[True] = True


class MonitorPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    replay_run_id: UUID


class PlanMonitoringRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    monitoring_id: UUID
    plan_id: UUID
    replay_run_id: UUID
    mode: Literal["REPLAY"] = "REPLAY"
    observed_at: datetime
    expected_shortage: MetricEnvelope[float]
    replayed_shortage: MetricEnvelope[float]
    deviation: MetricEnvelope[float]
    stale_input_warnings: list[str]
    audit_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_integration: Literal[False] = False


def canonical_hash(value: Any) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
