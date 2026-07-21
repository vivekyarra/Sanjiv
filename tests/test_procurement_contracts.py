from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sanjiv.contracts import (
    AssumptionStatus,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.main import app
from sanjiv.procurement.contracts import (
    AssumptionFingerprintReference,
    ConfirmedScenarioReference,
    ConstraintFamily,
    ConstraintReport,
    ConstraintViolation,
    EvidenceFingerprintReference,
    FixedReservePolicyInput,
    HardConstraintConfiguration,
    IndependentCheckResult,
    LandedCostBreakdown,
    ObjectiveBreakdown,
    ObjectiveWeight,
    ObjectiveWeights,
    ProcurementAction,
    ProcurementLifecycleTransition,
    ProcurementOptimisationInput,
    ProcurementOption,
    ProcurementPlan,
    ProcurementPlanFingerprintInputs,
    ProcurementPlanLifecycle,
    ProcurementPlanRequest,
    ProcurementProfile,
    RefineryAllocation,
    RejectedOption,
    RejectedOptionReasonCode,
    RouteAllocation,
    SimulationResultReference,
    SimulationRunReference,
    SolverConfiguration,
    SolverMetadata,
    SolverQuantity,
    SolverResult,
    SolverStatus,
    SupplierAllocation,
    TransportAvailability,
    TransportAvailabilityStatus,
    procurement_optimisation_input_fingerprint,
    procurement_plan_fingerprint,
)
from sanjiv.scenarios.contracts import TwinSnapshotReference

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000101")
ASSUMPTION_ID = UUID("00000000-0000-0000-0000-000000000201")
RUN_ID = UUID("00000000-0000-0000-0000-000000000301")
SCENARIO_ID = UUID("00000000-0000-0000-0000-000000000302")
RESULT_ID = UUID("00000000-0000-0000-0000-000000000303")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000304")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def metric(
    value: float,
    unit: str,
    *,
    truth_class: TruthClass = TruthClass.ASSUMPTION,
) -> MetricEnvelope[float]:
    return MetricEnvelope[float](
        value=value,
        unit=unit,
        truth_class=truth_class,
        confidence=0.7,
        evidence_ids=[EVIDENCE_ID],
        source_refs=[SourceRef(source_id="phase-4-contract-test", record_id="fixture-1")],
        effective_at=NOW,
        fetched_at=NOW,
        computed_at=NOW,
        freshness_status=FreshnessStatus.CURRENT,
        transformation="phase-4.contract-test.v1",
        model_version="procurement-contract-1.0.0",
    )


def modeled_metric(value: float, unit: str) -> MetricEnvelope[float]:
    return metric(value, unit, truth_class=TruthClass.MODELED)


def solver_configuration() -> SolverConfiguration:
    return SolverConfiguration(
        solver_version="contract-only",
        time_limit=SolverQuantity(value=30, unit="second"),
        relative_mip_gap=SolverQuantity(value=0.001, unit="fraction"),
    )


def objective_weights(
    profile: ProcurementProfile = ProcurementProfile.BALANCED,
) -> ObjectiveWeights:
    weight = ObjectiveWeight(value=1, unit="weight")
    return ObjectiveWeights(
        profile=profile,
        version=f"phase-4-{profile.value.casefold()}-v1",
        landed_cost=weight,
        shortfall=weight,
        delay=weight,
        route_risk=weight,
        supplier_concentration=weight,
        corridor_concentration=weight,
        compatibility_penalty=weight,
        emissions=weight,
    )


def optimisation_input_payload() -> dict[str, Any]:
    supplier_id, grade_id, route_id, refinery_id, option_id = (uuid4() for _ in range(5))
    run = SimulationRunReference(
        run_id=RUN_ID,
        scenario_id=SCENARIO_ID,
        scenario_fingerprint=HASH_A,
        simulation_fingerprint=HASH_B,
        twin_snapshot_id=SNAPSHOT_ID,
        twin_snapshot_fingerprint=HASH_C,
        model_version="simulation-1.0.0",
    )
    result = SimulationResultReference(
        result_id=RESULT_ID,
        run_id=RUN_ID,
        scenario_id=SCENARIO_ID,
        scenario_fingerprint=HASH_A,
        simulation_fingerprint=HASH_B,
        twin_snapshot_id=SNAPSHOT_ID,
        twin_snapshot_fingerprint=HASH_C,
    )
    option = ProcurementOption(
        option_id=option_id,
        supplier_id=supplier_id,
        grade_id=grade_id,
        route_id=route_id,
        refinery_id=refinery_id,
        delivery_window_start=NOW,
        delivery_window_end=NOW + timedelta(days=7),
        supplier_capacity=metric(100, "ktonne"),
        commercially_available_volume=metric(80, "ktonne"),
        route_capacity=metric(90, "ktonne"),
        refinery_receiving_capacity=metric(75, "ktonne"),
        commodity_price=metric(500, "USD_per_tonne"),
        freight=metric(20, "USD_per_tonne"),
        sanctions_permitted=True,
        compatibility_permitted=True,
        transport_availability=TransportAvailability(
            status=TransportAvailabilityStatus.CANDIDATE,
            candidate_reference="candidate-vessel-class-aframax",
            assumption_ids=[ASSUMPTION_ID],
        ),
        evidence_ids=[EVIDENCE_ID],
        assumption_ids=[ASSUMPTION_ID],
    )
    payload: dict[str, Any] = {
        "provenance": {
            "simulation_run": run,
            "simulation_result": result,
            "confirmed_scenario": ConfirmedScenarioReference(
                scenario_id=SCENARIO_ID,
                scenario_fingerprint=HASH_A,
                confirmed_at=NOW,
            ),
            "twin_snapshot": TwinSnapshotReference(
                snapshot_id=SNAPSHOT_ID,
                fingerprint=HASH_C,
                version="twin-v1",
                effective_at=NOW,
            ),
            "evidence": [
                EvidenceFingerprintReference(
                    evidence_id=EVIDENCE_ID,
                    raw_payload_hash=HASH_D,
                )
            ],
            "assumptions": [
                AssumptionFingerprintReference(
                    assumption_id=ASSUMPTION_ID,
                    assumption_hash=HASH_A,
                    status=AssumptionStatus.APPROVED,
                )
            ],
        },
        "hard_constraints": HardConstraintConfiguration(
            version="hard-constraints-v1",
            budget_limit=metric(1_000_000, "USD"),
            supplier_concentration_limit=metric(0.5, "fraction"),
            corridor_concentration_limit=metric(0.5, "fraction"),
        ),
        "reserve_policy": FixedReservePolicyInput(
            policy_id="fixed-phase-4-policy",
            policy_version="v1",
            policy_fingerprint=HASH_D,
            assumption_ids=[ASSUMPTION_ID],
        ),
        "options": [option],
    }
    payload = json.loads(
        json.dumps(
            payload,
            default=lambda value: value.model_dump(mode="json"),
        )
    )
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    return payload


def optimisation_input() -> ProcurementOptimisationInput:
    return ProcurementOptimisationInput.model_validate(optimisation_input_payload())


def fingerprint_inputs(
    input_data: ProcurementOptimisationInput | None = None,
) -> ProcurementPlanFingerprintInputs:
    input_data = input_data or optimisation_input()
    return ProcurementPlanFingerprintInputs(
        model_version="procurement-model-1.0.0",
        profile=ProcurementProfile.BALANCED,
        objective_weights=objective_weights(),
        solver_configuration=solver_configuration(),
        optimisation_input=input_data,
        optimisation_input_fingerprint=input_data.input_fingerprint,
        simulation_run=input_data.provenance.simulation_run,
        simulation_result=input_data.provenance.simulation_result,
        confirmed_scenario=input_data.provenance.confirmed_scenario,
        twin_snapshot=input_data.provenance.twin_snapshot,
        hard_constraint_version=input_data.hard_constraints.version,
        reserve_policy_fingerprint=input_data.reserve_policy.policy_fingerprint,
        evidence=input_data.provenance.evidence,
        assumptions=input_data.provenance.assumptions,
    )


def objective_breakdown() -> ObjectiveBreakdown:
    values = {
        name: modeled_metric(1, "objective_point")
        for name in (
            "landed_cost",
            "shortfall_penalty",
            "delay_penalty",
            "route_risk_penalty",
            "supplier_concentration_penalty",
            "corridor_concentration_penalty",
            "compatibility_penalty",
            "emissions_penalty",
            "total",
        )
    }
    return ObjectiveBreakdown(**values)


def landed_cost() -> LandedCostBreakdown:
    values = {name: modeled_metric(1, "USD_per_tonne") for name in LandedCostBreakdown.model_fields}
    return LandedCostBreakdown(**values)


def passed_check() -> IndependentCheckResult:
    return IndependentCheckResult(
        checker_version="checker-1.0.0",
        checked_at=NOW,
        passed=True,
        mass_balance_passed=True,
        bounds_passed=True,
        objective_reconstruction_passed=True,
        sanctions_exclusion_passed=True,
        compatibility_exclusion_passed=True,
        fingerprint_reproduction_passed=True,
        reported_objective=modeled_metric(1, "objective_point"),
        reconstructed_objective=modeled_metric(1, "objective_point"),
        tolerance=modeled_metric(0.001, "objective_point"),
    )


def feasible_solver_result(
    input_data: ProcurementOptimisationInput | None = None,
) -> SolverResult:
    source = (input_data or optimisation_input()).options[0]
    supplier = SupplierAllocation(
        supplier_id=source.supplier_id,
        grade_id=source.grade_id,
        volume=modeled_metric(10, "ktonne"),
    )
    route = RouteAllocation(route_id=source.route_id, volume=modeled_metric(10, "ktonne"))
    refinery = RefineryAllocation(
        refinery_id=source.refinery_id,
        grade_id=source.grade_id,
        volume=modeled_metric(10, "ktonne"),
    )
    action = ProcurementAction(
        action_id=uuid4(),
        option_id=source.option_id,
        supplier=supplier,
        route=route,
        refinery=refinery,
        delivery_window_start=NOW,
        delivery_window_end=NOW + timedelta(days=7),
        landed_cost=landed_cost(),
        evidence_ids=[EVIDENCE_ID],
        assumption_ids=[ASSUMPTION_ID],
    )
    return SolverResult(
        result_id=uuid4(),
        profile=ProcurementProfile.BALANCED,
        status=SolverStatus.FEASIBLE,
        metadata=SolverMetadata(
            solver_version="contract-only",
            model_version="procurement-model-1.0.0",
            objective_weight_version=objective_weights().version,
            hard_constraint_version="hard-constraints-v1",
            configuration=solver_configuration(),
            started_at=NOW,
            completed_at=NOW,
            runtime=SolverQuantity(value=0, unit="second"),
            iterations=SolverQuantity(value=0, unit="iteration"),
        ),
        objective=objective_breakdown(),
        actions=[action],
        supplier_allocations=[supplier],
        route_allocations=[route],
        refinery_allocations=[refinery],
        constraints=ConstraintReport(
            feasible=True,
            hard_constraint_version="hard-constraints-v1",
            checked_families=list(ConstraintFamily),
            checked_constraint_ids=["mass_balance", "sanctions", "compatibility"],
        ),
        independent_check=passed_check(),
    )


def test_procurement_input_rejects_invalid_units_negative_and_non_finite_quantities() -> None:
    payload = optimisation_input_payload()
    payload["options"][0]["supplier_capacity"] = metric(1, "barrel")
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    with pytest.raises(ValidationError, match="supplier_capacity unit"):
        ProcurementOptimisationInput.model_validate(payload)

    for value in (-1, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            SupplierAllocation(
                supplier_id=uuid4(),
                grade_id=uuid4(),
                volume=modeled_metric(value, "ktonne"),
            )


def test_profiles_statuses_and_lifecycle_transitions_are_closed() -> None:
    request = {
        "optimisation_input": optimisation_input(),
        "profiles": ["FASTEST"],
        "objective_weights": [objective_weights()],
        "solver_configuration": solver_configuration(),
        "model_version": "procurement-model-1.0.0",
    }
    with pytest.raises(ValidationError):
        ProcurementPlanRequest.model_validate(request)
    with pytest.raises(ValidationError):
        SolverResult.model_validate(
            {
                "result_id": uuid4(),
                "profile": "BALANCED",
                "status": "SOLVED",
                "metadata": feasible_solver_result().metadata,
            }
        )
    ProcurementLifecycleTransition(
        current=ProcurementPlanLifecycle.REQUESTED,
        target=ProcurementPlanLifecycle.SOLVING,
    )
    with pytest.raises(ValidationError, match="invalid procurement lifecycle transition"):
        ProcurementLifecycleTransition(
            current=ProcurementPlanLifecycle.REQUESTED,
            target=ProcurementPlanLifecycle.APPROVED,
        )


def test_infeasible_result_cannot_contain_actions() -> None:
    payload = feasible_solver_result().model_dump()
    payload["status"] = SolverStatus.INFEASIBLE
    with pytest.raises(ValidationError, match="cannot contain procurement actions"):
        SolverResult.model_validate(payload)


def test_failed_independent_check_blocks_feasible_result_and_plan() -> None:
    failed = passed_check().model_copy(
        update={
            "passed": False,
            "sanctions_exclusion_passed": False,
            "failure_codes": ["SANCTIONS_CHECK_FAILED"],
        }
    )
    payload = feasible_solver_result().model_dump()
    payload["independent_check"] = failed
    with pytest.raises(ValidationError, match="requires a passed independent check"):
        SolverResult.model_validate(payload)


def test_independent_check_rejects_forged_objective_reconstruction_status() -> None:
    payload = passed_check().model_dump()
    payload["reconstructed_objective"]["value"] = 10
    with pytest.raises(ValidationError, match="objective reconstruction status"):
        IndependentCheckResult.model_validate(payload)


def test_feasible_report_must_cover_every_hard_constraint_family() -> None:
    with pytest.raises(ValidationError, match="every hard constraint family"):
        ConstraintReport(
            feasible=True,
            hard_constraint_version="hard-constraints-v1",
            checked_families=[ConstraintFamily.PHYSICAL],
            checked_constraint_ids=["mass_balance"],
        )


def test_not_run_result_cannot_claim_execution_metadata() -> None:
    with pytest.raises(ValidationError, match="cannot contain execution metadata"):
        SolverResult(
            result_id=uuid4(),
            profile=ProcurementProfile.BALANCED,
            status=SolverStatus.NOT_RUN,
            metadata=feasible_solver_result().metadata,
        )


def test_sanctioned_and_incompatible_options_have_structured_rejections() -> None:
    payload = optimisation_input_payload()
    payload["options"][0]["sanctions_permitted"] = False
    payload["options"][0]["compatibility_permitted"] = False
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    option = ProcurementOptimisationInput.model_validate(payload).options[0]
    rejected = RejectedOption(
        option_id=option.option_id,
        reason_codes=[
            RejectedOptionReasonCode.SANCTIONS_EXCLUSION,
            RejectedOptionReasonCode.GRADE_INCOMPATIBLE,
        ],
        violated_constraint_ids=["sanctions:exact-id", "compatibility:grade-refinery"],
        explanation="Hard sanctions and grade compatibility constraints exclude this option.",
    )
    assert not option.sanctions_permitted and not option.compatibility_permitted
    assert len(rejected.reason_codes) == 2


def test_candidate_transport_cannot_claim_commercial_confirmation() -> None:
    with pytest.raises(ValidationError, match="cannot be commercially confirmed"):
        TransportAvailability(
            status=TransportAvailabilityStatus.CANDIDATE,
            candidate_reference="candidate-only",
            commercially_confirmed=True,
            evidence_ids=[EVIDENCE_ID],
        )


def test_simulation_and_twin_fingerprints_are_mandatory_and_consistent() -> None:
    payload = optimisation_input_payload()
    del payload["provenance"]["simulation_run"]["simulation_fingerprint"]
    with pytest.raises(ValidationError):
        ProcurementOptimisationInput.model_validate(payload)

    payload = optimisation_input_payload()
    payload["provenance"]["simulation_result"]["twin_snapshot_fingerprint"] = HASH_D
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    with pytest.raises(ValidationError, match="same twin snapshot"):
        ProcurementOptimisationInput.model_validate(payload)


def test_assumption_and_evidence_fingerprint_sets_must_be_complete() -> None:
    payload = optimisation_input_payload()
    payload["provenance"]["assumptions"] = []
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    with pytest.raises(ValidationError, match="assumption fingerprints must exactly match"):
        ProcurementOptimisationInput.model_validate(payload)

    payload = optimisation_input_payload()
    payload["provenance"]["evidence"] = []
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    with pytest.raises(ValidationError):
        ProcurementOptimisationInput.model_validate(payload)


def test_fingerprints_are_stable_for_canonical_json() -> None:
    payload = optimisation_input_payload()
    first = procurement_optimisation_input_fingerprint(payload)
    reordered = {key: payload[key] for key in reversed(payload)}
    assert procurement_optimisation_input_fingerprint(reordered) == first
    inputs = fingerprint_inputs()
    result = feasible_solver_result()
    assert procurement_plan_fingerprint(inputs, result) == procurement_plan_fingerprint(
        inputs, result
    )


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("model_version", "procurement-model-2.0.0"),
        ("profile", ProcurementProfile.HIGHEST_RESILIENCE),
        ("optimisation_input_fingerprint", HASH_D),
        ("hard_constraint_version", "hard-constraints-v2"),
        ("reserve_policy_fingerprint", HASH_A),
    ],
)
def test_plan_fingerprint_changes_after_material_scalar_change(
    field: str, replacement: object
) -> None:
    inputs = fingerprint_inputs()
    changed = inputs.model_copy(update={field: replacement})
    result = feasible_solver_result()
    assert procurement_plan_fingerprint(changed, result) != procurement_plan_fingerprint(
        inputs, result
    )


def test_plan_fingerprint_changes_after_nested_identity_or_configuration_change() -> None:
    inputs = fingerprint_inputs()
    variants = (
        inputs.model_copy(
            update={
                "simulation_run": inputs.simulation_run.model_copy(
                    update={"simulation_fingerprint": HASH_D}
                )
            }
        ),
        inputs.model_copy(
            update={
                "twin_snapshot": inputs.twin_snapshot.model_copy(update={"fingerprint": HASH_D})
            }
        ),
        inputs.model_copy(
            update={
                "objective_weights": inputs.objective_weights.model_copy(
                    update={"version": "balanced-v2"}
                )
            }
        ),
        inputs.model_copy(
            update={
                "solver_configuration": inputs.solver_configuration.model_copy(
                    update={"random_seed": 42}
                )
            }
        ),
        inputs.model_copy(
            update={
                "evidence": [inputs.evidence[0].model_copy(update={"raw_payload_hash": HASH_A})]
            }
        ),
        inputs.model_copy(
            update={
                "assumptions": [
                    inputs.assumptions[0].model_copy(update={"assumption_hash": HASH_B})
                ]
            }
        ),
    )
    result = feasible_solver_result()
    baseline = procurement_plan_fingerprint(inputs, result)
    assert all(procurement_plan_fingerprint(variant, result) != baseline for variant in variants)


def test_valid_independently_checked_plan_is_fingerprint_bound() -> None:
    inputs = fingerprint_inputs()
    result = feasible_solver_result(inputs.optimisation_input)
    plan = ProcurementPlan(
        plan_id=uuid4(),
        run_id=RUN_ID,
        profile=ProcurementProfile.BALANCED,
        lifecycle=ProcurementPlanLifecycle.FEASIBLE,
        fingerprint_inputs=inputs,
        plan_fingerprint=procurement_plan_fingerprint(inputs, result),
        solver_result=result,
        created_at=NOW,
        audit_event_ids=[uuid4()],
    )
    assert plan.solver_result.independent_check is not None
    with pytest.raises(ValidationError, match="plan fingerprint"):
        ProcurementPlan.model_validate(
            {**plan.model_dump(), "plan_fingerprint": HASH_D}
        )


def test_plan_fingerprint_changes_after_material_solver_output_change() -> None:
    inputs = fingerprint_inputs()
    result = feasible_solver_result()
    changed = result.model_copy(update={"result_id": uuid4()})
    assert procurement_plan_fingerprint(inputs, changed) != procurement_plan_fingerprint(
        inputs, result
    )


def test_plan_rejects_action_for_sanctioned_or_incompatible_input_option() -> None:
    payload = optimisation_input_payload()
    payload["options"][0]["sanctions_permitted"] = False
    payload["options"][0]["compatibility_permitted"] = False
    payload["input_fingerprint"] = procurement_optimisation_input_fingerprint(payload)
    input_data = ProcurementOptimisationInput.model_validate(payload)
    inputs = fingerprint_inputs(input_data)
    result = feasible_solver_result(input_data)
    with pytest.raises(ValidationError, match="sanctioned or incompatible"):
        ProcurementPlan(
            plan_id=uuid4(),
            run_id=RUN_ID,
            profile=ProcurementProfile.BALANCED,
            lifecycle=ProcurementPlanLifecycle.FEASIBLE,
            fingerprint_inputs=inputs,
            plan_fingerprint=procurement_plan_fingerprint(inputs, result),
            solver_result=result,
            created_at=NOW,
            audit_event_ids=[uuid4()],
        )


def test_infeasible_result_requires_structured_constraint_diagnostics() -> None:
    violation = ConstraintViolation(
        constraint_id="supplier:capacity",
        family=ConstraintFamily.SUPPLIER_CAPACITY,
        message="Requested volume exceeds supplier capacity.",
        actual=modeled_metric(11, "ktonne"),
        limit=modeled_metric(10, "ktonne"),
        excess=modeled_metric(1, "ktonne"),
    )
    result = SolverResult(
        result_id=uuid4(),
        profile=ProcurementProfile.BALANCED,
        status=SolverStatus.INFEASIBLE,
        metadata=feasible_solver_result().metadata,
        constraints=ConstraintReport(
            feasible=False,
            hard_constraint_version="hard-constraints-v1",
            checked_families=[ConstraintFamily.SUPPLIER_CAPACITY],
            checked_constraint_ids=["supplier:capacity"],
            violations=[violation],
        ),
    )
    assert not result.constraints.feasible if result.constraints else False


def test_input_fingerprint_changes_after_any_material_option_change() -> None:
    payload = optimisation_input_payload()
    baseline = procurement_optimisation_input_fingerprint(payload)
    changed = deepcopy(payload)
    changed["options"][0]["commodity_price"]["value"] = 501
    assert procurement_optimisation_input_fingerprint(changed) != baseline


def test_openapi_exposes_completed_procurement_routes_and_schemas() -> None:
    schema = app.openapi()
    expected = {
        "ProcurementOptimisationInput",
        "ProcurementPlanRequest",
        "ProcurementProfile",
        "ProcurementPlan",
        "ProcurementAction",
        "SupplierAllocation",
        "RouteAllocation",
        "RefineryAllocation",
        "ObjectiveBreakdown",
        "LandedCostBreakdown",
        "ConstraintReport",
        "ConstraintViolation",
        "RejectedOption",
        "SolverMetadata",
        "SolverResult",
        "IndependentCheckResult",
        "ProcurementPlanLifecycle",
        "ProcurementFailure",
        "ProcurementPlanFingerprintInputs",
        "EvidenceFingerprintReference",
        "AssumptionFingerprintReference",
        "SimulationRunReference",
        "SimulationResultReference",
        "TwinSnapshotReference",
    }
    assert expected <= set(schema["components"]["schemas"])
    assert "/api/v1/scenario-runs/{run_id}/procurement-plans" in schema["paths"]
    assert "/api/v1/procurement-plans/{plan_id}" in schema["paths"]
