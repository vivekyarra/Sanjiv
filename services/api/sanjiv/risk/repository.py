from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.risk.contracts import (
    AlertResult,
    AnomalyBaseline,
    BacktestResult,
    CorridorRiskResult,
    RiskLifecycleTransition,
    RiskTimelinePoint,
)


class RiskRepository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def save(
        self,
        risks: list[CorridorRiskResult],
        baselines: list[AnomalyBaseline],
        alerts: list[AlertResult],
        timeline: list[RiskTimelinePoint],
        transitions: list[RiskLifecycleTransition],
        backtest: BacktestResult,
    ) -> None: ...
    async def current(self) -> list[CorridorRiskResult]: ...
    async def risk(self, risk_id: UUID) -> CorridorRiskResult | None: ...
    async def alerts(self) -> list[AlertResult]: ...
    async def timeline(self, corridor_id: UUID) -> list[RiskTimelinePoint]: ...
    async def backtests(self) -> list[BacktestResult]: ...


class InMemoryRiskRepository:
    def __init__(self) -> None:
        self._risks: dict[UUID, CorridorRiskResult] = {}
        self._alerts: dict[UUID, AlertResult] = {}
        self._baselines: dict[str, AnomalyBaseline] = {}
        self._timeline: list[RiskTimelinePoint] = []
        self._backtests: dict[UUID, BacktestResult] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def save(
        self,
        risks: list[CorridorRiskResult],
        baselines: list[AnomalyBaseline],
        alerts: list[AlertResult],
        timeline: list[RiskTimelinePoint],
        transitions: list[RiskLifecycleTransition],
        backtest: BacktestResult,
    ) -> None:
        for risk_item in risks:
            self._risks.setdefault(risk_item.risk_id, risk_item)
        for baseline_item in baselines:
            self._baselines.setdefault(baseline_item.fingerprint, baseline_item)
        for alert_item in alerts:
            self._alerts.setdefault(alert_item.alert_id, alert_item)
        existing = {
            (item.corridor_id, item.effective_at, item.risk_fingerprint) for item in self._timeline
        }
        for timeline_item in timeline:
            key = (
                timeline_item.corridor_id,
                timeline_item.effective_at,
                timeline_item.risk_fingerprint,
            )
            if key not in existing:
                self._timeline.append(timeline_item)
                existing.add(key)
        self._backtests.setdefault(backtest.backtest_id, backtest)
        del transitions

    async def current(self) -> list[CorridorRiskResult]:
        return sorted(
            self._risks.values(), key=lambda item: (-item.severity.value, str(item.corridor_id))
        )

    async def risk(self, risk_id: UUID) -> CorridorRiskResult | None:
        return self._risks.get(risk_id)

    async def alerts(self) -> list[AlertResult]:
        return sorted(
            self._alerts.values(), key=lambda item: (-item.severity.value, str(item.alert_id))
        )

    async def timeline(self, corridor_id: UUID) -> list[RiskTimelinePoint]:
        return sorted(
            (item for item in self._timeline if item.corridor_id == corridor_id),
            key=lambda item: item.effective_at,
        )

    async def backtests(self) -> list[BacktestResult]:
        return list(self._backtests.values())


class PostgresRiskRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        await self._engine.dispose()

    async def save(
        self,
        risks: list[CorridorRiskResult],
        baselines: list[AnomalyBaseline],
        alerts: list[AlertResult],
        timeline: list[RiskTimelinePoint],
        transitions: list[RiskLifecycleTransition],
        backtest: BacktestResult,
    ) -> None:
        async with self._engine.begin() as connection:
            for baseline in baselines:
                await connection.execute(
                    text("""INSERT INTO risk_anomaly_baselines(
                      fingerprint,feature_type,window_starts_at,window_ends_at,version,payload
                    ) VALUES(
                      :fingerprint,:feature_type,:window_starts_at,:window_ends_at,:version,
                      CAST(:payload AS jsonb)
                    ) ON CONFLICT(fingerprint) DO NOTHING"""),
                    {
                        "fingerprint": baseline.fingerprint,
                        "feature_type": baseline.feature_type.value,
                        "window_starts_at": baseline.window_starts_at,
                        "window_ends_at": baseline.window_ends_at,
                        "version": baseline.version,
                        "payload": baseline.model_dump_json(),
                    },
                )
            for risk in risks:
                await connection.execute(
                    text("""INSERT INTO corridor_risk_results(
                      risk_id,corridor_id,severity,confidence,completeness,lifecycle,
                      model_version,fingerprint,effective_at,calculated_at,payload
                    ) VALUES(
                      :risk_id,:corridor_id,:severity,:confidence,:completeness,:lifecycle,
                      :model_version,:fingerprint,:effective_at,:calculated_at,
                      CAST(:payload AS jsonb)
                    ) ON CONFLICT(risk_id) DO NOTHING"""),
                    {
                        "risk_id": risk.risk_id,
                        "corridor_id": risk.corridor_id,
                        "severity": risk.severity.value,
                        "confidence": risk.confidence.value,
                        "completeness": risk.completeness.value,
                        "lifecycle": risk.lifecycle.value,
                        "model_version": risk.model_version,
                        "fingerprint": risk.fingerprint,
                        "effective_at": risk.effective_at,
                        "calculated_at": risk.calculated_at,
                        "payload": risk.model_dump_json(),
                    },
                )
                for feature in risk.features:
                    await connection.execute(
                        text(
                            """INSERT INTO normalized_risk_features(
                              feature_id,risk_id,corridor_id,feature_type,payload
                            ) VALUES(
                              :feature_id,:risk_id,:corridor_id,:feature_type,
                              CAST(:payload AS jsonb)
                            ) ON CONFLICT(feature_id) DO NOTHING"""
                        ),
                        {
                            "feature_id": feature.feature_id,
                            "risk_id": risk.risk_id,
                            "corridor_id": risk.corridor_id,
                            "feature_type": feature.feature_type.value,
                            "payload": feature.model_dump_json(),
                        },
                    )
                for contribution in risk.contributions:
                    await connection.execute(
                        text(
                            """INSERT INTO risk_feature_contributions(
                              risk_id,feature_type,payload
                            ) VALUES(
                              :risk_id,:feature_type,CAST(:payload AS jsonb)
                            ) ON CONFLICT(risk_id,feature_type) DO NOTHING"""
                        ),
                        {
                            "risk_id": risk.risk_id,
                            "feature_type": contribution.feature_type.value,
                            "payload": contribution.model_dump_json(),
                        },
                    )
                for failure in risk.source_failures:
                    await connection.execute(
                        text(
                            """INSERT INTO risk_source_failures(
                              risk_id,source_id,code,occurred_at,payload
                            ) VALUES(
                              :risk_id,:source_id,:code,:occurred_at,
                              CAST(:payload AS jsonb)
                            ) ON CONFLICT(risk_id,source_id,code) DO NOTHING"""
                        ),
                        {
                            "risk_id": risk.risk_id,
                            "source_id": failure.source_id,
                            "code": failure.code.value,
                            "occurred_at": failure.occurred_at,
                            "payload": failure.model_dump_json(),
                        },
                    )
            for alert in alerts:
                await connection.execute(
                    text(
                        """INSERT INTO risk_alerts(
                          alert_id,risk_id,corridor_id,severity_band,status,
                          effective_at,payload
                        ) VALUES(
                          :alert_id,:risk_id,:corridor_id,:severity_band,:status,
                          :effective_at,CAST(:payload AS jsonb)
                        ) ON CONFLICT(alert_id) DO NOTHING"""
                    ),
                    {
                        "alert_id": alert.alert_id,
                        "risk_id": alert.risk_id,
                        "corridor_id": alert.corridor_id,
                        "severity_band": alert.severity_band.value,
                        "status": alert.status.value,
                        "effective_at": alert.effective_at,
                        "payload": alert.model_dump_json(),
                    },
                )
            for point in timeline:
                await connection.execute(
                    text(
                        """INSERT INTO risk_timeline(
                          corridor_id,effective_at,risk_fingerprint,payload
                        ) VALUES(
                          :corridor_id,:effective_at,:risk_fingerprint,
                          CAST(:payload AS jsonb)
                        ) ON CONFLICT(
                          corridor_id,effective_at,risk_fingerprint
                        ) DO NOTHING"""
                    ),
                    {
                        "corridor_id": point.corridor_id,
                        "effective_at": point.effective_at,
                        "risk_fingerprint": point.risk_fingerprint,
                        "payload": point.model_dump_json(),
                    },
                )
            for transition in transitions:
                await connection.execute(
                    text("""INSERT INTO risk_lifecycle_transitions(
                      risk_id,current_state,target_state,occurred_at,payload
                    ) VALUES(
                      :risk_id,:current_state,:target_state,:occurred_at,CAST(:payload AS jsonb)
                    ) ON CONFLICT(risk_id,current_state,target_state) DO NOTHING"""),
                    {
                        "risk_id": transition.risk_id,
                        "current_state": transition.current.value,
                        "target_state": transition.target.value,
                        "occurred_at": transition.occurred_at,
                        "payload": transition.model_dump_json(),
                    },
                )
            await connection.execute(
                text(
                    """INSERT INTO risk_backtests(
                      backtest_id,library_id,model_version,fingerprint,payload,created_at
                    ) VALUES(
                      :backtest_id,:library_id,:model_version,:fingerprint,
                      CAST(:payload AS jsonb),now()
                    ) ON CONFLICT(backtest_id) DO NOTHING"""
                ),
                {
                    "backtest_id": backtest.backtest_id,
                    "library_id": backtest.library_id,
                    "model_version": backtest.model_version,
                    "fingerprint": backtest.fingerprint,
                    "payload": backtest.model_dump_json(),
                },
            )

    async def current(self) -> list[CorridorRiskResult]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT DISTINCT ON (corridor_id) payload
                            FROM corridor_risk_results
                            ORDER BY corridor_id,calculated_at DESC"""
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(
            (CorridorRiskResult.model_validate(item) for item in rows),
            key=lambda item: (-item.severity.value, str(item.corridor_id)),
        )

    async def risk(self, risk_id: UUID) -> CorridorRiskResult | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM corridor_risk_results WHERE risk_id=:risk_id"),
                    {"risk_id": risk_id},
                )
            ).scalar_one_or_none()
        return CorridorRiskResult.model_validate(payload) if isinstance(payload, dict) else None

    async def alerts(self) -> list[AlertResult]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text("SELECT payload FROM risk_alerts ORDER BY effective_at DESC")
                    )
                )
                .scalars()
                .all()
            )
        return [AlertResult.model_validate(item) for item in rows]

    async def timeline(self, corridor_id: UUID) -> list[RiskTimelinePoint]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT payload FROM risk_timeline
                            WHERE corridor_id=:corridor_id
                            ORDER BY effective_at"""
                        ),
                        {"corridor_id": corridor_id},
                    )
                )
                .scalars()
                .all()
            )
        return [RiskTimelinePoint.model_validate(item) for item in rows]

    async def backtests(self) -> list[BacktestResult]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text("SELECT payload FROM risk_backtests ORDER BY created_at DESC")
                    )
                )
                .scalars()
                .all()
            )
        return [BacktestResult.model_validate(item) for item in rows]
