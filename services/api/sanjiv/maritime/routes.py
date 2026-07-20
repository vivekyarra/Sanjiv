import asyncio
from typing import Annotated, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from sanjiv.contracts import SourceHealthRecord
from sanjiv.maritime.contracts import (
    Geofence,
    OperatingModeTransition,
    OperationsEvent,
    OperationsSnapshot,
    VesselHistoryResponse,
    VesselOperationalView,
)
from sanjiv.maritime.service import MaritimeWatchService

router = APIRouter(prefix="/api/v1", tags=["maritime-watch"])


def get_maritime_service(request: Request) -> MaritimeWatchService:
    return cast(MaritimeWatchService, request.app.state.maritime_service)


Service = Annotated[MaritimeWatchService, Depends(get_maritime_service)]


@router.get("/operations/snapshot", response_model=OperationsSnapshot)
async def operations_snapshot(service: Service) -> OperationsSnapshot:
    return await service.snapshot()


@router.get("/vessels/{vessel_id}", response_model=VesselOperationalView)
async def vessel_detail(vessel_id: UUID, service: Service) -> VesselOperationalView:
    item = await service.vessel(vessel_id)
    if item is None:
        raise HTTPException(status_code=404, detail="vessel not found")
    return item


@router.get("/vessels/{vessel_id}/history", response_model=VesselHistoryResponse)
async def vessel_history(
    vessel_id: UUID,
    service: Service,
    limit: int = Query(default=100, ge=1, le=1000),
) -> VesselHistoryResponse:
    result = await service.history(vessel_id, limit)
    if result is None:
        raise HTTPException(status_code=404, detail="vessel not found")
    return result


@router.get("/geofences", response_model=list[Geofence])
async def geofences(service: Service) -> list[Geofence]:
    return await service.repository.geofences()


@router.get("/sources/health", response_model=list[SourceHealthRecord])
async def source_health(service: Service) -> list[SourceHealthRecord]:
    snapshot = await service.snapshot()
    return [snapshot.source_health]


@router.get("/operations/mode-transitions", response_model=list[OperatingModeTransition])
async def mode_transitions(service: Service) -> list[OperatingModeTransition]:
    return await service.repository.transitions()


async def operations_socket(websocket: WebSocket) -> None:
    service: MaritimeWatchService = websocket.app.state.maritime_service
    try:
        after = int(websocket.query_params.get("after", "0"))
    except ValueError:
        await websocket.close(code=1008, reason="after cursor must be an integer")
        return
    await websocket.accept()
    backlog = service.broker.since(after)
    if backlog is None:
        await websocket.send_json(
            OperationsEvent(
                sequence=max(1, service.broker.cursor),
                event_type="RESYNC_REQUIRED",
                occurred_at=(await service.snapshot()).as_of,
                operating_mode=(await service.snapshot()).operating_mode,
                payload={
                    "reason": "cursor_outside_retention",
                    "snapshot_url": "/api/v1/operations/snapshot",
                },
            ).model_dump(mode="json")
        )
    else:
        for event in backlog:
            await websocket.send_json(event.model_dump(mode="json"))

    heartbeat_seconds = websocket.app.state.settings.sanjiv_websocket_heartbeat_seconds
    try:
        async with service.broker.subscribe() as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    snapshot = await service.snapshot()
                    await websocket.send_json(
                        OperationsEvent(
                            sequence=max(1, service.broker.cursor),
                            event_type="HEARTBEAT",
                            occurred_at=snapshot.as_of,
                            operating_mode=snapshot.operating_mode,
                            payload={
                                "cursor": snapshot.cursor,
                                "connection_state": snapshot.connection_state,
                                "freshness_status": snapshot.source_health.freshness_status,
                            },
                        ).model_dump(mode="json")
                    )
                else:
                    await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        return


websocket_router = APIRouter()
websocket_router.add_api_websocket_route("/ws/v1/operations", operations_socket)
