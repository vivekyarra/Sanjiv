from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.risk.adapters.base import AdapterPolicy, RawRiskSignal, RiskAdapterResult
from sanjiv.risk.contracts import RiskSourceFailure, RiskSourceFailureCode


class RiskFetcher(Protocol):
    def __call__(
        self,
        endpoint: str | None,
        credential: str | None,
        timeout_seconds: float,
    ) -> Awaitable[list[RawRiskSignal]]: ...


class RiskSourceRateLimited(RuntimeError):
    """Fetcher signal for a provider rate-limit response without response details."""


class LiveAdapterConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    endpoint: str | None = Field(default=None, pattern=r"^https://")
    credential_required: bool
    documentation_url: str = Field(pattern=r"^https://")
    usage_note: str


class HttpRiskAdapter:
    """Optional live boundary; a network fetcher is injected by deployment code."""

    def __init__(
        self,
        configuration: LiveAdapterConfiguration,
        *,
        credential: str | None,
        fetcher: RiskFetcher | None,
        policy: AdapterPolicy | None = None,
    ) -> None:
        self.configuration = configuration
        self.credential = credential
        self.fetcher = fetcher
        self._policy = policy or AdapterPolicy(
            timeout_seconds=10,
            max_retries=2,
            backoff_seconds=0.25,
            expected_cadence_seconds=3600,
            stale_after_seconds=7200,
            rate_limit_per_minute=30,
        )

    @property
    def source_id(self) -> str:
        return self.configuration.source_id

    @property
    def policy(self) -> AdapterPolicy:
        return self._policy

    async def fetch(self, case_id: str) -> RiskAdapterResult:
        del case_id
        if self.configuration.credential_required and not self.credential:
            return self._failure(RiskSourceFailureCode.CREDENTIAL_MISSING, False)
        if self.fetcher is None:
            return self._failure(RiskSourceFailureCode.UNAVAILABLE, False)
        for attempt in range(self.policy.max_retries + 1):
            try:
                signals = await asyncio.wait_for(
                    self.fetcher(
                        self.configuration.endpoint,
                        self.credential,
                        self.policy.timeout_seconds,
                    ),
                    timeout=self.policy.timeout_seconds,
                )
                return RiskAdapterResult(source_id=self.source_id, signals=signals, failures=[])
            except TimeoutError:
                if attempt < self.policy.max_retries:
                    await asyncio.sleep(self.policy.backoff_seconds * (2**attempt))
            except RiskSourceRateLimited:
                return self._failure(RiskSourceFailureCode.RATE_LIMITED, True)
            except Exception:
                return self._failure(RiskSourceFailureCode.UNAVAILABLE, True)
        return self._failure(RiskSourceFailureCode.UNAVAILABLE, True)

    def _failure(self, code: RiskSourceFailureCode, retryable: bool) -> RiskAdapterResult:
        return RiskAdapterResult(
            source_id=self.source_id,
            signals=[],
            failures=[
                RiskSourceFailure(
                    source_id=self.source_id,
                    code=code,
                    message=(
                        "Risk source is unavailable; credentials and request details are redacted."
                    ),
                    retryable=retryable,
                    occurred_at=datetime.now(UTC),
                )
            ],
        )


def live_adapter_configurations() -> tuple[LiveAdapterConfiguration, ...]:
    return (
        LiveAdapterConfiguration(
            source_id="GDELT",
            endpoint="https://api.gdeltproject.org/api/v2/doc/doc",
            credential_required=False,
            documentation_url="https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/",
            usage_note="Media signal only; citation required; not proof of a physical event.",
        ),
        LiveAdapterConfiguration(
            source_id="IMF_PORTWATCH",
            endpoint="https://portwatch.imf.org/api/search/",
            credential_required=False,
            documentation_url="https://portwatch.imf.org/pages/data-and-methodology/",
            usage_note="Port and chokepoint baseline; IMF attribution and integrity terms apply.",
        ),
        LiveAdapterConfiguration(
            source_id="EIA",
            endpoint="https://api.eia.gov/v2/",
            credential_required=True,
            documentation_url="https://www.eia.gov/opendata/documentation.php",
            usage_note="API v2; registered key, throttling and attribution required.",
        ),
        LiveAdapterConfiguration(
            source_id="FRED",
            endpoint="https://api.stlouisfed.org/fred/",
            credential_required=True,
            documentation_url="https://fred.stlouisfed.org/docs/api/fred/overview.html",
            usage_note="API key and series-specific rights required.",
        ),
        LiveAdapterConfiguration(
            source_id="NASA_FIRMS",
            endpoint="https://firms.modaps.eosdis.nasa.gov/api/area/csv/",
            credential_required=True,
            documentation_url="https://firms.modaps.eosdis.nasa.gov/api/area/",
            usage_note="MAP_KEY and transaction bounds apply; hotspot is not proof of damage.",
        ),
        LiveAdapterConfiguration(
            source_id="SANCTIONS_BOUNDARY",
            endpoint=None,
            credential_required=False,
            documentation_url="https://github.com/vivekyarra/Sanjiv",
            usage_note=(
                "Deployment injects the existing sanctions-list boundary; no "
                "undocumented endpoint is called."
            ),
        ),
        LiveAdapterConfiguration(
            source_id="AIS_PHASE_1",
            endpoint=None,
            credential_required=False,
            documentation_url="https://github.com/vivekyarra/Sanjiv",
            usage_note="Deployment injects Phase 1 AIS-derived features under existing licensing.",
        ),
    )
