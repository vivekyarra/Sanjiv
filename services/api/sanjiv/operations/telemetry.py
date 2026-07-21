from __future__ import annotations

import json
import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from time import perf_counter
from typing import Final
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from sanjiv.operations.contracts import RuntimeMetric

_MAX_SAMPLES: Final = 2000
_ID_MAX_LENGTH: Final = 128


def _safe_id(value: str | None) -> str:
    if (
        value
        and 1 <= len(value) <= _ID_MAX_LENGTH
        and all(character.isalnum() or character in "-_.:" for character in value)
    ):
        return value
    return str(uuid4())


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = fraction * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


@dataclass
class _OperationSamples:
    durations: deque[float]
    failures: int = 0


class TelemetryRegistry:
    def __init__(self) -> None:
        self._operations: dict[str, _OperationSamples] = defaultdict(
            lambda: _OperationSamples(deque(maxlen=_MAX_SAMPLES))
        )

    def record(self, operation: str, duration_ms: float, *, failed: bool) -> None:
        sample = self._operations[operation]
        sample.durations.append(max(0.0, duration_ms))
        sample.failures += int(failed)

    def snapshot(self) -> list[RuntimeMetric]:
        result: list[RuntimeMetric] = []
        for operation, sample in sorted(self._operations.items()):
            values = sorted(sample.durations)
            result.append(
                RuntimeMetric(
                    operation=operation,
                    count=len(values),
                    failures=sample.failures,
                    minimum_ms=round(values[0], 3) if values else 0.0,
                    median_ms=round(_percentile(values, 0.5), 3),
                    p95_ms=round(_percentile(values, 0.95), 3),
                    maximum_ms=round(values[-1], 3) if values else 0.0,
                )
            )
        return result


class TelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, registry: TelemetryRegistry, log_level: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._registry = registry
        self._logger = logging.getLogger("sanjiv.request")
        self._logger.setLevel(log_level.upper())

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = _safe_id(request.headers.get("X-Correlation-ID"))
        causation_id = _safe_id(request.headers.get("X-Causation-ID"))
        trace_id = uuid4().hex
        span_id = uuid4().hex[:16]
        request.state.correlation_id = correlation_id
        request.state.causation_id = causation_id
        started = perf_counter()
        failed = False
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            failed = status_code >= 500
        except Exception:
            failed = True
            raise
        finally:
            duration_ms = (perf_counter() - started) * 1000.0
            operation = f"{request.method} {request.url.path}"
            self._registry.record(operation, duration_ms, failed=failed)
            self._logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration_ms, 3),
                        "correlation_id": correlation_id,
                        "causation_id": causation_id,
                        "trace_id": trace_id,
                    },
                    separators=(",", ":"),
                )
            )
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Causation-ID"] = causation_id
        response.headers["traceparent"] = f"00-{trace_id}-{span_id}-01"
        return response
