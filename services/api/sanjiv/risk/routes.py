from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from sanjiv.risk.contracts import (
    CorridorRiskResult,
    PortWatchHormuzObservation,
    RiskAlertResponse,
    RiskBacktestResponse,
    RiskOverviewResponse,
    RiskTimelinePoint,
)
from sanjiv.risk.portwatch import PortWatchService, PortWatchUnavailable
from sanjiv.risk.service import RiskDomainError, RiskService
from sanjiv.scenarios.routes import DomainErrorResponse

router = APIRouter(prefix="/api/v1/risk", tags=["risk-intelligence"])


def _service(request: Request) -> RiskService:
    service: RiskService = request.app.state.risk_service
    return service


def _portwatch(request: Request) -> PortWatchService:
    service: PortWatchService = request.app.state.portwatch_service
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


@router.get("/portwatch/hormuz", response_model=PortWatchHormuzObservation)
async def portwatch_hormuz(request: Request) -> PortWatchHormuzObservation:
    try:
        return await _portwatch(request).hormuz_current()
    except PortWatchUnavailable as error:
        payload = DomainErrorResponse(
            code="PORTWATCH_UNAVAILABLE",
            message=str(error),
            correlation_id=uuid4(),
            details={"source_id": "IMF_PORTWATCH"},
        )
        raise HTTPException(status_code=503, detail=payload.model_dump(mode="json")) from error
