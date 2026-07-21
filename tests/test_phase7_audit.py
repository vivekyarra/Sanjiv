from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.audit.claims import assert_audited_narrative, blocked_claim_codes
from sanjiv.contracts import FreshnessStatus
from sanjiv.main import create_app
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service


def _settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "sanjiv_maritime_storage": "memory",
        "sanjiv_maritime_autostart": False,
        "sanjiv_scenario_storage": "memory",
        "sanjiv_procurement_storage": "memory",
        "sanjiv_reserve_storage": "memory",
        "sanjiv_risk_storage": "memory",
        "sanjiv_audit_storage": "memory",
        "sanjiv_replay_dataset": REPLAY_MANIFEST,
        "sanjiv_geofence_fixture": GEOFENCES,
        "sanjiv_replay_runtime_dir": tmp_path,
    }
    values.update(updates)
    return Settings(**values)


def _plans(client: TestClient) -> tuple[str, str]:
    snapshot = build_default_twin_service().current()
    compiled = client.post(
        "/api/v1/scenarios/compile",
        headers={"Idempotency-Key": "phase7-compile"},
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
            headers={"Idempotency-Key": "phase7-confirm"},
            json={"confirming_identity": "forged-and-ignored"},
        ).status_code
        == 200
    )
    run = client.post(
        "/api/v1/scenario-runs",
        headers={"Idempotency-Key": "phase7-run"},
        json={"scenario_id": scenario_id, "configuration": {}},
    ).json()
    run_id = run["run_id"]
    procurement = client.post(
        f"/api/v1/scenario-runs/{run_id}/procurement-plans",
        headers={"Idempotency-Key": "phase7-procurement"},
        json={},
    ).json()
    procurement_id = procurement["plans"][1]["plan_id"]
    reserve = client.post(
        f"/api/v1/scenario-runs/{run_id}/reserve-plans",
        headers={"Idempotency-Key": "phase7-reserve"},
        json={"procurement_plan_id": procurement_id},
    ).json()
    return procurement_id, reserve["plans"][1]["plan_id"]


def _binding(audit: dict[str, object]) -> dict[str, object]:
    fingerprints = audit["fingerprints"]
    assert isinstance(fingerprints, dict)
    return {
        "plan_fingerprint": fingerprints["plan"],
        "assumption_fingerprint": fingerprints["assumptions"],
        "audit_fingerprint": audit["audit_fingerprint"],
    }


def test_procurement_and_reserve_have_complete_audits_and_explanations(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        for plan_id in _plans(client):
            audit = client.get(f"/api/v1/plans/{plan_id}/audit")
            assert audit.status_code == 200, audit.text
            body = audit.json()
            assert body["status"] == "PASSED"
            assert body["evidence_coverage_percentage"] == 100
            assert body["covered_metric_count"] == body["total_metric_count"] > 0
            assert body["checker_passed"] is True
            assert body["recomputation_passed"] is True
            assert body["approval_allowed"] is True
            explanation = client.get(f"/api/v1/plans/{plan_id}/explanation")
            assert explanation.status_code == 200
            assert explanation.json()["usable"] is True
            assert explanation.json()["deterministic"] is True
            assert "does not place orders" in explanation.json()["no_execution_notice"]
            assert client.get(f"/api/v1/plans/{plan_id}/assumptions").json()


def test_server_owned_roles_lifecycle_idempotency_and_immutable_approval(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        plan_id, _ = _plans(client)
        audit = client.get(f"/api/v1/plans/{plan_id}/audit").json()
        binding = _binding(audit)
        path = f"/api/v1/plans/{plan_id}"
        submitted = client.post(
            f"{path}/reviews",
            headers={
                "Idempotency-Key": "phase7-submit-review",
                "X-Sanjiv-Demo-Identity": "local-demo-operator",
                "X-Sanjiv-Role": "administrator",
            },
            json={**binding, "action": "SUBMIT_FOR_REVIEW", "comment": "Ready for review."},
        )
        assert submitted.status_code == 200
        forged_approver = client.post(
            f"{path}/approvals",
            headers={
                "Idempotency-Key": "phase7-forged-approval",
                "X-Sanjiv-Demo-Identity": "local-demo-operator",
                "X-Sanjiv-Role": "approver",
            },
            json={**binding, "comment": "Caller claims approver role."},
        )
        assert forged_approver.status_code == 403
        reviewed = client.post(
            f"{path}/reviews",
            headers={
                "Idempotency-Key": "phase7-review-note",
                "X-Sanjiv-Demo-Identity": "local-demo-reviewer",
            },
            json={**binding, "action": "REVIEW", "comment": "Evidence checked."},
        )
        assert reviewed.status_code == 200
        approval_headers = {
            "Idempotency-Key": "phase7-final-approval",
            "X-Sanjiv-Demo-Identity": "local-demo-approver",
        }
        approved = client.post(
            f"{path}/approvals",
            headers=approval_headers,
            json={**binding, "comment": "Approved for decision support only."},
        )
        assert approved.status_code == 200
        assert approved.json()["actor_id"] == "local-demo-approver"
        assert approved.json()["state"] == "APPROVED"
        repeated = client.post(
            f"{path}/approvals",
            headers=approval_headers,
            json={**binding, "comment": "Approved for decision support only."},
        )
        assert repeated.json() == approved.json()
        conflicting_reuse = client.post(
            f"{path}/approvals",
            headers=approval_headers,
            json={**binding, "comment": "Different request under the same key."},
        )
        assert conflicting_reuse.status_code == 409
        assert conflicting_reuse.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"
        invalid_second_approval = client.post(
            f"{path}/approvals",
            headers={
                "Idempotency-Key": "phase7-second-approval",
                "X-Sanjiv-Demo-Identity": "local-demo-approver",
            },
            json={**binding, "comment": "Attempt a mutable terminal record."},
        )
        assert invalid_second_approval.status_code == 409
        governance = client.get(f"{path}/governance").json()
        assert governance["state"] == "APPROVED"
        assert len(governance["records"]) == 3


def test_stale_binding_and_production_fail_closed(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        plan_id, _ = _plans(client)
        audit = client.get(f"/api/v1/plans/{plan_id}/audit").json()
        binding = _binding(audit)
        binding["plan_fingerprint"] = "0" * 64
        response = client.post(
            f"/api/v1/plans/{plan_id}/reviews",
            headers={
                "Idempotency-Key": "phase7-stale-plan",
                "X-Sanjiv-Demo-Identity": "local-demo-operator",
            },
            json={**binding, "action": "SUBMIT_FOR_REVIEW"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "STALE_PLAN_FINGERPRINT"

    production = _settings(tmp_path, sanjiv_env="production", sanjiv_governance_api_keys="{}")
    with TestClient(create_app(settings=production)) as client:
        response = client.post(
            "/api/v1/plans/00000000-0000-0000-0000-000000000000/reviews",
            headers={"Idempotency-Key": "phase7-production-closed"},
            json={
                "action": "SUBMIT_FOR_REVIEW",
                "plan_fingerprint": "0" * 64,
                "assumption_fingerprint": "0" * 64,
                "audit_fingerprint": "0" * 64,
            },
        )
        assert response.status_code == 503


def test_claim_policy_blocks_embellishment_and_unaudited_figures() -> None:
    assert "CHARTER_AVAILABILITY" in blocked_claim_codes("This tanker is available for charter.")
    assert "RESERVE_EXECUTION" in blocked_claim_codes("The reserve has been released.")
    assert assert_audited_narrative("Shortage falls by 17.5%.", {"17.5%"}) == []
    assert "UNAUDITED_FIGURE" in assert_audited_narrative("Shortage falls by 18%.", {"17.5%"})


def test_expired_assumption_blocks_every_presentation_path(tmp_path: Path) -> None:
    app = create_app(settings=_settings(tmp_path))
    with TestClient(app) as client:
        plan_id, _ = _plans(client)
        audit = asyncio.run(
            app.state.audit_service.audit_plan(UUID(plan_id), at=datetime(2028, 1, 1, tzinfo=UTC))
        )
        assert audit.status == "FAILED"
        assert any(item.code == "ASSUMPTION_EXPIRED" for item in audit.failures)
        assert audit.usable is False
        assert audit.approval_allowed is False
        assert audit.export_allowed is False
        assert audit.definitive_narrative_allowed is False


def test_tampered_evidence_and_stale_metric_remain_visible_and_blocked(
    tmp_path: Path,
) -> None:
    app = create_app(settings=_settings(tmp_path))
    with TestClient(app) as client:
        plan_id, _ = _plans(client)
        identifier = UUID(plan_id)
        repository = app.state.procurement_service.repository
        plan = asyncio.run(repository.plan(identifier))
        assert plan is not None
        bad_reference = plan.fingerprint_inputs.evidence[0].model_copy(
            update={"raw_payload_hash": "0" * 64}
        )
        references = [bad_reference, *plan.fingerprint_inputs.evidence[1:]]
        provenance = plan.fingerprint_inputs.optimisation_input.provenance.model_copy(
            update={"evidence": references}
        )
        optimisation_input = plan.fingerprint_inputs.optimisation_input.model_copy(
            update={"provenance": provenance}
        )
        fingerprint_inputs = plan.fingerprint_inputs.model_copy(
            update={"evidence": references, "optimisation_input": optimisation_input}
        )
        assert plan.solver_result.shortage is not None
        stale_shortage = plan.solver_result.shortage.model_copy(
            update={
                "freshness_status": FreshnessStatus.STALE,
                "evidence_ids": [uuid4()],
            }
        )
        solver_result = plan.solver_result.model_copy(update={"shortage": stale_shortage})
        tampered = plan.model_copy(
            update={"fingerprint_inputs": fingerprint_inputs, "solver_result": solver_result}
        )
        repository._plans[identifier] = tampered
        audit = client.get(f"/api/v1/plans/{plan_id}/audit")
        assert audit.status_code == 200
        body = audit.json()
        codes = {item["code"] for item in body["failures"]}
        assert {
            "EVIDENCE_HASH_MISMATCH",
            "EVIDENCE_MISSING",
            "METRIC_STALE",
            "RECOMPUTATION_MISMATCH",
        } <= codes
        shortage = next(item for item in body["metrics"] if item["path"].endswith("shortage"))
        assert shortage["status"] == "FAILED"
        assert shortage["value"] == stale_shortage.value


def test_phase7_openapi_contracts(tmp_path: Path) -> None:
    schema = create_app(settings=_settings(tmp_path)).openapi()
    for route in (
        "/api/v1/evidence/{evidence_id}",
        "/api/v1/plans/{plan_id}/audit",
        "/api/v1/plans/{plan_id}/explanation",
        "/api/v1/plans/{plan_id}/reviews",
        "/api/v1/plans/{plan_id}/approvals",
        "/api/v1/plans/{plan_id}/rejections",
        "/api/v1/plans/{plan_id}/supersessions",
    ):
        assert route in schema["paths"]
    for contract in (
        "EvidenceAuditResult",
        "PlanExplanation",
        "PlanLifecycleRecord",
        "PlanGovernanceState",
    ):
        assert contract in schema["components"]["schemas"]
