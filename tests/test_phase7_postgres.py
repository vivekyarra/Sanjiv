from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from maritime_helpers import GEOFENCES, REPLAY_MANIFEST
from sanjiv.main import create_app
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=False,
        sanjiv_replay_dataset=REPLAY_MANIFEST,
        sanjiv_geofence_fixture=GEOFENCES,
        sanjiv_replay_runtime_dir=tmp_path,
    )


def test_postgres_rehydrates_audit_and_immutable_approval(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot = build_default_twin_service().current()
    with TestClient(create_app(settings=settings)) as client:
        compiled = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "phase7-postgres-compile"},
            json={
                "mode": "DETERMINISTIC_TEXT",
                "twin_snapshot_id": str(snapshot.snapshot_id),
                "text": "Reduce Hormuz capacity by 61% for 13 days.",
            },
        ).json()
        scenario_id = compiled["candidate"]["scenario_id"]
        client.post(
            f"/api/v1/scenarios/{scenario_id}/confirm",
            headers={"Idempotency-Key": "phase7-postgres-confirm"},
            json={"confirming_identity": "ignored"},
        )
        run = client.post(
            "/api/v1/scenario-runs",
            headers={"Idempotency-Key": "phase7-postgres-run"},
            json={"scenario_id": scenario_id, "configuration": {}},
        ).json()
        response = client.post(
            f"/api/v1/scenario-runs/{run['run_id']}/procurement-plans",
            headers={"Idempotency-Key": "phase7-postgres-plan"},
            json={},
        ).json()
        plan_id = response["plans"][1]["plan_id"]
        audit = client.get(f"/api/v1/plans/{plan_id}/audit").json()
        binding = {
            "plan_fingerprint": audit["fingerprints"]["plan"],
            "assumption_fingerprint": audit["fingerprints"]["assumptions"],
            "audit_fingerprint": audit["audit_fingerprint"],
        }
        client.post(
            f"/api/v1/plans/{plan_id}/reviews",
            headers={
                "Idempotency-Key": "phase7-postgres-submit",
                "X-Sanjiv-Demo-Identity": "local-demo-operator",
            },
            json={**binding, "action": "SUBMIT_FOR_REVIEW", "comment": "Ready."},
        )
        approved = client.post(
            f"/api/v1/plans/{plan_id}/approvals",
            headers={
                "Idempotency-Key": "phase7-postgres-approve",
                "X-Sanjiv-Demo-Identity": "local-demo-approver",
            },
            json={**binding, "comment": "Approved for decision support."},
        )
        assert approved.status_code == 200
        record_id = approved.json()["record_id"]

    with TestClient(create_app(settings=settings)) as restarted:
        governance = restarted.get(f"/api/v1/plans/{plan_id}/governance")
        assert governance.status_code == 200
        assert governance.json()["state"] == "APPROVED"
        assert (
            governance.json()["latest_audit"]["audit_fingerprint"] == binding["audit_fingerprint"]
        )

    database_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                "UPDATE plan_lifecycle_records SET actor_id='forged' WHERE record_id=%s",
                (record_id,),
            )
        except psycopg.errors.RaiseException:
            connection.rollback()
        else:
            raise AssertionError("immutable approval update unexpectedly succeeded")
