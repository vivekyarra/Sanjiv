from __future__ import annotations

import secrets
from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from sanjiv.contracts import Assumption, AuditEvent, EvidenceRecord
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmedScenario,
    ConfirmScenarioRequest,
    ScenarioCompileResponse,
    ScenarioFormMetadata,
    ScenarioValidationResult,
    SupportedScenarioType,
)
from sanjiv.scenarios.service import ScenarioDomainError, ScenarioService
from sanjiv.settings import Settings
from sanjiv.simulation.contracts import (
    SimulationProgressEvent,
    SimulationResult,
    SimulationRun,
    StartSimulationRequest,
    TimelinePoint,
)

router = APIRouter(prefix="/api/v1", tags=["scenario-lab"])


class DomainErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    correlation_id: UUID
    details: dict[str, str | float | int | bool]


def _service(request: Request) -> ScenarioService:
    service: ScenarioService = request.app.state.scenario_service
    return service


def _operator_identity(request: Request, supplied_key: str | None) -> str:
    settings: Settings = request.app.state.settings
    expected_key = settings.sanjiv_scenario_api_key
    if expected_key is not None and (
        supplied_key is None or not secrets.compare_digest(supplied_key, expected_key)
    ):
        raise HTTPException(status_code=401, detail="Invalid scenario operator credential.")
    if expected_key is None and settings.sanjiv_env not in {"development", "test"}:
        raise HTTPException(
            status_code=503,
            detail="Scenario mutations require SANJIV_SCENARIO_API_KEY outside local demo mode.",
        )
    return settings.sanjiv_scenario_operator_identity


def _raise(error: ScenarioDomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code, message=error.message, correlation_id=uuid4(), details={}
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


@router.get("/scenario-types", response_model=list[SupportedScenarioType])
async def scenario_types(request: Request) -> list[SupportedScenarioType]:
    return _service(request).supported_types()


@router.get("/scenarios/form-metadata", response_model=ScenarioFormMetadata)
async def form_metadata(request: Request) -> ScenarioFormMetadata:
    return _service(request).form_metadata()


@router.post("/scenarios/compile", response_model=ScenarioCompileResponse)
async def compile_candidate(
    payload: CompileScenarioRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> ScenarioCompileResponse:
    _operator_identity(request, scenario_api_key)
    try:
        return await _service(request).compile(payload, idempotency_key=idempotency_key)
    except ScenarioDomainError as error:
        _raise(error)


@router.post("/scenarios/{scenario_id}/validate", response_model=ScenarioValidationResult)
async def validate_candidate(
    scenario_id: UUID,
    request: Request,
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> ScenarioValidationResult:
    _operator_identity(request, scenario_api_key)
    try:
        return await _service(request).validate(scenario_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenarios/{scenario_id}/validation", response_model=ScenarioValidationResult)
async def validation_result(scenario_id: UUID, request: Request) -> ScenarioValidationResult:
    try:
        return await _service(request).validation(scenario_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.post("/scenarios/{scenario_id}/confirm", response_model=ConfirmedScenario)
async def confirm_candidate(
    scenario_id: UUID,
    payload: ConfirmScenarioRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> ConfirmedScenario:
    identity = _operator_identity(request, scenario_api_key)
    del payload  # The audited identity is server-configured, never caller asserted.
    server_payload = ConfirmScenarioRequest(confirming_identity=identity)
    try:
        return await _service(request).confirm(
            scenario_id, server_payload, idempotency_key=idempotency_key
        )
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenarios/{scenario_id}", response_model=ConfirmedScenario)
async def confirmed_scenario(scenario_id: UUID, request: Request) -> ConfirmedScenario:
    try:
        return await _service(request).confirmed(scenario_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenarios/{scenario_id}/assumptions", response_model=list[Assumption])
async def scenario_assumptions(scenario_id: UUID, request: Request) -> list[Assumption]:
    try:
        return (await _service(request).confirmed(scenario_id)).candidate.parameters.assumptions
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenarios/{scenario_id}/audit-events", response_model=list[AuditEvent])
async def scenario_audit_events(scenario_id: UUID, request: Request) -> list[AuditEvent]:
    try:
        await _service(request).confirmed(scenario_id)
        return await _service(request).repository.audits(scenario_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenarios/{scenario_id}/evidence", response_model=list[EvidenceRecord])
async def scenario_evidence(scenario_id: UUID, request: Request) -> list[EvidenceRecord]:
    try:
        confirmed = await _service(request).confirmed(scenario_id)
        snapshot = _service(request).twin_service.get(confirmed.twin_snapshot.snapshot_id)
        if snapshot is None:
            raise ScenarioDomainError(
                "TWIN_SNAPSHOT_MISSING", "Frozen twin snapshot not found.", status_code=404
            )
        return snapshot.evidence_records
    except ScenarioDomainError as error:
        _raise(error)


@router.post("/scenario-runs", response_model=SimulationRun, status_code=status.HTTP_202_ACCEPTED)
async def start_simulation(
    payload: StartSimulationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> SimulationRun:
    _operator_identity(request, scenario_api_key)
    try:
        run = await _service(request).start(payload, idempotency_key=idempotency_key)
        if run.result is None:
            background_tasks.add_task(_service(request).execute, run.run_id)
        return run
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenario-runs/{run_id}", response_model=SimulationRun)
async def simulation_status(run_id: UUID, request: Request) -> SimulationRun:
    try:
        return await _service(request).get_run(run_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenario-runs/{run_id}/progress", response_model=list[SimulationProgressEvent])
async def simulation_progress(run_id: UUID, request: Request) -> list[SimulationProgressEvent]:
    try:
        return await _service(request).progress(run_id)
    except ScenarioDomainError as error:
        _raise(error)


@router.post("/scenario-runs/{run_id}/cancel", response_model=SimulationRun)
async def cancel_simulation(
    run_id: UUID,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> SimulationRun:
    _operator_identity(request, scenario_api_key)
    try:
        return await _service(request).cancel(run_id, idempotency_key=idempotency_key)
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenario-runs/{run_id}/results", response_model=SimulationResult)
async def simulation_results(run_id: UUID, request: Request) -> SimulationResult:
    try:
        run = await _service(request).get_run(run_id)
        if run.result is None:
            raise ScenarioDomainError(
                "SIMULATION_RESULT_NOT_READY",
                "Simulation result is not available.",
                status_code=409,
            )
        return run.result
    except ScenarioDomainError as error:
        _raise(error)


@router.get("/scenario-runs/{run_id}/timeline", response_model=list[TimelinePoint])
async def simulation_timeline(run_id: UUID, request: Request) -> list[TimelinePoint]:
    result = await simulation_results(run_id, request)
    return list(result.timeline)
