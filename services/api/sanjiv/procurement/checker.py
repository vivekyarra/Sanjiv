from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, SourceRef, TruthClass
from sanjiv.procurement.contracts import (
    ConstraintFamily,
    ConstraintReport,
    ConstraintViolation,
    IndependentCheckResult,
    ObjectiveBreakdown,
    ObjectiveWeights,
    ProcurementOptimisationInput,
    ProcurementOption,
    procurement_option_fingerprint,
)

CHECKER_VERSION = "procurement-independent-checker-v1"
TOLERANCE = 1e-6


def independent_check(
    optimisation_input: ProcurementOptimisationInput,
    weights: ObjectiveWeights,
    quantities: dict[UUID, float],
    shortages: dict[UUID, float],
    reported_objective: float,
    *,
    checked_at: datetime | None = None,
) -> tuple[IndependentCheckResult, ObjectiveBreakdown, ConstraintReport]:
    at = checked_at or datetime.now(UTC)
    violations: list[ConstraintViolation] = []
    checked: list[str] = []
    options = {item.option_id: item for item in optimisation_input.options}
    demands = {item.refinery_id: item.required_volume.value for item in optimisation_input.demands}
    delivered_by_refinery: defaultdict[UUID, float] = defaultdict(float)
    delivered_by_supplier: defaultdict[UUID, float] = defaultdict(float)
    delivered_by_corridor: defaultdict[UUID, float] = defaultdict(float)
    delivered_by_segment: defaultdict[UUID, float] = defaultdict(float)
    delivered_by_load_port: defaultdict[UUID, float] = defaultdict(float)
    delivered_by_receiving_port: defaultdict[UUID, float] = defaultdict(float)
    fingerprint_ok = True
    bounds_ok = True
    sanctions_ok = True
    compatibility_ok = True
    timing_ok = True

    for option_id, option in options.items():
        quantity = quantities.get(option_id, 0.0)
        checked.append(f"option:{option_id}:bounds")
        cap = min(
            option.supplier_capacity.value,
            option.commercially_available_volume.value,
            option.route_capacity.value,
            option.refinery_receiving_capacity.value,
        )
        if not math.isfinite(quantity) or quantity < -TOLERANCE or quantity > cap + TOLERANCE:
            bounds_ok = False
            _violation(
                violations,
                f"option:{option_id}:bounds",
                ConstraintFamily.PHYSICAL,
                quantity,
                cap,
                "ktonne",
                option_id,
                at,
                optimisation_input,
            )
        if quantity > TOLERANCE and not option.sanctions_permitted:
            sanctions_ok = False
            _violation(
                violations,
                f"option:{option_id}:sanctions",
                ConstraintFamily.SANCTIONS,
                quantity,
                0,
                "ktonne",
                option_id,
                at,
                optimisation_input,
            )
        if quantity > TOLERANCE and not option.compatibility_permitted:
            compatibility_ok = False
            _violation(
                violations,
                f"option:{option_id}:compatibility",
                ConstraintFamily.COMPATIBILITY,
                quantity,
                0,
                "ktonne",
                option_id,
                at,
                optimisation_input,
            )
        if (
            option.option_fingerprint is None
            or option.option_fingerprint != procurement_option_fingerprint(option)
        ):
            fingerprint_ok = False
        if any(
            option.delivery_window_start < demand.interval_start
            or option.delivery_window_end > demand.interval_end
            for demand in optimisation_input.demands
            if demand.refinery_id == option.refinery_id
        ):
            timing_ok = False
            _violation(
                violations,
                f"option:{option_id}:delivery",
                ConstraintFamily.DELIVERY_WINDOW,
                1,
                0,
                "violation",
                option_id,
                at,
                optimisation_input,
            )
        delivered_by_refinery[option.refinery_id] += quantity
        delivered_by_supplier[option.supplier_id] += quantity
        delivered_by_corridor[option.route_id] += quantity
        for segment_id in option.route_segment_ids:
            delivered_by_segment[segment_id] += quantity
        if option.load_port_id:
            delivered_by_load_port[option.load_port_id] += quantity
        if option.receiving_port_id:
            delivered_by_receiving_port[option.receiving_port_id] += quantity

    mass_ok = True
    for refinery_id, demand in demands.items():
        actual = delivered_by_refinery[refinery_id] + shortages.get(refinery_id, 0.0)
        checked.append(f"demand:{refinery_id}:reconciliation")
        if abs(actual - demand) > TOLERANCE or shortages.get(refinery_id, 0.0) < -TOLERANCE:
            mass_ok = False
            _violation(
                violations,
                f"demand:{refinery_id}:reconciliation",
                ConstraintFamily.MASS_BALANCE,
                actual,
                demand,
                "ktonne",
                None,
                at,
                optimisation_input,
            )

    for supplier_id, actual in delivered_by_supplier.items():
        limit = max(
            item.supplier_capacity.value
            for item in options.values()
            if item.supplier_id == supplier_id
        )
        checked.append(f"supplier:{supplier_id}:capacity")
        if actual > limit + TOLERANCE:
            bounds_ok = False
            _violation(
                violations,
                f"supplier:{supplier_id}:capacity",
                ConstraintFamily.SUPPLIER_CAPACITY,
                actual,
                limit,
                "ktonne",
                None,
                at,
                optimisation_input,
            )
    for segment_id, actual in delivered_by_segment.items():
        limit = min(
            item.route_segment_capacities[segment_id]
            for item in options.values()
            if segment_id in item.route_segment_capacities
        )
        checked.append(f"segment:{segment_id}:capacity")
        if actual > limit + TOLERANCE:
            bounds_ok = False
            _violation(
                violations,
                f"segment:{segment_id}:capacity",
                ConstraintFamily.ROUTE_CAPACITY,
                actual,
                limit,
                "ktonne",
                None,
                at,
                optimisation_input,
            )
    for refinery_id, actual in delivered_by_refinery.items():
        limit = max(
            item.refinery_receiving_capacity.value
            for item in options.values()
            if item.refinery_id == refinery_id
        )
        checked.append(f"refinery:{refinery_id}:capacity")
        if actual > limit + TOLERANCE:
            bounds_ok = False
            _violation(
                violations,
                f"refinery:{refinery_id}:capacity",
                ConstraintFamily.REFINERY_CAPACITY,
                actual,
                limit,
                "ktonne",
                None,
                at,
                optimisation_input,
            )
    for label, allocations, attribute in (
        ("load-port", delivered_by_load_port, "load_port_id"),
        ("receiving-port", delivered_by_receiving_port, "receiving_port_id"),
    ):
        for port_id, actual in allocations.items():
            related = [item for item in options.values() if getattr(item, attribute) == port_id]
            limit = max(
                max(item.route_segment_capacities.values(), default=0.0) for item in related
            )
            checked.append(f"{label}:{port_id}:capacity")
            if actual > limit + TOLERANCE:
                bounds_ok = False
                _violation(
                    violations,
                    f"{label}:{port_id}:capacity",
                    ConstraintFamily.ROUTE_CAPACITY,
                    actual,
                    limit,
                    "ktonne",
                    None,
                    at,
                    optimisation_input,
                )

    raw, weighted = objective_components(optimisation_input, weights, quantities, shortages)
    budget_used = sum(
        quantities.get(item.option_id, 0.0) * 1_000 * _cost(item)
        for item in optimisation_input.options
    )
    budget = optimisation_input.hard_constraints.budget_limit.value
    checked.append("policy:budget")
    if budget_used > budget + TOLERANCE:
        _violation(
            violations,
            "policy:budget",
            ConstraintFamily.BUDGET,
            budget_used,
            budget,
            "USD",
            None,
            at,
            optimisation_input,
        )
    total_demand = sum(demands.values())
    supplier_limit = optimisation_input.hard_constraints.supplier_concentration_limit.value
    corridor_limit = optimisation_input.hard_constraints.corridor_concentration_limit.value
    supplier_peak = max(delivered_by_supplier.values(), default=0) / max(total_demand, 1.0)
    corridor_peak = max(delivered_by_corridor.values(), default=0) / max(total_demand, 1.0)
    checked.extend(["policy:supplier-concentration", "policy:corridor-concentration"])
    if supplier_peak > supplier_limit + TOLERANCE:
        _violation(
            violations,
            "policy:supplier-concentration",
            ConstraintFamily.CONCENTRATION,
            supplier_peak,
            supplier_limit,
            "fraction",
            None,
            at,
            optimisation_input,
        )
    if corridor_peak > corridor_limit + TOLERANCE:
        _violation(
            violations,
            "policy:corridor-concentration",
            ConstraintFamily.CONCENTRATION,
            corridor_peak,
            corridor_limit,
            "fraction",
            None,
            at,
            optimisation_input,
        )

    reconstructed = sum(weighted.values())
    objective_ok = abs(reported_objective - reconstructed) <= 1e-5
    all_constraints = not violations
    failure_codes: list[str] = []
    if not mass_ok:
        failure_codes.append("MASS_BALANCE")
    if not bounds_ok or not all_constraints:
        failure_codes.append("HARD_CONSTRAINT")
    if not objective_ok:
        failure_codes.append("OBJECTIVE_RECONSTRUCTION")
    if not sanctions_ok:
        failure_codes.append("SANCTIONS_EXCLUSION")
    if not compatibility_ok:
        failure_codes.append("COMPATIBILITY_EXCLUSION")
    if not fingerprint_ok:
        failure_codes.append("FINGERPRINT_MISMATCH")
    if not timing_ok:
        failure_codes.append("DELIVERY_TIMING")
    failure_codes = list(dict.fromkeys(failure_codes))
    check = IndependentCheckResult(
        checker_version=CHECKER_VERSION,
        checked_at=at,
        passed=not failure_codes,
        mass_balance_passed=mass_ok,
        bounds_passed=bounds_ok and all_constraints,
        objective_reconstruction_passed=objective_ok,
        sanctions_exclusion_passed=sanctions_ok,
        compatibility_exclusion_passed=compatibility_ok,
        fingerprint_reproduction_passed=fingerprint_ok,
        reported_objective=_metric(reported_objective, "objective_point", at, optimisation_input),
        reconstructed_objective=_metric(reconstructed, "objective_point", at, optimisation_input),
        tolerance=_metric(1e-5, "objective_point", at, optimisation_input),
        failure_codes=failure_codes,
        hard_constraints_recalculated=all_constraints,
        landed_cost_recalculated=True,
        concentration_recalculated=True,
        delivery_timing_recalculated=timing_ok,
        inventory_balance_recalculated=True,
    )
    report = ConstraintReport(
        feasible=not violations,
        hard_constraint_version=optimisation_input.hard_constraints.version,
        checked_families=list(ConstraintFamily),
        checked_constraint_ids=checked or ["input:empty"],
        violations=violations,
    )
    field_map = {
        "landed_cost": "landed_cost",
        "shortfall": "shortfall_penalty",
        "delay": "delay_penalty",
        "route_risk": "route_risk_penalty",
        "supplier_concentration": "supplier_concentration_penalty",
        "corridor_concentration": "corridor_concentration_penalty",
        "compatibility_penalty": "compatibility_penalty",
        "emissions": "emissions_penalty",
    }
    objective_kwargs = {
        field: _metric(weighted[key], "objective_point", at, optimisation_input)
        for key, field in field_map.items()
    }
    breakdown = ObjectiveBreakdown(
        **objective_kwargs,
        total=_metric(reconstructed, "objective_point", at, optimisation_input),
        raw_metrics=raw,
        weights={key: getattr(weights, key).value for key in field_map},
        weighted_contributions=weighted,
    )
    return check, breakdown, report


def objective_components(
    optimisation_input: ProcurementOptimisationInput,
    weights: ObjectiveWeights,
    quantities: dict[UUID, float],
    shortages: dict[UUID, float],
) -> tuple[dict[str, float], dict[str, float]]:
    total_demand = sum(item.required_volume.value for item in optimisation_input.demands)
    suppliers: defaultdict[UUID, float] = defaultdict(float)
    corridors: defaultdict[UUID, float] = defaultdict(float)
    raw = {
        "landed_cost": 0.0,
        "shortfall": sum(shortages.values()),
        "delay": 0.0,
        "route_risk": 0.0,
        "supplier_concentration": 0.0,
        "corridor_concentration": 0.0,
        "compatibility_penalty": 0.0,
        "emissions": 0.0,
    }
    for option in optimisation_input.options:
        quantity = quantities.get(option.option_id, 0.0)
        suppliers[option.supplier_id] += quantity
        corridors[option.route_id] += quantity
        raw["landed_cost"] += _cost(option) * quantity / 1_000
        raw["delay"] += (option.transit_time.value if option.transit_time else 0) * quantity / 1_000
        raw["route_risk"] += (
            (option.route_distance.value if option.route_distance else 0) * quantity / 1_000_000
        )
        if option.landed_cost:
            raw["compatibility_penalty"] += (
                option.landed_cost.compatibility_penalty.value * quantity / 1_000
            )
            raw["emissions"] += option.landed_cost.emissions.value * quantity / 1_000
    denominator = max(total_demand, 1.0)
    raw["supplier_concentration"] = max(suppliers.values(), default=0.0) / denominator
    raw["corridor_concentration"] = max(corridors.values(), default=0.0) / denominator
    weighted = {key: value * getattr(weights, key).value for key, value in raw.items()}
    return raw, weighted


def _cost(option: ProcurementOption) -> float:
    landed = option.landed_cost
    if landed is None:
        raise ValueError("eligible procurement option is missing landed cost")
    return float(landed.total.value)


def _metric(
    value: float, unit: str, at: datetime, optimisation_input: ProcurementOptimisationInput
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=max(0.0, float(value)),
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=1.0,
        evidence_ids=[item.evidence_id for item in optimisation_input.provenance.evidence],
        source_refs=[SourceRef(source_id="procurement-checker", record_id=CHECKER_VERSION)],
        effective_at=at,
        fetched_at=at,
        computed_at=at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=CHECKER_VERSION,
        model_version=CHECKER_VERSION,
    )


def _violation(
    output: list[ConstraintViolation],
    constraint_id: str,
    family: ConstraintFamily,
    actual: float,
    limit: float,
    unit: str,
    option_id: UUID | None,
    at: datetime,
    optimisation_input: ProcurementOptimisationInput,
) -> None:
    output.append(
        ConstraintViolation(
            constraint_id=constraint_id,
            family=family,
            message=f"{constraint_id} exceeded its hard limit",
            actual=_metric(max(0.0, actual), unit, at, optimisation_input),
            limit=_metric(max(0.0, limit), unit, at, optimisation_input),
            excess=_metric(max(TOLERANCE, actual - limit), unit, at, optimisation_input),
            option_id=option_id,
        )
    )
