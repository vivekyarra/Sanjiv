from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, SourceRef, TruthClass
from sanjiv.scenarios.contracts import (
    ConfirmedScenario,
    DisruptionEffect,
    DisruptionTargetType,
    DisruptionType,
)
from sanjiv.simulation.contracts import (
    BaselineResult,
    DisruptedResult,
    FlowResult,
    InventoryPoint,
    InventoryTrajectory,
    PhysicalInvariantReport,
    RefineryThroughputResult,
    SimulationConfiguration,
    SimulationProvenance,
    SimulationResult,
    TimelinePoint,
    UncertaintyRange,
)
from sanjiv.twin.contracts import AssetKind, BaselineFlow, TwinRoute, TwinSnapshot

SIMULATION_MODEL_VERSION = "no-action-impact-1.0.0"
SIMULATION_TRANSFORMATION = "no-action-impact.daily-mass-balance.v1"
MASS_BALANCE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class _StepState:
    flow_values: dict[UUID, float]
    route_capacities: dict[UUID, float]
    refinery_receipts: dict[UUID, float]
    refinery_throughput: dict[UUID, float]
    refinery_shortfall: dict[UUID, float]
    inventories: dict[UUID, float]
    total_supply: float
    total_throughput: float
    total_shortfall: float
    residual: float


def simulation_fingerprint(
    confirmed: ConfirmedScenario,
    configuration: SimulationConfiguration,
) -> str:
    payload = {
        "scenario_fingerprint": confirmed.scenario_fingerprint,
        "snapshot_fingerprint": confirmed.twin_snapshot.fingerprint,
        "model_version": SIMULATION_MODEL_VERSION,
        "configuration": configuration.model_dump(mode="json"),
        "assumptions": [
            item.model_dump(mode="json") for item in confirmed.candidate.parameters.assumptions
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_no_action_simulation(
    run_id: UUID,
    confirmed: ConfirmedScenario,
    snapshot: TwinSnapshot,
    configuration: SimulationConfiguration,
    *,
    computed_at: datetime | None = None,
) -> SimulationResult:
    started = perf_counter()
    calculated_at = (computed_at or datetime.now(UTC)).astimezone(UTC)
    original_snapshot_fingerprint = snapshot.fingerprint
    fingerprint = simulation_fingerprint(confirmed, configuration)
    horizon_days = math.ceil(confirmed.candidate.parameters.simulation_horizon.days)
    if horizon_days <= 0 or horizon_days > 90:
        raise ValueError("simulation horizon is outside the supported deterministic range")

    baseline_by_refinery = {
        node.id: node.baseline_demand.value
        for node in snapshot.nodes
        if node.kind is AssetKind.REFINERY and node.baseline_demand is not None
    }
    inventory_assumptions = _inventory_assumptions(confirmed, baseline_by_refinery)
    opening_inventory = {
        refinery_id: value[0] for refinery_id, value in inventory_assumptions.items()
    }
    timeline: list[TimelinePoint] = []
    central_states: list[_StepState] = []
    cumulative = 0.0
    for step in range(horizon_days):
        starts_at = confirmed.candidate.parameters.disruption_start + timedelta(days=step)
        active = _active_effects(confirmed, starts_at)
        state = _simulate_step(snapshot, active, baseline_by_refinery, opening_inventory)
        central_states.append(state)
        opening_inventory = state.inventories
        cumulative += state.total_shortfall
        timeline.append(
            TimelinePoint(
                step=step,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(days=1),
                baseline_supply=_metric(
                    snapshot.mass_balance.total_supply.value,
                    "ktonne_per_day",
                    snapshot,
                    calculated_at,
                    "baseline-supply",
                ),
                disrupted_supply=_metric(
                    state.total_supply,
                    "ktonne_per_day",
                    snapshot,
                    calculated_at,
                    "disrupted-supply",
                ),
                refinery_throughput=_metric(
                    state.total_throughput,
                    "ktonne_per_day",
                    snapshot,
                    calculated_at,
                    "refinery-throughput",
                ),
                shortfall=_metric(
                    state.total_shortfall, "ktonne_per_day", snapshot, calculated_at, "shortfall"
                ),
                cumulative_shortfall=_metric(
                    cumulative, "ktonne", snapshot, calculated_at, "cumulative-shortfall"
                ),
            )
        )

    peak_index = max(
        range(len(central_states)), key=lambda index: central_states[index].total_shortfall
    )
    peak = central_states[peak_index]
    flows = _flow_results(snapshot, peak, calculated_at)
    refinery_results = _refinery_results(snapshot, peak, baseline_by_refinery, calculated_at)
    inventory_trajectories = _inventory_trajectories(
        snapshot, central_states, inventory_assumptions, confirmed, calculated_at
    )
    lower_shortfall, upper_shortfall = _uncertainty_bounds(
        confirmed, snapshot, configuration, baseline_by_refinery
    )
    evidence_ids = [item.id for item in snapshot.evidence_records]
    assumption_ids = [item.id for item in confirmed.candidate.parameters.assumptions]
    assumption_ids.extend(item.id for item in snapshot.assumptions)
    assumption_ids = list(dict.fromkeys(assumption_ids))
    runtime_ms = (perf_counter() - started) * 1000
    affected_routes = [item.route_id for item in flows if item.affected]
    affected_assets = [
        effect.target.asset_id
        for effect in confirmed.candidate.parameters.disruptions
        if effect.target.asset_id is not None
    ]
    max_residual = max(abs(item.residual) for item in central_states)
    baseline_unchanged = snapshot.mass_balance.total_supply.value == sum(
        value for value in baseline_by_refinery.values()
    )
    invariants = PhysicalInvariantReport(
        non_negative_flows=all(
            value >= -MASS_BALANCE_TOLERANCE
            for state in central_states
            for value in state.flow_values.values()
        ),
        non_negative_inventories=all(
            value >= -MASS_BALANCE_TOLERANCE
            for state in central_states
            for value in state.inventories.values()
        ),
        route_capacities_respected=_route_capacities_respected(snapshot, central_states),
        closed_routes_zero=_closed_routes_zero(confirmed, snapshot, central_states),
        supplier_limits_respected=_supplier_limits_respected(snapshot, central_states),
        refinery_limits_respected=_refinery_limits_respected(snapshot, central_states),
        grade_compatibility_respected=_compatibility_respected(snapshot, central_states),
        mass_conserved=max_residual <= MASS_BALANCE_TOLERANCE,
        cumulative_values_reconcile=abs(
            cumulative - sum(item.total_shortfall for item in central_states)
        )
        <= MASS_BALANCE_TOLERANCE,
        baseline_unchanged=baseline_unchanged,
        snapshot_unchanged=snapshot.fingerprint == original_snapshot_fingerprint,
        max_mass_balance_residual=max_residual,
        tolerance=MASS_BALANCE_TOLERANCE,
    )
    if not all(
        value
        for name, value in invariants.model_dump().items()
        if isinstance(value, bool) and name != "non_negative_inventories"
    ) or (inventory_trajectories and not invariants.non_negative_inventories):
        raise ValueError("physical invariant validation failed")

    result_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:simulation-result:{fingerprint}")
    baseline_total = snapshot.mass_balance.total_supply.value
    cumulative_metric = _metric(
        cumulative, "ktonne", snapshot, calculated_at, "cumulative-shortfall"
    )
    provenance = SimulationProvenance(
        scenario_id=confirmed.scenario_id,
        twin_snapshot=confirmed.twin_snapshot,
        scenario_fingerprint=confirmed.scenario_fingerprint,
        simulation_fingerprint=fingerprint,
        model_version=SIMULATION_MODEL_VERSION,
        evidence_ids=evidence_ids,
        assumption_ids=assumption_ids,
        confidence=min(item.confidence for item in snapshot.evidence_records),
        freshness_status=FreshnessStatus.CURRENT,
        effective_at=snapshot.effective_at,
        fetched_at=max(item.fetched_at for item in snapshot.evidence_records),
        computed_at=calculated_at,
        transformation=SIMULATION_TRANSFORMATION,
    )
    return SimulationResult(
        result_id=result_id,
        run_id=run_id,
        provenance=provenance,
        baseline=BaselineResult(
            total_supply=_metric(
                baseline_total, "ktonne_per_day", snapshot, calculated_at, "baseline-total-supply"
            ),
            total_demand=_metric(
                baseline_total, "ktonne_per_day", snapshot, calculated_at, "baseline-total-demand"
            ),
            refinery_throughput=_metric(
                baseline_total,
                "ktonne_per_day",
                snapshot,
                calculated_at,
                "baseline-refinery-throughput",
            ),
            shortfall=_metric(0.0, "ktonne_per_day", snapshot, calculated_at, "baseline-shortfall"),
        ),
        disrupted=DisruptedResult(
            total_supply=_metric(
                peak.total_supply,
                "ktonne_per_day",
                snapshot,
                calculated_at,
                "disrupted-total-supply",
            ),
            total_demand=_metric(
                baseline_total, "ktonne_per_day", snapshot, calculated_at, "disrupted-total-demand"
            ),
            refinery_throughput=_metric(
                peak.total_throughput,
                "ktonne_per_day",
                snapshot,
                calculated_at,
                "disrupted-refinery-throughput",
            ),
            shortfall=_metric(
                peak.total_shortfall,
                "ktonne_per_day",
                snapshot,
                calculated_at,
                "disrupted-shortfall",
            ),
            cumulative_shortfall=cumulative_metric,
        ),
        timeline=timeline,
        flows=flows,
        refinery_throughput=refinery_results,
        inventory_trajectories=inventory_trajectories,
        inventory_status="ASSUMPTION_DEPENDENT" if inventory_trajectories else "UNKNOWN",
        affected_asset_ids=list(dict.fromkeys(affected_assets)),
        affected_route_ids=list(dict.fromkeys(affected_routes)),
        uncertainty=UncertaintyRange(
            central=cumulative_metric,
            lower_bound=_metric(
                lower_shortfall, "ktonne", snapshot, calculated_at, "uncertainty-lower"
            ),
            upper_bound=_metric(
                upper_shortfall, "ktonne", snapshot, calculated_at, "uncertainty-upper"
            ),
            parameters_varied=["capacity_reduction percentage points"],
            assumption_ids=assumption_ids,
            model_version=SIMULATION_MODEL_VERSION,
        ),
        invariants=invariants,
        runtime_ms=runtime_ms,
    )


def _simulate_step(
    snapshot: TwinSnapshot,
    effects: list[DisruptionEffect],
    baseline_by_refinery: dict[UUID, float],
    opening_inventory: dict[UUID, float],
) -> _StepState:
    route_by_id = {item.id: item for item in snapshot.routes}
    groups: dict[tuple[UUID, UUID, float], list[BaselineFlow]] = defaultdict(list)
    for flow in snapshot.baseline_flows:
        groups[(flow.supplier_id, flow.grade_id, flow.volume.value)].append(flow)
    flow_values: dict[UUID, float] = {}
    route_capacities = {
        route.id: _effective_route_capacity(route, effects) for route in snapshot.routes
    }
    for (supplier_id, _grade_id, baseline), path in groups.items():
        multiplier = _path_multiplier(
            supplier_id, [route_by_id[item.route_id] for item in path], effects
        )
        value = max(0.0, baseline * multiplier)
        for flow in path:
            flow_values[flow.id] = min(value, route_capacities[flow.route_id])

    receipts: defaultdict[UUID, float] = defaultdict(float)
    for flow in snapshot.baseline_flows:
        route = route_by_id[flow.route_id]
        if route.destination_id in baseline_by_refinery:
            receipts[route.destination_id] += flow_values[flow.id]
    throughput: dict[UUID, float] = {}
    shortfall: dict[UUID, float] = {}
    inventories: dict[UUID, float] = {}
    for refinery_id, demand in baseline_by_refinery.items():
        capacity = _refinery_capacity(snapshot, refinery_id, effects, demand)
        available = receipts[refinery_id] + opening_inventory.get(refinery_id, 0.0)
        processed = min(demand, capacity, available)
        throughput[refinery_id] = max(0.0, processed)
        shortfall[refinery_id] = max(0.0, demand - processed)
        if refinery_id in opening_inventory:
            inventories[refinery_id] = max(0.0, available - processed)
    total_supply = sum(receipts.values())
    total_throughput = sum(throughput.values())
    total_shortfall = sum(shortfall.values())
    inventory_change = sum(inventories.values()) - sum(opening_inventory.values())
    residual = total_supply - total_throughput - inventory_change
    return _StepState(
        flow_values=flow_values,
        route_capacities=route_capacities,
        refinery_receipts=dict(receipts),
        refinery_throughput=throughput,
        refinery_shortfall=shortfall,
        inventories=inventories,
        total_supply=total_supply,
        total_throughput=total_throughput,
        total_shortfall=total_shortfall,
        residual=residual,
    )


def _active_effects(confirmed: ConfirmedScenario, starts_at: datetime) -> list[DisruptionEffect]:
    disruption_start = confirmed.candidate.parameters.disruption_start
    disruption_end = disruption_start + timedelta(
        days=confirmed.candidate.parameters.disruption_duration.days
    )
    interval_end = starts_at + timedelta(days=1)
    return (
        confirmed.candidate.parameters.disruptions
        if starts_at < disruption_end and interval_end > disruption_start
        else []
    )


def _path_multiplier(
    supplier_id: UUID, routes: list[TwinRoute], effects: list[DisruptionEffect]
) -> float:
    multiplier = 1.0
    route_ids = {item.id for item in routes}
    node_ids = {item.origin_id for item in routes} | {item.destination_id for item in routes}
    chokepoint_ids = {item for route in routes for item in route.chokepoint_ids}
    for effect in effects:
        target_id = effect.target.asset_id
        if target_id is None:
            continue
        applies = (
            (
                effect.target.target_type is DisruptionTargetType.SUPPLIER
                and target_id == supplier_id
            )
            or (effect.target.target_type is DisruptionTargetType.ROUTE and target_id in route_ids)
            or (
                effect.target.target_type is DisruptionTargetType.CHOKEPOINT
                and target_id in node_ids | chokepoint_ids
            )
            or (
                effect.target.target_type
                in {DisruptionTargetType.PORT, DisruptionTargetType.REFINERY}
                and target_id in node_ids
            )
        )
        if applies:
            multiplier = min(multiplier, 1.0 - effect.capacity_reduction.value / 100.0)
    return max(0.0, multiplier)


def _effective_route_capacity(route: TwinRoute, effects: list[DisruptionEffect]) -> float:
    multiplier = 1.0
    for effect in effects:
        target_id = effect.target.asset_id
        if target_id is None:
            continue
        applies = (
            (effect.target.target_type is DisruptionTargetType.ROUTE and target_id == route.id)
            or (
                effect.target.target_type is DisruptionTargetType.CHOKEPOINT
                and target_id in {route.origin_id, route.destination_id, *route.chokepoint_ids}
            )
            or (
                effect.target.target_type is DisruptionTargetType.PORT
                and target_id in {route.origin_id, route.destination_id}
            )
        )
        if applies:
            multiplier = min(multiplier, 1.0 - effect.capacity_reduction.value / 100.0)
    return max(0.0, route.capacity.value * multiplier)


def _refinery_capacity(
    snapshot: TwinSnapshot, refinery_id: UUID, effects: list[DisruptionEffect], fallback: float
) -> float:
    node = next(item for item in snapshot.nodes if item.id == refinery_id)
    capacity = node.capacity.value if node.capacity is not None else fallback
    for effect in effects:
        if (
            effect.disruption_type is DisruptionType.REFINERY_THROUGHPUT_DISRUPTION
            and effect.target.asset_id == refinery_id
        ):
            capacity *= 1.0 - effect.capacity_reduction.value / 100.0
    return max(0.0, capacity)


def _flow_results(
    snapshot: TwinSnapshot, state: _StepState, computed_at: datetime
) -> list[FlowResult]:
    route_by_id = {item.id: item for item in snapshot.routes}
    return [
        FlowResult(
            route_id=flow.route_id,
            route_canonical_id=route_by_id[flow.route_id].canonical_id,
            supplier_id=flow.supplier_id,
            grade_id=flow.grade_id,
            baseline_flow=_metric(
                flow.volume.value, "ktonne_per_day", snapshot, computed_at, "baseline-flow"
            ),
            disrupted_flow=_metric(
                state.flow_values[flow.id],
                "ktonne_per_day",
                snapshot,
                computed_at,
                "disrupted-flow",
            ),
            disrupted_capacity=_metric(
                state.route_capacities[flow.route_id],
                "ktonne_per_day",
                snapshot,
                computed_at,
                "disrupted-route-capacity",
            ),
            affected=state.flow_values[flow.id] < flow.volume.value - MASS_BALANCE_TOLERANCE,
        )
        for flow in snapshot.baseline_flows
    ]


def _refinery_results(
    snapshot: TwinSnapshot, state: _StepState, baseline: dict[UUID, float], computed_at: datetime
) -> list[RefineryThroughputResult]:
    nodes = {item.id: item for item in snapshot.nodes}
    return [
        RefineryThroughputResult(
            refinery_id=refinery_id,
            refinery_canonical_id=nodes[refinery_id].canonical_id,
            baseline_throughput=_metric(
                demand, "ktonne_per_day", snapshot, computed_at, "baseline-refinery-throughput"
            ),
            disrupted_receipts=_metric(
                state.refinery_receipts.get(refinery_id, 0.0),
                "ktonne_per_day",
                snapshot,
                computed_at,
                "disrupted-refinery-receipts",
            ),
            disrupted_throughput=_metric(
                state.refinery_throughput[refinery_id],
                "ktonne_per_day",
                snapshot,
                computed_at,
                "disrupted-refinery-throughput",
            ),
            shortfall=_metric(
                state.refinery_shortfall[refinery_id],
                "ktonne_per_day",
                snapshot,
                computed_at,
                "refinery-shortfall",
            ),
        )
        for refinery_id, demand in baseline.items()
    ]


def _inventory_assumptions(
    confirmed: ConfirmedScenario, refineries: dict[UUID, float]
) -> dict[UUID, tuple[float, UUID]]:
    output: dict[UUID, tuple[float, UUID]] = {}
    for assumption in confirmed.candidate.parameters.assumptions:
        if not assumption.key.startswith("initial_inventory:"):
            continue
        identifier = assumption.key.split(":", 1)[1]
        try:
            refinery_id = UUID(identifier)
        except ValueError:
            continue
        if (
            refinery_id in refineries
            and assumption.unit == "ktonne"
            and isinstance(assumption.value, (int, float))
            and not isinstance(assumption.value, bool)
            and float(assumption.value) >= 0
        ):
            output[refinery_id] = (float(assumption.value), assumption.id)
    return output


def _inventory_trajectories(
    snapshot: TwinSnapshot,
    states: list[_StepState],
    assumptions: dict[UUID, tuple[float, UUID]],
    confirmed: ConfirmedScenario,
    computed_at: datetime,
) -> list[InventoryTrajectory]:
    nodes = {item.id: item for item in snapshot.nodes}
    start = confirmed.candidate.parameters.disruption_start
    return [
        InventoryTrajectory(
            refinery_id=refinery_id,
            refinery_canonical_id=nodes[refinery_id].canonical_id,
            assumption_id=assumption_id,
            points=[
                InventoryPoint(
                    starts_at=start + timedelta(days=index),
                    ending_inventory=_metric(
                        state.inventories[refinery_id],
                        "ktonne",
                        snapshot,
                        computed_at,
                        "assumption-dependent-inventory",
                    ),
                )
                for index, state in enumerate(states)
            ],
        )
        for refinery_id, (_value, assumption_id) in assumptions.items()
    ]


def _uncertainty_bounds(
    confirmed: ConfirmedScenario,
    snapshot: TwinSnapshot,
    configuration: SimulationConfiguration,
    baseline: dict[UUID, float],
) -> tuple[float, float]:
    totals: list[float] = []
    for direction in (-1.0, 1.0):
        effects = [
            effect.model_copy(
                update={
                    "capacity_reduction": effect.capacity_reduction.model_copy(
                        update={
                            "value": min(
                                100.0,
                                max(
                                    0.0,
                                    effect.capacity_reduction.value
                                    + direction * configuration.uncertainty_reduction_delta,
                                ),
                            )
                        }
                    )
                }
            )
            for effect in confirmed.candidate.parameters.disruptions
        ]
        opening: dict[UUID, float] = {}
        cumulative = 0.0
        horizon = math.ceil(confirmed.candidate.parameters.simulation_horizon.days)
        for step in range(horizon):
            starts_at = confirmed.candidate.parameters.disruption_start + timedelta(days=step)
            active = effects if _active_effects(confirmed, starts_at) else []
            state = _simulate_step(snapshot, active, baseline, opening)
            opening = state.inventories
            cumulative += state.total_shortfall
        totals.append(cumulative)
    return min(totals), max(totals)


def _metric(
    value: float, unit: str, snapshot: TwinSnapshot, computed_at: datetime, suffix: str
) -> MetricEnvelope[float]:
    evidence = snapshot.evidence_records
    fetched_at = max(item.fetched_at for item in evidence)
    calculated_at = max(computed_at, fetched_at)
    return MetricEnvelope[float](
        value=round(max(0.0, value), 9),
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=min(item.confidence for item in evidence),
        evidence_ids=[item.id for item in evidence],
        source_refs=[
            SourceRef(source_id=item.source_id, record_id=item.source_record_id)
            for item in evidence
        ],
        effective_at=max(item.effective_at for item in evidence),
        fetched_at=fetched_at,
        computed_at=calculated_at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=f"{SIMULATION_TRANSFORMATION}.{suffix}",
        model_version=SIMULATION_MODEL_VERSION,
    )


def _route_capacities_respected(snapshot: TwinSnapshot, states: list[_StepState]) -> bool:
    route_for_flow = {flow.id: flow.route_id for flow in snapshot.baseline_flows}
    for state in states:
        totals: defaultdict[UUID, float] = defaultdict(float)
        for flow_id, value in state.flow_values.items():
            totals[route_for_flow[flow_id]] += value
        if any(
            total > state.route_capacities[route_id] + MASS_BALANCE_TOLERANCE
            for route_id, total in totals.items()
        ):
            return False
    return True


def _closed_routes_zero(
    confirmed: ConfirmedScenario, snapshot: TwinSnapshot, states: list[_StepState]
) -> bool:
    closed = {
        effect.target.asset_id
        for effect in confirmed.candidate.parameters.disruptions
        if effect.capacity_reduction.value == 100
        and effect.target.target_type is DisruptionTargetType.ROUTE
    }
    return all(
        value <= MASS_BALANCE_TOLERANCE
        for state in states
        for flow, value in ((flow, state.flow_values[flow.id]) for flow in snapshot.baseline_flows)
        if flow.route_id in closed
    )


def _supplier_limits_respected(snapshot: TwinSnapshot, states: list[_StepState]) -> bool:
    first_route_flows = [
        flow
        for flow in snapshot.baseline_flows
        if any(
            route.id == flow.route_id and route.origin_id == flow.supplier_id
            for route in snapshot.routes
        )
    ]
    supplies = {
        node.id: node.baseline_supply.value
        for node in snapshot.nodes
        if node.baseline_supply is not None
    }
    return all(
        sum(
            state.flow_values[flow.id] for flow in first_route_flows if flow.supplier_id == supplier
        )
        <= limit + MASS_BALANCE_TOLERANCE
        for state in states
        for supplier, limit in supplies.items()
    )


def _refinery_limits_respected(snapshot: TwinSnapshot, states: list[_StepState]) -> bool:
    limits = {
        node.id: node.capacity.value if node.capacity else node.baseline_demand.value
        for node in snapshot.nodes
        if node.kind is AssetKind.REFINERY and node.baseline_demand is not None
    }
    return all(
        value <= limits[refinery] + MASS_BALANCE_TOLERANCE
        for state in states
        for refinery, value in state.refinery_throughput.items()
    )


def _compatibility_respected(snapshot: TwinSnapshot, states: list[_StepState]) -> bool:
    allowed = {(item.grade_id, item.refinery_id): item.allowed for item in snapshot.compatibility}
    route_by_id = {item.id: item for item in snapshot.routes}
    return all(
        allowed.get((flow.grade_id, route_by_id[flow.route_id].destination_id), True)
        or all(state.flow_values[flow.id] <= MASS_BALANCE_TOLERANCE for state in states)
        for flow in snapshot.baseline_flows
    )
