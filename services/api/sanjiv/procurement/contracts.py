from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import to_jsonable_python

from sanjiv.contracts import AssumptionStatus, MetricEnvelope, TruthClass
from sanjiv.scenarios.contracts import TwinSnapshotReference

SHA256_PATTERN = r"^[a-f0-9]{64}$"
MAX_OPTIONS = 500
MAX_ACTIONS = 500
MAX_REFERENCES = 2_000
BoundedConstraintId = Annotated[str, Field(min_length=1, max_length=200)]
BoundedCode = Annotated[str, Field(min_length=1, max_length=100)]
BoundedDetailKey = Annotated[str, Field(min_length=1, max_length=100)]
BoundedDetailText = Annotated[str, Field(max_length=1_000)]
BoundedDetailFloat = Annotated[float, Field(ge=-1e12, le=1e12, allow_inf_nan=False)]
BoundedDetailInt = Annotated[int, Field(ge=-1_000_000_000, le=1_000_000_000)]


class ProcurementProfile(StrEnum):
    LOWEST_COST = "LOWEST_COST"
    BALANCED = "BALANCED"
    HIGHEST_RESILIENCE = "HIGHEST_RESILIENCE"


class SolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"


class ProcurementPlanLifecycle(StrEnum):
    REQUESTED = "REQUESTED"
    SOLVING = "SOLVING"
    CHECKING = "CHECKING"
    FEASIBLE = "FEASIBLE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class ConstraintFamily(StrEnum):
    PHYSICAL = "PHYSICAL"
    SUPPLIER_CAPACITY = "SUPPLIER_CAPACITY"
    ROUTE_CAPACITY = "ROUTE_CAPACITY"
    REFINERY_CAPACITY = "REFINERY_CAPACITY"
    DELIVERY_WINDOW = "DELIVERY_WINDOW"
    BUDGET = "BUDGET"
    SANCTIONS = "SANCTIONS"
    COMPATIBILITY = "COMPATIBILITY"
    POLICY = "POLICY"
    CONCENTRATION = "CONCENTRATION"
    MASS_BALANCE = "MASS_BALANCE"


class RejectedOptionReasonCode(StrEnum):
    SANCTIONS_EXCLUSION = "SANCTIONS_EXCLUSION"
    GRADE_INCOMPATIBLE = "GRADE_INCOMPATIBLE"
    SUPPLIER_CAPACITY_EXCEEDED = "SUPPLIER_CAPACITY_EXCEEDED"
    ROUTE_CAPACITY_EXCEEDED = "ROUTE_CAPACITY_EXCEEDED"
    REFINERY_CAPACITY_EXCEEDED = "REFINERY_CAPACITY_EXCEEDED"
    DELIVERY_WINDOW_MISSED = "DELIVERY_WINDOW_MISSED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CONCENTRATION_LIMIT_EXCEEDED = "CONCENTRATION_LIMIT_EXCEEDED"
    COMMERCIAL_AVAILABILITY_UNVERIFIED = "COMMERCIAL_AVAILABILITY_UNVERIFIED"
    TRANSPORT_AVAILABILITY_UNVERIFIED = "TRANSPORT_AVAILABILITY_UNVERIFIED"
    POLICY_EXCLUSION = "POLICY_EXCLUSION"
    DOMINATED = "DOMINATED"


class TransportAvailabilityStatus(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    CANDIDATE = "CANDIDATE"
    EVIDENCE_BACKED_CONFIRMED = "EVIDENCE_BACKED_CONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"


class ProcurementFailureStage(StrEnum):
    INPUT_VALIDATION = "INPUT_VALIDATION"
    SOLVER = "SOLVER"
    INDEPENDENT_CHECK = "INDEPENDENT_CHECK"
    CONTRACT = "CONTRACT"


class EvidenceFingerprintReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: UUID
    raw_payload_hash: str = Field(pattern=SHA256_PATTERN)


class AssumptionFingerprintReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assumption_id: UUID
    assumption_hash: str = Field(pattern=SHA256_PATTERN)
    status: AssumptionStatus


class SimulationRunReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=SHA256_PATTERN)
    simulation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    twin_snapshot_id: UUID
    twin_snapshot_fingerprint: str = Field(pattern=SHA256_PATTERN)
    model_version: str = Field(min_length=1, max_length=100)


class SimulationResultReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: UUID
    run_id: UUID
    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=SHA256_PATTERN)
    simulation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    twin_snapshot_id: UUID
    twin_snapshot_fingerprint: str = Field(pattern=SHA256_PATTERN)


class ConfirmedScenarioReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: UUID
    scenario_fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at: datetime


class SolverQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["second", "fraction", "iteration"]


class SolverConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solver_name: Literal["HIGHS"] = "HIGHS"
    solver_version: str = Field(min_length=1, max_length=100)
    time_limit: SolverQuantity
    relative_mip_gap: SolverQuantity
    deterministic: Literal[True] = True
    thread_count: int = Field(default=1, ge=1, le=64)
    random_seed: int = Field(default=0, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_units(self) -> Self:
        _require_unit(self.time_limit, {"second"}, "time_limit")
        _require_unit(self.relative_mip_gap, {"fraction"}, "relative_mip_gap")
        if self.relative_mip_gap.value > 1:
            raise ValueError("relative_mip_gap must be at most 1 fraction")
        return self


class ObjectiveWeight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["weight"] = "weight"


class ObjectiveWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ProcurementProfile
    version: str = Field(min_length=1, max_length=100)
    landed_cost: ObjectiveWeight
    shortfall: ObjectiveWeight
    delay: ObjectiveWeight
    route_risk: ObjectiveWeight
    supplier_concentration: ObjectiveWeight
    corridor_concentration: ObjectiveWeight
    compatibility_penalty: ObjectiveWeight
    emissions: ObjectiveWeight

    @model_validator(mode="after")
    def require_positive_objective(self) -> Self:
        weights = (
            self.landed_cost,
            self.shortfall,
            self.delay,
            self.route_risk,
            self.supplier_concentration,
            self.corridor_concentration,
            self.compatibility_penalty,
            self.emissions,
        )
        if not any(item.value > 0 for item in weights):
            raise ValueError("at least one objective weight must be positive")
        return self


class FixedReservePolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    decision_variables_enabled: Literal[False] = False
    release_schedule_fixed: Literal[True] = True
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_REFERENCES)
    assumption_ids: list[UUID] = Field(default_factory=list, max_length=MAX_REFERENCES)

    @model_validator(mode="after")
    def require_policy_provenance(self) -> Self:
        if not self.evidence_ids and not self.assumption_ids:
            raise ValueError("fixed reserve policy requires evidence or assumption references")
        _require_unique(self.evidence_ids, "reserve policy evidence")
        _require_unique(self.assumption_ids, "reserve policy assumptions")
        return self


class HardConstraintConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1, max_length=100)
    physical_constraints_enforced: Literal[True] = True
    sanctions_exclusion_enforced: Literal[True] = True
    compatibility_exclusion_enforced: Literal[True] = True
    policy_constraints_enforced: Literal[True] = True
    reserve_policy_fixed: Literal[True] = True
    budget_limit: MetricEnvelope[float]
    supplier_concentration_limit: MetricEnvelope[float]
    corridor_concentration_limit: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_metrics(self) -> Self:
        _validate_non_negative_metric(self.budget_limit, {"USD"}, "budget_limit")
        _validate_fraction_metric(
            self.supplier_concentration_limit, "supplier_concentration_limit"
        )
        _validate_fraction_metric(
            self.corridor_concentration_limit, "corridor_concentration_limit"
        )
        return self


class TransportAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: TransportAvailabilityStatus
    candidate_reference: str | None = Field(default=None, min_length=1, max_length=200)
    commercially_confirmed: bool = False
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    assumption_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        _require_unique(self.evidence_ids, "transport evidence")
        _require_unique(self.assumption_ids, "transport assumptions")
        if self.status is TransportAvailabilityStatus.EVIDENCE_BACKED_CONFIRMED:
            if not self.commercially_confirmed or not self.evidence_ids or self.assumption_ids:
                raise ValueError(
                    "commercially confirmed transport requires verified evidence and no assumptions"
                )
        elif self.commercially_confirmed:
            raise ValueError("candidate or unverified transport cannot be commercially confirmed")
        if self.status is TransportAvailabilityStatus.CANDIDATE and not (
            self.evidence_ids or self.assumption_ids
        ):
            raise ValueError("candidate transport requires visible evidence or assumptions")
        return self


class ProcurementOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: UUID
    supplier_id: UUID
    grade_id: UUID
    route_id: UUID
    refinery_id: UUID
    delivery_window_start: datetime
    delivery_window_end: datetime
    supplier_capacity: MetricEnvelope[float]
    commercially_available_volume: MetricEnvelope[float]
    route_capacity: MetricEnvelope[float]
    refinery_receiving_capacity: MetricEnvelope[float]
    commodity_price: MetricEnvelope[float]
    freight: MetricEnvelope[float]
    sanctions_permitted: bool
    compatibility_permitted: bool
    transport_availability: TransportAvailability
    evidence_ids: list[UUID] = Field(min_length=1, max_length=MAX_REFERENCES)
    assumption_ids: list[UUID] = Field(default_factory=list, max_length=MAX_REFERENCES)

    @model_validator(mode="after")
    def validate_option(self) -> Self:
        if self.delivery_window_end <= self.delivery_window_start:
            raise ValueError("delivery window end must be after start")
        metrics = {
            "supplier_capacity": self.supplier_capacity,
            "commercially_available_volume": self.commercially_available_volume,
            "route_capacity": self.route_capacity,
            "refinery_receiving_capacity": self.refinery_receiving_capacity,
        }
        for name, metric in metrics.items():
            _validate_non_negative_metric(metric, {"ktonne"}, name)
        _validate_non_negative_metric(self.commodity_price, {"USD_per_tonne"}, "commodity_price")
        _validate_non_negative_metric(self.freight, {"USD_per_tonne"}, "freight")
        _require_unique(self.evidence_ids, "option evidence")
        _require_unique(self.assumption_ids, "option assumptions")
        all_metrics = (*metrics.values(), self.commodity_price, self.freight)
        metric_evidence = {
            evidence_id for metric in all_metrics for evidence_id in metric.evidence_ids
        }
        if not metric_evidence <= set(self.evidence_ids):
            raise ValueError("option metric evidence must be declared by the option")
        if any(metric.truth_class is TruthClass.ASSUMPTION for metric in all_metrics) and not (
            self.assumption_ids
        ):
            raise ValueError("assumption-backed commercial values require visible assumptions")
        return self


class ProcurementProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    simulation_run: SimulationRunReference
    simulation_result: SimulationResultReference
    confirmed_scenario: ConfirmedScenarioReference
    twin_snapshot: TwinSnapshotReference
    evidence: list[EvidenceFingerprintReference] = Field(
        min_length=1, max_length=MAX_REFERENCES
    )
    assumptions: list[AssumptionFingerprintReference] = Field(
        default_factory=list, max_length=MAX_REFERENCES
    )

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.simulation_result.run_id != self.simulation_run.run_id:
            raise ValueError("simulation result must belong to the exact scenario run")
        if (
            self.simulation_result.simulation_fingerprint
            != self.simulation_run.simulation_fingerprint
        ):
            raise ValueError("simulation result fingerprint must match the scenario run")
        if self.simulation_result.scenario_id != self.simulation_run.scenario_id:
            raise ValueError("simulation result scenario must match the scenario run")
        if (
            self.simulation_result.scenario_fingerprint
            != self.simulation_run.scenario_fingerprint
        ):
            raise ValueError("simulation result scenario fingerprint must match the run")
        if self.confirmed_scenario.scenario_id != self.simulation_run.scenario_id:
            raise ValueError("confirmed scenario must match the scenario run")
        if (
            self.confirmed_scenario.scenario_fingerprint
            != self.simulation_run.scenario_fingerprint
        ):
            raise ValueError("confirmed scenario fingerprint must match the scenario run")
        twin_identities = {
            (
                self.simulation_run.twin_snapshot_id,
                self.simulation_run.twin_snapshot_fingerprint,
            ),
            (
                self.simulation_result.twin_snapshot_id,
                self.simulation_result.twin_snapshot_fingerprint,
            ),
            (self.twin_snapshot.snapshot_id, self.twin_snapshot.fingerprint),
        }
        if len(twin_identities) != 1:
            raise ValueError("run, result and procurement input must bind the same twin snapshot")
        _require_unique([item.evidence_id for item in self.evidence], "input evidence")
        _require_unique([item.assumption_id for item in self.assumptions], "input assumptions")
        return self


class ProcurementOptimisationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_schema_version: Literal["procurement-input-v1"] = "procurement-input-v1"
    provenance: ProcurementProvenance
    hard_constraints: HardConstraintConfiguration
    reserve_policy: FixedReservePolicyInput
    options: list[ProcurementOption] = Field(min_length=1, max_length=MAX_OPTIONS)
    input_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        _require_unique([item.option_id for item in self.options], "procurement options")
        evidence_ids = {item.evidence_id for item in self.provenance.evidence}
        assumption_refs = {item.assumption_id: item for item in self.provenance.assumptions}
        assumption_ids = set(assumption_refs)
        referenced_evidence = set(self.reserve_policy.evidence_ids)
        referenced_assumptions = set(self.reserve_policy.assumption_ids)
        for option in self.options:
            referenced_evidence.update(option.evidence_ids)
            referenced_evidence.update(option.transport_availability.evidence_ids)
            referenced_assumptions.update(option.assumption_ids)
            referenced_assumptions.update(option.transport_availability.assumption_ids)
        for metric in (
            self.hard_constraints.budget_limit,
            self.hard_constraints.supplier_concentration_limit,
            self.hard_constraints.corridor_concentration_limit,
        ):
            referenced_evidence.update(metric.evidence_ids)
        hard_constraint_metrics = (
            self.hard_constraints.budget_limit,
            self.hard_constraints.supplier_concentration_limit,
            self.hard_constraints.corridor_concentration_limit,
        )
        if referenced_evidence != evidence_ids:
            raise ValueError(
                "procurement input evidence fingerprints must exactly match referenced evidence"
            )
        if referenced_assumptions != assumption_ids:
            raise ValueError(
                "procurement input assumption fingerprints must exactly match "
                "referenced assumptions"
            )
        if any(
            metric.truth_class is TruthClass.ASSUMPTION for metric in hard_constraint_metrics
        ) and not assumption_ids:
            raise ValueError("assumption-backed hard constraints require visible assumptions")
        if any(
            reference.status is not AssumptionStatus.APPROVED
            for reference in assumption_refs.values()
        ):
            raise ValueError("procurement input assumptions must be approved")
        expected = procurement_optimisation_input_fingerprint(self)
        if self.input_fingerprint != expected:
            raise ValueError("input fingerprint does not match canonical procurement inputs")
        return self


class ProcurementPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    optimisation_input: ProcurementOptimisationInput
    profiles: list[ProcurementProfile] = Field(min_length=1, max_length=3)
    objective_weights: list[ObjectiveWeights] = Field(min_length=1, max_length=3)
    solver_configuration: SolverConfiguration
    model_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_profiles(self) -> Self:
        _require_unique(self.profiles, "requested profiles")
        weight_profiles = [item.profile for item in self.objective_weights]
        _require_unique(weight_profiles, "objective weight profiles")
        if set(weight_profiles) != set(self.profiles):
            raise ValueError("every requested profile requires exactly one objective weight set")
        return self


class SupplierAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_id: UUID
    grade_id: UUID
    volume: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_volume(self) -> Self:
        _validate_modeled_non_negative_metric(
            self.volume, {"ktonne"}, "supplier allocation volume"
        )
        return self


class RouteAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: UUID
    volume: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_volume(self) -> Self:
        _validate_modeled_non_negative_metric(
            self.volume, {"ktonne"}, "route allocation volume"
        )
        return self


class RefineryAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    refinery_id: UUID
    grade_id: UUID
    volume: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_volume(self) -> Self:
        _validate_modeled_non_negative_metric(
            self.volume, {"ktonne"}, "refinery allocation volume"
        )
        return self


class LandedCostBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commodity_price: MetricEnvelope[float]
    quality_differential: MetricEnvelope[float]
    freight: MetricEnvelope[float]
    insurance_and_risk_premium: MetricEnvelope[float]
    port_and_handling: MetricEnvelope[float]
    route_fees: MetricEnvelope[float]
    financing: MetricEnvelope[float]
    emissions: MetricEnvelope[float]
    compatibility_penalty: MetricEnvelope[float]
    total: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_costs(self) -> Self:
        for name in self.__class__.model_fields:
            metric = getattr(self, name)
            _validate_modeled_non_negative_metric(metric, {"USD_per_tonne"}, name)
        return self


class ProcurementAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: UUID
    option_id: UUID
    action_type: Literal["PROCURE"] = "PROCURE"
    supplier: SupplierAllocation
    route: RouteAllocation
    refinery: RefineryAllocation
    delivery_window_start: datetime
    delivery_window_end: datetime
    landed_cost: LandedCostBreakdown
    evidence_ids: list[UUID] = Field(min_length=1, max_length=MAX_REFERENCES)
    assumption_ids: list[UUID] = Field(default_factory=list, max_length=MAX_REFERENCES)

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.delivery_window_end <= self.delivery_window_start:
            raise ValueError("procurement action delivery window is invalid")
        volumes = (self.supplier.volume.value, self.route.volume.value, self.refinery.volume.value)
        if max(volumes) - min(volumes) > 1e-9:
            raise ValueError("supplier, route and refinery action volumes must reconcile")
        _require_unique(self.evidence_ids, "action evidence")
        _require_unique(self.assumption_ids, "action assumptions")
        return self


class ObjectiveBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    landed_cost: MetricEnvelope[float]
    shortfall_penalty: MetricEnvelope[float]
    delay_penalty: MetricEnvelope[float]
    route_risk_penalty: MetricEnvelope[float]
    supplier_concentration_penalty: MetricEnvelope[float]
    corridor_concentration_penalty: MetricEnvelope[float]
    compatibility_penalty: MetricEnvelope[float]
    emissions_penalty: MetricEnvelope[float]
    total: MetricEnvelope[float]

    @model_validator(mode="after")
    def validate_objective(self) -> Self:
        for name in self.__class__.model_fields:
            metric = getattr(self, name)
            _validate_modeled_non_negative_metric(metric, {"objective_point"}, name)
        return self


class ConstraintViolation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str = Field(min_length=1, max_length=200)
    family: ConstraintFamily
    message: str = Field(min_length=1, max_length=1000)
    actual: MetricEnvelope[float]
    limit: MetricEnvelope[float]
    excess: MetricEnvelope[float]
    option_id: UUID | None = None

    @model_validator(mode="after")
    def validate_violation(self) -> Self:
        for name, metric in (
            ("actual", self.actual),
            ("limit", self.limit),
            ("excess", self.excess),
        ):
            _validate_finite_metric(metric, name)
        if len({self.actual.unit, self.limit.unit, self.excess.unit}) != 1:
            raise ValueError("constraint violation quantities must use the same unit")
        if self.excess.value <= 0:
            raise ValueError("constraint violation excess must be positive")
        return self


class ConstraintReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feasible: bool
    hard_constraint_version: str = Field(min_length=1, max_length=100)
    checked_families: list[ConstraintFamily] = Field(min_length=1, max_length=20)
    checked_constraint_ids: list[BoundedConstraintId] = Field(min_length=1, max_length=2_000)
    violations: list[ConstraintViolation] = Field(default_factory=list, max_length=2_000)

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        _require_unique(self.checked_families, "checked constraint families")
        _require_unique(self.checked_constraint_ids, "checked constraints")
        if self.feasible and self.violations:
            raise ValueError("feasible constraint report cannot contain violations")
        if not self.feasible and not self.violations:
            raise ValueError("infeasible constraint report requires violations")
        if self.feasible and set(self.checked_families) != set(ConstraintFamily):
            raise ValueError("feasible report must cover every hard constraint family")
        return self


class RejectedOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: UUID
    reason_codes: list[RejectedOptionReasonCode] = Field(min_length=1, max_length=20)
    violated_constraint_ids: list[BoundedConstraintId] = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_reasons(self) -> Self:
        _require_unique(self.reason_codes, "rejected option reasons")
        _require_unique(self.violated_constraint_ids, "rejected option constraints")
        return self


class SolverMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solver_name: Literal["HIGHS"] = "HIGHS"
    solver_version: str = Field(min_length=1, max_length=100)
    model_version: str = Field(min_length=1, max_length=100)
    objective_weight_version: str = Field(min_length=1, max_length=100)
    hard_constraint_version: str = Field(min_length=1, max_length=100)
    configuration: SolverConfiguration
    started_at: datetime | None = None
    completed_at: datetime | None = None
    runtime: SolverQuantity | None = None
    iterations: SolverQuantity | None = None

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        if self.completed_at is not None and self.started_at is None:
            raise ValueError("completed solver metadata requires started_at")
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("solver completed_at must not precede started_at")
        if self.runtime is not None:
            _require_unit(self.runtime, {"second"}, "runtime")
        if self.iterations is not None:
            _require_unit(self.iterations, {"iteration"}, "iterations")
        return self


class IndependentCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checker_version: str = Field(min_length=1, max_length=100)
    checked_at: datetime
    passed: bool
    mass_balance_passed: bool
    bounds_passed: bool
    objective_reconstruction_passed: bool
    sanctions_exclusion_passed: bool
    compatibility_exclusion_passed: bool
    fingerprint_reproduction_passed: bool
    reported_objective: MetricEnvelope[float]
    reconstructed_objective: MetricEnvelope[float]
    tolerance: MetricEnvelope[float]
    failure_codes: list[BoundedCode] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_check(self) -> Self:
        _validate_modeled_non_negative_metric(
            self.reported_objective, {"objective_point"}, "reported_objective"
        )
        _validate_modeled_non_negative_metric(
            self.reconstructed_objective,
            {"objective_point"},
            "reconstructed_objective",
        )
        _validate_modeled_non_negative_metric(
            self.tolerance, {"objective_point"}, "tolerance"
        )
        checks = (
            self.mass_balance_passed,
            self.bounds_passed,
            self.objective_reconstruction_passed,
            self.sanctions_exclusion_passed,
            self.compatibility_exclusion_passed,
            self.fingerprint_reproduction_passed,
        )
        expected_passed = all(checks) and not self.failure_codes
        objective_within_tolerance = (
            abs(self.reported_objective.value - self.reconstructed_objective.value)
            <= self.tolerance.value
        )
        if self.objective_reconstruction_passed != objective_within_tolerance:
            raise ValueError(
                "objective reconstruction status does not match values and tolerance"
            )
        if self.passed != expected_passed:
            raise ValueError("independent check status does not match its check results")
        if not self.passed and not self.failure_codes:
            raise ValueError("failed independent check requires failure codes")
        _require_unique(self.failure_codes, "independent check failures")
        return self


class ProcurementFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=1000)
    stage: ProcurementFailureStage
    retryable: bool = False
    details: dict[
        BoundedDetailKey,
        BoundedDetailText | BoundedDetailFloat | BoundedDetailInt | bool,
    ] = Field(
        default_factory=dict, max_length=50
    )

    @model_validator(mode="after")
    def reject_non_finite_details(self) -> Self:
        if any(
            isinstance(value, float) and not math.isfinite(value)
            for value in self.details.values()
        ):
            raise ValueError("failure details cannot contain non-finite values")
        return self


class SolverResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: UUID
    profile: ProcurementProfile
    status: SolverStatus
    metadata: SolverMetadata
    objective: ObjectiveBreakdown | None = None
    actions: list[ProcurementAction] = Field(default_factory=list, max_length=MAX_ACTIONS)
    supplier_allocations: list[SupplierAllocation] = Field(
        default_factory=list, max_length=MAX_ACTIONS
    )
    route_allocations: list[RouteAllocation] = Field(default_factory=list, max_length=MAX_ACTIONS)
    refinery_allocations: list[RefineryAllocation] = Field(
        default_factory=list, max_length=MAX_ACTIONS
    )
    constraints: ConstraintReport | None = None
    rejected_options: list[RejectedOption] = Field(default_factory=list, max_length=MAX_OPTIONS)
    independent_check: IndependentCheckResult | None = None
    failure: ProcurementFailure | None = None

    @model_validator(mode="after")
    def validate_result_state(self) -> Self:
        allocations_present = any(
            (
                self.actions,
                self.supplier_allocations,
                self.route_allocations,
                self.refinery_allocations,
            )
        )
        usable_status = self.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}
        if usable_status:
            if not self.actions or self.objective is None or self.constraints is None:
                raise ValueError(
                    "feasible solver result requires actions, objective and constraints"
                )
            if not self.constraints.feasible:
                raise ValueError("feasible solver status requires a feasible constraint report")
            if self.independent_check is None or not self.independent_check.passed:
                raise ValueError("feasible solver status requires a passed independent check")
            if self.failure is not None:
                raise ValueError("feasible solver status cannot include a failure")
        else:
            if allocations_present:
                raise ValueError("non-feasible solver result cannot contain procurement actions")
            if self.objective is not None:
                raise ValueError("non-feasible solver result cannot contain an objective")
            if self.status is SolverStatus.INFEASIBLE and (
                self.constraints is None or self.constraints.feasible
            ):
                raise ValueError("infeasible solver result requires violated constraints")
            if self.status in {SolverStatus.TIMEOUT, SolverStatus.ERROR} and self.failure is None:
                raise ValueError("timeout or error solver result requires a typed failure")
            if self.status is SolverStatus.NOT_RUN and any(
                (self.constraints, self.independent_check, self.failure)
            ):
                raise ValueError("not-run solver result cannot contain execution output")
        if self.status is SolverStatus.NOT_RUN and any(
            (
                self.metadata.started_at,
                self.metadata.completed_at,
                self.metadata.runtime,
                self.metadata.iterations,
            )
        ):
            raise ValueError("not-run solver result cannot contain execution metadata")
        if self.status is not SolverStatus.NOT_RUN and (
            self.metadata.started_at is None
            or self.metadata.completed_at is None
            or self.metadata.runtime is None
        ):
            raise ValueError("executed solver result requires complete execution metadata")
        return self


class ProcurementPlanFingerprintInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str = Field(min_length=1, max_length=100)
    profile: ProcurementProfile
    objective_weights: ObjectiveWeights
    solver_configuration: SolverConfiguration
    optimisation_input: ProcurementOptimisationInput
    optimisation_input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    simulation_run: SimulationRunReference
    simulation_result: SimulationResultReference
    confirmed_scenario: ConfirmedScenarioReference
    twin_snapshot: TwinSnapshotReference
    hard_constraint_version: str = Field(min_length=1, max_length=100)
    reserve_policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    evidence: list[EvidenceFingerprintReference] = Field(
        min_length=1, max_length=MAX_REFERENCES
    )
    assumptions: list[AssumptionFingerprintReference] = Field(
        default_factory=list, max_length=MAX_REFERENCES
    )

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.objective_weights.profile is not self.profile:
            raise ValueError("objective weights must match the fingerprint profile")
        if self.optimisation_input.input_fingerprint != self.optimisation_input_fingerprint:
            raise ValueError("fingerprint inputs must contain the exact optimisation input")
        provenance = self.optimisation_input.provenance
        if (
            self.simulation_run != provenance.simulation_run
            or self.simulation_result != provenance.simulation_result
            or self.confirmed_scenario != provenance.confirmed_scenario
            or self.twin_snapshot != provenance.twin_snapshot
            or self.evidence != provenance.evidence
            or self.assumptions != provenance.assumptions
        ):
            raise ValueError("fingerprint references must match the exact optimisation input")
        if self.hard_constraint_version != self.optimisation_input.hard_constraints.version:
            raise ValueError("hard constraint version must match the optimisation input")
        if (
            self.reserve_policy_fingerprint
            != self.optimisation_input.reserve_policy.policy_fingerprint
        ):
            raise ValueError("reserve policy fingerprint must match the optimisation input")
        ProcurementProvenance(
            simulation_run=self.simulation_run,
            simulation_result=self.simulation_result,
            confirmed_scenario=self.confirmed_scenario,
            twin_snapshot=self.twin_snapshot,
            evidence=self.evidence,
            assumptions=self.assumptions,
        )
        return self


class ProcurementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: UUID
    run_id: UUID
    profile: ProcurementProfile
    lifecycle: Literal[
        ProcurementPlanLifecycle.FEASIBLE,
        ProcurementPlanLifecycle.APPROVED,
        ProcurementPlanLifecycle.REJECTED,
        ProcurementPlanLifecycle.SUPERSEDED,
    ]
    fingerprint_inputs: ProcurementPlanFingerprintInputs
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    solver_result: SolverResult
    created_at: datetime
    audit_event_ids: list[UUID] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_operational_plan(self) -> Self:
        if self.run_id != self.fingerprint_inputs.simulation_run.run_id:
            raise ValueError("plan run must match fingerprint inputs")
        if self.profile is not self.fingerprint_inputs.profile:
            raise ValueError("plan profile must match fingerprint inputs")
        if self.solver_result.profile is not self.profile:
            raise ValueError("solver result profile must match plan profile")
        metadata = self.solver_result.metadata
        if metadata.model_version != self.fingerprint_inputs.model_version:
            raise ValueError("solver metadata model version must match fingerprint inputs")
        if metadata.objective_weight_version != self.fingerprint_inputs.objective_weights.version:
            raise ValueError("solver objective weight version must match fingerprint inputs")
        if metadata.hard_constraint_version != self.fingerprint_inputs.hard_constraint_version:
            raise ValueError("solver hard constraint version must match fingerprint inputs")
        if metadata.configuration != self.fingerprint_inputs.solver_configuration:
            raise ValueError("solver configuration must match fingerprint inputs")
        if self.solver_result.status not in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}:
            raise ValueError("operational procurement plan requires feasible solver status")
        if (
            self.solver_result.independent_check is None
            or not self.solver_result.independent_check.passed
        ):
            raise ValueError("operational procurement plan requires a passed independent check")
        if self.plan_fingerprint != procurement_plan_fingerprint(
            self.fingerprint_inputs, self.solver_result
        ):
            raise ValueError("plan fingerprint does not match canonical fingerprint inputs")
        evidence_ids = {item.evidence_id for item in self.fingerprint_inputs.evidence}
        assumption_ids = {item.assumption_id for item in self.fingerprint_inputs.assumptions}
        for action in self.solver_result.actions:
            if not set(action.evidence_ids) <= evidence_ids:
                raise ValueError("plan action references evidence outside fingerprint inputs")
            if not set(action.assumption_ids) <= assumption_ids:
                raise ValueError("plan action references assumptions outside fingerprint inputs")
        options = {
            item.option_id: item for item in self.fingerprint_inputs.optimisation_input.options
        }
        for action in self.solver_result.actions:
            option = options.get(action.option_id)
            if option is None:
                raise ValueError("plan action must reference an exact optimisation input option")
            if not option.sanctions_permitted or not option.compatibility_permitted:
                raise ValueError("plan action cannot select a sanctioned or incompatible option")
            if (
                action.supplier.supplier_id != option.supplier_id
                or action.supplier.grade_id != option.grade_id
                or action.route.route_id != option.route_id
                or action.refinery.refinery_id != option.refinery_id
                or action.refinery.grade_id != option.grade_id
            ):
                raise ValueError("plan action allocations must match the referenced input option")
            if (
                action.delivery_window_start < option.delivery_window_start
                or action.delivery_window_end > option.delivery_window_end
            ):
                raise ValueError("plan action delivery window must fit the input option")
            volume = action.supplier.volume.value
            capacity = min(
                option.supplier_capacity.value,
                option.commercially_available_volume.value,
                option.route_capacity.value,
                option.refinery_receiving_capacity.value,
            )
            if volume > capacity:
                raise ValueError("plan action volume exceeds the referenced option capacity")
        _require_unique(self.audit_event_ids, "plan audit events")
        return self


class ProcurementPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    run_id: UUID
    results: list[SolverResult] = Field(min_length=1, max_length=3)
    plans: list[ProcurementPlan] = Field(default_factory=list, max_length=3)
    failures: list[ProcurementFailure] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        _require_unique([item.profile for item in self.results], "response result profiles")
        _require_unique([item.profile for item in self.plans], "response plan profiles")
        feasible_profiles = {
            item.profile
            for item in self.results
            if item.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}
        }
        if {item.profile for item in self.plans} != feasible_profiles:
            raise ValueError("plans must exist exactly for independently checked feasible results")
        if any(item.run_id != self.run_id for item in self.plans):
            raise ValueError("response plans must belong to the requested run")
        return self


class ProcurementLifecycleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current: ProcurementPlanLifecycle
    target: ProcurementPlanLifecycle

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        allowed: dict[ProcurementPlanLifecycle, set[ProcurementPlanLifecycle]] = {
            ProcurementPlanLifecycle.REQUESTED: {
                ProcurementPlanLifecycle.SOLVING,
                ProcurementPlanLifecycle.FAILED,
            },
            ProcurementPlanLifecycle.SOLVING: {
                ProcurementPlanLifecycle.CHECKING,
                ProcurementPlanLifecycle.FAILED,
            },
            ProcurementPlanLifecycle.CHECKING: {
                ProcurementPlanLifecycle.FEASIBLE,
                ProcurementPlanLifecycle.FAILED,
            },
            ProcurementPlanLifecycle.FEASIBLE: {
                ProcurementPlanLifecycle.APPROVED,
                ProcurementPlanLifecycle.REJECTED,
                ProcurementPlanLifecycle.SUPERSEDED,
            },
            ProcurementPlanLifecycle.APPROVED: {ProcurementPlanLifecycle.SUPERSEDED},
            ProcurementPlanLifecycle.REJECTED: set(),
            ProcurementPlanLifecycle.FAILED: set(),
            ProcurementPlanLifecycle.SUPERSEDED: set(),
        }
        if self.target not in allowed[self.current]:
            raise ValueError(
                f"invalid procurement lifecycle transition: {self.current}->{self.target}"
            )
        return self


def procurement_optimisation_input_fingerprint(
    value: ProcurementOptimisationInput | dict[str, Any],
) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    payload.pop("input_fingerprint", None)
    payload.setdefault("input_schema_version", "procurement-input-v1")
    return _sha256(payload)


def procurement_plan_fingerprint(
    inputs: ProcurementPlanFingerprintInputs, solver_result: SolverResult
) -> str:
    return _sha256(
        {
            "fingerprint_inputs": inputs.model_dump(mode="json"),
            "solver_result": solver_result.model_dump(mode="json"),
        }
    )


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        to_jsonable_python(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_finite_metric(metric: MetricEnvelope[float], field: str) -> None:
    if not math.isfinite(metric.value):
        raise ValueError(f"{field} must be finite")
    if len(metric.evidence_ids) > MAX_REFERENCES or len(metric.source_refs) > MAX_REFERENCES:
        raise ValueError(f"{field} provenance exceeds the bounded reference limit")


def _validate_non_negative_metric(
    metric: MetricEnvelope[float], allowed_units: set[str], field: str
) -> None:
    _validate_finite_metric(metric, field)
    if metric.value < 0:
        raise ValueError(f"{field} must not be negative")
    _require_unit(metric, allowed_units, field)


def _validate_fraction_metric(metric: MetricEnvelope[float], field: str) -> None:
    _validate_non_negative_metric(metric, {"fraction"}, field)
    if metric.value > 1:
        raise ValueError(f"{field} must be at most 1 fraction")


def _validate_modeled_non_negative_metric(
    metric: MetricEnvelope[float], allowed_units: set[str], field: str
) -> None:
    _validate_non_negative_metric(metric, allowed_units, field)
    if metric.truth_class is not TruthClass.MODELED:
        raise ValueError(f"{field} optimiser output must use truth class MODELED")


def _require_unit(value: Any, allowed_units: set[str], field: str) -> None:
    if value.unit not in allowed_units:
        allowed = ", ".join(sorted(allowed_units))
        raise ValueError(f"{field} unit must be one of: {allowed}")


def _require_unique(values: list[Any], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")


PROCUREMENT_OPENAPI_MODELS: tuple[type[BaseModel], ...] = (
    ProcurementOptimisationInput,
    ProcurementPlanRequest,
    ProcurementPlanResponse,
    ProcurementPlan,
    ProcurementAction,
    SupplierAllocation,
    RouteAllocation,
    RefineryAllocation,
    ObjectiveBreakdown,
    LandedCostBreakdown,
    ConstraintReport,
    ConstraintViolation,
    RejectedOption,
    SolverMetadata,
    SolverResult,
    IndependentCheckResult,
    ProcurementLifecycleTransition,
    ProcurementFailure,
    ProcurementPlanFingerprintInputs,
)
