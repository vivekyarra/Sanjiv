from __future__ import annotations

from datetime import UTC, datetime

import pytest
from procurement_helpers import solved_procurement
from sanjiv.procurement.checker import independent_check
from sanjiv.procurement.contracts import ProcurementProfile, SolverStatus
from sanjiv.procurement.service import ProcurementExecutionRequest


@pytest.mark.asyncio
async def test_all_profiles_are_sequentially_solved_checked_and_distinct() -> None:
    _, _, response = await solved_procurement()
    assert [item.profile for item in response.results] == list(ProcurementProfile)
    assert len(response.plans) == 3
    assert all(
        item.status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE} for item in response.results
    )
    assert all(
        item.independent_check and item.independent_check.passed for item in response.results
    )
    assert all(
        item.delivered_volume and item.delivered_volume.value > 0 for item in response.results
    )
    assert len({item.plan_fingerprint for item in response.plans}) == 3
    assert all(
        action.assumption_ids for plan in response.plans for action in plan.solver_result.actions
    )


@pytest.mark.asyncio
async def test_independent_checker_rejects_forged_capacity_and_objective() -> None:
    _, _, response = await solved_procurement()
    plan = response.plans[0]
    quantities = {
        action.option_id: action.supplier.volume.value for action in plan.solver_result.actions
    }
    first = plan.fingerprint_inputs.optimisation_input.options[0]
    quantities[first.option_id] = first.commercially_available_volume.value + 1
    shortages = {
        item.refinery_id: 0.0 for item in plan.fingerprint_inputs.optimisation_input.demands
    }
    check, _, report = independent_check(
        plan.fingerprint_inputs.optimisation_input,
        plan.fingerprint_inputs.objective_weights,
        quantities,
        shortages,
        plan.solver_result.objective.total.value + 100,
        checked_at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    assert not check.passed
    assert "HARD_CONSTRAINT" in check.failure_codes
    assert "OBJECTIVE_RECONSTRUCTION" in check.failure_codes
    assert not report.feasible


@pytest.mark.asyncio
async def test_exact_fingerprint_reuse_is_immutable() -> None:
    service, run, first = await solved_procurement()
    second = await service.create(
        run.run_id,
        ProcurementExecutionRequest(),
        idempotency_key="different-key-same-input",
        actor_id="phase-4-test-operator",
    )
    assert second.reused
    assert [item.plan_fingerprint for item in second.plans] == [
        item.plan_fingerprint for item in first.plans
    ]
    assert [item.plan_id for item in second.plans] == [item.plan_id for item in first.plans]
