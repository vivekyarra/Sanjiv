from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sanjiv.risk.adapters.fixture import FixtureRiskAdapter, RiskReplayCase
from sanjiv.risk.alerts import evaluate_alert
from sanjiv.risk.backtest import run_fixture_backtest
from sanjiv.risk.contracts import (
    AlertResult,
    BacktestResult,
    CorridorRiskResult,
    RiskLifecycle,
    RiskLifecycleTransition,
    RiskOverviewResponse,
    RiskTimelinePoint,
    canonical_hash,
)
from sanjiv.risk.engine import build_baselines, calculate_corridor_risk
from sanjiv.risk.repository import RiskRepository

CURRENT_CASES = (
    "true-disruption-escalation",
    "port-chokepoint-anomaly",
    "source-outage",
    "sanctions-change",
    "ais-without-corroboration",
)


class RiskDomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 404) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class RiskService:
    def __init__(self, *, repository: RiskRepository, adapter: FixtureRiskAdapter) -> None:
        self.repository = repository
        self.adapter = adapter

    async def initialize(self) -> None:
        await self.repository.initialize()
        if not await self.repository.current():
            await self._seed_fixture()

    async def close(self) -> None:
        await self.repository.close()

    async def overview(self) -> RiskOverviewResponse:
        return RiskOverviewResponse(
            risks=await self.repository.current(),
            generated_at=datetime.now(UTC),
            mode="FIXTURE",
        )

    async def get(self, risk_id: UUID) -> CorridorRiskResult:
        risk = await self.repository.risk(risk_id)
        if risk is None:
            raise RiskDomainError("RISK_NOT_FOUND", "Corridor risk result not found.")
        return risk

    async def alerts(self) -> list[AlertResult]:
        return await self.repository.alerts()

    async def timeline(self, corridor_id: UUID) -> list[RiskTimelinePoint]:
        return await self.repository.timeline(corridor_id)

    async def backtests(self) -> list[BacktestResult]:
        return await self.repository.backtests()

    async def _seed_fixture(self) -> None:
        at = datetime(2026, 7, 21, 12, tzinfo=UTC)
        baselines = build_baselines(self.adapter.baseline(), at=at)
        raw_cases = {item.case_id: item for item in self.adapter.cases()}
        risks = []
        alerts = []
        for case_id in CURRENT_CASES:
            raw = raw_cases[case_id]
            adapted = await self.adapter.fetch(case_id)
            corridor_id = adapted.signals[0].corridor_id
            risk = calculate_corridor_risk(
                corridor_id,
                raw.corridor,
                adapted.signals,
                baselines,
                adapted.failures,
                calculated_at=at,
            )
            risks.append(risk)
            alerts.append(evaluate_alert(risk, created_at=at))
        backtest = await run_fixture_backtest(self.adapter)
        timeline = self._timeline(backtest, raw_cases, risks, at)
        transitions = [
            RiskLifecycleTransition(
                risk_id=risk.risk_id,
                current=RiskLifecycle.CREATED,
                target=risk.lifecycle,
                occurred_at=at,
                reason="Fixture calculation completed with explicit source state.",
            )
            for risk in risks
        ]
        await self.repository.save(
            risks,
            list(baselines.values()),
            alerts,
            timeline,
            transitions,
            backtest,
        )

    def _timeline(
        self,
        backtest: BacktestResult,
        raw_cases: dict[str, RiskReplayCase],
        current: list[CorridorRiskResult],
        at: datetime,
    ) -> list[RiskTimelinePoint]:
        current_by_id = {item.corridor_id: item for item in current}
        output = []
        for index, case in enumerate(backtest.cases):
            raw = raw_cases[case.case_id]
            adapted_corridor = (
                next(item.corridor_id for item in current if item.corridor_name == raw.corridor)
                if any(item.corridor_name == raw.corridor for item in current)
                else None
            )
            if adapted_corridor is None:
                continue
            risk = current_by_id[adapted_corridor]
            output.append(
                RiskTimelinePoint(
                    corridor_id=adapted_corridor,
                    effective_at=at - timedelta(hours=len(backtest.cases) - index),
                    severity=case.severity,
                    confidence=case.confidence,
                    completeness=case.completeness,
                    risk_fingerprint=canonical_hash(
                        {"case": case.case_id, "model": backtest.model_version}
                    ),
                )
            )
            output.append(
                RiskTimelinePoint(
                    corridor_id=risk.corridor_id,
                    effective_at=at,
                    severity=risk.severity,
                    confidence=risk.confidence,
                    completeness=risk.completeness,
                    risk_fingerprint=risk.fingerprint,
                )
            )
        return output
