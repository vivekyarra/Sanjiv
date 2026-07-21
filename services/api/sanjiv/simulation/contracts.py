from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, TruthClass
from sanjiv.scenarios.contracts import TwinSnapshotReference


class SimulationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SimulationConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    time_step: int = Field(default=1, ge=1, le=1)
    time_step_unit: Literal["day"] = "day"
    uncertainty_method: Literal["BOUNDED_SENSITIVITY"] = "BOUNDED_SENSITIVITY"
    uncertainty_reduction_delta: float = Field(
        default=10.0, ge=0, le=25, allow_inf_nan=False
    )
    uncertainty_reduction_unit: Literal["percentage_point"] = "percentage_point"


class StartSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: UUID
    configuration: SimulationConfiguration = Field(default_factory=SimulationConfiguration)


class SimulationFailureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False
    details: dict[str, str | float | int | bool] = Field(default_factory=dict)


class SimulationProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    sequence: int = Field(ge=1)
    status: SimulationStatus
    progress_percent: float = Field(ge=0, le=100)
    phase: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    occurred_at: datetime


class SimulationProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: UUID
    twin_snapshot: TwinSnapshotReference
    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    simulation_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(min_length=1)
    truth_class: Literal[TruthClass.MODELED] = TruthClass.MODELED
    confidence: float = Field(ge=0, le=1)
    freshness_status: FreshnessStatus
    effective_at: datetime
    fetched_at: datetime
    computed_at: datetime
    transformation: str


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_supply: MetricEnvelope[float]
    total_demand: MetricEnvelope[float]
    refinery_throughput: MetricEnvelope[float]
    shortfall: MetricEnvelope[float]


class DisruptedResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_supply: MetricEnvelope[float]
    total_demand: MetricEnvelope[float]
    refinery_throughput: MetricEnvelope[float]
    shortfall: MetricEnvelope[float]
    cumulative_shortfall: MetricEnvelope[float]


class TimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int = Field(ge=0)
    starts_at: datetime
    ends_at: datetime
    baseline_supply: MetricEnvelope[float]
    disrupted_supply: MetricEnvelope[float]
    refinery_throughput: MetricEnvelope[float]
    shortfall: MetricEnvelope[float]
    cumulative_shortfall: MetricEnvelope[float]


class FlowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: UUID
    route_canonical_id: str
    supplier_id: UUID
    grade_id: UUID
    baseline_flow: MetricEnvelope[float]
    disrupted_flow: MetricEnvelope[float]
    disrupted_capacity: MetricEnvelope[float]
    affected: bool


class RefineryThroughputResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    refinery_id: UUID
    refinery_canonical_id: str
    baseline_throughput: MetricEnvelope[float]
    disrupted_receipts: MetricEnvelope[float]
    disrupted_throughput: MetricEnvelope[float]
    shortfall: MetricEnvelope[float]


class InventoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_at: datetime
    ending_inventory: MetricEnvelope[float]


class InventoryTrajectory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    refinery_id: UUID
    refinery_canonical_id: str
    assumption_id: UUID
    assumption_dependent: Literal[True] = True
    points: list[InventoryPoint]


class UncertaintyRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    central: MetricEnvelope[float]
    lower_bound: MetricEnvelope[float]
    upper_bound: MetricEnvelope[float]
    parameters_varied: list[str]
    variation_method: Literal["BOUNDED_SENSITIVITY"] = "BOUNDED_SENSITIVITY"
    assumption_ids: list[UUID] = Field(min_length=1)
    model_version: str
    probability_claimed: Literal[False] = False


class PhysicalInvariantReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    non_negative_flows: bool
    non_negative_inventories: bool
    route_capacities_respected: bool
    closed_routes_zero: bool
    supplier_limits_respected: bool
    refinery_limits_respected: bool
    grade_compatibility_respected: bool
    mass_conserved: bool
    cumulative_values_reconcile: bool
    baseline_unchanged: bool
    snapshot_unchanged: bool
    max_mass_balance_residual: float = Field(ge=0)
    tolerance: float = Field(gt=0)


class SimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: UUID
    run_id: UUID
    provenance: SimulationProvenance
    baseline: BaselineResult
    disrupted: DisruptedResult
    timeline: list[TimelinePoint] = Field(min_length=1)
    flows: list[FlowResult] = Field(min_length=1)
    refinery_throughput: list[RefineryThroughputResult] = Field(min_length=1)
    inventory_trajectories: list[InventoryTrajectory] = Field(default_factory=list)
    inventory_status: Literal["UNKNOWN", "ASSUMPTION_DEPENDENT"]
    affected_asset_ids: list[UUID]
    affected_route_ids: list[UUID]
    uncertainty: UncertaintyRange
    invariants: PhysicalInvariantReport
    runtime_ms: float = Field(ge=0)


class SimulationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    twin_snapshot: TwinSnapshotReference
    simulation_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str
    configuration: SimulationConfiguration
    status: SimulationStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    runtime_ms: float | None = Field(default=None, ge=0)
    reused_result: bool = False
    result: SimulationResult | None = None
    failure: SimulationFailureResult | None = None
    cancellation_requested_at: datetime | None = None
