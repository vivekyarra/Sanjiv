from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sanjiv.contracts import (
    Assumption,
    AuditEvent,
    EvidenceRecord,
    MetricEnvelope,
    SourceHealthRecord,
)
from sanjiv.maritime.adapters import AISStreamAdapter, ReplayAISAdapter
from sanjiv.maritime.geofences import GeofenceEngine, load_geofences
from sanjiv.maritime.recording import RawBatchRecorder
from sanjiv.maritime.repository import InMemoryMaritimeRepository, PostgresMaritimeRepository
from sanjiv.maritime.routes import router as maritime_router
from sanjiv.maritime.routes import websocket_router
from sanjiv.maritime.service import MaritimeWatchService
from sanjiv.settings import Settings, get_settings


class HealthResponse(BaseModel):
    status: Literal["alive", "ready"]
    service: Literal["sanjiv-api"] = "sanjiv-api"
    version: Literal["0.2.0"] = "0.2.0"
    checked_at: datetime


class FoundationContractSample(BaseModel):
    metric: MetricEnvelope[float]
    evidence: EvidenceRecord
    source_health: SourceHealthRecord
    assumption: Assumption
    audit_event: AuditEvent


def build_maritime_service(settings: Settings) -> MaritimeWatchService:
    geofences = load_geofences(settings.sanjiv_geofence_fixture)
    repository = (
        PostgresMaritimeRepository(settings.database_url)
        if settings.sanjiv_maritime_storage == "postgres"
        else InMemoryMaritimeRepository()
    )
    replay = ReplayAISAdapter(
        settings.sanjiv_replay_dataset,
        speed=settings.sanjiv_replay_speed,
        loop=settings.sanjiv_replay_loop,
    )
    live = None
    if settings.sanjiv_ais_enabled and settings.aisstream_api_key:
        live = AISStreamAdapter(
            api_key=settings.aisstream_api_key,
            url=settings.sanjiv_aisstream_url,
            bounding_boxes=settings.sanjiv_ais_bounding_boxes,
            connect_timeout_seconds=settings.sanjiv_ais_connect_timeout_seconds,
            subscription_timeout_seconds=settings.sanjiv_ais_subscription_timeout_seconds,
            max_retries=settings.sanjiv_ais_max_retries,
            reconnect_base_seconds=settings.sanjiv_ais_reconnect_base_seconds,
            reconnect_max_seconds=settings.sanjiv_ais_reconnect_max_seconds,
            queue_size=settings.sanjiv_ais_queue_size,
        )
    return MaritimeWatchService(
        repository=repository,
        geofence_engine=GeofenceEngine(geofences),
        live_adapter=live,
        replay_adapter=replay,
        recorder=RawBatchRecorder(settings.sanjiv_replay_runtime_dir),
        stale_after_seconds=settings.sanjiv_stale_after_seconds,
    )


def create_app(
    *,
    settings: Settings | None = None,
    maritime_service: MaritimeWatchService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    service = maritime_service or build_maritime_service(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        geofences = load_geofences(resolved_settings.sanjiv_geofence_fixture)
        await service.repository.initialize(geofences)
        await service.initialize()
        if resolved_settings.sanjiv_maritime_autostart:
            service.start()
        yield
        await service.stop()
        close = getattr(service.repository, "close", None)
        if close is not None:
            await close()

    application = FastAPI(
        title="Sanjiv API",
        summary="India's Energy Resilience Command Center",
        description="Keep India's energy moving.",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.maritime_service = service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(maritime_router)
    application.include_router(websocket_router)

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="alive", checked_at=datetime.now(UTC))

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse:
        return HealthResponse(status="ready", checked_at=datetime.now(UTC))

    @application.get(
        "/api/v1/contracts/sample",
        response_model=FoundationContractSample,
        tags=["foundation"],
    )
    async def contract_sample() -> FoundationContractSample:
        from sanjiv.sample import build_foundation_sample

        return build_foundation_sample()

    return application


app = create_app()
