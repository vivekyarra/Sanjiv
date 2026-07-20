from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import networkx as nx

from sanjiv.contracts import (
    Assumption,
    DataMode,
    EvidenceRecord,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.twin.contracts import (
    AssetKind,
    BaselineFlow,
    CompatibilityClass,
    CrudeGrade,
    MassBalanceReport,
    RefineryCompatibility,
    TwinNode,
    TwinRoute,
    TwinSnapshot,
    canonical_uuid,
)
from sanjiv.twin.importers import (
    ISPRLImporter,
    PPACImporter,
    ReferenceDataset,
    ReferenceRecord,
    RepositoryFixtureImporter,
    UNComtradeImporter,
    load_reference_dataset,
)

TWIN_MODEL_VERSION = "india-energy-network-1.0.0"
COMPATIBILITY_MODEL_VERSION = "crude-refinery-compatibility-1.0.0"
MASS_BALANCE_MODEL_VERSION = "twin-mass-balance-1.0.0"
DEFAULT_FIXTURE = Path("data/fixtures/twin/india-energy-network-v1.json")


class TwinService:
    def __init__(self, snapshot: TwinSnapshot) -> None:
        self._snapshots = (snapshot,)

    def current(self) -> TwinSnapshot:
        return self._snapshots[-1]

    def get(self, snapshot_id: UUID) -> TwinSnapshot | None:
        return next((item for item in self._snapshots if item.snapshot_id == snapshot_id), None)


@lru_cache
def build_default_twin_service(path: Path = DEFAULT_FIXTURE) -> TwinService:
    dataset = load_reference_dataset(path)
    records: list[ReferenceRecord] = []
    importers = (
        PPACImporter(),
        ISPRLImporter(),
        UNComtradeImporter(),
        RepositoryFixtureImporter(),
    )
    for importer in importers:
        records.extend(importer.import_records(dataset))
    snapshot = _build_snapshot(dataset, records)
    return TwinService(snapshot)


def _build_snapshot(dataset: ReferenceDataset, records: list[ReferenceRecord]) -> TwinSnapshot:
    evidence_by_record = {item.record_id: _evidence(item) for item in records}
    assumptions_by_record = {
        item.record_id: _assumption(item)
        for item in records
        if item.truth_class is TruthClass.ASSUMPTION
    }
    nodes: list[TwinNode] = []
    for record in records:
        for raw in _section(record, "nodes"):
            evidence = evidence_by_record[record.record_id]
            assumption = assumptions_by_record.get(record.record_id)
            capacity = _optional_metric(record, evidence, raw, "capacity", "capacity_unit")
            supply = _optional_metric(
                record, evidence, raw, "baseline_supply", "baseline_supply_unit"
            )
            demand = _optional_metric(
                record, evidence, raw, "baseline_demand", "baseline_demand_unit"
            )
            canonical_id = _required_str(raw, "canonical_id")
            attributes_raw = raw.get("attributes", {})
            if not isinstance(attributes_raw, dict):
                raise ValueError(f"{canonical_id} attributes must be an object")
            nodes.append(
                TwinNode(
                    id=canonical_uuid(canonical_id),
                    canonical_id=canonical_id,
                    kind=AssetKind(_required_str(raw, "kind")),
                    name=_required_str(raw, "name"),
                    country_code=_required_str(raw, "country_code"),
                    latitude=_required_float(raw, "latitude"),
                    longitude=_required_float(raw, "longitude"),
                    capacity=capacity,
                    baseline_supply=supply,
                    baseline_demand=demand,
                    evidence_ids=[evidence.id],
                    assumption_ids=[assumption.id] if assumption else [],
                    attributes={
                        str(key): _attribute(value) for key, value in attributes_raw.items()
                    },
                )
            )
    node_by_canonical = {item.canonical_id: item for item in nodes}
    routes: list[TwinRoute] = []
    for record in records:
        for raw in _section(record, "routes"):
            evidence = evidence_by_record[record.record_id]
            assumption = assumptions_by_record.get(record.record_id)
            canonical_id = _required_str(raw, "canonical_id")
            routes.append(
                TwinRoute(
                    id=canonical_uuid(canonical_id),
                    canonical_id=canonical_id,
                    origin_id=_node_id(node_by_canonical, raw, "origin"),
                    destination_id=_node_id(node_by_canonical, raw, "destination"),
                    capacity=_metric(
                        record,
                        evidence,
                        _required_float(raw, "capacity"),
                        _required_str(raw, "capacity_unit"),
                        "route-capacity",
                    ),
                    transit_time=_metric(
                        record,
                        evidence,
                        _required_float(raw, "transit_days"),
                        "day",
                        "route-transit-time",
                    ),
                    distance=_metric(
                        record,
                        evidence,
                        _required_float(raw, "distance_nm"),
                        "nautical_mile",
                        "route-distance",
                    ),
                    chokepoint_ids=[
                        _canonical_lookup(node_by_canonical, value).id
                        for value in _string_list(raw.get("chokepoints", []))
                    ],
                    evidence_ids=[evidence.id],
                    assumption_ids=[assumption.id] if assumption else [],
                )
            )
    routes_by_canonical = {item.canonical_id: item for item in routes}
    grades: list[CrudeGrade] = []
    grade_records: dict[UUID, ReferenceRecord] = {}
    for record in records:
        for raw in _section(record, "grades"):
            evidence = evidence_by_record[record.record_id]
            assumption = assumptions_by_record.get(record.record_id)
            canonical_id = _required_str(raw, "canonical_id")
            grade = CrudeGrade(
                id=canonical_uuid(canonical_id),
                canonical_id=canonical_id,
                name=_required_str(raw, "name"),
                origin_country_code=_required_str(raw, "origin_country_code"),
                load_port_ids=[
                    _canonical_lookup(node_by_canonical, value).id
                    for value in _string_list(raw.get("load_ports", []))
                ],
                api_gravity=_metric(
                    record,
                    evidence,
                    _required_float(raw, "api_gravity"),
                    "degree_api",
                    "grade-api-gravity",
                ),
                sulfur_pct=_metric(
                    record,
                    evidence,
                    _required_float(raw, "sulfur_pct"),
                    "percent_mass",
                    "grade-sulfur",
                ),
                sanctions_state=_required_str(raw, "sanctions_state"),
                evidence_ids=[evidence.id],
                assumption_ids=[assumption.id] if assumption else [],
            )
            grades.append(grade)
            grade_records[grade.id] = record
    grade_by_canonical = {item.canonical_id: item for item in grades}
    flows: list[BaselineFlow] = []
    for record in records:
        evidence = evidence_by_record[record.record_id]
        assumption = assumptions_by_record.get(record.record_id)
        for allocation_index, raw in enumerate(_section(record, "allocations")):
            supplier = _canonical_lookup(node_by_canonical, _required_str(raw, "supplier"))
            grade = _canonical_lookup(grade_by_canonical, _required_str(raw, "grade"))
            volume = _required_float(raw, "volume_ktonne_per_day")
            for route_canonical in _string_list(raw.get("route_ids", [])):
                route = _canonical_lookup(routes_by_canonical, route_canonical)
                flow_id = uuid5(
                    NAMESPACE_URL,
                    f"urn:sanjiv:baseline-flow:{record.record_id}:{allocation_index}:{route_canonical}",
                )
                flows.append(
                    BaselineFlow(
                        id=flow_id,
                        route_id=route.id,
                        supplier_id=supplier.id,
                        grade_id=grade.id,
                        volume=_metric(
                            record,
                            evidence,
                            volume,
                            "ktonne_per_day",
                            "baseline-allocation",
                        ),
                        evidence_ids=[evidence.id],
                        assumption_ids=[assumption.id] if assumption else [],
                    )
                )
    compatibility = _compatibility(
        nodes, grades, evidence_by_record, grade_records, records, assumptions_by_record
    )
    _validate_graph(nodes, routes)
    _validate_allocations(routes, flows, compatibility)
    created_at = max(item.fetched_at for item in records).astimezone(UTC)
    mass_balance = _mass_balance(nodes, routes, flows, evidence_by_record, created_at)
    return TwinSnapshot.create(
        version=dataset.version,
        effective_at=min(item.effective_at for item in records).astimezone(UTC),
        created_at=created_at,
        nodes=sorted(nodes, key=lambda item: item.canonical_id),
        routes=sorted(routes, key=lambda item: item.canonical_id),
        grades=sorted(grades, key=lambda item: item.canonical_id),
        compatibility=sorted(
            compatibility, key=lambda item: (str(item.refinery_id), str(item.grade_id))
        ),
        baseline_flows=sorted(flows, key=lambda item: str(item.id)),
        evidence_records=sorted(evidence_by_record.values(), key=lambda item: str(item.id)),
        assumptions=sorted(assumptions_by_record.values(), key=lambda item: str(item.id)),
        mass_balance=mass_balance,
    )


def _compatibility(
    nodes: list[TwinNode],
    grades: list[CrudeGrade],
    evidence_by_record: dict[str, EvidenceRecord],
    grade_records: dict[UUID, ReferenceRecord],
    records: list[ReferenceRecord],
    assumptions_by_record: dict[str, Assumption],
) -> list[RefineryCompatibility]:
    node_record_by_evidence = {
        evidence_by_record[item.record_id].id: item for item in records
    }
    output: list[RefineryCompatibility] = []
    for refinery in (item for item in nodes if item.kind is AssetKind.REFINERY):
        refinery_record = node_record_by_evidence[refinery.evidence_ids[0]]
        api_min = float(refinery.attributes["preferred_api_min"])
        api_max = float(refinery.attributes["preferred_api_max"])
        sulfur_max = float(refinery.attributes["sulfur_max_pct"])
        for grade in grades:
            grade_record = grade_records[grade.id]
            gravity = _range_score(grade.api_gravity.value, api_min, api_max, 15.0)
            sulfur = (
                1.0
                if grade.sulfur_pct.value <= sulfur_max
                else max(0.0, 1.0 - (grade.sulfur_pct.value - sulfur_max) / 2.0)
            )
            configuration = 0.75
            logistics = 1.0
            score_value = round(
                0.35 * gravity + 0.35 * sulfur + 0.15 * configuration + 0.15 * logistics,
                6,
            )
            classification = (
                CompatibilityClass.PREFERRED
                if score_value >= 0.8
                else CompatibilityClass.ACCEPTABLE
                if score_value >= 0.6
                else CompatibilityClass.DIFFICULT
                if score_value >= 0.4
                else CompatibilityClass.DISALLOWED
            )
            evidence = [
                evidence_by_record[refinery_record.record_id],
                evidence_by_record[grade_record.record_id],
            ]
            assumption_ids = [
                assumptions_by_record[item.record_id].id
                for item in (refinery_record, grade_record)
                if item.record_id in assumptions_by_record
            ]
            output.append(
                RefineryCompatibility(
                    grade_id=grade.id,
                    refinery_id=refinery.id,
                    score=_derived_metric(
                        score_value,
                        "fraction",
                        evidence,
                        "crude-refinery-compatibility.weighted-score.v1",
                        COMPATIBILITY_MODEL_VERSION,
                    ),
                    classification=classification,
                    allowed=classification is not CompatibilityClass.DISALLOWED,
                    component_scores={
                        "gravity": gravity,
                        "sulfur": sulfur,
                        "configuration": configuration,
                        "logistics": logistics,
                    },
                    evidence_ids=[item.id for item in evidence],
                    assumption_ids=assumption_ids,
                    explanation=(
                        "Deterministic weighted score from visible gravity, sulfur, "
                        "configuration, and logistics inputs; refinery operating limits "
                        "are assumptions."
                    ),
                )
            )
    return output


def _validate_graph(nodes: list[TwinNode], routes: list[TwinRoute]) -> None:
    graph: nx.MultiDiGraph[UUID] = nx.MultiDiGraph()
    for node in sorted(nodes, key=lambda item: item.canonical_id):
        graph.add_node(node.id, kind=node.kind)
    for route in sorted(routes, key=lambda item: item.canonical_id):
        graph.add_edge(route.origin_id, route.destination_id, key=route.id)
    refineries = {item.id for item in nodes if item.kind is AssetKind.REFINERY}
    for node in nodes:
        if node.kind in {AssetKind.SUPPLIER, AssetKind.RESERVE_SITE} and not any(
            nx.has_path(graph, node.id, refinery_id) for refinery_id in refineries
        ):
            raise ValueError(f"{node.canonical_id} has no path to an Indian refinery")
    active_nodes = [item.id for item in nodes if graph.degree(item.id) > 0]
    if active_nodes and not nx.is_weakly_connected(graph.subgraph(active_nodes)):
        raise ValueError("digital twin graph is not weakly connected")


def _validate_allocations(
    routes: list[TwinRoute],
    flows: list[BaselineFlow],
    compatibility: list[RefineryCompatibility],
) -> None:
    route_by_id = {item.id: item for item in routes}
    route_totals: defaultdict[UUID, float] = defaultdict(float)
    allowed = {(item.grade_id, item.refinery_id): item.allowed for item in compatibility}
    for flow in flows:
        route = route_by_id[flow.route_id]
        route_totals[route.id] += flow.volume.value
        if (flow.grade_id, route.destination_id) in allowed and not allowed[
            (flow.grade_id, route.destination_id)
        ]:
            raise ValueError("baseline allocation uses an incompatible grade/refinery pair")
    for route_id, volume in route_totals.items():
        if volume > route_by_id[route_id].capacity.value + 1e-9:
            canonical_id = route_by_id[route_id].canonical_id
            raise ValueError(f"baseline exceeds route capacity: {canonical_id}")


def _mass_balance(
    nodes: list[TwinNode],
    routes: list[TwinRoute],
    flows: list[BaselineFlow],
    evidence_by_record: dict[str, EvidenceRecord],
    computed_at: datetime,
    tolerance: float = 1e-6,
) -> MassBalanceReport:
    route_by_id = {item.id: item for item in routes}
    inflow: defaultdict[UUID, float] = defaultdict(float)
    outflow: defaultdict[UUID, float] = defaultdict(float)
    for flow in flows:
        route = route_by_id[flow.route_id]
        outflow[route.origin_id] += flow.volume.value
        inflow[route.destination_id] += flow.volume.value
    supply = sum(item.baseline_supply.value for item in nodes if item.baseline_supply)
    demand = sum(item.baseline_demand.value for item in nodes if item.baseline_demand)
    residuals: dict[str, float] = {}
    for node in nodes:
        if node.kind is AssetKind.SUPPLIER and node.baseline_supply:
            residual = node.baseline_supply.value - outflow[node.id]
        elif node.kind is AssetKind.REFINERY and node.baseline_demand:
            residual = inflow[node.id] - node.baseline_demand.value
        elif node.kind in {AssetKind.LOAD_PORT, AssetKind.CHOKEPOINT, AssetKind.INDIAN_PORT}:
            residual = inflow[node.id] - outflow[node.id]
        else:
            continue
        residuals[node.canonical_id] = round(residual, 9)
    absolute = abs(supply - demand)
    conserved = absolute <= tolerance and all(
        abs(value) <= tolerance for value in residuals.values()
    )
    evidence = list(evidence_by_record.values())
    return MassBalanceReport(
        total_supply=_derived_metric(
            supply,
            "ktonne_per_day",
            evidence,
            "twin-mass-balance.total-supply.v1",
            MASS_BALANCE_MODEL_VERSION,
            computed_at,
        ),
        total_demand=_derived_metric(
            demand,
            "ktonne_per_day",
            evidence,
            "twin-mass-balance.total-demand.v1",
            MASS_BALANCE_MODEL_VERSION,
            computed_at,
        ),
        absolute_residual=_derived_metric(
            absolute,
            "ktonne_per_day",
            evidence,
            "twin-mass-balance.absolute-residual.v1",
            MASS_BALANCE_MODEL_VERSION,
            computed_at,
        ),
        tolerance=_derived_metric(
            tolerance,
            "ktonne_per_day",
            evidence,
            "twin-mass-balance.tolerance.v1",
            MASS_BALANCE_MODEL_VERSION,
            computed_at,
        ),
        conserved=conserved,
        node_residuals=residuals,
        model_version=MASS_BALANCE_MODEL_VERSION,
    )


def _evidence(record: ReferenceRecord) -> EvidenceRecord:
    encoded = json.dumps(record.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return EvidenceRecord(
        id=uuid5(NAMESPACE_URL, f"urn:sanjiv:evidence:{record.source_id}:{record.record_id}"),
        source_id=record.source_id,
        source_record_id=record.record_id,
        source_url=record.source_url,
        dataset=record.dataset,
        dataset_version=record.dataset_version,
        effective_at=record.effective_at,
        fetched_at=record.fetched_at,
        mode=record.mode,
        truth_class=record.truth_class,
        raw_payload_hash=hashlib.sha256(encoded).hexdigest(),
        transformation=record.transformation,
        confidence=record.confidence,
        license=f"{record.license}; redistribution: {record.redistribution_rights}",
    )


def _assumption(record: ReferenceRecord) -> Assumption:
    if record.expires_at is None:
        raise ValueError(f"assumption record {record.record_id} requires expires_at")
    return Assumption(
        id=uuid5(NAMESPACE_URL, f"urn:sanjiv:assumption:{record.source_id}:{record.record_id}"),
        key=f"twin_reference.{record.record_id}",
        value=record.payload,
        unit="reference_record",
        rationale=(
            "Deterministic offline reference used where verified operational data is unavailable."
        ),
        source_gap="No verified redistributable operational dataset is bundled for these values.",
        owner="sanjiv-reference-data",
        entered_at=record.fetched_at,
        effective_at=record.effective_at,
        expires_at=record.expires_at,
    )


def _metric(
    record: ReferenceRecord,
    evidence: EvidenceRecord,
    value: float,
    unit: str,
    suffix: str,
) -> MetricEnvelope[float]:
    freshness = (
        FreshnessStatus.REPLAY if record.mode is DataMode.REPLAY else FreshnessStatus.CURRENT
    )
    return MetricEnvelope[float](
        value=value,
        unit=unit,
        truth_class=record.truth_class,
        confidence=record.confidence,
        evidence_ids=[evidence.id],
        source_refs=[SourceRef(source_id=record.source_id, record_id=record.record_id)],
        effective_at=record.effective_at,
        fetched_at=record.fetched_at,
        computed_at=record.fetched_at,
        freshness_status=freshness,
        transformation=f"{record.transformation}.{suffix}",
        model_version=TWIN_MODEL_VERSION,
    )


def _derived_metric(
    value: float,
    unit: str,
    evidence: list[EvidenceRecord],
    transformation: str,
    model_version: str,
    computed_at: datetime | None = None,
) -> MetricEnvelope[float]:
    effective_at = max(item.effective_at for item in evidence)
    fetched_at = max(item.fetched_at for item in evidence)
    calculated_at = computed_at or fetched_at
    return MetricEnvelope[float](
        value=value,
        unit=unit,
        truth_class=TruthClass.DERIVED,
        confidence=min(item.confidence for item in evidence),
        evidence_ids=[item.id for item in evidence],
        source_refs=[
            SourceRef(source_id=item.source_id, record_id=item.source_record_id)
            for item in evidence
        ],
        effective_at=effective_at,
        fetched_at=fetched_at,
        computed_at=calculated_at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=transformation,
        model_version=model_version,
    )


def _optional_metric(
    record: ReferenceRecord,
    evidence: EvidenceRecord,
    raw: dict[str, Any],
    value_key: str,
    unit_key: str,
) -> MetricEnvelope[float] | None:
    if value_key not in raw:
        return None
    return _metric(
        record,
        evidence,
        _required_float(raw, value_key),
        _required_str(raw, unit_key),
        value_key.replace("_", "-"),
    )


def _section(record: ReferenceRecord, key: str) -> list[dict[str, Any]]:
    raw = record.payload.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{record.record_id}.{key} must be an array")
    if not all(isinstance(item, dict) for item in raw):
        raise ValueError(f"{record.record_id}.{key} entries must be objects")
    return raw


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_float(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("expected an array of strings")
    return value


def _canonical_lookup(items: dict[str, Any], canonical_id: str) -> Any:
    try:
        return items[canonical_id]
    except KeyError as exc:
        raise ValueError(f"unknown canonical identifier: {canonical_id}") from exc


def _node_id(items: dict[str, TwinNode], raw: dict[str, Any], key: str) -> UUID:
    node: TwinNode = _canonical_lookup(items, _required_str(raw, key))
    return node.id


def _attribute(value: Any) -> str | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    raise ValueError("asset attributes must be strings, numbers, or booleans")


def _range_score(value: float, minimum: float, maximum: float, falloff: float) -> float:
    if minimum <= value <= maximum:
        return 1.0
    distance = minimum - value if value < minimum else value - maximum
    return max(0.0, 1.0 - distance / falloff)
