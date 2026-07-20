from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sanjiv.contracts import Assumption, EvidenceRecord, MetricEnvelope


class AssetKind(StrEnum):
    SUPPLIER = "SUPPLIER"
    LOAD_PORT = "LOAD_PORT"
    CHOKEPOINT = "CHOKEPOINT"
    INDIAN_PORT = "INDIAN_PORT"
    REFINERY = "REFINERY"
    RESERVE_SITE = "RESERVE_SITE"


class Commodity(StrEnum):
    CRUDE_OIL = "CRUDE_OIL"


class CompatibilityClass(StrEnum):
    PREFERRED = "PREFERRED"
    ACCEPTABLE = "ACCEPTABLE"
    DIFFICULT = "DIFFICULT"
    DISALLOWED = "DISALLOWED"


class TwinNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9:_-]{2,127}$")
    kind: AssetKind
    name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capacity: MetricEnvelope[float] | None = None
    baseline_supply: MetricEnvelope[float] | None = None
    baseline_demand: MetricEnvelope[float] | None = None
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)
    attributes: dict[str, str | float | bool] = Field(default_factory=dict)


class TwinRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9:_-]{2,127}$")
    origin_id: UUID
    destination_id: UUID
    commodity: Commodity = Commodity.CRUDE_OIL
    capacity: MetricEnvelope[float]
    transit_time: MetricEnvelope[float]
    distance: MetricEnvelope[float]
    chokepoint_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)
    available: bool = True


class CrudeGrade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9:_-]{2,127}$")
    name: str = Field(min_length=1, max_length=200)
    origin_country_code: str = Field(min_length=2, max_length=2)
    load_port_ids: list[UUID] = Field(min_length=1)
    api_gravity: MetricEnvelope[float]
    sulfur_pct: MetricEnvelope[float]
    sanctions_state: str = Field(min_length=1, max_length=50)
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)


class RefineryCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grade_id: UUID
    refinery_id: UUID
    score: MetricEnvelope[float]
    classification: CompatibilityClass
    allowed: bool
    component_scores: dict[str, float]
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)
    explanation: str = Field(min_length=1, max_length=1000)


class BaselineFlow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    route_id: UUID
    supplier_id: UUID
    grade_id: UUID
    volume: MetricEnvelope[float]
    evidence_ids: list[UUID] = Field(min_length=1)
    assumption_ids: list[UUID] = Field(default_factory=list)


class MassBalanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_supply: MetricEnvelope[float]
    total_demand: MetricEnvelope[float]
    absolute_residual: MetricEnvelope[float]
    tolerance: MetricEnvelope[float]
    conserved: bool
    node_residuals: dict[str, float]
    model_version: str


class TwinSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    version: str = Field(min_length=1, max_length=100)
    effective_at: datetime
    created_at: datetime
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    nodes: list[TwinNode] = Field(min_length=1)
    routes: list[TwinRoute] = Field(min_length=1)
    grades: list[CrudeGrade] = Field(min_length=12, max_length=20)
    compatibility: list[RefineryCompatibility] = Field(min_length=1)
    baseline_flows: list[BaselineFlow] = Field(min_length=1)
    evidence_records: list[EvidenceRecord] = Field(min_length=1)
    assumptions: list[Assumption] = Field(default_factory=list)
    mass_balance: MassBalanceReport

    @classmethod
    def create(
        cls,
        *,
        version: str,
        effective_at: datetime,
        created_at: datetime,
        nodes: list[TwinNode],
        routes: list[TwinRoute],
        grades: list[CrudeGrade],
        compatibility: list[RefineryCompatibility],
        baseline_flows: list[BaselineFlow],
        evidence_records: list[EvidenceRecord],
        assumptions: list[Assumption],
        mass_balance: MassBalanceReport,
    ) -> Self:
        payload = _fingerprint_payload(
            version=version,
            effective_at=effective_at,
            created_at=created_at,
            nodes=nodes,
            routes=routes,
            grades=grades,
            compatibility=compatibility,
            baseline_flows=baseline_flows,
            evidence_records=evidence_records,
            assumptions=assumptions,
            mass_balance=mass_balance,
        )
        fingerprint = _sha256(payload)
        return cls(
            snapshot_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:twin-snapshot:{fingerprint}"),
            fingerprint=fingerprint,
            **payload,
        )

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        payload = _fingerprint_payload(
            version=self.version,
            effective_at=self.effective_at,
            created_at=self.created_at,
            nodes=self.nodes,
            routes=self.routes,
            grades=self.grades,
            compatibility=self.compatibility,
            baseline_flows=self.baseline_flows,
            evidence_records=self.evidence_records,
            assumptions=self.assumptions,
            mass_balance=self.mass_balance,
        )
        expected = _sha256(payload)
        if self.fingerprint != expected:
            raise ValueError("snapshot fingerprint does not match canonical content")
        if self.snapshot_id != uuid5(NAMESPACE_URL, f"urn:sanjiv:twin-snapshot:{expected}"):
            raise ValueError("snapshot_id does not match fingerprint")
        _validate_unique(self.nodes, "node")
        _validate_unique(self.routes, "route")
        _validate_unique(self.grades, "grade")
        node_ids = {item.id for item in self.nodes}
        grade_ids = {item.id for item in self.grades}
        route_ids = {item.id for item in self.routes}
        evidence_ids = {item.id for item in self.evidence_records}
        assumption_ids = {item.id for item in self.assumptions}
        for route in self.routes:
            if route.origin_id not in node_ids or route.destination_id not in node_ids:
                raise ValueError(f"route {route.canonical_id} has an unknown endpoint")
            if not set(route.chokepoint_ids) <= node_ids:
                raise ValueError(f"route {route.canonical_id} has an unknown chokepoint")
        for grade in self.grades:
            if not set(grade.load_port_ids) <= node_ids:
                raise ValueError(f"grade {grade.canonical_id} has an unknown load port")
        for item in self.compatibility:
            if item.grade_id not in grade_ids or item.refinery_id not in node_ids:
                raise ValueError("compatibility record has an unknown grade or refinery")
        for flow in self.baseline_flows:
            if flow.route_id not in route_ids or flow.grade_id not in grade_ids:
                raise ValueError("baseline flow has an unknown route or grade")
            if flow.supplier_id not in node_ids:
                raise ValueError("baseline flow has an unknown supplier")
        links: list[tuple[list[UUID], list[UUID]]] = [
            (item.evidence_ids, item.assumption_ids) for item in self.nodes
        ]
        links.extend((item.evidence_ids, item.assumption_ids) for item in self.routes)
        links.extend((item.evidence_ids, item.assumption_ids) for item in self.grades)
        links.extend((item.evidence_ids, item.assumption_ids) for item in self.compatibility)
        links.extend((item.evidence_ids, item.assumption_ids) for item in self.baseline_flows)
        for linked_evidence_ids, linked_assumption_ids in links:
            if not set(linked_evidence_ids) <= evidence_ids:
                raise ValueError("snapshot entity references missing evidence")
            if not set(linked_assumption_ids) <= assumption_ids:
                raise ValueError("snapshot entity references missing assumptions")
        if not self.mass_balance.conserved:
            raise ValueError("a non-conserving baseline cannot become a twin snapshot")
        return self


def canonical_uuid(canonical_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:sanjiv:twin:{canonical_id}")


def _validate_unique(items: list[Any], label: str) -> None:
    ids = [item.id for item in items]
    canonical_ids = [item.canonical_id for item in items]
    if len(ids) != len(set(ids)) or len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError(f"duplicate {label} identifier")


def _fingerprint_payload(**payload: Any) -> dict[str, Any]:
    return payload


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")
