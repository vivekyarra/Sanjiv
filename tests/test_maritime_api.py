from pathlib import Path

from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.main import create_app
from sanjiv.settings import Settings


def test_rest_snapshot_source_health_and_websocket_heartbeat(tmp_path: Path) -> None:
    settings = Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
        sanjiv_websocket_heartbeat_seconds=0.01,
    )
    with TestClient(create_app(settings=settings)) as client:
        snapshot = client.get("/api/v1/operations/snapshot")
        assert snapshot.status_code == 200
        payload = snapshot.json()
        assert payload["schema_version"] == "1.0"
        assert payload["operating_mode"] == "DEGRADED"
        assert len(payload["geofences"]) >= 7

        source_health = client.get("/api/v1/sources/health")
        assert source_health.status_code == 200
        assert source_health.json()[0]["mode"] == "REPLAY"

        with client.websocket_connect("/ws/v1/operations?after=0") as socket:
            heartbeat = socket.receive_json()
            assert heartbeat["event_type"] == "HEARTBEAT"
            assert heartbeat["schema_version"] == "1.0"
            assert heartbeat["payload"]["cursor"] == 0


def test_openapi_contains_phase_one_rest_contracts(tmp_path: Path) -> None:
    settings = Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )
    schema = create_app(settings=settings).openapi()
    paths = schema["paths"]
    assert "/api/v1/operations/snapshot" in paths
    assert "/api/v1/vessels/{vessel_id}/history" in paths
    assert "/api/v1/sources/health" in paths
    required = schema["components"]["schemas"]["VesselPosition"]["required"]
    assert {"source_timestamp", "fetched_at", "evidence_ids", "truth_class"} <= set(required)
