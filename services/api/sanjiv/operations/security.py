from __future__ import annotations

import hashlib
import hmac
from collections import deque
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from sanjiv.settings import Settings

MAX_RATE_LIMIT_IDENTITIES = 10_000
OVERFLOW_RATE_LIMIT_IDENTITY = "overflow"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


class ProductionSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings
        self._requests: dict[str, deque[float]] = {}

    def _configured_api_keys(self) -> list[str]:
        keys = list(self._settings.api_keys)
        if self._settings.sanjiv_scenario_api_key:
            keys.append(self._settings.sanjiv_scenario_api_key)
        keys.extend(self._settings.governance_api_keys)
        return keys

    def _valid_api_key(self, supplied: str | None) -> bool:
        if supplied is None:
            return False
        return any(
            hmac.compare_digest(supplied, configured) for configured in self._configured_api_keys()
        )

    @staticmethod
    def _rate_limit_key(identity: str) -> str:
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _rate_limited(self, client_key: str) -> bool:
        now = monotonic()
        if (
            client_key not in self._requests
            and len(self._requests) >= MAX_RATE_LIMIT_IDENTITIES - 1
        ):
            expired = [
                identity
                for identity, requests in self._requests.items()
                if not requests or now - requests[-1] >= 60.0
            ]
            for identity in expired:
                del self._requests[identity]
        if (
            client_key not in self._requests
            and len(self._requests) >= MAX_RATE_LIMIT_IDENTITIES - 1
        ):
            client_key = OVERFLOW_RATE_LIMIT_IDENTITY
        window = self._requests.setdefault(client_key, deque())
        while window and now - window[0] >= 60.0:
            window.popleft()
        if len(window) >= self._settings.sanjiv_rate_limit_per_minute:
            return True
        window.append(now)
        return False

    @staticmethod
    def _has_domain_auth(path: str) -> bool:
        if path.startswith("/api/v1/scenarios") or path.startswith("/api/v1/scenario-runs"):
            return True
        governance_suffixes = (
            "/reviews",
            "/approvals",
            "/rejections",
            "/supersessions",
            "/comments",
        )
        return path.startswith("/api/v1/plans/") and path.endswith(governance_suffixes)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        origin = request.headers.get("Origin")
        if origin and origin not in self._settings.allowed_origins:
            return _error(403, "ORIGIN_NOT_ALLOWED", "Request origin is not allowed.")

        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                request_bytes = int(content_length)
            except ValueError:
                return _error(400, "INVALID_CONTENT_LENGTH", "Content-Length must be an integer.")
            if request_bytes < 0:
                return _error(400, "INVALID_CONTENT_LENGTH", "Content-Length must not be negative.")
            if request_bytes > self._settings.sanjiv_max_request_bytes:
                return _error(
                    413,
                    "REQUEST_TOO_LARGE",
                    "Request exceeds the configured size limit.",
                )
        if request.method in {"POST", "PUT", "PATCH"} and content_length not in {None, "0"}:
            media_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if media_type != "application/json":
                return _error(415, "UNSUPPORTED_MEDIA_TYPE", "Only JSON requests are accepted.")

        supplied_key = (
            request.headers.get("X-Sanjiv-API-Key")
            or request.headers.get("X-Sanjiv-Scenario-Key")
            or request.headers.get("X-Sanjiv-Governance-Key")
        )
        requires_perimeter_auth = not self._has_domain_auth(path)
        if (
            self._settings.sanjiv_env.casefold() == "production"
            and path.startswith("/api/v1")
            and requires_perimeter_auth
        ):
            if not self._configured_api_keys():
                return _error(
                    503,
                    "AUTH_CONFIGURATION_REQUIRED",
                    "Production API authentication is not configured.",
                )
            if not self._valid_api_key(supplied_key):
                return _error(401, "AUTHENTICATION_REQUIRED", "A valid API key is required.")

        client_host = request.client.host if request.client else "unknown"
        identity = supplied_key or client_host
        client_key = self._rate_limit_key(identity)
        if self._rate_limited(client_key):
            rate_response = _error(429, "RATE_LIMITED", "Request rate limit exceeded.")
            rate_response.headers["Retry-After"] = "60"
            return rate_response

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response
