from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request

from sanjiv.reserve.contracts import ReservePlan, ReservePlanResponse
from sanjiv.reserve.service import ReserveDomainError, ReserveExecutionRequest, ReserveService
from sanjiv.scenarios.routes import DomainErrorResponse, _operator_identity
from sanjiv.scenarios.service import ScenarioDomainError

router = APIRouter(prefix="/api/v1", tags=["strategic-reserve"])


def _service(request: Request) -> ReserveService:
    service: ReserveService = request.app.state.reserve_service
    return service


def _raise(error: ReserveDomainError | ScenarioDomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code, message=error.message, correlation_id=uuid4(), details={}
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


@router.post("/scenario-runs/{run_id}/reserve-plans", response_model=ReservePlanResponse)
async def create_reserve_plans(
    run_id: UUID,
    payload: ReserveExecutionRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    scenario_api_key: str | None = Header(default=None, alias="X-Sanjiv-Scenario-Key"),
) -> ReservePlanResponse:
    actor = _operator_identity(request, scenario_api_key)
    try:
        return await _service(request).create(
            run_id, payload, idempotency_key=idempotency_key, actor_id=actor
        )
    except (ReserveDomainError, ScenarioDomainError) as error:
        _raise(error)


@router.get("/reserve-plans/{plan_id}", response_model=ReservePlan)
async def reserve_plan(plan_id: UUID, request: Request) -> ReservePlan:
    try:
        return await _service(request).get(plan_id)
    except ReserveDomainError as error:
        _raise(error)
