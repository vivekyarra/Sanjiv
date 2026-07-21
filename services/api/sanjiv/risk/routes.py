from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from sanjiv.risk.contracts import (
    CorridorRiskResult,
    RiskAlertResponse,
    RiskBacktestResponse,
    RiskOverviewResponse,
    RiskTimelinePoint,
)
from sanjiv.risk.service import RiskDomainError, RiskService
from sanjiv.scenarios.routes import DomainErrorResponse

router = APIRouter(prefix="/api/v1/risk", tags=["risk-intelligence"])


def _service(request: Request) -> RiskService:
    service: RiskService = request.app.state.risk_service
    return service


def _raise(error: RiskDomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code,
        message=error.message,
        correlation_id=uuid4(),
        details={},
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


@router.get("/corridors", response_model=RiskOverviewResponse)
async def corridor_risks(request: Request) -> RiskOverviewResponse:
    return await _service(request).overview()


@router.get("/corridors/{risk_id}", response_model=CorridorRiskResult)
async def corridor_risk(risk_id: UUID, request: Request) -> CorridorRiskResult:
    try:
        return await _service(request).get(risk_id)
    except RiskDomainError as error:
        _raise(error)


@router.get("/corridors/{corridor_id}/timeline", response_model=list[RiskTimelinePoint])
async def corridor_timeline(corridor_id: UUID, request: Request) -> list[RiskTimelinePoint]:
    return await _service(request).timeline(corridor_id)


@router.get("/alerts", response_model=RiskAlertResponse)
async def risk_alerts(request: Request) -> RiskAlertResponse:
    return RiskAlertResponse(alerts=await _service(request).alerts())


@router.get("/backtests", response_model=RiskBacktestResponse)
async def risk_backtests(request: Request) -> RiskBacktestResponse:
    return RiskBacktestResponse(results=await _service(request).backtests())
