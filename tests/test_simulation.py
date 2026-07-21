from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sanjiv.contracts import Assumption
from sanjiv.contracts.governance import AssumptionStatus
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmScenarioRequest,
    DisruptionEffect,
    DisruptionTarget,
    DisruptionTargetType,
    DisruptionType,
    DurationQuantity,
    DurationUnit,
    PercentageQuantity,
    ScenarioCompileMode,
    StructuredScenarioInput,
)
from sanjiv.scenarios.service import ScenarioDomainError
from sanjiv.simulation.contracts import (
    SimulationConfiguration,
    SimulationStatus,
    StartSimulationRequest,
)
from sanjiv.simulation.engine import run_no_action_simulation, simulation_fingerprint
from sanjiv.twin.contracts import AssetKind
from scenario_helpers import NOW, confirmed_text, memory_service


@pytest.mark.asyncio
async def test_hormuz_closure_is_deterministic_mass_conserving_no_action() -> None:
    service = memory_service()
    confirmed = await confirmed_text(service)
    snapshot = service.twin_service.current()
    config = SimulationConfiguration()
    run_id = confirmed.scenario_id
    first = run_no_action_simulation(run_id, confirmed, snapshot, config, computed_at=NOW)
    second = run_no_action_simulation(run_id, confirmed, snapshot, config, computed_at=NOW)
    first_payload = first.model_dump(mode="json", exclude={"runtime_ms"})
    second_payload = second.model_dump(mode="json", exclude={"runtime_ms"})
    assert first_payload == second_payload
    assert first.baseline.total_supply.value == 250
    assert first.baseline.shortfall.value == 0
    assert first.disrupted.shortfall.value == 200
    assert first.disrupted.cumulative_shortfall.value == sum(
        item.shortfall.value for item in first.timeline
    )
    assert first.inventory_status == "UNKNOWN"
    assert first.inventory_trajectories == []
    assert all(value for value in first.invariants.model_dump().values() if isinstance(value, bool))


@pytest.mark.asyncio
async def test_full_closure_forces_every_hormuz_path_flow_to_zero() -> None:
    service = memory_service()
    confirmed = await confirmed_text(service)
    result = run_no_action_simulation(
        confirmed.scenario_id,
        confirmed,
        service.twin_service.current(),
        SimulationConfiguration(),
        computed_at=NOW,
    )
    assert all(
        flow.disrupted_flow.value == 0
        for flow in result.flows
        if "hormuz" in flow.route_canonical_id
    )
    assert result.invariants.closed_routes_zero
    assert result.invariants.route_capacities_respected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Reduce Hormuz capacity by 50% for 21 days.",
        "Reduce supplier Iraq Baseline Supplier availability by 30% for 10 days.",
        "Close Hormuz and reduce Jamnagar throughput by 20% for 14 days.",
    ],
)
async def test_route_supplier_and_refinery_reductions_respect_constraints(text: str) -> None:
    service = memory_service()
    confirmed = await confirmed_text(service, text)
    result = run_no_action_simulation(
        confirmed.scenario_id,
        confirmed,
        service.twin_service.current(),
        SimulationConfiguration(),
        computed_at=NOW,
    )
    assert result.disrupted.cumulative_shortfall.value > 0
    assert result.invariants.route_capacities_respected
    assert result.invariants.supplier_limits_respected
    assert result.invariants.refinery_limits_respected
    assert result.invariants.grade_compatibility_respected
    assert result.invariants.mass_conserved


@pytest.mark.asyncio
async def test_fingerprint_reuse_requires_complete_exact_match() -> None:
    service = memory_service()
    confirmed = await confirmed_text(service)
    first = await service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="run-first",
        now=NOW,
    )
    completed = await service.execute(first.run_id)
    reused = await service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="run-second",
        now=NOW,
    )
    assert completed.status is SimulationStatus.COMPLETED
    assert reused.run_id == completed.run_id
    assert reused.reused_result

    changed = SimulationConfiguration(uncertainty_reduction_delta=5)
    assert simulation_fingerprint(confirmed, changed) != completed.simulation_fingerprint


@pytest.mark.asyncio
async def test_unconfirmed_scenario_cannot_run_and_queued_run_can_cancel() -> None:
    service = memory_service()
    snapshot = service.twin_service.current()
    with pytest.raises(ScenarioDomainError, match="unconfirmed"):
        await service.start(
            StartSimulationRequest(scenario_id=snapshot.snapshot_id),
            idempotency_key="unconfirmed-run",
        )
    confirmed = await confirmed_text(service)
    queued = await service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="cancel-run",
        now=NOW,
    )
    cancelled = await service.cancel(queued.run_id, idempotency_key="cancel-request")
    assert cancelled.status is SimulationStatus.CANCELLED
    assert cancelled.result is None
    assert (await service.progress(queued.run_id))[-1].status is SimulationStatus.CANCELLED


@pytest.mark.asyncio
async def test_failure_returns_typed_result_without_fabrication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = memory_service()
    confirmed = await confirmed_text(service)
    queued = await service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="failure-run",
        now=NOW,
    )

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ValueError("unsafe model input")

    monkeypatch.setattr("sanjiv.scenarios.service.run_no_action_simulation", fail)
    failed = await service.execute(queued.run_id)
    assert failed.status is SimulationStatus.FAILED
    assert failed.failure is not None
    assert failed.failure.code == "SIMULATION_INVARIANT_FAILURE"
    assert failed.result is None


@pytest.mark.asyncio
async def test_runtime_and_uncertainty_are_measured_and_deterministic() -> None:
    service = memory_service()
    confirmed = await confirmed_text(service)
    result = run_no_action_simulation(
        confirmed.scenario_id,
        confirmed,
        service.twin_service.current(),
        SimulationConfiguration(),
        computed_at=datetime(2026, 7, 21, 13, tzinfo=UTC),
    )
    assert result.runtime_ms >= 0
    assert result.uncertainty.lower_bound.value <= result.uncertainty.central.value
    assert result.uncertainty.central.value <= result.uncertainty.upper_bound.value
    assert not result.uncertainty.probability_claimed
    assert result.uncertainty.variation_method == "BOUNDED_SENSITIVITY"


@pytest.mark.asyncio
async def test_inventory_exists_only_from_visible_approved_assumption() -> None:
    service = memory_service()
    snapshot = service.twin_service.current()
    refinery = next(node for node in snapshot.nodes if node.kind is AssetKind.REFINERY)
    assumption = Assumption(
        key=f"initial_inventory:{refinery.id}",
        value=25.0,
        unit="ktonne",
        rationale="Exercise the explicit Phase 3 inventory boundary.",
        source_gap="Current private refinery inventory is unavailable.",
        owner="phase-3-test-operator",
        entered_at=NOW,
        effective_at=NOW,
        expires_at=NOW + timedelta(days=30),
        approved_at=NOW,
        approved_by="phase-3-test-operator",
        status=AssumptionStatus.APPROVED,
    )
    structured = StructuredScenarioInput(
        scenario_name="Hormuz closure with explicit inventory",
        twin_snapshot_id=snapshot.snapshot_id,
        disruption_start=NOW,
        disruption_duration=DurationQuantity(value=14, unit=DurationUnit.DAY),
        disruptions=[
            DisruptionEffect(
                disruption_type=DisruptionType.CHOKEPOINT_CLOSURE,
                target=DisruptionTarget(
                    target_type=DisruptionTargetType.CHOKEPOINT,
                    requested_identifier="Strait of Hormuz",
                ),
                capacity_reduction=PercentageQuantity(value=100),
            )
        ],
        assumptions=[assumption],
    )
    compiled = await service.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.STRUCTURED_FORM,
            twin_snapshot_id=snapshot.snapshot_id,
            structured=structured,
        ),
        idempotency_key="inventory-compile",
        now=NOW,
    )
    assert compiled.candidate is not None
    confirmed = await service.confirm(
        compiled.candidate.scenario_id,
        ConfirmScenarioRequest(confirming_identity="phase-3-test-operator"),
        idempotency_key="inventory-confirm",
        now=NOW,
    )
    result = run_no_action_simulation(
        confirmed.scenario_id,
        confirmed,
        snapshot,
        SimulationConfiguration(),
        computed_at=NOW,
    )
    assert result.inventory_status == "ASSUMPTION_DEPENDENT"
    assert result.inventory_trajectories[0].assumption_id == assumption.id
    assert all(
        point.ending_inventory.value >= 0
        for trajectory in result.inventory_trajectories
        for point in trajectory.points
    )
