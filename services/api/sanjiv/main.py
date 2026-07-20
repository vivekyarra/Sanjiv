from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from sanjiv.contracts import (
    Assumption,
    AuditEvent,
    EvidenceRecord,
    MetricEnvelope,
    SourceHealthRecord,
)
from sanjiv.settings import get_settings


class HealthResponse(BaseModel):
    status: Literal["alive", "ready"]
    service: Literal["sanjiv-api"] = "sanjiv-api"
    version: Literal["0.1.0"] = "0.1.0"
    checked_at: datetime


class FoundationContractSample(BaseModel):
    metric: MetricEnvelope[float]
    evidence: EvidenceRecord
    source_health: SourceHealthRecord
    assumption: Assumption
    audit_event: AuditEvent


app = FastAPI(
    title="Sanjiv API",
    summary="India's Energy Resilience Command Center",
    description="Keep India's energy moving.",
    version="0.1.0",
)


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def liveness() -> HealthResponse:
    return HealthResponse(status="alive", checked_at=datetime.now(UTC))


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def readiness() -> HealthResponse:
    get_settings()
    return HealthResponse(status="ready", checked_at=datetime.now(UTC))


@app.get(
    "/api/v1/contracts/sample",
    response_model=FoundationContractSample,
    tags=["foundation"],
    include_in_schema=True,
)
async def contract_sample() -> FoundationContractSample:
    """Expose the typed Phase 0 sample; no operational feature or live claim."""
    from sanjiv.sample import build_foundation_sample

    return build_foundation_sample()
