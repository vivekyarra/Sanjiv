from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from reserve_helpers import solved_reserve
from sanjiv.procurement.contracts import SolverStatus
from sanjiv.reserve.checker import independent_reserve_check
from sanjiv.reserve.contracts import (
    InventoryTruthStatus,
    ReserveLifecycleTransition,
    ReservePlanLifecycle,
    ReservePolicyProfile,
)
from sanjiv.reserve.inputs import build_reserve_input
from sanjiv.reserve.profiles import reserve_policy
from sanjiv.reserve.service import ReserveExecutionRequest


@pytest.mark.asyncio
async def test_all_reserve_profiles_are_deterministic_checked_and_coordinated() -> None:
    _, _, procurement, response = await solved_reserve()
    assert [item.profile for item in response.results] == list(ReservePolicyProfile)
    assert len(response.plans) == 4
    assert all(item.status is SolverStatus.OPTIMAL for item in response.results)
    assert all(item.checker and item.checker.passed for item in response.results)
    assert all(
        plan.input.provenance.procurement_plan_fingerprint == procurement.plan_fingerprint
        for plan in response.plans
    )
    assert len({item.plan_fingerprint for item in response.plans}) == 4


@pytest.mark.asyncio
async def test_no_reserve_use_forces_zero_release_and_preserves_mass() -> None:
    _, _, _, response = await solved_reserve()
    plan = next(
        item for item in response.plans if item.profile is ReservePolicyProfile.NO_RESERVE_USE
    )
    assert plan.result.actions == []
    ending_points = {
        point.site_id: point for point in plan.result.timeline if point.at == plan.input.ends_at
    }
    assert len(plan.result.timeline) == len(plan.input.sites) * 2
    for site in plan.input.sites:
        assert site.opening_inventory is not None
        assert ending_points[site.site_id].inventory.value == pytest.approx(
            site.opening_inventory.value
        )
    assert plan.result.residual_shortage is not None
    assert plan.result.residual_shortage.value == pytest.approx(
        sum(item.required_volume.value for item in plan.input.demands)
    )


@pytest.mark.asyncio
async def test_public_capacity_does_not_infer_opening_fill_and_expiry_blocks() -> None:
    service, _, procurement, response = await solved_reserve()
    plan = response.plans[1]
    assert all(site.capacity.truth_class.value == "OBSERVED" for site in plan.input.sites)
    assert all(
        site.opening_inventory_status is InventoryTruthStatus.UNEXPIRED_ASSUMPTION
        for site in plan.input.sites
    )
    assert all(
        site.opening_inventory and site.opening_inventory.value != site.capacity.value
        for site in plan.input.sites
    )
    snapshot = service.scenario_service.twin_service.current()
    with pytest.raises(ValueError, match="expired"):
        build_reserve_input(
            procurement,
            snapshot,
            reserve_policy(ReservePolicyProfile.BALANCED),
            at=plan.input.ends_at + timedelta(days=400),
        )


@pytest.mark.asyncio
async def test_unknown_inventory_and_fingerprint_forgery_are_rejected() -> None:
    _, _, _, response = await solved_reserve()
    reserve_input = response.plans[1].input
    unknown = reserve_input.sites[0].model_copy(
        update={"opening_inventory": None, "opening_inventory_status": InventoryTruthStatus.UNKNOWN}
    )
    with pytest.raises(ValidationError, match="UNKNOWN opening inventory"):
        reserve_input.model_copy(update={"sites": [unknown, *reserve_input.sites[1:]]}).model_dump()
        type(reserve_input).model_validate(
            {
                **reserve_input.model_dump(mode="json"),
                "sites": [
                    unknown.model_dump(mode="json"),
                    *[item.model_dump(mode="json") for item in reserve_input.sites[1:]],
                ],
            }
        )
    with pytest.raises(ValidationError, match="fingerprint"):
        type(reserve_input).model_validate(
            {**reserve_input.model_dump(mode="json"), "input_fingerprint": "0" * 64}
        )


@pytest.mark.asyncio
async def test_checker_rejects_forged_floor_capacity_and_objective() -> None:
    _, _, _, response = await solved_reserve()
    plan = response.plans[1]
    dispatch = {site.site_id: 0.0 for site in plan.input.sites}
    first = plan.input.sites[0]
    assert first.opening_inventory is not None
    dispatch[first.site_id] = first.opening_inventory.value + 1
    shortages = {item.refinery_id: item.required_volume.value for item in plan.input.demands}
    check, _, report = independent_reserve_check(
        plan.input, dispatch, shortages, plan.result.objective.total.value + 100
    )
    assert not check.passed
    assert not check.floor_passed
    assert not check.objective_passed
    assert not report.feasible


@pytest.mark.asyncio
async def test_reserve_exact_fingerprint_reuse_is_immutable() -> None:
    service, run, procurement, first = await solved_reserve()
    second = await service.create(
        run.run_id,
        ReserveExecutionRequest(procurement_plan_id=procurement.plan_id),
        idempotency_key="different-reserve-key",
        actor_id="phase-5-test-operator",
    )
    assert second.reused
    assert [item.plan_id for item in second.plans] == [item.plan_id for item in first.plans]


def test_invalid_reserve_lifecycle_transition_is_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid reserve lifecycle"):
        ReserveLifecycleTransition(
            current=ReservePlanLifecycle.FEASIBLE,
            target=ReservePlanLifecycle.SOLVING,
            occurred_at=datetime.now(UTC),
            actor_id="test-operator",
        )
