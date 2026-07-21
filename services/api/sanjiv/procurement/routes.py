from __future__ import annotations

from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request

from sanjiv.procurement.contracts import ProcurementPlan, ProcurementPlanResponse
from sanjiv.procurement.service import (
    ProcurementDomainError,
    ProcurementExecutionRequest,
    ProcurementService,
)
from sanjiv.scenarios.routes import DomainErrorResponse, _operator_identity
from sanjiv.scenarios.service import ScenarioDomainError

router = APIRouter(prefix="/api/v1", tags=["response-planner"])


def _service(request: Request) -> ProcurementService:
    service: ProcurementService = request.app.state.procurement_service
    return service


def _raise(error: ProcurementDomainError | ScenarioDomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code,
        message=error.message,
        correlation_id=uuid4(),
        details={},
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


@router.post(
    "/scenario-runs/{run_id}/procurement-plans",
    response_model=ProcurementPlanResponse,
)
async def create_procurement_plans(
    run_id: UUID,
    payload: ProcurementExecutionRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> ProcurementPlanResponse:
    actor = _operator_identity(request, scenario_api_key)
    try:
        return await _service(request).create(
            run_id,
            payload,
            idempotency_key=idempotency_key,
            actor_id=actor,
        )
    except (ProcurementDomainError, ScenarioDomainError) as error:
        _raise(error)


@router.get("/procurement-plans/{plan_id}", response_model=ProcurementPlan)
async def procurement_plan(plan_id: UUID, request: Request) -> ProcurementPlan:
    try:
        return await _service(request).get(plan_id)
    except ProcurementDomainError as error:
        _raise(error)
