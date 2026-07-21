# ruff: noqa: E402 -- this standalone script bootstraps the API source tree before imports.

from __future__ import annotations

import asyncio
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient
from sanjiv.main import create_app
from sanjiv.maritime.broker import OperationsBroker
from sanjiv.maritime.contracts import OperatingMode
from sanjiv.risk.adapters import FixtureRiskAdapter
from sanjiv.risk.repository import InMemoryRiskRepository
from sanjiv.risk.service import RiskService
from sanjiv.settings import Settings
from sanjiv.twin.service import build_default_twin_service

SAMPLES = 5


def _stats(values: list[float], unit: str = "ms") -> dict[str, object]:
    ordered = sorted(round(value, 3) for value in values)
    p95_index = min(len(ordered) - 1, max(0, round(0.95 * (len(ordered) - 1))))
    return {
        "unit": unit,
        "samples": len(ordered),
        "minimum": ordered[0],
        "median": round(statistics.median(ordered), 3),
        "p95": ordered[p95_index],
        "maximum": ordered[-1],
    }


def _timed(action: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    result = action()
    return result, (time.perf_counter() - started) * 1000.0


async def _broker_benchmark() -> tuple[float, int, bool]:
    broker = OperationsBroker(history_size=200, subscriber_queue_size=10)
    started = time.perf_counter()
    async with broker.subscribe() as queue:
        for index in range(100):
            await broker.publish(
                "HEARTBEAT",
                OperatingMode.REPLAY,
                {"sequence": index},
            )
        received = []
        while not queue.empty():
            received.append(queue.get_nowait())
    elapsed = (time.perf_counter() - started) * 1000.0
    resync = any(item.event_type == "RESYNC_REQUIRED" for item in received)
    return elapsed, len(received), resync


async def _risk_benchmark(manifest: Path) -> float:
    service = RiskService(repository=InMemoryRiskRepository(), adapter=FixtureRiskAdapter(manifest))
    started = time.perf_counter()
    await service.initialize()
    elapsed = (time.perf_counter() - started) * 1000.0
    await service.close()
    return elapsed


def main() -> None:
    settings = Settings(
        sanjiv_maritime_storage="memory",
        sanjiv_maritime_autostart=True,
        sanjiv_replay_speed=1000,
        sanjiv_scenario_storage="memory",
        sanjiv_procurement_storage="memory",
        sanjiv_reserve_storage="memory",
        sanjiv_risk_storage="memory",
        sanjiv_audit_storage="memory",
        sanjiv_phase8_storage="memory",
    )
    snapshot = build_default_twin_service().current()
    measurements: dict[str, list[float]] = {
        "ais_ingest_to_map": [],
        "scenario_compilation": [],
        "simulation": [],
        "procurement_optimisation": [],
        "reserve_optimisation": [],
        "evidence_audit": [],
        "briefing_export": [],
        "signal_to_recommendation": [],
    }
    with TestClient(create_app(settings=settings)) as client:
        ingest_started = time.perf_counter()
        vessel_count = 0
        for _ in range(100):
            snapshot_response = client.get("/api/v1/operations/snapshot").json()
            vessel_count = int((snapshot_response.get("vessel_count") or {}).get("value", 0))
            if vessel_count:
                break
            time.sleep(0.01)
        measurements["ais_ingest_to_map"].append((time.perf_counter() - ingest_started) * 1000.0)

        for index in range(SAMPLES):
            flow_started = time.perf_counter()
            duration = 10 + index
            compiled, elapsed = _timed(
                lambda duration=duration, index=index: client.post(
                    "/api/v1/scenarios/compile",
                    headers={"Idempotency-Key": f"benchmark-compile-{index}"},
                    json={
                        "mode": "DETERMINISTIC_TEXT",
                        "twin_snapshot_id": str(snapshot.snapshot_id),
                        "text": f"Close the Strait of Hormuz for {duration} days.",
                    },
                )
            )
            compiled.raise_for_status()
            measurements["scenario_compilation"].append(elapsed)
            scenario_id = compiled.json()["candidate"]["scenario_id"]
            confirmed = client.post(
                f"/api/v1/scenarios/{scenario_id}/confirm",
                headers={"Idempotency-Key": f"benchmark-confirm-{index}"},
                json={"confirming_identity": "ignored"},
            )
            confirmed.raise_for_status()
            run, elapsed = _timed(
                lambda index=index, scenario_id=scenario_id: client.post(
                    "/api/v1/scenario-runs",
                    headers={"Idempotency-Key": f"benchmark-run-{index}"},
                    json={"scenario_id": scenario_id, "configuration": {}},
                )
            )
            run.raise_for_status()
            measurements["simulation"].append(elapsed)
            run_id = run.json()["run_id"]
            procurement, elapsed = _timed(
                lambda index=index, run_id=run_id: client.post(
                    f"/api/v1/scenario-runs/{run_id}/procurement-plans",
                    headers={"Idempotency-Key": f"benchmark-procurement-{index}"},
                    json={},
                )
            )
            procurement.raise_for_status()
            measurements["procurement_optimisation"].append(elapsed)
            balanced = procurement.json()["plans"][1]["plan_id"]
            reserve, elapsed = _timed(
                lambda index=index, run_id=run_id, balanced=balanced: client.post(
                    f"/api/v1/scenario-runs/{run_id}/reserve-plans",
                    headers={"Idempotency-Key": f"benchmark-reserve-{index}"},
                    json={"procurement_plan_id": balanced},
                )
            )
            reserve.raise_for_status()
            measurements["reserve_optimisation"].append(elapsed)
            audit, elapsed = _timed(
                lambda balanced=balanced: client.get(f"/api/v1/plans/{balanced}/audit")
            )
            audit.raise_for_status()
            measurements["evidence_audit"].append(elapsed)
            exported, elapsed = _timed(
                lambda index=index, balanced=balanced: client.post(
                    f"/api/v1/plans/{balanced}/exports",
                    headers={"Idempotency-Key": f"benchmark-export-{index}"},
                    json={"kind": "PDF_BRIEFING"},
                )
            )
            exported.raise_for_status()
            measurements["briefing_export"].append(elapsed)
            measurements["signal_to_recommendation"].append(
                (time.perf_counter() - flow_started) * 1000.0
            )

        def load_request(_: int) -> int:
            return client.get("/api/v1/operations/status").status_code

        load_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as executor:
            load_statuses = list(executor.map(load_request, range(64)))
        load_elapsed = (time.perf_counter() - load_started) * 1000.0
        if any(status != 200 for status in load_statuses):
            raise RuntimeError(f"load gate returned non-success statuses: {load_statuses}")

    broker_elapsed, delivered_after_overflow, resync_observed = asyncio.run(_broker_benchmark())
    risk_values = [
        asyncio.run(_risk_benchmark(settings.sanjiv_risk_replay_manifest)) for _ in range(SAMPLES)
    ]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    report = {
        "schema_version": "1.0",
        "run_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit": commit,
        "source_state": "DIRTY_UNCOMMITTED_PHASE9",
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "not reported by operating system",
            "logical_cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "dataset": {
            "twin_nodes": len(snapshot.nodes),
            "twin_routes": len(snapshot.routes),
            "twin_flows": len(snapshot.baseline_flows),
            "replay_cases": 21,
            "benchmark_samples": SAMPLES,
            "load_requests": len(load_statuses),
            "load_concurrency": 8,
        },
        "classification": "MEASURED_LOCAL_SYNTHETIC_FIXTURE",
        "metrics": {name: _stats(values) for name, values in measurements.items()},
        "websocket_delivery_loss_resync": {
            **_stats([broker_elapsed]),
            "published": 100,
            "queue_items_after_overflow": delivered_after_overflow,
            "resync_observed": resync_observed,
        },
        "risk_scoring": _stats(risk_values),
        "declared_concurrency_load": {
            **_stats([load_elapsed]),
            "requests": len(load_statuses),
            "concurrency": 8,
            "successful": sum(status == 200 for status in load_statuses),
        },
        "browser_metrics_file": "reports/performance/browser-benchmark.json",
        "notice": (
            "Targets are not claims. Values are actual local fixture measurements for this run; "
            "the commit is the Phase 8 parent of the uncommitted Phase 9 working tree."
        ),
    }
    target = Path("reports/performance/phase9-benchmark.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
