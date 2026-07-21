from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import to_jsonable_python

from sanjiv.contracts import AssumptionStatus, MetricEnvelope, TruthClass
from sanjiv.procurement.contracts import (
    AssumptionFingerprintReference,
    ConfirmedScenarioReference,
    EvidenceFingerprintReference,
    SimulationResultReference,
    SimulationRunReference,
    SolverMetadata,
    SolverStatus,
)
from sanjiv.scenarios.contracts import TwinSnapshotReference

SHA256_PATTERN = r"^[a-f0-9]{64}$"


class ReservePolicyProfile(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE_CONTINUITY = "AGGRESSIVE_CONTINUITY"
    NO_RESERVE_USE = "NO_RESERVE_USE"


class InventoryTruthStatus(StrEnum):
    VERIFIED_USER_INPUT = "VERIFIED_USER_INPUT"
    UNEXPIRED_ASSUMPTION = "UNEXPIRED_ASSUMPTION"
    UNKNOWN = "UNKNOWN"


class ReservePlanLifecycle(StrEnum):
    REQUESTED = "REQUESTED"
    SOLVING = "SOLVING"
    CHECKING = "CHECKING"
    FEASIBLE = "FEASIBLE"
    FAILED = "FAILED"


class ReserveRejectedReason(StrEnum):
    UNKNOWN_INVENTORY = "UNKNOWN_INVENTORY"
    EXPIRED_ASSUMPTION = "EXPIRED_ASSUMPTION"
    DISCONNECTED = "DISCONNECTED"
    TRANSIT_TOO_LATE = "TRANSIT_TOO_LATE"
    CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"
    POLICY_FLOOR = "POLICY_FLOOR"
    NO_RESERVE_USE = "NO_RESERVE_USE"
    HIGHER_OBJECTIVE = "HIGHER_OBJECTIVE"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"


class ReservePolicyWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: ReservePolicyProfile
    version: str
    shortage: float = Field(ge=0, allow_inf_nan=False)
    reserve_depletion: float = Field(ge=0, allow_inf_nan=False)
    logistics_cost: float = Field(ge=0, allow_inf_nan=False)
    future_vulnerability: float = Field(ge=0, allow_inf_nan=False)
    minimum_floor_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)


class ReserveSiteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    site_id: UUID
    site_name: str = Field(min_length=1, max_length=200)
    refinery_id: UUID
    route_id: UUID
    capacity: MetricEnvelope[float]
    opening_inventory: MetricEnvelope[float] | None
    opening_inventory_status: InventoryTruthStatus
    minimum_policy_floor: MetricEnvelope[float]
    draw_rate_limit: MetricEnvelope[float]
    route_capacity: MetricEnvelope[float]
    transit_time: MetricEnvelope[float]
    refinery_receipt_capacity: MetricEnvelope[float]
    procurement_committed_receipts: MetricEnvelope[float]
    logistics_cost: MetricEnvelope[float]
    replenishment: MetricEnvelope[float] | None = None
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_site(self) -> Self:
        metrics = {
            "capacity": (self.capacity, "ktonne"),
            "minimum_policy_floor": (self.minimum_policy_floor, "ktonne"),
            "draw_rate_limit": (self.draw_rate_limit, "ktonne_per_day"),
            "route_capacity": (self.route_capacity, "ktonne_per_day"),
            "transit_time": (self.transit_time, "day"),
            "refinery_receipt_capacity": (self.refinery_receipt_capacity, "ktonne"),
            "procurement_committed_receipts": (self.procurement_committed_receipts, "ktonne"),
            "logistics_cost": (self.logistics_cost, "USD_per_tonne"),
        }
        if self.opening_inventory is not None:
            metrics["opening_inventory"] = (self.opening_inventory, "ktonne")
        if self.replenishment is not None:
            metrics["replenishment"] = (self.replenishment, "ktonne")
        for name, (metric, unit) in metrics.items():
            if (
                metric.unit != unit
                or not isinstance(metric.value, (int, float))
                or not math.isfinite(metric.value)
                or metric.value < 0
            ):
                raise ValueError(f"{name} must be finite, nonnegative and use {unit}")
        if self.opening_inventory_status is InventoryTruthStatus.UNKNOWN:
            if self.opening_inventory is not None:
                raise ValueError("UNKNOWN opening inventory cannot carry a value")
        elif self.opening_inventory is None:
            raise ValueError("known opening inventory requires a value")
        if (
            self.opening_inventory is not None
            and self.opening_inventory.value > self.capacity.value + 1e-9
        ):
            raise ValueError("opening inventory exceeds observed storage capacity")
        if self.minimum_policy_floor.value > self.capacity.value + 1e-9:
            raise ValueError("minimum floor exceeds storage capacity")
        if self.replenishment is not None and self.replenishment.truth_class not in {
            TruthClass.OBSERVED,
            TruthClass.ASSUMPTION,
        }:
            raise ValueError("replenishment requires verified input or an explicit assumption")
        return self


class ReserveDemandRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    refinery_id: UUID
    required_volume: MetricEnvelope[float]


class ReserveProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    simulation_run: SimulationRunReference
    simulation_result: SimulationResultReference
    confirmed_scenario: ConfirmedScenarioReference
    twin_snapshot: TwinSnapshotReference
    procurement_plan_id: UUID
    procurement_plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    procurement_input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    procurement_checker_version: str
    evidence: list[EvidenceFingerprintReference] = Field(min_length=1)
    assumptions: list[AssumptionFingerprintReference]

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        run = self.simulation_run
        result = self.simulation_result
        if (
            result.run_id != run.run_id
            or result.scenario_id != run.scenario_id
            or result.scenario_fingerprint != run.scenario_fingerprint
            or result.simulation_fingerprint != run.simulation_fingerprint
        ):
            raise ValueError("reserve provenance must bind one exact simulation")
        if (
            self.confirmed_scenario.scenario_id != run.scenario_id
            or self.confirmed_scenario.scenario_fingerprint != run.scenario_fingerprint
        ):
            raise ValueError("reserve provenance must bind the confirmed scenario")
        twins = {
            (run.twin_snapshot_id, run.twin_snapshot_fingerprint),
            (result.twin_snapshot_id, result.twin_snapshot_fingerprint),
            (self.twin_snapshot.snapshot_id, self.twin_snapshot.fingerprint),
        }
        if len(twins) != 1:
            raise ValueError("reserve provenance must bind one immutable twin")
        if any(item.status is not AssumptionStatus.APPROVED for item in self.assumptions):
            raise ValueError("reserve provenance requires approved assumptions")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate reserve evidence reference")
        if len({item.assumption_id for item in self.assumptions}) != len(self.assumptions):
            raise ValueError("duplicate reserve assumption reference")
        return self


class ReserveOptimisationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["reserve-input-v1"] = "reserve-input-v1"
    provenance: ReserveProvenance
    policy: ReservePolicyWeights
    starts_at: datetime
    ends_at: datetime
    interval_hours: Literal[24] = 24
    sites: list[ReserveSiteInput] = Field(min_length=1, max_length=20)
    demands: list[ReserveDemandRequirement] = Field(min_length=1, max_length=100)
    model_version: Literal["reserve-optimiser-v1"] = "reserve-optimiser-v1"
    checker_version: Literal["reserve-checker-v1"] = "reserve-checker-v1"
    tolerance: float = Field(default=1e-6, gt=0, allow_inf_nan=False)
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("reserve horizon is invalid")
        if len({item.site_id for item in self.sites}) != len(self.sites):
            raise ValueError("duplicate reserve site")
        if any(
            item.opening_inventory_status is InventoryTruthStatus.UNKNOWN for item in self.sites
        ):
            raise ValueError("UNKNOWN opening inventory blocks that reserve site")
        if self.input_fingerprint != reserve_input_fingerprint(self):
            raise ValueError("reserve input fingerprint mismatch")
        return self


class ReserveAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action_id: UUID
    site_id: UUID
    refinery_id: UUID
    route_id: UUID
    dispatch: MetricEnvelope[float]
    in_transit: MetricEnvelope[float]
    receipt: MetricEnvelope[float]
    remaining_inventory: MetricEnvelope[float]
    remaining_cover: MetricEnvelope[float]
    dispatch_at: datetime
    receipt_at: datetime
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID]
    truth_label: Literal[TruthClass.MODELED] = TruthClass.MODELED
    guidance_only: Literal[True] = True


class ReserveInventoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    site_id: UUID
    at: datetime
    inventory: MetricEnvelope[float]
    cover: MetricEnvelope[float]


class ReserveObjective(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raw_metrics: dict[str, float]
    weights: dict[str, float]
    weighted_contributions: dict[str, float]
    total: MetricEnvelope[float]

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        collections = (self.raw_metrics, self.weights, self.weighted_contributions)
        if any(
            not math.isfinite(value) or value < 0
            for values in collections
            for value in values.values()
        ):
            raise ValueError("reserve objective values must be finite and nonnegative")
        if abs(sum(self.weighted_contributions.values()) - self.total.value) > 1e-6:
            raise ValueError("reserve objective contributions do not reconcile")
        return self


class ReserveConstraintReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feasible: bool
    checked: list[str] = Field(min_length=1)
    violations: list[str] = Field(default_factory=list)


class ReserveCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    checker_version: Literal["reserve-checker-v1"] = "reserve-checker-v1"
    checked_at: datetime
    passed: bool
    opening_inventory_passed: bool
    floor_passed: bool
    conservation_passed: bool
    draw_rate_passed: bool
    dispatch_receipt_passed: bool
    transit_passed: bool
    capacity_passed: bool
    procurement_coordination_passed: bool
    shortage_passed: bool
    objective_passed: bool
    fingerprint_passed: bool
    failure_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_passed(self) -> Self:
        flags = [
            getattr(self, name)
            for name in self.__class__.model_fields
            if name.endswith("_passed") and name != "passed"
        ]
        if self.passed != (all(flags) and not self.failure_codes):
            raise ValueError("reserve checker status mismatch")
        return self


class ReserveFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=1000)
    stage: Literal["INPUT", "SOLVER", "CHECKER", "CONTRACT"]
    retryable: bool = False


class ReserveRejectedOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    site_id: UUID
    reason: ReserveRejectedReason
    constraint_id: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=1000)


class ReserveLifecycleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    current: ReservePlanLifecycle
    target: ReservePlanLifecycle
    occurred_at: datetime
    actor_id: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        allowed = {
            ReservePlanLifecycle.REQUESTED: {
                ReservePlanLifecycle.SOLVING,
                ReservePlanLifecycle.FAILED,
            },
            ReservePlanLifecycle.SOLVING: {
                ReservePlanLifecycle.CHECKING,
                ReservePlanLifecycle.FAILED,
            },
            ReservePlanLifecycle.CHECKING: {
                ReservePlanLifecycle.FEASIBLE,
                ReservePlanLifecycle.FAILED,
            },
        }
        if self.target not in allowed.get(self.current, set()):
            raise ValueError(f"invalid reserve lifecycle transition: {self.current}->{self.target}")
        return self


class ReserveSolverResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    result_id: UUID
    profile: ReservePolicyProfile
    status: SolverStatus
    metadata: SolverMetadata
    actions: list[ReserveAction] = Field(default_factory=list)
    timeline: list[ReserveInventoryPoint] = Field(default_factory=list)
    objective: ReserveObjective | None = None
    constraints: ReserveConstraintReport | None = None
    checker: ReserveCheckResult | None = None
    residual_shortage: MetricEnvelope[float] | None = None
    rejected_options: list[ReserveRejectedOption] = Field(default_factory=list)
    failure: ReserveFailure | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        usable = self.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}
        if usable and (
            self.objective is None
            or self.constraints is None
            or self.checker is None
            or not self.checker.passed
        ):
            raise ValueError("usable reserve result requires an independently checked plan")
        if self.status in {SolverStatus.INFEASIBLE, SolverStatus.ERROR} and self.actions:
            raise ValueError("infeasible or error result cannot contain reserve actions")
        return self


class ReservePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: UUID
    run_id: UUID
    procurement_plan_id: UUID
    profile: ReservePolicyProfile
    lifecycle: ReservePlanLifecycle
    input: ReserveOptimisationInput
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    result: ReserveSolverResult
    created_at: datetime
    audit_event_ids: list[UUID] = Field(min_length=1)
    recommendation_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        if self.input_fingerprint != self.input.input_fingerprint:
            raise ValueError("reserve plan input fingerprint mismatch")
        if self.procurement_plan_id != self.input.provenance.procurement_plan_id:
            raise ValueError("reserve plan procurement binding mismatch")
        if self.run_id != self.input.provenance.simulation_run.run_id:
            raise ValueError("reserve plan run binding mismatch")
        if self.profile is not self.input.policy.profile or self.result.profile is not self.profile:
            raise ValueError("reserve plan policy profile mismatch")
        if self.lifecycle is not ReservePlanLifecycle.FEASIBLE:
            raise ValueError("only feasible reserve plans are terminal usable plans")
        if self.result.status not in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}:
            raise ValueError("reserve plan requires a usable solver result")
        if self.result.checker is None or not self.result.checker.passed:
            raise ValueError("reserve plan requires a passed independent checker")
        if self.result.metadata.model_version != self.input.model_version.replace(
            "optimiser", "pyomo-highs"
        ):
            raise ValueError("reserve plan model version mismatch")
        evidence_ids = {item.evidence_id for item in self.input.provenance.evidence}
        assumption_ids = {item.assumption_id for item in self.input.provenance.assumptions}
        for action in self.result.actions:
            if not set(action.evidence_ids) <= evidence_ids:
                raise ValueError("reserve action references evidence outside the input")
            if not set(action.assumption_ids) <= assumption_ids:
                raise ValueError("reserve action references assumptions outside the input")
            quantities = (action.dispatch.value, action.in_transit.value, action.receipt.value)
            if max(quantities) - min(quantities) > self.input.tolerance:
                raise ValueError("reserve dispatch, transit and receipt must reconcile")
        expected = reserve_plan_fingerprint(self.input, self.result)
        if self.plan_fingerprint != expected:
            raise ValueError("reserve plan fingerprint mismatch")
        return self


class ReservePlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: UUID
    run_id: UUID
    procurement_plan_id: UUID
    results: list[ReserveSolverResult]
    plans: list[ReservePlan]
    failures: list[ReserveFailure]
    reused: bool = False


def reserve_input_fingerprint(value: ReserveOptimisationInput | dict[str, Any]) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else dict(to_jsonable_python(value))
    )
    payload.pop("input_fingerprint", None)
    payload.setdefault("schema_version", "reserve-input-v1")
    payload.setdefault("interval_hours", 24)
    payload.setdefault("model_version", "reserve-optimiser-v1")
    payload.setdefault("checker_version", "reserve-checker-v1")
    payload.setdefault("tolerance", 1e-6)
    return _hash(payload)


def reserve_plan_fingerprint(value: ReserveOptimisationInput, result: ReserveSolverResult) -> str:
    return _hash({"input": value.model_dump(mode="json"), "result": result.model_dump(mode="json")})


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            to_jsonable_python(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


RESERVE_OPENAPI_MODELS: tuple[type[BaseModel], ...] = (
    ReserveOptimisationInput,
    ReservePlan,
    ReservePlanResponse,
    ReserveSolverResult,
    ReserveAction,
    ReserveInventoryPoint,
    ReserveObjective,
    ReserveConstraintReport,
    ReserveCheckResult,
    ReserveFailure,
    ReserveRejectedOption,
    ReserveLifecycleTransition,
    ReservePolicyWeights,
    ReserveSiteInput,
)
