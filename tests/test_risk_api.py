from pathlib import Path

from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.main import create_app
from sanjiv.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_scenario_storage="memory",
        sanjiv_procurement_storage="memory",
        sanjiv_reserve_storage="memory",
        sanjiv_risk_storage="memory",
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def test_risk_apis_expose_ranked_details_alerts_timeline_and_backtests(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        overview = client.get("/api/v1/risk/corridors")
        assert overview.status_code == 200
        risks = overview.json()["risks"]
        assert len(risks) == 5
        assert [item["severity"]["value"] for item in risks] == sorted(
            [item["severity"]["value"] for item in risks], reverse=True
        )
        detail = client.get(f"/api/v1/risk/corridors/{risks[0]['risk_id']}")
        assert detail.status_code == 200
        assert len(detail.json()["contributions"]) == 6
        timeline = client.get(f"/api/v1/risk/corridors/{risks[0]['corridor_id']}/timeline")
        assert timeline.status_code == 200 and timeline.json()
        alerts = client.get("/api/v1/risk/alerts").json()["alerts"]
        assert alerts and all(item["autonomous_action"] is False for item in alerts)
        backtest = client.get("/api/v1/risk/backtests").json()["results"][0]
        assert backtest["fixture_evidence_only"] is True
        assert len(backtest["cases"]) == 10


def test_risk_not_found_is_typed(tmp_path: Path) -> None:
    with TestClient(create_app(settings=_settings(tmp_path))) as client:
        response = client.get("/api/v1/risk/corridors/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["code"] == "RISK_NOT_FOUND"


def test_openapi_exposes_phase_six_routes_and_contracts(tmp_path: Path) -> None:
    schema = create_app(settings=_settings(tmp_path)).openapi()
    for route in (
        "/api/v1/risk/corridors",
        "/api/v1/risk/corridors/{risk_id}",
        "/api/v1/risk/corridors/{corridor_id}/timeline",
        "/api/v1/risk/alerts",
        "/api/v1/risk/backtests",
    ):
        assert route in schema["paths"]
    for contract in (
        "NormalizedRiskFeature",
        "FeatureContribution",
        "CorridorRiskResult",
        "AlertResult",
        "BacktestResult",
    ):
        assert contract in schema["components"]["schemas"]
