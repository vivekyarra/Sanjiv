from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, SourceRef, TruthClass
from sanjiv.reserve.contracts import (
    ReserveCheckResult,
    ReserveConstraintReport,
    ReserveObjective,
    ReserveOptimisationInput,
    ReservePolicyProfile,
    reserve_input_fingerprint,
)

CHECKER_VERSION = "reserve-checker-v1"


def independent_reserve_check(
    optimisation_input: ReserveOptimisationInput,
    dispatch: dict[UUID, float],
    shortages: dict[UUID, float],
    reported_objective: float,
    *,
    checked_at: datetime | None = None,
) -> tuple[ReserveCheckResult, ReserveObjective, ReserveConstraintReport]:
    at = checked_at or datetime.now(UTC)
    tolerance = optimisation_input.tolerance
    days = (optimisation_input.ends_at - optimisation_input.starts_at).total_seconds() / 86400
    demand = {item.refinery_id: item.required_volume.value for item in optimisation_input.demands}
    receipts: defaultdict[UUID, float] = defaultdict(float)
    failures: set[str] = set()
    opening_ok = floor_ok = conservation_ok = draw_ok = transit_ok = capacity_ok = (
        coordination_ok
    ) = True
    raw = {
        "shortage": sum(shortages.values()),
        "reserve_depletion": 0.0,
        "logistics_cost": 0.0,
        "future_vulnerability": 0.0,
    }
    for site in optimisation_input.sites:
        quantity = dispatch.get(site.site_id, 0.0)
        opening = site.opening_inventory.value if site.opening_inventory else math.nan
        replenishment = site.replenishment.value if site.replenishment else 0.0
        remaining = opening + replenishment - quantity
        if (
            not all(math.isfinite(value) for value in (quantity, opening, replenishment, remaining))
            or quantity < -tolerance
        ):
            opening_ok = False
            failures.add("INVALID_OPENING_OR_DISPATCH")
            continue
        if (
            remaining < site.minimum_policy_floor.value - tolerance
            or remaining > site.capacity.value + tolerance
        ):
            floor_ok = False
            failures.add("POLICY_FLOOR_OR_STORAGE")
        if abs(opening + replenishment - quantity - remaining) > tolerance:
            conservation_ok = False
            failures.add("STOCK_CONSERVATION")
        if quantity > site.draw_rate_limit.value * days + tolerance:
            draw_ok = False
            failures.add("DRAW_RATE")
        if (
            quantity > site.route_capacity.value * days + tolerance
            or site.transit_time.value > days + tolerance
        ):
            transit_ok = False
            failures.add("ROUTE_OR_TRANSIT")
        if (
            quantity + site.procurement_committed_receipts.value
            > site.refinery_receipt_capacity.value + tolerance
        ):
            coordination_ok = False
            failures.add("PROCUREMENT_SHARED_CAPACITY")
        if (
            optimisation_input.policy.profile is ReservePolicyProfile.NO_RESERVE_USE
            and quantity > tolerance
        ):
            capacity_ok = False
            failures.add("NO_RESERVE_USE")
        receipts[site.refinery_id] += quantity
        raw["reserve_depletion"] += quantity
        raw["logistics_cost"] += quantity * site.logistics_cost.value / 1000.0
        raw["future_vulnerability"] += quantity / max(site.capacity.value, 1.0)
    shortage_ok = True
    for refinery_id, required in demand.items():
        shortage = shortages.get(refinery_id, 0.0)
        if (
            not math.isfinite(shortage)
            or shortage < -tolerance
            or abs(receipts[refinery_id] + shortage - required) > tolerance
        ):
            shortage_ok = False
            failures.add("RECEIPT_SHORTAGE_RECONCILIATION")
    weights = {
        "shortage": optimisation_input.policy.shortage,
        "reserve_depletion": optimisation_input.policy.reserve_depletion,
        "logistics_cost": optimisation_input.policy.logistics_cost,
        "future_vulnerability": optimisation_input.policy.future_vulnerability,
    }
    weighted = {key: raw[key] * weights[key] for key in raw}
    reconstructed = sum(weighted.values())
    objective_ok = (
        math.isfinite(reported_objective) and abs(reported_objective - reconstructed) <= tolerance
    )
    if not objective_ok:
        failures.add("OBJECTIVE_RECONSTRUCTION")
    fingerprint_ok = optimisation_input.input_fingerprint == reserve_input_fingerprint(
        optimisation_input
    )
    if not fingerprint_ok:
        failures.add("FINGERPRINT_MISMATCH")
    dispatch_receipt_ok = conservation_ok and transit_ok
    passed = (
        all(
            (
                opening_ok,
                floor_ok,
                conservation_ok,
                draw_ok,
                dispatch_receipt_ok,
                transit_ok,
                capacity_ok,
                coordination_ok,
                shortage_ok,
                objective_ok,
                fingerprint_ok,
            )
        )
        and not failures
    )
    check = ReserveCheckResult(
        checked_at=at,
        passed=passed,
        opening_inventory_passed=opening_ok,
        floor_passed=floor_ok,
        conservation_passed=conservation_ok,
        draw_rate_passed=draw_ok,
        dispatch_receipt_passed=dispatch_receipt_ok,
        transit_passed=transit_ok,
        capacity_passed=capacity_ok,
        procurement_coordination_passed=coordination_ok,
        shortage_passed=shortage_ok,
        objective_passed=objective_ok,
        fingerprint_passed=fingerprint_ok,
        failure_codes=sorted(failures),
    )
    objective = ReserveObjective(
        raw_metrics=raw,
        weights=weights,
        weighted_contributions=weighted,
        total=_metric(reconstructed, "objective_point", at, optimisation_input),
    )
    checked = [
        "opening_inventory",
        "storage_capacity",
        "minimum_policy_floor",
        "stock_conservation",
        "draw_rate",
        "route_capacity",
        "transit_delay",
        "refinery_receipt",
        "procurement_shared_capacity",
        "receipt_reconciliation",
        "no_hidden_losses",
        "no_hidden_replenishment",
        "no_reserve_use",
        "fingerprint",
    ]
    return (
        check,
        objective,
        ReserveConstraintReport(feasible=passed, checked=checked, violations=sorted(failures)),
    )


def _metric(
    value: float, unit: str, at: datetime, optimisation_input: ReserveOptimisationInput
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=max(0.0, float(value)),
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=1.0,
        evidence_ids=[item.evidence_id for item in optimisation_input.provenance.evidence],
        source_refs=[SourceRef(source_id="reserve-checker", record_id=CHECKER_VERSION)],
        effective_at=at,
        fetched_at=at,
        computed_at=at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=CHECKER_VERSION,
        model_version=CHECKER_VERSION,
    )
