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
        sanjiv_reserve_storage="memory",
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def _run_and_procurement(client: TestClient) -> tuple[str, str]:
    snapshot = build_default_twin_service().current()
    compiled = client.post(
        "/api/v1/scenarios/compile",
        headers={"Idempotency-Key": "reserve-api-compile"},
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
            headers={"Idempotency-Key": "reserve-api-confirm"},
            json={"confirming_identity": "ignored"},
        ).status_code
        == 200
    )
    run = client.post(
        "/api/v1/scenario-runs",
        headers={"Idempotency-Key": "reserve-api-run"},
        json={"scenario_id": scenario_id, "configuration": {}},
    ).json()
    procurement = client.post(
        f"/api/v1/scenario-runs/{run['run_id']}/procurement-plans",
        headers={"Idempotency-Key": "reserve-api-procurement"},
        json={},
    ).json()
    return run["run_id"], procurement["plans"][1]["plan_id"]


def test_reserve_api_persists_checked_plans_and_reuses(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        run_id, procurement_plan_id = _run_and_procurement(client)
        payload = {"procurement_plan_id": procurement_plan_id}
        response = client.post(
            f"/api/v1/scenario-runs/{run_id}/reserve-plans",
            headers={"Idempotency-Key": "reserve-plan-001"},
            json=payload,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["plans"]) == 4
        assert all(item["result"]["checker"]["passed"] for item in body["plans"])
        saved = client.get(f"/api/v1/reserve-plans/{body['plans'][0]['plan_id']}")
        assert saved.status_code == 200
        reused = client.post(
            f"/api/v1/scenario-runs/{run_id}/reserve-plans",
            headers={"Idempotency-Key": "reserve-plan-002"},
            json=payload,
        )
        assert reused.json()["reused"] is True


def test_reserve_api_requires_idempotency_and_production_security(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(
        update={"sanjiv_env": "production", "sanjiv_scenario_api_key": "operator-secret"}
    )
    with TestClient(create_app(settings=settings)) as client:
        path = "/api/v1/scenario-runs/00000000-0000-0000-0000-000000000000/reserve-plans"
        assert (
            client.post(
                path, json={"procurement_plan_id": "00000000-0000-0000-0000-000000000000"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                path,
                headers={"Idempotency-Key": "reserve-denied"},
                json={"procurement_plan_id": "00000000-0000-0000-0000-000000000000"},
            ).status_code
            == 401
        )


def test_openapi_exposes_phase_five_routes_and_contracts(tmp_path: Path) -> None:
    schema = create_app(settings=_settings(tmp_path)).openapi()
    assert "/api/v1/scenario-runs/{run_id}/reserve-plans" in schema["paths"]
    assert "/api/v1/reserve-plans/{plan_id}" in schema["paths"]
    for contract in (
        "ReserveExecutionRequest",
        "ReservePlanResponse",
        "ReserveOptimisationInput",
        "ReserveCheckResult",
    ):
        assert contract in schema["components"]["schemas"]
