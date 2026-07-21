from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.main import create_app
from sanjiv.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def test_phase8_postgres_restart_readback_and_immutability(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/v1/replay-cases/lpg-hormuz-14d/runs",
            headers={"Idempotency-Key": "phase8-postgres-replay"},
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        plans = client.get(f"/api/v1/replay-runs/{run_id}/lpg-plans")
        assert plans.status_code == 200
        plan_id = plans.json()[0]["plan_id"]

    with TestClient(create_app(settings=settings)) as restarted:
        replay = restarted.get(f"/api/v1/replay-runs/{run_id}")
        assert replay.status_code == 200
        assert replay.json()["case_id"] == "lpg-hormuz-14d"
        plans = restarted.get(f"/api/v1/replay-runs/{run_id}/lpg-plans")
        assert plans.status_code == 200
        assert plans.json()[0]["plan_id"] == plan_id

    database_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                "UPDATE phase8_replay_runs SET case_id='forged' WHERE run_id=%s",
                (run_id,),
            )
        except psycopg.errors.RaiseException:
            connection.rollback()
        else:
            raise AssertionError("immutable replay update unexpectedly succeeded")
