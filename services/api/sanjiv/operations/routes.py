from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request

from sanjiv.operations.contracts import ComponentHealth, OperationsStatus
from sanjiv.operations.dependencies import dependency_health
from sanjiv.operations.telemetry import TelemetryRegistry

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _worker_health(runtime_dir: Path, now: datetime) -> list[ComponentHealth]:
    result: list[ComponentHealth] = []
    for role in ("ingestion", "refresh", "compute"):
        path = runtime_dir / f"{role}.json"
        if not path.exists():
            result.append(
                ComponentHealth(
                    component=f"worker:{role}",
                    status="NOT_CONFIGURED",
                    checked_at=now,
                    detail="No worker heartbeat has been observed.",
                )
            )
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            heartbeat = datetime.fromisoformat(str(payload["heartbeat_at"]).replace("Z", "+00:00"))
            stale = (now - heartbeat).total_seconds() > 30
            result.append(
                ComponentHealth(
                    component=f"worker:{role}",
                    status="DEGRADED" if stale else "HEALTHY",
                    checked_at=now,
                    detail=f"pid={payload.get('pid', 'unknown')} mode={payload.get('mode', role)}",
                    stale=stale,
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            result.append(
                ComponentHealth(
                    component=f"worker:{role}",
                    status="UNAVAILABLE",
                    checked_at=now,
                    detail="Worker heartbeat is unreadable.",
                    stale=True,
                )
            )
    return result


@router.get("/status", response_model=OperationsStatus)
async def operations_status(request: Request) -> OperationsStatus:
    now = datetime.now(UTC)
    settings = request.app.state.settings
    telemetry: TelemetryRegistry = request.app.state.telemetry
    source_snapshot = await request.app.state.maritime_service.snapshot()
    components = [
        ComponentHealth(
            component="source:maritime",
            status="HEALTHY"
            if source_snapshot.source_health.state.value == "READY"
            else "DEGRADED",
            checked_at=now,
            detail=(
                f"mode={source_snapshot.operating_mode.value} "
                f"freshness={source_snapshot.source_health.freshness_status.value}"
            ),
            stale=source_snapshot.source_health.freshness_status.value == "STALE",
        )
    ]
    components.extend(_worker_health(settings.sanjiv_worker_runtime_dir, now))
    if settings.sanjiv_dependency_checks_enabled:
        components.extend(await dependency_health(settings))
    return OperationsStatus(
        status="DEGRADED"
        if any(item.status in {"DEGRADED", "UNAVAILABLE"} for item in components)
        else "READY",
        checked_at=now,
        commit_sha=os.getenv("SANJIV_COMMIT_SHA", "development"),
        environment=settings.sanjiv_env,
        components=components,
        runtimes=telemetry.snapshot(),
    )
