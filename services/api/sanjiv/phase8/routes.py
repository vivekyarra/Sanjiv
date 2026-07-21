from __future__ import annotations

from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response

from sanjiv.audit.routes import resolve_governance_identity
from sanjiv.audit.service import AuditDomainError
from sanjiv.phase8.contracts import (
    BriefingExport,
    CreateCommentRequest,
    CreateExportRequest,
    LpgNetwork,
    LpgPlan,
    MonitorPlanRequest,
    PlanComment,
    PlanMonitoringRecord,
    ReplayCatalogue,
    ReplayRun,
    SensitivityRequest,
    SensitivityResult,
)
from sanjiv.phase8.service import Phase8DomainError, Phase8Service
from sanjiv.scenarios.routes import DomainErrorResponse

router = APIRouter(prefix="/api/v1", tags=["phase-8"])


def _service(request: Request) -> Phase8Service:
    service: Phase8Service = request.app.state.phase8_service
    return service


def _raise(error: Phase8DomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code, message=error.message, correlation_id=uuid4(), details={}
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


@router.get("/replay-catalogue", response_model=ReplayCatalogue)
async def replay_catalogue(request: Request) -> ReplayCatalogue:
    return _service(request).catalogue


@router.post("/replay-cases/{case_id}/runs", response_model=ReplayRun)
async def execute_replay(
    case_id: str,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> ReplayRun:
    del idempotency_key
    try:
        return await _service(request).execute_replay(case_id)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/replay-runs", response_model=list[ReplayRun])
async def replay_runs(request: Request) -> list[ReplayRun]:
    return await _service(request).replays()


@router.get("/replay-runs/{run_id}", response_model=ReplayRun)
async def replay_run(run_id: UUID, request: Request) -> ReplayRun:
    try:
        return await _service(request).replay(run_id)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/lpg/network", response_model=LpgNetwork)
async def lpg_network(request: Request) -> LpgNetwork:
    return _service(request).lpg_network


@router.get("/replay-runs/{run_id}/lpg-plans", response_model=list[LpgPlan])
async def lpg_plans(run_id: UUID, request: Request) -> list[LpgPlan]:
    try:
        return await _service(request).lpg_plans(run_id)
    except Phase8DomainError as error:
        _raise(error)


@router.post("/plans/{plan_id}/sensitivity-runs", response_model=SensitivityResult)
async def sensitivity(
    plan_id: UUID,
    payload: SensitivityRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> SensitivityResult:
    del idempotency_key
    try:
        return await _service(request).sensitivity(plan_id, payload)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/sensitivity-runs/{sensitivity_id}", response_model=SensitivityResult)
async def sensitivity_result(sensitivity_id: UUID, request: Request) -> SensitivityResult:
    try:
        return await _service(request).sensitivity_result(sensitivity_id)
    except Phase8DomainError as error:
        _raise(error)


@router.post("/plans/{plan_id}/exports", response_model=BriefingExport)
async def create_export(
    plan_id: UUID,
    payload: CreateExportRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> BriefingExport:
    del idempotency_key
    try:
        return await _service(request).create_export(plan_id, payload)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/exports/{export_id}", response_model=BriefingExport)
async def export_metadata(export_id: UUID, request: Request) -> BriefingExport:
    try:
        metadata, _ = await _service(request).export(export_id)
        return metadata
    except Phase8DomainError as error:
        _raise(error)


@router.post("/lpg-plans/{plan_id}/exports", response_model=BriefingExport)
async def create_lpg_export(
    plan_id: UUID,
    payload: CreateExportRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> BriefingExport:
    del idempotency_key
    try:
        return await _service(request).create_lpg_export(plan_id, payload)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/exports/{export_id}/download")
async def download_export(export_id: UUID, request: Request) -> Response:
    try:
        metadata, content = await _service(request).export(export_id)
        return Response(
            content=content,
            media_type=metadata.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{metadata.filename}"',
                "X-Sanjiv-Artifact-SHA256": metadata.sha256,
            },
        )
    except Phase8DomainError as error:
        _raise(error)


@router.post("/plans/{plan_id}/comments", response_model=PlanComment)
async def create_comment(
    plan_id: UUID,
    payload: CreateCommentRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    demo_identity: str | None = Header(default=None, alias="X-Sanjiv-Demo-Identity"),
    governance_key: str | None = Header(default=None, alias="X-Sanjiv-Governance-Key"),
) -> PlanComment:
    try:
        actor_id, actor_role = resolve_governance_identity(request, demo_identity, governance_key)
        return await _service(request).comment(
            plan_id,
            payload.comment,
            actor_id=actor_id,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
        )
    except (Phase8DomainError, AuditDomainError) as error:
        _raise(Phase8DomainError(error.code, error.message, error.status_code))


@router.get("/plans/{plan_id}/comments", response_model=list[PlanComment])
async def comments(plan_id: UUID, request: Request) -> list[PlanComment]:
    try:
        return await _service(request).comments(plan_id)
    except Phase8DomainError as error:
        _raise(error)


@router.post("/plans/{plan_id}/monitoring", response_model=PlanMonitoringRecord)
async def create_monitoring(
    plan_id: UUID,
    payload: MonitorPlanRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
) -> PlanMonitoringRecord:
    del idempotency_key
    try:
        return await _service(request).monitor(plan_id, payload)
    except Phase8DomainError as error:
        _raise(error)


@router.get("/plans/{plan_id}/monitoring", response_model=list[PlanMonitoringRecord])
async def monitoring(plan_id: UUID, request: Request) -> list[PlanMonitoringRecord]:
    try:
        return await _service(request).monitoring(plan_id)
    except Phase8DomainError as error:
        _raise(error)
