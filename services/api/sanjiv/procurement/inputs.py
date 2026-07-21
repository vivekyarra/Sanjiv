from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.contracts import (
    AssumptionStatus,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.procurement.contracts import (
    AssumptionFingerprintReference,
    ConfirmedScenarioReference,
    EvidenceFingerprintReference,
    FixedReservePolicyInput,
    HardConstraintConfiguration,
    ProcurementOptimisationInput,
    ProcurementOption,
    ProcurementProfile,
    ProcurementProvenance,
    RejectedOptionReasonCode,
    SimulationResultReference,
    SimulationRunReference,
    TransportAvailability,
    TransportAvailabilityStatus,
    procurement_optimisation_input_fingerprint,
)
from sanjiv.procurement.costs import CostConfiguration, reconcile_landed_cost
from sanjiv.scenarios.contracts import ConfirmedScenario, TwinSnapshotReference
from sanjiv.simulation.contracts import SimulationResult, SimulationRun
from sanjiv.twin.contracts import AssetKind, TwinSnapshot


class PlanningHorizon(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    starts_at: datetime
    ends_at: datetime
    interval_hours: int = Field(gt=0, le=168)


class CommercialOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    components: dict[str, float]
    capacity_ktonne: float = Field(ge=0)
    available_ktonne: float = Field(ge=0)
    evidence_ids: list[UUID] = Field(default_factory=list)
    assumption_ids: list[UUID] = Field(default_factory=list)
    transport_status: TransportAvailabilityStatus = TransportAvailabilityStatus.CANDIDATE
    commercially_confirmed: bool = False


class DemandRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    refinery_id: UUID
    interval_start: datetime
    interval_end: datetime
    baseline_throughput: MetricEnvelope[float]
    disrupted_throughput: MetricEnvelope[float]
    shortfall: MetricEnvelope[float]


class ExcludedOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    supplier_id: UUID
    grade_id: UUID
    route_id: UUID
    refinery_id: UUID
    reason: RejectedOptionReasonCode
    detail: str = Field(min_length=1, max_length=500)


class ProcurementInputBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input: ProcurementOptimisationInput | None = None
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    excluded_options: list[ExcludedOption] = Field(default_factory=list)
    assumptions_requiring_visibility: list[UUID] = Field(default_factory=list)
    evidence_coverage: dict[str, int] = Field(default_factory=dict)
    input_fingerprint: str | None = None
    demands: list[DemandRequirement] = Field(default_factory=list)


def build_procurement_input(
    run: SimulationRun,
    result: SimulationResult,
    confirmed: ConfirmedScenario,
    snapshot: TwinSnapshot,
    *,
    profile: ProcurementProfile,
    horizon: PlanningHorizon,
    reserve_policy: FixedReservePolicyInput,
    hard_constraints: HardConstraintConfiguration,
    cost_configuration: CostConfiguration,
    commercial_inputs: Mapping[tuple[UUID, UUID, UUID, UUID], CommercialOptionInput],
) -> ProcurementInputBuildResult:
    errors: list[str] = []
    if run.status.value != "COMPLETED" or run.result is None:
        errors.append("simulation run must be the exact completed run")
    if (
        result.run_id != run.run_id
        or result.provenance.simulation_fingerprint != run.simulation_fingerprint
    ):
        errors.append("simulation result is not bound to the exact run")
    if (
        confirmed.scenario_id != run.scenario_id
        or confirmed.scenario_fingerprint != run.scenario_fingerprint
    ):
        errors.append("confirmed scenario is not bound to the exact run")
    if (
        confirmed.twin_snapshot != run.twin_snapshot
        or snapshot.fingerprint != run.twin_snapshot.fingerprint
    ):
        errors.append("twin snapshot is not the exact immutable snapshot")
    if horizon.ends_at <= horizon.starts_at:
        errors.append("planning horizon is invalid")
    if errors:
        return ProcurementInputBuildResult(blocking_errors=errors)

    evidence = {item.id: item for item in snapshot.evidence_records}
    assumptions = {item.id: item for item in snapshot.assumptions}
    refs = [
        EvidenceFingerprintReference(
            evidence_id=item.id, raw_payload_hash=item.raw_payload_hash.lower()
        )
        for item in evidence.values()
    ]
    arefs = [
        AssumptionFingerprintReference(
            assumption_id=item.id,
            assumption_hash=_hash(item.model_dump(mode="json")),
            status=item.status,
        )
        for item in assumptions.values()
    ]
    if any(item.status is not AssumptionStatus.APPROVED for item in assumptions.values()):
        return ProcurementInputBuildResult(
            blocking_errors=["all source assumptions must be approved"]
        )
    node_by_id = {item.id: item for item in snapshot.nodes}
    route_by_id = {item.id: item for item in snapshot.routes}
    grade_by_id = {item.id: item for item in snapshot.grades}
    compat = {(item.grade_id, item.refinery_id): item for item in snapshot.compatibility}
    refinery_ids = {item.id for item in snapshot.nodes if item.kind is AssetKind.REFINERY}
    supplier_ids = {item.id for item in snapshot.nodes if item.kind is AssetKind.SUPPLIER}
    options: list[ProcurementOption] = []
    excluded: list[ExcludedOption] = []
    for flow in sorted(
        result.flows,
        key=lambda item: (str(item.supplier_id), str(item.grade_id), str(item.route_id)),
    ):
        route = route_by_id.get(flow.route_id)
        grade = grade_by_id.get(flow.grade_id)
        if route is None or grade is None or flow.supplier_id not in supplier_ids:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=flow.grade_id,
                    route_id=flow.route_id,
                    refinery_id=route.destination_id if route else UUID(int=0),
                    reason=RejectedOptionReasonCode.POLICY_EXCLUSION,
                    detail="asset absent from frozen snapshot",
                )
            )
            continue
        refinery_id = route.destination_id
        if refinery_id not in refinery_ids:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=flow.grade_id,
                    route_id=flow.route_id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.POLICY_EXCLUSION,
                    detail="route destination is not a refinery",
                )
            )
            continue
        compatibility = compat.get((grade.id, refinery_id))
        if compatibility is None or not compatibility.allowed:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.GRADE_INCOMPATIBLE,
                    detail="grade/refinery compatibility is not permitted",
                )
            )
            continue
        if not route.available:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.POLICY_EXCLUSION,
                    detail="route is unavailable in frozen snapshot",
                )
            )
            continue
        assert route is not None and grade is not None
        commercial = commercial_inputs.get((flow.supplier_id, grade.id, route.id, refinery_id))
        if commercial is None:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.COMMERCIAL_AVAILABILITY_UNVERIFIED,
                    detail="commercial values require evidence or an approved assumption",
                )
            )
            continue
        if not commercial.evidence_ids and not commercial.assumption_ids:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.COMMERCIAL_AVAILABILITY_UNVERIFIED,
                    detail="commercial values have no provenance",
                )
            )
            continue
        if not set(commercial.evidence_ids) <= set(evidence) or not set(
            commercial.assumption_ids
        ) <= set(assumptions):
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.COMMERCIAL_AVAILABILITY_UNVERIFIED,
                    detail="commercial provenance is absent from the immutable snapshot",
                )
            )
            continue
        try:
            cost = reconcile_landed_cost(
                commercial.components,
                configuration=cost_configuration,
                evidence_ids=commercial.evidence_ids,
                assumption_ids=commercial.assumption_ids,
                at=horizon.starts_at,
            )
            if (
                commercial.transport_status is TransportAvailabilityStatus.EVIDENCE_BACKED_CONFIRMED
                and commercial.commercially_confirmed
                and not commercial.evidence_ids
            ):
                raise ValueError("transport confirmation lacks evidence")
            start = horizon.starts_at
            end = min(
                horizon.ends_at,
                start + timedelta(hours=max(1, round(route.transit_time.value / 24))),
            )
            if end <= start:
                raise ValueError("delivery interval is outside horizon")

            option_evidence_ids = commercial.evidence_ids or [next(iter(evidence))]
            refinery_capacity = node_by_id[refinery_id].capacity
            refinery_capacity_value = (
                refinery_capacity.value
                if refinery_capacity is not None
                else commercial.capacity_ktonne
            )

            def metric(
                value: float,
                unit: str,
                name: str,
                evidence_ids: list[UUID] = option_evidence_ids,
            ) -> MetricEnvelope[float]:
                return MetricEnvelope(
                    value=value,
                    unit=unit,
                    truth_class=TruthClass.DERIVED,
                    confidence=1.0,
                    evidence_ids=evidence_ids,
                    source_refs=[SourceRef(source_id="procurement-input-builder", record_id=name)],
                    effective_at=horizon.starts_at,
                    fetched_at=horizon.starts_at,
                    computed_at=horizon.starts_at,
                    freshness_status=FreshnessStatus.CURRENT,
                    transformation="procurement.input-builder.v1",
                    model_version=cost_configuration.version,
                )

            options.append(
                ProcurementOption(
                    option_id=uuid5(
                        NAMESPACE_URL,
                        f"urn:sanjiv:procurement-option:{flow.supplier_id}:{grade.id}:{route.id}:{refinery_id}:{start.isoformat()}",
                    ),
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    delivery_window_start=start,
                    delivery_window_end=end,
                    supplier_capacity=metric(
                        commercial.capacity_ktonne, "ktonne", "supplier-capacity"
                    ),
                    commercially_available_volume=metric(
                        commercial.available_ktonne, "ktonne", "commercial-availability"
                    ),
                    route_capacity=metric(route.capacity.value, "ktonne", "route-capacity"),
                    refinery_receiving_capacity=metric(
                        refinery_capacity_value,
                        "ktonne",
                        "refinery-capacity",
                    ),
                    commodity_price=metric(
                        commercial.components["commodity_price"], "USD_per_tonne", "commodity-price"
                    ),
                    freight=metric(commercial.components["freight"], "USD_per_tonne", "freight"),
                    sanctions_permitted=grade.sanctions_state.upper()
                    not in {"SANCTIONED", "PROHIBITED"},
                    compatibility_permitted=compatibility.allowed,
                    transport_availability=TransportAvailability(
                        status=commercial.transport_status,
                        commercially_confirmed=commercial.commercially_confirmed,
                        evidence_ids=commercial.evidence_ids,
                        assumption_ids=commercial.assumption_ids,
                    ),
                    evidence_ids=sorted(set(commercial.evidence_ids)),
                    assumption_ids=sorted(set(commercial.assumption_ids)),
                    landed_cost=cost,
                    route_distance=route.distance,
                    transit_time=route.transit_time,
                    chokepoint_ids=route.chokepoint_ids,
                )
            )
        except (KeyError, ValueError) as exc:
            excluded.append(
                ExcludedOption(
                    supplier_id=flow.supplier_id,
                    grade_id=grade.id,
                    route_id=route.id,
                    refinery_id=refinery_id,
                    reason=RejectedOptionReasonCode.COMMERCIAL_AVAILABILITY_UNVERIFIED,
                    detail=str(exc),
                )
            )
    if not options:
        return ProcurementInputBuildResult(
            blocking_errors=["no eligible procurement options"], excluded_options=excluded
        )
    used_evidence = set(reserve_policy.evidence_ids)
    used_assumptions = set(reserve_policy.assumption_ids)
    for option in options:
        used_evidence.update(option.evidence_ids)
        used_evidence.update(option.transport_availability.evidence_ids)
        used_assumptions.update(option.assumption_ids)
        used_assumptions.update(option.transport_availability.assumption_ids)
    for constraint_metric in (
        hard_constraints.budget_limit,
        hard_constraints.supplier_concentration_limit,
        hard_constraints.corridor_concentration_limit,
    ):
        used_evidence.update(constraint_metric.evidence_ids)
    used_evidence.update(reserve_policy.evidence_ids)
    used_assumptions.update(reserve_policy.assumption_ids)
    refs = [item for item in refs if item.evidence_id in used_evidence]
    arefs = [item for item in arefs if item.assumption_id in used_assumptions]
    provenance = ProcurementProvenance(
        simulation_run=SimulationRunReference(
            run_id=run.run_id,
            scenario_id=run.scenario_id,
            scenario_fingerprint=run.scenario_fingerprint,
            simulation_fingerprint=run.simulation_fingerprint,
            twin_snapshot_id=snapshot.snapshot_id,
            twin_snapshot_fingerprint=snapshot.fingerprint,
            model_version=run.model_version,
        ),
        simulation_result=SimulationResultReference(
            result_id=result.result_id,
            run_id=run.run_id,
            scenario_id=run.scenario_id,
            scenario_fingerprint=run.scenario_fingerprint,
            simulation_fingerprint=run.simulation_fingerprint,
            twin_snapshot_id=snapshot.snapshot_id,
            twin_snapshot_fingerprint=snapshot.fingerprint,
        ),
        confirmed_scenario=ConfirmedScenarioReference(
            scenario_id=confirmed.scenario_id,
            scenario_fingerprint=confirmed.scenario_fingerprint,
            confirmed_at=confirmed.confirmed_at,
        ),
        twin_snapshot=TwinSnapshotReference(
            snapshot_id=snapshot.snapshot_id,
            fingerprint=snapshot.fingerprint,
            version=snapshot.version,
            effective_at=snapshot.effective_at,
        ),
        evidence=refs,
        assumptions=arefs,
    )
    built = ProcurementOptimisationInput(
        provenance=provenance,
        hard_constraints=hard_constraints,
        reserve_policy=reserve_policy,
        options=sorted(options, key=lambda item: str(item.option_id)),
        input_fingerprint="0" * 64,
    )
    built = built.model_copy(
        update={"input_fingerprint": procurement_optimisation_input_fingerprint(built)}
    )
    return ProcurementInputBuildResult(
        input=built,
        excluded_options=excluded,
        assumptions_requiring_visibility=sorted(
            {item for option in options for item in option.assumption_ids}
        ),
        input_fingerprint=built.input_fingerprint,
        evidence_coverage={"evidence": len(refs), "assumptions": len(arefs)},
    )


def _hash(value: object) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
