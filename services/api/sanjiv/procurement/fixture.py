from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from sanjiv.contracts import (
    Assumption,
    AssumptionStatus,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.procurement.contracts import FixedReservePolicyInput, HardConstraintConfiguration
from sanjiv.procurement.inputs import CommercialOptionInput
from sanjiv.twin.contracts import TwinSnapshot, canonical_uuid

FIXTURE_PATH = Path("data/fixtures/procurement/commercial-inputs-v1.json")


class CommercialFixtureBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    classification: str
    version: str
    redistribution_rights: str
    assumptions: dict[UUID, Assumption]
    commercial_inputs: dict[tuple[UUID, UUID, UUID, UUID], CommercialOptionInput]
    hard_constraints: HardConstraintConfiguration
    reserve_policy: FixedReservePolicyInput


def load_commercial_fixture(snapshot: TwinSnapshot, *, at: datetime) -> CommercialFixtureBundle:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if raw.get("classification") != "SYNTHETIC_FIXTURE":
        raise ValueError("commercial fixture must be classified SYNTHETIC_FIXTURE")
    effective_at = _utc(raw["effective_at"])
    expires_at = _utc(raw["expires_at"])
    if expires_at <= at:
        raise ValueError("commercial fixture assumptions are expired")
    assumptions: dict[UUID, Assumption] = {}
    common = {
        "rationale": raw["rationale"],
        "source_gap": raw["source_gap"],
        "owner": raw["owner"],
        "entered_at": effective_at,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "approved_at": effective_at,
        "approved_by": raw["approved_by"],
        "status": AssumptionStatus.APPROVED,
    }
    evidence_id = min((item.id for item in snapshot.evidence_records), key=str)
    commercial_inputs: dict[tuple[UUID, UUID, UUID, UUID], CommercialOptionInput] = {}
    for item in raw["options"]:
        assumption = Assumption(
            id=UUID(item["assumption_id"]),
            key=f"procurement:{item['key']}",
            value=item["values"],
            unit=item["unit"],
            **common,
        )
        assumptions[assumption.id] = assumption
        values = _finite_values(item["values"])
        components = {
            key: value
            for key, value in values.items()
            if key not in {"capacity_ktonne", "available_ktonne"}
        }
        commercial_inputs[
            (
                canonical_uuid(item["supplier"]),
                canonical_uuid(item["grade"]),
                canonical_uuid(item["route"]),
                canonical_uuid(item["refinery"]),
            )
        ] = CommercialOptionInput(
            components=components,
            capacity_ktonne=values["capacity_ktonne"],
            available_ktonne=values["available_ktonne"],
            evidence_ids=[evidence_id],
            assumption_ids=[assumption.id],
        )
    policy_values: dict[str, tuple[float | bool, UUID]] = {}
    for item in raw["policies"]:
        value = item["value"]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("commercial policy values must be finite")
        assumption = Assumption(
            id=UUID(item["assumption_id"]),
            key=f"procurement:{item['key']}",
            value=value,
            unit=item["unit"],
            **common,
        )
        assumptions[assumption.id] = assumption
        policy_values[item["key"]] = (value, assumption.id)

    def metric(key: str, unit: str) -> MetricEnvelope[float]:
        value, _ = policy_values[key]
        return MetricEnvelope(
            value=float(value),
            unit=unit,
            truth_class=TruthClass.ASSUMPTION,
            confidence=0.55,
            evidence_ids=[evidence_id],
            source_refs=[SourceRef(source_id="commercial-fixture-v1", record_id=key)],
            effective_at=effective_at,
            fetched_at=effective_at,
            computed_at=effective_at,
            freshness_status=FreshnessStatus.CURRENT,
            transformation="procurement.fixture-policy.v1",
            model_version=raw["version"],
        )

    policy_ids = sorted((item[1] for item in policy_values.values()), key=str)
    reserve_hash = _hash([assumptions[item].model_dump(mode="json") for item in policy_ids])
    return CommercialFixtureBundle(
        classification=raw["classification"],
        version=raw["version"],
        redistribution_rights=raw["redistribution_rights"],
        assumptions=assumptions,
        commercial_inputs=commercial_inputs,
        hard_constraints=HardConstraintConfiguration(
            version="procurement-hard-constraints-v1",
            budget_limit=metric("budget", "USD"),
            supplier_concentration_limit=metric("supplier_concentration", "fraction"),
            corridor_concentration_limit=metric("corridor_concentration", "fraction"),
        ),
        reserve_policy=FixedReservePolicyInput(
            policy_id="phase-4-fixed-no-reserve-decision",
            policy_version="fixed-reserve-policy-v1",
            policy_fingerprint=reserve_hash,
            assumption_ids=policy_ids,
        ),
    )


def _finite_values(raw: dict[str, Any]) -> dict[str, float]:
    values = {key: float(value) for key, value in raw.items()}
    if any(not math.isfinite(value) or value < 0 for value in values.values()):
        raise ValueError("commercial fixture values must be finite and nonnegative")
    return values


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
