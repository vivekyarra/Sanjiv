from pathlib import Path

from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.main import create_app
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_scenario_storage="memory",
        sanjiv_procurement_storage="memory",
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def _completed_run(client: TestClient) -> str:
    snapshot = build_default_twin_service().current()
    compiled = client.post(
        "/api/v1/scenarios/compile",
        headers={"Idempotency-Key": "proc-api-compile"},
        json={
            "mode": "DETERMINISTIC_TEXT",
            "twin_snapshot_id": str(snapshot.snapshot_id),
            "text": "Close the Strait of Hormuz for 14 days.",
        },
    ).json()
    scenario_id = compiled["candidate"]["scenario_id"]
    confirmation = client.post(
        f"/api/v1/scenarios/{scenario_id}/confirm",
        headers={"Idempotency-Key": "proc-api-confirm"},
        json={"confirming_identity": "ignored-client-identity"},
    )
    assert confirmation.status_code == 200
    started = client.post(
        "/api/v1/scenario-runs",
        headers={"Idempotency-Key": "proc-api-run-001"},
        json={"scenario_id": scenario_id, "configuration": {}},
    )
    assert started.status_code == 202
    return str(started.json()["run_id"])


def test_procurement_api_persists_three_checked_plans_and_reuses(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        run_id = _completed_run(client)
        request = {"profiles": ["LOWEST_COST", "BALANCED", "HIGHEST_RESILIENCE"]}
        response = client.post(
            f"/api/v1/scenario-runs/{run_id}/procurement-plans",
            headers={"Idempotency-Key": "procurement-plan-001"},
            json=request,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["plans"]) == 3
        assert all(item["solver_result"]["independent_check"]["passed"] for item in body["plans"])
        for plan in body["plans"]:
            saved = client.get(f"/api/v1/procurement-plans/{plan['plan_id']}")
            assert saved.status_code == 200
            assert saved.json()["plan_fingerprint"] == plan["plan_fingerprint"]
        reused = client.post(
            f"/api/v1/scenario-runs/{run_id}/procurement-plans",
            headers={"Idempotency-Key": "procurement-plan-002"},
            json=request,
        )
        assert reused.json()["reused"] is True


def test_procurement_api_requires_idempotency_and_production_credential(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"sanjiv_env": "production", "sanjiv_scenario_api_key": "operator-secret"}
    )
    with TestClient(create_app(settings=settings)) as client:
        missing_key = client.post(
            "/api/v1/scenario-runs/00000000-0000-0000-0000-000000000000/procurement-plans",
            json={},
        )
        denied = client.post(
            "/api/v1/scenario-runs/00000000-0000-0000-0000-000000000000/procurement-plans",
            headers={"Idempotency-Key": "production-denied"},
            json={},
        )
        assert missing_key.status_code == 422
        assert denied.status_code == 401


def test_openapi_exposes_phase_four_routes_and_contracts(tmp_path: Path) -> None:
    schema = create_app(settings=_settings(tmp_path)).openapi()
    assert "/api/v1/scenario-runs/{run_id}/procurement-plans" in schema["paths"]
    assert "/api/v1/procurement-plans/{plan_id}" in schema["paths"]
    for contract in (
        "ProcurementExecutionRequest",
        "ProcurementPlanResponse",
        "ProcurementPlan",
        "ProcurementDemand",
        "IndependentCheckResult",
    ):
        assert contract in schema["components"]["schemas"]
