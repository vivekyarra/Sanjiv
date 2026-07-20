from uuid import UUID

from fastapi import APIRouter, HTTPException

from sanjiv.twin.contracts import TwinSnapshot
from sanjiv.twin.service import TwinService, build_default_twin_service

router = APIRouter(prefix="/api/v1/twin", tags=["digital-twin"])


def _service() -> TwinService:
    return build_default_twin_service()


@router.get("/snapshots/current", response_model=TwinSnapshot)
async def current_snapshot() -> TwinSnapshot:
    return _service().current()


@router.get("/snapshots/{snapshot_id}", response_model=TwinSnapshot)
async def snapshot_by_id(snapshot_id: UUID) -> TwinSnapshot:
    snapshot = _service().get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Twin snapshot not found")
    return snapshot


@router.get("/network", response_model=TwinSnapshot)
async def network() -> TwinSnapshot:
    return _service().current()
