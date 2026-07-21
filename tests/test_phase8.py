from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.audit.contracts import EvidenceAuditStatus
from sanjiv.main import create_app
from sanjiv.phase8.contracts import ExportKind
from sanjiv.phase8.service import load_lpg_network, load_replay_catalogue
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service

PHASE8_REPLAY = Path("data/replay/energy-validation-v1/manifest.json")
LPG_MANIFEST = Path("data/fixtures/lpg/manifest.json")


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "sanjiv_maritime_storage": "memory",
        "sanjiv_maritime_autostart": False,
        "sanjiv_scenario_storage": "memory",
        "sanjiv_procurement_storage": "memory",
        "sanjiv_reserve_storage": "memory",
        "sanjiv_risk_storage": "memory",
        "sanjiv_audit_storage": "memory",
        "sanjiv_phase8_storage": "memory",
        "sanjiv_replay_dataset": REPLAY_MANIFEST,
        "sanjiv_geofence_fixture": GEOFENCES,
        "sanjiv_replay_runtime_dir": tmp_path,
        "sanjiv_phase8_replay_manifest": PHASE8_REPLAY,
        "sanjiv_lpg_fixture_manifest": LPG_MANIFEST,
    }
    values.update(updates)
    return Settings(**values)


def _procurement_plan(client: TestClient) -> str:
    snapshot = build_default_twin_service().current()
    compiled = client.post(
        "/api/v1/scenarios/compile",
        headers={"Idempotency-Key": "phase8-compile"},
        json={
            "mode": "DETERMINISTIC_TEXT",
            "twin_snapshot_id": str(snapshot.snapshot_id),
            "text": "Close the Strait of Hormuz for 14 days.",
        },
    ).json()
    scenario_id = compiled["candidate"]["scenario_id"]
    assert (
        client.post(
            f"/api/v1/scenarios/{scenario_id}/confirm",
            headers={"Idempotency-Key": "phase8-confirm"},
            json={"confirming_identity": "caller-value-is-not-authoritative"},
        ).status_code
        == 200
    )
    run = client.post(
        "/api/v1/scenario-runs",
        headers={"Idempotency-Key": "phase8-simulation"},
        json={"scenario_id": scenario_id, "configuration": {}},
    ).json()
    plans = client.post(
        f"/api/v1/scenario-runs/{run['run_id']}/procurement-plans",
        headers={"Idempotency-Key": "phase8-procurement"},
        json={},
    ).json()
    return str(plans["plans"][1]["plan_id"])


def test_catalogue_has_at_least_twenty_redistributable_checksummed_cases() -> None:
    catalogue = load_replay_catalogue(PHASE8_REPLAY)
    assert len(catalogue.cases) >= 20
    assert len({item.case_id for item in catalogue.cases}) == len(catalogue.cases)
    assert all(item.classification.value == "SYNTHETIC_FIXTURE" for item in catalogue.cases)
    assert all(item.license == "CC0-1.0" for item in catalogue.cases)
    assert {item.commodity.value for item in catalogue.cases} == {"CRUDE_OIL", "LPG"}


def test_catalogue_and_lpg_fixture_reject_checksum_tampering(tmp_path: Path) -> None:
    manifest = json.loads(PHASE8_REPLAY.read_text(encoding="utf-8"))
    (tmp_path / "cases.json").write_text('{"cases":[]}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        load_replay_catalogue(tmp_path / "manifest.json")
    except ValueError as error:
        assert "checksum" in str(error)
    else:
        raise AssertionError("tampered replay payload must fail")
    network, checksum = load_lpg_network(LPG_MANIFEST)
    assert network.unit == "tonne_per_day"
    assert (
        checksum
        == hashlib.sha256(
            Path("data/fixtures/lpg/india-lpg-network-v1.json").read_bytes()
        ).hexdigest()
    )
    assert network.public_reserve_policy == "NOT_APPLICABLE"


def test_all_replay_cases_execute_with_truth_metrics_and_expected_failures(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        catalogue = client.get("/api/v1/replay-catalogue")
        assert catalogue.status_code == 200
        cases = catalogue.json()["cases"]
        for case in cases:
            response = client.post(
                f"/api/v1/replay-cases/{case['case_id']}/runs",
                headers={"Idempotency-Key": f"replay-{case['case_id']}"},
            )
            assert response.status_code == 200, response.text
            run = response.json()
            assert run["classification"] == "SYNTHETIC_FIXTURE"
            assert run["truth_label"] == "FIXTURE"
            assert run["timeline"]
            assert run["fingerprint"]
            assert set(run["expected_invariants"]) == {
                key for key, passed in run["invariant_results"].items() if passed
            }
            for name in (
                "detection_lead_time",
                "recommendation_runtime",
                "evidence_coverage",
                "no_action_shortage",
                "recommended_shortage",
                "shortfall_reduction",
                "cost_increase",
            ):
                metric = run[name]
                assert metric["truth_class"] == "MODELED"
                assert metric["freshness_status"] == "REPLAY"
                assert metric["evidence_ids"]
            if case["event_type"] in {"STALE_EVIDENCE", "SOLVER_INFEASIBILITY"}:
                assert run["audit_status"] == "FAILED"
                assert run["export_allowed"] is False
            else:
                assert run["audit_status"] == "PASSED"
        assert len(client.get("/api/v1/replay-runs").json()) == len(cases)


def test_lpg_replay_uses_typed_assets_units_constraints_and_no_reserve(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        run = client.post(
            "/api/v1/replay-cases/lpg-hormuz-14d/runs",
            headers={"Idempotency-Key": "phase8-lpg-run"},
        ).json()
        plans = client.get(f"/api/v1/replay-runs/{run['run_id']}/lpg-plans")
        assert plans.status_code == 200, plans.text
        body = plans.json()
        assert [item["profile"] for item in body] == [
            "LOWEST_COST",
            "BALANCED",
            "HIGHEST_RESILIENCE",
        ]
        for plan in body:
            assert plan["reserve_handling"] == "NOT_APPLICABLE"
            assert plan["checker_passed"] is True
            assert plan["audit_status"] == "PASSED"
            assert plan["evidence_coverage"]["value"] == 100
            assert plan["delivered_volume"]["unit"] == "tonne"
            assert plan["residual_shortage"]["value"] >= 0
            assert all(item["volume"]["unit"] == "tonne" for item in plan["allocations"])
        exported = client.post(
            f"/api/v1/lpg-plans/{body[1]['plan_id']}/exports",
            headers={"Idempotency-Key": "phase8-lpg-export"},
            json={"kind": "MACHINE_READABLE_JSON"},
        )
        assert exported.status_code == 200, exported.text
        assert exported.json()["plan_kind"] == "LPG"
        payload = client.get(f"/api/v1/exports/{exported.json()['export_id']}/download").json()
        assert payload["lpg_plan"]["residual_shortage"] == body[1]["residual_shortage"]
        assert payload["reserve_guidance"] == "NOT_APPLICABLE"


def test_lpg_scenario_compiles_without_substituting_crude_assets(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        snapshot = build_default_twin_service().current()
        compiled = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "phase8-lpg-compile"},
            json={
                "mode": "DETERMINISTIC_TEXT",
                "twin_snapshot_id": str(snapshot.snapshot_id),
                "text": ("Reduce Strait of Hormuz capacity by 65% for 14 days for LPG."),
            },
        )
        assert compiled.status_code == 200, compiled.text
        body = compiled.json()
        assert body["candidate"]["parameters"]["commodity"] == "LPG"
        scenario_id = body["candidate"]["scenario_id"]
        assert (
            client.post(
                f"/api/v1/scenarios/{scenario_id}/confirm",
                headers={"Idempotency-Key": "phase8-lpg-confirm"},
                json={"confirming_identity": "local-demo-operator"},
            ).status_code
            == 200
        )
        refused = client.post(
            "/api/v1/scenario-runs",
            headers={"Idempotency-Key": "phase8-lpg-wrong-pipeline"},
            json={"scenario_id": scenario_id, "configuration": {}},
        )
        assert refused.status_code == 422
        assert refused.json()["code"] == "LPG_PIPELINE_REQUIRED"


def test_sensitivity_is_seeded_reproducible_and_not_probability(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        plan_id = _procurement_plan(client)
        payload = {
            "mode": "FAST",
            "seed": 73,
            "ranges": [],
            "correlations": [
                {
                    "left": "disruption_duration",
                    "right": "freight_premium",
                    "coefficient": 0.4,
                }
            ],
        }
        first = client.post(
            f"/api/v1/plans/{plan_id}/sensitivity-runs",
            headers={"Idempotency-Key": "phase8-sensitivity-one"},
            json=payload,
        )
        second = client.post(
            f"/api/v1/plans/{plan_id}/sensitivity-runs",
            headers={"Idempotency-Key": "phase8-sensitivity-two"},
            json=payload,
        )
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        result = first.json()
        assert result["sample_count"] == 40
        assert result["probability_claimed"] is False
        assert result["p10"]["value"] <= result["median"]["value"] <= result["p90"]["value"]
        assert result["stability_method_version"] == "allocation-l1-threshold-v1"
        readback = client.get(f"/api/v1/sensitivity-runs/{result['sensitivity_id']}")
        assert readback.status_code == 200
        assert readback.json() == result
        deep = client.post(
            f"/api/v1/plans/{plan_id}/sensitivity-runs",
            headers={"Idempotency-Key": "phase8-sensitivity-deep"},
            json={"mode": "DEEP", "seed": 73},
        )
        assert deep.status_code == 200
        assert deep.json()["sample_count"] == 500


def test_all_audited_exports_match_api_values_and_pdf_checksum(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        plan_id = _procurement_plan(client)
        audit = client.get(f"/api/v1/plans/{plan_id}/audit").json()
        for kind in ExportKind:
            created = client.post(
                f"/api/v1/plans/{plan_id}/exports",
                headers={"Idempotency-Key": f"phase8-export-{kind.value}"},
                json={"kind": kind.value},
            )
            assert created.status_code == 200, created.text
            metadata = created.json()
            download = client.get(f"/api/v1/exports/{metadata['export_id']}/download")
            assert download.status_code == 200
            assert hashlib.sha256(download.content).hexdigest() == metadata["sha256"]
            assert metadata["audit_fingerprint"] == audit["audit_fingerprint"]
            if kind is ExportKind.PDF_BRIEFING:
                assert download.content.startswith(b"%PDF-1.4")
            else:
                exported = download.json()
                assert exported["audit"]["metrics"] == audit["metrics"]
                assert exported["execution_authorized"] is False


def test_failed_current_audit_blocks_export(tmp_path: Path) -> None:
    application = create_app(settings=_settings(tmp_path))
    with TestClient(application) as client:
        plan_id = _procurement_plan(client)
        original = application.state.audit_service.audit_plan

        async def failed_audit(subject_id: object) -> object:
            result = await original(subject_id)
            return result.model_copy(
                update={
                    "status": EvidenceAuditStatus.FAILED,
                    "export_allowed": False,
                }
            )

        application.state.audit_service.audit_plan = failed_audit
        blocked = client.post(
            f"/api/v1/plans/{plan_id}/exports",
            headers={"Idempotency-Key": "phase8-blocked-export"},
            json={"kind": "MACHINE_READABLE_JSON"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "EXPORT_BLOCKED_BY_AUDIT"


def test_comments_monitoring_authorization_and_idempotency(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        plan_id = _procurement_plan(client)
        comment = client.post(
            f"/api/v1/plans/{plan_id}/comments",
            headers={
                "Idempotency-Key": "phase8-comment",
                "X-Sanjiv-Demo-Identity": "local-demo-reviewer",
            },
            json={"comment": "Review note with no execution instruction."},
        )
        assert comment.status_code == 200, comment.text
        repeated = client.post(
            f"/api/v1/plans/{plan_id}/comments",
            headers={
                "Idempotency-Key": "phase8-comment",
                "X-Sanjiv-Demo-Identity": "local-demo-reviewer",
            },
            json={"comment": "Review note with no execution instruction."},
        )
        assert repeated.json()["comment_id"] == comment.json()["comment_id"]
        conflict = client.post(
            f"/api/v1/plans/{plan_id}/comments",
            headers={
                "Idempotency-Key": "phase8-comment",
                "X-Sanjiv-Demo-Identity": "local-demo-reviewer",
            },
            json={"comment": "Changed request under reused idempotency key."},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
        assert client.get(f"/api/v1/plans/{plan_id}/comments").json()[0]["actor_role"] == "reviewer"
        forged = client.post(
            f"/api/v1/plans/{plan_id}/comments",
            headers={
                "Idempotency-Key": "phase8-forged",
                "X-Sanjiv-Demo-Identity": "unknown-admin",
            },
            json={"comment": "forged"},
        )
        assert forged.status_code == 401
        replay = client.post(
            "/api/v1/replay-cases/hormuz-partial-14d/runs",
            headers={"Idempotency-Key": "phase8-monitor-replay"},
        ).json()
        monitored = client.post(
            f"/api/v1/plans/{plan_id}/monitoring",
            headers={"Idempotency-Key": "phase8-monitor"},
            json={"replay_run_id": replay["run_id"]},
        )
        assert monitored.status_code == 200, monitored.text
        assert monitored.json()["mode"] == "REPLAY"
        assert monitored.json()["execution_integration"] is False
        assert client.get(f"/api/v1/plans/{plan_id}/monitoring").json()


def test_production_comments_fail_closed_without_identity_configuration(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path, sanjiv_env="production"))) as client:
        response = client.post(
            "/api/v1/plans/00000000-0000-0000-0000-000000000001/comments",
            headers={"Idempotency-Key": "phase8-prod-closed"},
            json={"comment": "must not authenticate"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "IDENTITY_CONFIGURATION_MISSING"
