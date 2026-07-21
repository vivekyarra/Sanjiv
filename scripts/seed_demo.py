# ruff: noqa: E402 -- this standalone script bootstraps the API source tree before imports.

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient
from sanjiv.main import create_app
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service


def main() -> None:
    settings = Settings(sanjiv_ais_enabled=False, sanjiv_maritime_autostart=False)
    snapshot = build_default_twin_service().current()
    with TestClient(create_app(settings=settings)) as client:
        compiled = client.post(
            "/api/v1/scenarios/compile",
            headers={"Idempotency-Key": "demo-seed-compile-v1"},
            json={
                "mode": "DETERMINISTIC_TEXT",
                "twin_snapshot_id": str(snapshot.snapshot_id),
                "text": "Close the Strait of Hormuz for 14 days.",
            },
        )
        compiled.raise_for_status()
        scenario_id = compiled.json()["candidate"]["scenario_id"]
        confirmed = client.post(
            f"/api/v1/scenarios/{scenario_id}/confirm",
            headers={"Idempotency-Key": "demo-seed-confirm-v1"},
            json={"confirming_identity": "ignored-client-identity"},
        )
        confirmed.raise_for_status()
        run = client.post(
            "/api/v1/scenario-runs",
            headers={"Idempotency-Key": "demo-seed-simulation-v1"},
            json={"scenario_id": scenario_id, "configuration": {}},
        )
        run.raise_for_status()
        run_id = run.json()["run_id"]
        procurement = client.post(
            f"/api/v1/scenario-runs/{run_id}/procurement-plans",
            headers={"Idempotency-Key": "demo-seed-procurement-v1"},
            json={},
        )
        procurement.raise_for_status()
        procurement_ids = [item["plan_id"] for item in procurement.json()["plans"]]
        balanced_id = procurement_ids[1]
        reserve = client.post(
            f"/api/v1/scenario-runs/{run_id}/reserve-plans",
            headers={"Idempotency-Key": "demo-seed-reserve-v1"},
            json={"procurement_plan_id": balanced_id},
        )
        reserve.raise_for_status()
        reserve_ids = [item["plan_id"] for item in reserve.json()["plans"]]
        audit = client.get(f"/api/v1/plans/{balanced_id}/audit")
        audit.raise_for_status()
        replay = client.post(
            "/api/v1/replay-cases/hormuz-partial-14d/runs",
            headers={"Idempotency-Key": "demo-seed-replay-v1"},
        )
        replay.raise_for_status()
        payload = {
            "classification": "SYNTHETIC_FIXTURE",
            "scenario_id": scenario_id,
            "simulation_run_id": run_id,
            "procurement_plan_ids": procurement_ids,
            "reserve_plan_ids": reserve_ids,
            "audit_id": audit.json()["audit_id"],
            "replay_run_id": replay.json()["run_id"],
            "twin_snapshot_id": str(snapshot.snapshot_id),
            "notice": "Decision support only; no order or reserve action was executed.",
        }
    target = Path("data/runtime/demo/seed-manifest.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
