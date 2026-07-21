from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str
    status: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "NOT_CONFIGURED"]
    checked_at: datetime
    detail: str
    stale: bool = False


class RuntimeMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str
    count: int = Field(ge=0)
    failures: int = Field(ge=0)
    minimum_ms: float = Field(ge=0)
    median_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    maximum_ms: float = Field(ge=0)


class OperationsStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["READY", "DEGRADED"]
    checked_at: datetime
    commit_sha: str
    environment: str
    components: list[ComponentHealth]
    runtimes: list[RuntimeMetric]
    correlation_ids_enabled: Literal[True] = True
    causation_ids_enabled: Literal[True] = True
    opentelemetry_compatible: Literal[True] = True
