import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sanjiv.audit.repository import InMemoryAuditRepository, PostgresAuditRepository
from sanjiv.audit.routes import router as audit_router
from sanjiv.audit.service import AuditService
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
from sanjiv.operations.dependencies import dependency_health
from sanjiv.operations.routes import router as operations_router
from sanjiv.operations.security import ProductionSecurityMiddleware
from sanjiv.operations.telemetry import TelemetryMiddleware, TelemetryRegistry
from sanjiv.phase8.repository import InMemoryPhase8Repository, PostgresPhase8Repository
from sanjiv.phase8.routes import router as phase8_router
from sanjiv.phase8.service import Phase8Service
from sanjiv.procurement.openapi import add_procurement_contract_schemas
from sanjiv.procurement.repository import (
    InMemoryProcurementRepository,
    PostgresProcurementRepository,
)
from sanjiv.procurement.routes import router as procurement_router
from sanjiv.procurement.service import ProcurementService
from sanjiv.reserve.openapi import add_reserve_contract_schemas
from sanjiv.reserve.repository import InMemoryReserveRepository, PostgresReserveRepository
from sanjiv.reserve.routes import router as reserve_router
from sanjiv.reserve.service import ReserveService
from sanjiv.risk.adapters import FixtureRiskAdapter
from sanjiv.risk.openapi import add_risk_contract_schemas
from sanjiv.risk.repository import InMemoryRiskRepository, PostgresRiskRepository
from sanjiv.risk.routes import router as risk_router
from sanjiv.risk.service import RiskService
from sanjiv.scenarios.compiler import (
    DisabledScenarioProvider,
    OpenAIResponsesScenarioProvider,
)
from sanjiv.scenarios.repository import (
    InMemoryScenarioRepository,
    PostgresScenarioRepository,
)
from sanjiv.scenarios.routes import router as scenario_router
from sanjiv.scenarios.service import ScenarioService
from sanjiv.settings import Settings, get_settings
from sanjiv.twin.routes import router as twin_router
from sanjiv.twin.service import build_default_twin_service


class HealthResponse(BaseModel):
    status: Literal["alive", "ready"]
    service: Literal["sanjiv-api"] = "sanjiv-api"
    version: Literal["0.3.0"] = "0.3.0"
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
    provider = (
        OpenAIResponsesScenarioProvider(
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.sanjiv_llm_model,
        )
        if resolved_settings.sanjiv_llm_provider.casefold() == "openai"
        else DisabledScenarioProvider()
    )
    twin_service = build_default_twin_service()
    scenario_repository = (
        PostgresScenarioRepository(resolved_settings.database_url, twin_service.current())
        if resolved_settings.sanjiv_scenario_storage == "postgres"
        else InMemoryScenarioRepository()
    )
    scenario_service = ScenarioService(
        twin_service=twin_service,
        repository=scenario_repository,
        provider=provider,
    )
    procurement_repository = (
        PostgresProcurementRepository(resolved_settings.database_url)
        if resolved_settings.sanjiv_procurement_storage == "postgres"
        else InMemoryProcurementRepository()
    )
    procurement_service = ProcurementService(
        scenario_service=scenario_service,
        repository=procurement_repository,
    )
    reserve_repository = (
        PostgresReserveRepository(resolved_settings.database_url)
        if resolved_settings.sanjiv_reserve_storage == "postgres"
        else InMemoryReserveRepository()
    )
    reserve_service = ReserveService(
        scenario_service=scenario_service,
        procurement_service=procurement_service,
        repository=reserve_repository,
    )
    risk_repository = (
        PostgresRiskRepository(resolved_settings.database_url)
        if resolved_settings.sanjiv_risk_storage == "postgres"
        else InMemoryRiskRepository()
    )
    risk_service = RiskService(
        repository=risk_repository,
        adapter=FixtureRiskAdapter(resolved_settings.sanjiv_risk_replay_manifest),
    )
    audit_repository = (
        PostgresAuditRepository(resolved_settings.database_url)
        if resolved_settings.sanjiv_audit_storage == "postgres"
        else InMemoryAuditRepository()
    )
    audit_service = AuditService(
        scenario_service=scenario_service,
        procurement_service=procurement_service,
        reserve_service=reserve_service,
        repository=audit_repository,
    )
    phase8_repository = (
        PostgresPhase8Repository(resolved_settings.database_url)
        if resolved_settings.sanjiv_phase8_storage == "postgres"
        else InMemoryPhase8Repository()
    )
    phase8_service = Phase8Service(
        audit_service=audit_service,
        repository=phase8_repository,
        replay_manifest=resolved_settings.sanjiv_phase8_replay_manifest,
        lpg_manifest=resolved_settings.sanjiv_lpg_fixture_manifest,
        risk_service=risk_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        geofences = load_geofences(resolved_settings.sanjiv_geofence_fixture)
        await service.repository.initialize(geofences)
        await scenario_service.initialize()
        await procurement_service.initialize()
        await reserve_service.initialize()
        await risk_service.initialize()
        await audit_service.initialize()
        await phase8_service.initialize()
        await service.initialize()
        if resolved_settings.sanjiv_maritime_autostart:
            service.start()
        yield
        await service.stop()
        await scenario_service.close()
        await procurement_service.close()
        await reserve_service.close()
        await risk_service.close()
        await audit_service.close()
        await phase8_service.close()
        close = getattr(service.repository, "close", None)
        if close is not None:
            await close()

    application = FastAPI(
        title="Sanjiv API",
        summary="India's Energy Resilience Command Center",
        description="Keep India's energy moving.",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.maritime_service = service
    application.state.scenario_service = scenario_service
    application.state.procurement_service = procurement_service
    application.state.reserve_service = reserve_service
    application.state.risk_service = risk_service
    application.state.audit_service = audit_service
    application.state.phase8_service = phase8_service
    telemetry = TelemetryRegistry()
    application.state.telemetry = telemetry
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "X-Sanjiv-Scenario-Key",
            "X-Sanjiv-Demo-Identity",
            "X-Sanjiv-Governance-Key",
            "X-Sanjiv-API-Key",
            "X-Correlation-ID",
            "X-Causation-ID",
        ],
    )
    application.add_middleware(ProductionSecurityMiddleware, settings=resolved_settings)
    application.add_middleware(
        TelemetryMiddleware,
        registry=telemetry,
        log_level=resolved_settings.sanjiv_log_level,
    )
    application.include_router(maritime_router)
    application.include_router(websocket_router)
    application.include_router(twin_router)
    application.include_router(scenario_router)
    application.include_router(procurement_router)
    application.include_router(reserve_router)
    application.include_router(risk_router)
    application.include_router(audit_router)
    application.include_router(phase8_router)
    application.include_router(operations_router)

    @application.exception_handler(HTTPException)
    async def typed_http_error(_: Request, error: HTTPException) -> JSONResponse:
        if isinstance(error.detail, dict) and "code" in error.detail:
            return JSONResponse(status_code=error.status_code, content=error.detail)
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @application.exception_handler(Exception)
    async def redacted_internal_error(request: Request, error: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", "unavailable")
        logging.getLogger("sanjiv.error").error(
            "unhandled_error type=%s correlation_id=%s",
            type(error).__name__,
            correlation_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "The request failed safely; internal details were redacted.",
                "correlation_id": correlation_id,
            },
        )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="alive", checked_at=datetime.now(UTC))

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse | JSONResponse:
        if resolved_settings.sanjiv_dependency_checks_enabled:
            dependencies = await dependency_health(resolved_settings)
            unavailable = [item.component for item in dependencies if item.status != "HEALTHY"]
            if unavailable:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "degraded",
                        "service": "sanjiv-api",
                        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "unavailable": unavailable,
                    },
                )
        return HealthResponse(status="ready", checked_at=datetime.now(UTC))

    @application.get(
        "/api/v1/contracts/sample",
        response_model=FoundationContractSample,
        tags=["foundation"],
    )
    async def contract_sample() -> FoundationContractSample:
        from sanjiv.sample import build_foundation_sample

        return build_foundation_sample()

    add_procurement_contract_schemas(application)
    add_reserve_contract_schemas(application)
    add_risk_contract_schemas(application)
    return application


app = create_app()
