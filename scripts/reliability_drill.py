from __future__ import annotations

import contextlib
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "recovery" / "reliability-drill.json"
READY_URL = "http://localhost:8000/health/ready"
STATUS_URL = "http://localhost:8000/api/v1/operations/status"


def _run(*arguments: str) -> str:
    result = subprocess.run(
        [*arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.stdout.strip()


def _compose(*arguments: str) -> str:
    return _run("docker", "compose", *arguments)


def _get_json(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _wait_for(
    url: str,
    predicate: Any,
    *,
    timeout: float = 90,
) -> tuple[int, dict[str, Any], float]:
    started = time.perf_counter()
    last_status = 0
    last_payload: dict[str, Any] = {}
    while time.perf_counter() - started < timeout:
        try:
            last_status, last_payload = _get_json(url)
            if predicate(last_status, last_payload):
                return last_status, last_payload, round(
                    (time.perf_counter() - started) * 1000, 3
                )
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError(
        f"Timed out waiting for {url}; status={last_status} payload={last_payload}"
    )


def _ready() -> tuple[int, dict[str, Any], float]:
    return _wait_for(
        READY_URL,
        lambda status, payload: status == 200 and payload.get("status") == "ready",
    )


def _dependency_outage(service: str, component: str) -> dict[str, Any]:
    _compose("stop", service)
    status, payload, detection_ms = _wait_for(
        READY_URL,
        lambda current, body: current == 503 and component in body.get("unavailable", []),
    )
    _compose("start", service)
    _, recovered, recovery_ms = _ready()
    return {
        "service": service,
        "expected_component": component,
        "outage_status": status,
        "outage_payload": payload,
        "detection_ms": detection_ms,
        "recovery_ms": recovery_ms,
        "recovered_status": recovered["status"],
        "result": "PASS",
    }


def _worker_outage() -> dict[str, Any]:
    _compose("stop", "compute-worker")
    status, payload, detection_ms = _wait_for(
        STATUS_URL,
        lambda current, body: current == 200
        and any(
            item.get("component") == "worker:compute"
            and item.get("status") == "DEGRADED"
            and item.get("stale") is True
            for item in body.get("components", [])
        ),
        timeout=60,
    )
    _compose("start", "compute-worker")
    _, recovered, recovery_ms = _wait_for(
        STATUS_URL,
        lambda current, body: current == 200
        and any(
            item.get("component") == "worker:compute"
            and item.get("status") == "HEALTHY"
            for item in body.get("components", [])
        ),
    )
    return {
        "service": "compute-worker",
        "outage_status": status,
        "operations_status": payload["status"],
        "detection_ms": detection_ms,
        "recovery_ms": recovery_ms,
        "recovered_status": recovered["status"],
        "result": "PASS",
    }


def _api_restart() -> dict[str, Any]:
    started = time.perf_counter()
    _compose("restart", "api")
    _, payload, _ = _ready()
    return {
        "service": "api",
        "recovery_ms": round((time.perf_counter() - started) * 1000, 3),
        "recovered_status": payload["status"],
        "result": "PASS",
    }


def main() -> None:
    _ready()
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": str(uuid.uuid4()),
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "commit_sha": _run("git", "rev-parse", "HEAD"),
        "environment": "docker-compose app profile; local synthetic replay",
        "classification": "SYNTHETIC_FIXTURE",
        "checks": [],
        "limitations": [
            "Offline verification uses credential-free local replay; "
            "the host network is not physically disconnected.",
            "The drill stops one dependency at a time and does not measure multi-region failover.",
        ],
    }
    stopped: set[str] = set()
    try:
        for service, component in (
            ("redis", "cache:redis"),
            ("minio", "object-store:minio"),
            ("postgres", "database:postgres"),
        ):
            stopped.add(service)
            report["checks"].append(_dependency_outage(service, component))
            stopped.discard(service)
        stopped.add("compute-worker")
        report["checks"].append(_worker_outage())
        stopped.discard("compute-worker")
        report["checks"].append(_api_restart())
        report["result"] = "PASS"
    except Exception as error:
        report["result"] = "FAIL"
        report["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for service in sorted(stopped):
            with contextlib.suppress(
                subprocess.CalledProcessError, subprocess.TimeoutExpired
            ):
                _compose("start", service)
        report["completed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
