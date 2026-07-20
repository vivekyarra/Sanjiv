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
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def test_complete_api_lifecycle_candidate_to_persisted_result(tmp_path: Path) -> None:
    snapshot = build_default_twin_service().current()
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        supported = client.get("/api/v1/scenario-types")
        metadata = client.get("/api/v1/scenarios/form-metadata")
        assert supported.status_code == 200 and len(supported.json()) >= 6
        assert metadata.json()["llm_provider_available"] is False

        compiled = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "api-compile-001"},
            json={
                "mode": "DETERMINISTIC_TEXT",
                "twin_snapshot_id": str(snapshot.snapshot_id),
                "text": "Close the Strait of Hormuz for 14 days.",
            },
        )
        assert compiled.status_code == 200
        assert compiled.json()["validation"]["valid"] is True
        scenario_id = compiled.json()["candidate"]["scenario_id"]
        assert client.get(f"/api/v1/scenarios/{scenario_id}/validation").status_code == 200

        confirmed = client.post(
            f"/api/v1/scenarios/{scenario_id}/confirm",
            headers={"Idempotency-Key": "api-confirm-001"},
            json={"confirming_identity": "local-demo"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["lifecycle"] == "CONFIRMED"
        assert confirmed.json()["confirmed_by"] == "local-demo-operator"
        assert client.get(f"/api/v1/scenarios/{scenario_id}/assumptions").json()
        assert client.get(f"/api/v1/scenarios/{scenario_id}/evidence").json()
        assert client.get(f"/api/v1/scenarios/{scenario_id}/audit-events").json()

        started = client.post(
            "/api/v1/scenario-runs",
            headers={"Idempotency-Key": "api-run-0000001"},
            json={"scenario_id": scenario_id, "configuration": {}},
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        status = client.get(f"/api/v1/scenario-runs/{run_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "COMPLETED"
        assert status.json()["runtime_ms"] >= 0
        progress = client.get(f"/api/v1/scenario-runs/{run_id}/progress").json()
        assert progress[0]["status"] == "QUEUED"
        assert progress[-1]["status"] == "COMPLETED"
        result = client.get(f"/api/v1/scenario-runs/{run_id}/results")
        timeline = client.get(f"/api/v1/scenario-runs/{run_id}/timeline")
        assert result.status_code == 200
        assert result.json()["inventory_status"] == "UNKNOWN"
        assert len(timeline.json()) == 30


def test_production_scenario_mutations_require_server_credential(tmp_path: Path) -> None:
    snapshot = build_default_twin_service().current()
    settings = _settings(tmp_path).model_copy(
        update={"sanjiv_env": "production", "sanjiv_scenario_api_key": "test-operator-key"}
    )
    payload = {
        "mode": "DETERMINISTIC_TEXT",
        "twin_snapshot_id": str(snapshot.snapshot_id),
        "text": "Close the Strait of Hormuz for 14 days.",
    }
    with TestClient(create_app(settings=settings)) as client:
        denied = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "production-denied"},
            json=payload,
        )
        allowed = client.post(
            "/api/v1/scenarios/compile",
            headers={
                "Idempotency-Key": "production-allowed",
                "X-Sanjiv-Scenario-Key": "test-operator-key",
            },
            json=payload,
        )
        assert denied.status_code == 401
        assert allowed.status_code == 200


def test_api_uses_typed_errors_and_requires_confirmation(tmp_path: Path) -> None:
    snapshot = build_default_twin_service().current()
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        compiled = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "api-invalid-compile"},
            json={
                "mode": "DETERMINISTIC_TEXT",
                "twin_snapshot_id": str(snapshot.snapshot_id),
                "text": "Close an imaginary strait for 14 days.",
            },
        )
        assert compiled.status_code == 200
        assert compiled.json()["candidate"] is None
        unconfirmed = client.post(
            "/api/v1/scenario-runs",
            headers={"Idempotency-Key": "api-unconfirmed-run"},
            json={"scenario_id": str(snapshot.snapshot_id), "configuration": {}},
        )
        assert unconfirmed.status_code == 409
        assert set(unconfirmed.json()) == {"code", "message", "correlation_id", "details"}


def test_openapi_freezes_phase_three_rest_and_progress_contracts(tmp_path: Path) -> None:
    schema = create_app(settings=_settings(tmp_path)).openapi()
    for path in (
        "/api/v1/scenario-types",
        "/api/v1/scenarios/form-metadata",
        "/api/v1/scenarios/compile",
        "/api/v1/scenarios/{scenario_id}/validate",
        "/api/v1/scenarios/{scenario_id}/confirm",
        "/api/v1/scenario-runs",
        "/api/v1/scenario-runs/{run_id}",
        "/api/v1/scenario-runs/{run_id}/progress",
        "/api/v1/scenario-runs/{run_id}/cancel",
        "/api/v1/scenario-runs/{run_id}/results",
    ):
        assert path in schema["paths"]
    for contract in (
        "ScenarioCandidate",
        "ScenarioValidationResult",
        "ConfirmedScenario",
        "SimulationRun",
        "SimulationProgressEvent",
        "SimulationResult",
        "SimulationFailureResult",
        "UncertaintyRange",
    ):
        assert contract in schema["components"]["schemas"]
