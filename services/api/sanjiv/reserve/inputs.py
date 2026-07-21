from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sanjiv.contracts import (
    Assumption,
    AssumptionStatus,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.procurement.contracts import (
    AssumptionFingerprintReference,
    EvidenceFingerprintReference,
    ProcurementPlan,
)
from sanjiv.reserve.contracts import (
    InventoryTruthStatus,
    ReserveDemandRequirement,
    ReserveOptimisationInput,
    ReservePolicyWeights,
    ReserveProvenance,
    ReserveSiteInput,
    reserve_input_fingerprint,
)
from sanjiv.twin.contracts import AssetKind, TwinSnapshot, canonical_uuid

FIXTURE_PATH = Path("data/fixtures/reserve/reserve-inputs-v1.json")


def load_reserve_fixture_assumptions(
    *, at: datetime, fixture_path: Path = FIXTURE_PATH
) -> list[Assumption]:
    """Rehydrate the immutable reserve assumption records used by the input builder."""
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if raw.get("classification") != "SYNTHETIC_FIXTURE":
        raise ValueError("reserve fixture must be classified SYNTHETIC_FIXTURE")
    effective = _utc(raw["effective_at"])
    expires = _utc(raw["expires_at"])
    if expires <= at:
        raise ValueError("reserve opening-inventory assumptions are expired")
    return [
        Assumption(
            id=UUID(item["assumption_id"]),
            key=f"reserve:{item['site']}:operational-inputs",
            value={
                key: value
                for key, value in item.items()
                if key not in {"assumption_id", "site", "refinery", "route"}
            },
            unit="reserve_operational_bundle",
            rationale=raw["rationale"],
            source_gap=raw["source_gap"],
            owner=raw["owner"],
            entered_at=effective,
            effective_at=effective,
            expires_at=expires,
            approved_at=effective,
            approved_by=raw["approved_by"],
            status=AssumptionStatus.APPROVED,
        )
        for item in raw["sites"]
    ]


def build_reserve_input(
    procurement_plan: ProcurementPlan,
    snapshot: TwinSnapshot,
    policy: ReservePolicyWeights,
    *,
    at: datetime | None = None,
    fixture_path: Path = FIXTURE_PATH,
) -> ReserveOptimisationInput:
    if (
        procurement_plan.solver_result.independent_check is None
        or not procurement_plan.solver_result.independent_check.passed
    ):
        raise ValueError("reserve planning requires a checked procurement plan")
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if raw.get("classification") != "SYNTHETIC_FIXTURE":
        raise ValueError("reserve fixture must be classified SYNTHETIC_FIXTURE")
    effective = _utc(raw["effective_at"])
    expires = _utc(raw["expires_at"])
    starts = min(
        item.interval_start
        for item in procurement_plan.fingerprint_inputs.optimisation_input.demands
    )
    ends = max(
        item.interval_end for item in procurement_plan.fingerprint_inputs.optimisation_input.demands
    )
    checked_at = at or starts
    if expires <= checked_at:
        raise ValueError("reserve opening-inventory assumptions are expired")
    horizon_days = (ends - starts).total_seconds() / 86400
    node_by_id = {item.id: item for item in snapshot.nodes}
    route_by_id = {item.id: item for item in snapshot.routes}
    evidence_by_id = {item.id: item for item in snapshot.evidence_records}
    assumptions: list[Assumption] = []
    sites: list[ReserveSiteInput] = []
    procurement_receipts: dict[UUID, float] = {}
    for action in procurement_plan.solver_result.actions:
        procurement_receipts[action.refinery.refinery_id] = (
            procurement_receipts.get(action.refinery.refinery_id, 0.0)
            + action.refinery.volume.value
        )
    for item in raw["sites"]:
        site_id = canonical_uuid(item["site"])
        refinery_id = canonical_uuid(item["refinery"])
        route_id = canonical_uuid(item["route"])
        node = node_by_id.get(site_id)
        route = route_by_id.get(route_id)
        refinery = node_by_id.get(refinery_id)
        if node is None or node.kind is not AssetKind.RESERVE_SITE or node.capacity is None:
            raise ValueError(f"reserve site is absent from the exact twin: {item['site']}")
        if (
            route is None
            or route.origin_id != site_id
            or route.destination_id != refinery_id
            or not route.available
        ):
            raise ValueError(f"reserve route is disconnected: {item['route']}")
        if refinery is None or refinery.capacity is None:
            raise ValueError(f"reserve receiving refinery is invalid: {item['refinery']}")
        values = {
            key: float(value)
            for key, value in item.items()
            if key.endswith(("_ktonne", "_fraction", "_day", "_tonne"))
        }
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise ValueError("reserve fixture values must be finite and nonnegative")
        assumption = Assumption(
            id=UUID(item["assumption_id"]),
            key=f"reserve:{item['site']}:operational-inputs",
            value={
                key: value
                for key, value in item.items()
                if key not in {"assumption_id", "site", "refinery", "route"}
            },
            unit="reserve_operational_bundle",
            rationale=raw["rationale"],
            source_gap=raw["source_gap"],
            owner=raw["owner"],
            entered_at=effective,
            effective_at=effective,
            expires_at=expires,
            approved_at=effective,
            approved_by=raw["approved_by"],
            status=AssumptionStatus.APPROVED,
        )
        assumptions.append(assumption)
        observed_capacity = _capacity_ktonne(node.capacity.value, node.capacity.unit)
        opening_inventory = float(item["opening_inventory_ktonne"])
        # A policy cannot manufacture stock to restore an already-under-floor site.
        # In that state the current verified/assumed opening balance becomes the
        # effective no-further-draw floor.
        floor = min(opening_inventory, observed_capacity * policy.minimum_floor_fraction)
        receipt_capacity = (
            _daily_capacity(refinery.capacity.value, refinery.capacity.unit) * horizon_days
        )
        committed = procurement_receipts.get(refinery_id, 0.0)
        evidence_ids = sorted(
            set(node.evidence_ids + route.evidence_ids + refinery.evidence_ids), key=str
        )
        sites.append(
            ReserveSiteInput(
                site_id=site_id,
                site_name=node.name,
                refinery_id=refinery_id,
                route_id=route_id,
                capacity=_metric(
                    observed_capacity,
                    "ktonne",
                    TruthClass.OBSERVED,
                    effective,
                    checked_at,
                    node.evidence_ids,
                    "reserve.capacity-normalisation.v1",
                ),
                opening_inventory=_metric(
                    opening_inventory,
                    "ktonne",
                    TruthClass.ASSUMPTION,
                    effective,
                    checked_at,
                    evidence_ids,
                    "reserve.fixture-opening-inventory.v1",
                ),
                opening_inventory_status=InventoryTruthStatus.UNEXPIRED_ASSUMPTION,
                minimum_policy_floor=_metric(
                    floor,
                    "ktonne",
                    TruthClass.ASSUMPTION,
                    effective,
                    checked_at,
                    evidence_ids,
                    policy.version,
                ),
                draw_rate_limit=_metric(
                    float(item["draw_rate_ktonne_per_day"]),
                    "ktonne_per_day",
                    TruthClass.ASSUMPTION,
                    effective,
                    checked_at,
                    evidence_ids,
                    "reserve.fixture-draw-rate.v1",
                ),
                route_capacity=_metric(
                    _daily_capacity(route.capacity.value, route.capacity.unit),
                    "ktonne_per_day",
                    route.capacity.truth_class,
                    route.capacity.effective_at,
                    checked_at,
                    route.evidence_ids,
                    "reserve.route-capacity-normalisation.v1",
                ),
                transit_time=_metric(
                    route.transit_time.value,
                    "day",
                    route.transit_time.truth_class,
                    route.transit_time.effective_at,
                    checked_at,
                    route.evidence_ids,
                    "reserve.transit-normalisation.v1",
                ),
                refinery_receipt_capacity=_metric(
                    receipt_capacity,
                    "ktonne",
                    refinery.capacity.truth_class,
                    refinery.capacity.effective_at,
                    checked_at,
                    refinery.evidence_ids,
                    "reserve.receipt-capacity-horizon.v1",
                ),
                procurement_committed_receipts=_metric(
                    committed,
                    "ktonne",
                    TruthClass.DERIVED,
                    starts,
                    checked_at,
                    procurement_plan.solver_result.actions[0].evidence_ids
                    if procurement_plan.solver_result.actions
                    else evidence_ids,
                    "reserve.procurement-coordination.v1",
                ),
                logistics_cost=_metric(
                    float(item["logistics_cost_usd_per_tonne"]),
                    "USD_per_tonne",
                    TruthClass.ASSUMPTION,
                    effective,
                    checked_at,
                    evidence_ids,
                    "reserve.fixture-logistics-cost.v1",
                ),
                evidence_ids=evidence_ids,
                assumption_ids=[assumption.id],
            )
        )
    demands: list[ReserveDemandRequirement] = []
    for demand in procurement_plan.fingerprint_inputs.optimisation_input.demands:
        residual = max(
            0.0, demand.required_volume.value - procurement_receipts.get(demand.refinery_id, 0.0)
        )
        demands.append(
            ReserveDemandRequirement(
                refinery_id=demand.refinery_id,
                required_volume=_metric(
                    residual,
                    "ktonne",
                    TruthClass.DERIVED,
                    starts,
                    checked_at,
                    demand.required_volume.evidence_ids,
                    "reserve.residual-demand-after-procurement.v1",
                ),
            )
        )
    evidence_refs_by_id = {
        item.evidence_id: item for item in procurement_plan.fingerprint_inputs.evidence
    }
    for eid in sorted({value for site in sites for value in site.evidence_ids}, key=str):
        evidence_refs_by_id.setdefault(
            eid,
            EvidenceFingerprintReference(
                evidence_id=eid,
                raw_payload_hash=evidence_by_id[eid].raw_payload_hash.lower(),
            ),
        )
    evidence_refs = [evidence_refs_by_id[key] for key in sorted(evidence_refs_by_id, key=str)]
    reserve_assumption_refs = [
        AssumptionFingerprintReference(
            assumption_id=item.id,
            assumption_hash=_hash(item.model_dump(mode="json")),
            status=item.status,
        )
        for item in sorted(assumptions, key=lambda value: str(value.id))
    ]
    assumption_refs_by_id = {
        item.assumption_id: item for item in procurement_plan.fingerprint_inputs.assumptions
    }
    assumption_refs_by_id.update({item.assumption_id: item for item in reserve_assumption_refs})
    assumption_refs = [assumption_refs_by_id[key] for key in sorted(assumption_refs_by_id, key=str)]
    procurement_input = procurement_plan.fingerprint_inputs.optimisation_input
    provenance = ReserveProvenance(
        simulation_run=procurement_input.provenance.simulation_run,
        simulation_result=procurement_input.provenance.simulation_result,
        confirmed_scenario=procurement_input.provenance.confirmed_scenario,
        twin_snapshot=procurement_input.provenance.twin_snapshot,
        procurement_plan_id=procurement_plan.plan_id,
        procurement_plan_fingerprint=procurement_plan.plan_fingerprint,
        procurement_input_fingerprint=procurement_plan.input_fingerprint
        if hasattr(procurement_plan, "input_fingerprint")
        else procurement_plan.fingerprint_inputs.optimisation_input_fingerprint,
        procurement_checker_version=procurement_plan.solver_result.independent_check.checker_version,
        evidence=evidence_refs,
        assumptions=assumption_refs,
    )
    payload: dict[str, Any] = {
        "provenance": provenance,
        "policy": policy,
        "starts_at": starts,
        "ends_at": ends,
        "sites": sorted(sites, key=lambda value: str(value.site_id)),
        "demands": sorted(demands, key=lambda value: str(value.refinery_id)),
    }
    return ReserveOptimisationInput.model_validate(
        {**payload, "input_fingerprint": reserve_input_fingerprint(payload)}
    )


def _metric(
    value: float,
    unit: str,
    truth: TruthClass,
    effective: datetime,
    computed: datetime,
    evidence_ids: list[UUID],
    transformation: str,
) -> MetricEnvelope[float]:
    fetched = max(effective, min(computed, computed))
    return MetricEnvelope(
        value=value,
        unit=unit,
        truth_class=truth,
        confidence=0.55 if truth is TruthClass.ASSUMPTION else 0.9,
        evidence_ids=evidence_ids,
        source_refs=[SourceRef(source_id="reserve-input-builder", record_id=transformation)],
        effective_at=effective,
        fetched_at=fetched,
        computed_at=max(fetched, computed),
        freshness_status=FreshnessStatus.CURRENT,
        transformation=transformation,
        model_version="reserve-input-builder-v1",
    )


def _capacity_ktonne(value: float, unit: str) -> float:
    if unit == "million_metric_tonne":
        return value * 1000.0
    if unit == "ktonne":
        return value
    raise ValueError(f"unsupported reserve capacity unit: {unit}")


def _daily_capacity(value: float, unit: str) -> float:
    if unit != "ktonne_per_day":
        raise ValueError(f"unsupported daily capacity unit: {unit}")
    return value


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
