import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sanjiv.contracts import DataMode, TruthClass
from sanjiv.twin.contracts import AssetKind, TwinSnapshot
from sanjiv.twin.importers import PPACImporter, ReferenceDataset, ReferenceRecord
from sanjiv.twin.service import build_default_twin_service


def test_default_snapshot_is_deterministic_complete_and_mass_conserving() -> None:
    build_default_twin_service.cache_clear()
    first = build_default_twin_service().current()
    build_default_twin_service.cache_clear()
    second = build_default_twin_service().current()

    assert first.snapshot_id == second.snapshot_id
    assert first.fingerprint == second.fingerprint
    assert len(first.nodes) == 19
    assert len(first.routes) == 18
    assert len(first.grades) == 12
    assert len(first.compatibility) == 36
    assert first.mass_balance.conserved
    assert first.mass_balance.absolute_residual.value == 0
    assert all(abs(value) <= 1e-6 for value in first.mass_balance.node_residuals.values())


def test_every_twin_entity_has_existing_evidence_and_assumption_coverage() -> None:
    snapshot = build_default_twin_service().current()
    evidence_ids = {item.id for item in snapshot.evidence_records}
    assumption_ids = {item.id for item in snapshot.assumptions}
    entities = [
        *snapshot.nodes,
        *snapshot.routes,
        *snapshot.grades,
        *snapshot.compatibility,
        *snapshot.baseline_flows,
    ]
    assert all(item.evidence_ids and set(item.evidence_ids) <= evidence_ids for item in entities)
    assert all(set(item.assumption_ids) <= assumption_ids for item in entities)
    assert all(item.expires_at is not None for item in snapshot.assumptions)


def test_reserve_capacity_never_implies_current_fill() -> None:
    snapshot = build_default_twin_service().current()
    reserves = [item for item in snapshot.nodes if item.kind is AssetKind.RESERVE_SITE]
    assert len(reserves) == 3
    assert all(
        item.capacity and item.capacity.truth_class is TruthClass.OBSERVED for item in reserves
    )
    assert all(item.attributes["current_fill_known"] is False for item in reserves)
    assert all(
        "fill" not in item.attributes or item.attributes["current_fill_status"] == "UNKNOWN"
        for item in reserves
    )


def test_allocation_uses_only_allowed_grade_refinery_pairs() -> None:
    snapshot = build_default_twin_service().current()
    routes = {item.id: item for item in snapshot.routes}
    allowed = {(item.grade_id, item.refinery_id): item.allowed for item in snapshot.compatibility}
    for flow in snapshot.baseline_flows:
        destination = routes[flow.route_id].destination_id
        if (flow.grade_id, destination) in allowed:
            assert allowed[(flow.grade_id, destination)]


def test_snapshot_rejects_unknown_route_endpoint() -> None:
    snapshot = build_default_twin_service().current()
    payload = snapshot.model_dump(mode="json")
    payload["routes"][0]["origin_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="fingerprint|unknown endpoint"):
        TwinSnapshot.model_validate(payload)


def test_importer_rejects_fixture_record_presented_as_observed() -> None:
    source = ReferenceRecord.model_validate(
        {
            "source_id": "PPAC",
            "record_id": "bad",
            "dataset": "bad fixture",
            "dataset_version": "1",
            "effective_at": "2026-07-20T00:00:00Z",
            "fetched_at": "2026-07-20T00:00:00Z",
            "mode": DataMode.FIXTURE,
            "truth_class": TruthClass.OBSERVED,
            "confidence": 1,
            "source_url": "https://example.com",
            "license": "test",
            "redistribution_rights": "test",
            "transformation": "test.v1",
            "payload": {"nodes": []},
        }
    )
    dataset = ReferenceDataset(dataset_id="bad", version="1", records=[source])
    with pytest.raises(ValueError, match="fixture records cannot be presented as observed"):
        PPACImporter().import_records(dataset)


def test_fixture_declares_redistribution_and_never_claims_live() -> None:
    path = Path("data/fixtures/twin/india-energy-network-v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for record in payload["records"]:
        assert record["redistribution_rights"]
        assert record["mode"] != "LIVE"
        if record["mode"] == "FIXTURE":
            assert record["truth_class"] == "ASSUMPTION"
