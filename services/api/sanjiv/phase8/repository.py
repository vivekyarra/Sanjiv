from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.phase8.contracts import (
    BriefingExport,
    LpgPlan,
    PlanComment,
    PlanMonitoringRecord,
    ReplayRun,
    SensitivityResult,
)


class Phase8Repository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def save_replay(self, run: ReplayRun) -> ReplayRun: ...
    async def replay(self, run_id: UUID) -> ReplayRun | None: ...
    async def replays(self) -> list[ReplayRun]: ...
    async def save_lpg_plans(self, run_id: UUID, plans: list[LpgPlan]) -> None: ...
    async def lpg_plans(self, run_id: UUID) -> list[LpgPlan]: ...
    async def lpg_plan(self, plan_id: UUID) -> LpgPlan | None: ...
    async def save_sensitivity(self, result: SensitivityResult) -> SensitivityResult: ...
    async def sensitivity(self, sensitivity_id: UUID) -> SensitivityResult | None: ...
    async def save_export(self, metadata: BriefingExport, content: bytes) -> BriefingExport: ...
    async def export(self, export_id: UUID) -> tuple[BriefingExport, bytes] | None: ...
    async def append_comment(self, comment: PlanComment) -> PlanComment: ...
    async def comments(self, plan_id: UUID) -> list[PlanComment]: ...
    async def save_monitoring(self, record: PlanMonitoringRecord) -> PlanMonitoringRecord: ...
    async def monitoring(self, plan_id: UUID) -> list[PlanMonitoringRecord]: ...


class InMemoryPhase8Repository:
    def __init__(self) -> None:
        self._replays: dict[UUID, ReplayRun] = {}
        self._lpg_plans: dict[UUID, list[LpgPlan]] = {}
        self._sensitivity: dict[UUID, SensitivityResult] = {}
        self._exports: dict[UUID, tuple[BriefingExport, bytes]] = {}
        self._comments: dict[UUID, list[PlanComment]] = {}
        self._monitoring: dict[UUID, list[PlanMonitoringRecord]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def save_replay(self, run: ReplayRun) -> ReplayRun:
        self._replays.setdefault(run.run_id, run)
        return self._replays[run.run_id]

    async def replay(self, run_id: UUID) -> ReplayRun | None:
        return self._replays.get(run_id)

    async def replays(self) -> list[ReplayRun]:
        return sorted(
            self._replays.values(), key=lambda item: (item.completed_at, str(item.run_id))
        )

    async def save_lpg_plans(self, run_id: UUID, plans: list[LpgPlan]) -> None:
        self._lpg_plans.setdefault(run_id, plans)

    async def lpg_plans(self, run_id: UUID) -> list[LpgPlan]:
        return list(self._lpg_plans.get(run_id, []))

    async def lpg_plan(self, plan_id: UUID) -> LpgPlan | None:
        return next(
            (
                plan
                for plans in self._lpg_plans.values()
                for plan in plans
                if plan.plan_id == plan_id
            ),
            None,
        )

    async def save_sensitivity(self, result: SensitivityResult) -> SensitivityResult:
        self._sensitivity.setdefault(result.sensitivity_id, result)
        return self._sensitivity[result.sensitivity_id]

    async def sensitivity(self, sensitivity_id: UUID) -> SensitivityResult | None:
        return self._sensitivity.get(sensitivity_id)

    async def save_export(self, metadata: BriefingExport, content: bytes) -> BriefingExport:
        self._exports.setdefault(metadata.export_id, (metadata, content))
        return self._exports[metadata.export_id][0]

    async def export(self, export_id: UUID) -> tuple[BriefingExport, bytes] | None:
        return self._exports.get(export_id)

    async def append_comment(self, comment: PlanComment) -> PlanComment:
        async with self._lock:
            comments = self._comments.setdefault(comment.plan_id, [])
            if not any(item.comment_id == comment.comment_id for item in comments):
                comments.append(comment)
            return next(item for item in comments if item.comment_id == comment.comment_id)

    async def comments(self, plan_id: UUID) -> list[PlanComment]:
        return list(self._comments.get(plan_id, []))

    async def save_monitoring(self, record: PlanMonitoringRecord) -> PlanMonitoringRecord:
        records = self._monitoring.setdefault(record.plan_id, [])
        if not any(item.monitoring_id == record.monitoring_id for item in records):
            records.append(record)
        return next(item for item in records if item.monitoring_id == record.monitoring_id)

    async def monitoring(self, plan_id: UUID) -> list[PlanMonitoringRecord]:
        return list(self._monitoring.get(plan_id, []))


class PostgresPhase8Repository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        await self._engine.dispose()

    async def save_replay(self, run: ReplayRun) -> ReplayRun:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO phase8_replay_runs(run_id,case_id,completed_at,payload) "
                    "VALUES(:run_id,:case_id,:completed_at,CAST(:payload AS jsonb)) "
                    "ON CONFLICT(run_id) DO NOTHING"
                ),
                {
                    "run_id": run.run_id,
                    "case_id": run.case_id,
                    "completed_at": run.completed_at,
                    "payload": run.model_dump_json(),
                },
            )
        return (await self.replay(run.run_id)) or run

    async def replay(self, run_id: UUID) -> ReplayRun | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM phase8_replay_runs WHERE run_id=:run_id"),
                    {"run_id": run_id},
                )
            ).scalar_one_or_none()
        return ReplayRun.model_validate(payload) if isinstance(payload, dict) else None

    async def replays(self) -> list[ReplayRun]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("SELECT payload FROM phase8_replay_runs ORDER BY completed_at,run_id")
                )
            ).scalars()
            return [ReplayRun.model_validate(item) for item in rows if isinstance(item, dict)]

    async def save_lpg_plans(self, run_id: UUID, plans: list[LpgPlan]) -> None:
        async with self._engine.begin() as connection:
            for plan in plans:
                await connection.execute(
                    text(
                        "INSERT INTO phase8_lpg_plans(plan_id,replay_run_id,payload) "
                        "VALUES(:plan_id,:run_id,CAST(:payload AS jsonb)) "
                        "ON CONFLICT(plan_id) DO NOTHING"
                    ),
                    {
                        "plan_id": plan.plan_id,
                        "run_id": run_id,
                        "payload": plan.model_dump_json(),
                    },
                )

    async def lpg_plans(self, run_id: UUID) -> list[LpgPlan]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT payload FROM phase8_lpg_plans "
                        "WHERE replay_run_id=:run_id ORDER BY plan_id"
                    ),
                    {"run_id": run_id},
                )
            ).scalars()
            return [LpgPlan.model_validate(item) for item in rows if isinstance(item, dict)]

    async def lpg_plan(self, plan_id: UUID) -> LpgPlan | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM phase8_lpg_plans WHERE plan_id=:plan_id"),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
        return LpgPlan.model_validate(payload) if isinstance(payload, dict) else None

    async def save_sensitivity(self, result: SensitivityResult) -> SensitivityResult:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO phase8_sensitivity_runs(sensitivity_id,plan_id,payload) "
                    "VALUES(:id,:plan_id,CAST(:payload AS jsonb)) "
                    "ON CONFLICT(sensitivity_id) DO NOTHING"
                ),
                {
                    "id": result.sensitivity_id,
                    "plan_id": result.plan_id,
                    "payload": result.model_dump_json(),
                },
            )
        return (await self.sensitivity(result.sensitivity_id)) or result

    async def sensitivity(self, sensitivity_id: UUID) -> SensitivityResult | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM phase8_sensitivity_runs WHERE sensitivity_id=:id"),
                    {"id": sensitivity_id},
                )
            ).scalar_one_or_none()
        return SensitivityResult.model_validate(payload) if isinstance(payload, dict) else None

    async def save_export(self, metadata: BriefingExport, content: bytes) -> BriefingExport:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO phase8_exports"
                    "(export_id,plan_id,kind,created_at,metadata,content) "
                    "VALUES(:id,:plan_id,:kind,:created_at,CAST(:metadata AS jsonb),:content) "
                    "ON CONFLICT(export_id) DO NOTHING"
                ),
                {
                    "id": metadata.export_id,
                    "plan_id": metadata.plan_id,
                    "kind": metadata.kind.value,
                    "created_at": metadata.created_at,
                    "metadata": metadata.model_dump_json(),
                    "content": content,
                },
            )
        stored = await self.export(metadata.export_id)
        return stored[0] if stored else metadata

    async def export(self, export_id: UUID) -> tuple[BriefingExport, bytes] | None:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT metadata,content FROM phase8_exports WHERE export_id=:id"),
                    {"id": export_id},
                )
            ).one_or_none()
        if row is None or not isinstance(row[0], dict):
            return None
        return BriefingExport.model_validate(row[0]), bytes(row[1])

    async def append_comment(self, comment: PlanComment) -> PlanComment:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO phase8_plan_comments(comment_id,plan_id,created_at,payload) "
                    "VALUES(:id,:plan_id,:created_at,CAST(:payload AS jsonb)) "
                    "ON CONFLICT(comment_id) DO NOTHING"
                ),
                {
                    "id": comment.comment_id,
                    "plan_id": comment.plan_id,
                    "created_at": comment.created_at,
                    "payload": comment.model_dump_json(),
                },
            )
            payload = (
                await connection.execute(
                    text("SELECT payload FROM phase8_plan_comments WHERE comment_id=:id"),
                    {"id": comment.comment_id},
                )
            ).scalar_one()
        return PlanComment.model_validate(payload)

    async def comments(self, plan_id: UUID) -> list[PlanComment]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT payload FROM phase8_plan_comments "
                        "WHERE plan_id=:plan_id ORDER BY created_at,comment_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalars()
            return [PlanComment.model_validate(item) for item in rows if isinstance(item, dict)]

    async def save_monitoring(self, record: PlanMonitoringRecord) -> PlanMonitoringRecord:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO phase8_plan_monitoring(monitoring_id,plan_id,observed_at,payload) "
                    "VALUES(:id,:plan_id,:observed_at,CAST(:payload AS jsonb)) "
                    "ON CONFLICT(monitoring_id) DO NOTHING"
                ),
                {
                    "id": record.monitoring_id,
                    "plan_id": record.plan_id,
                    "observed_at": record.observed_at,
                    "payload": record.model_dump_json(),
                },
            )
        return record

    async def monitoring(self, plan_id: UUID) -> list[PlanMonitoringRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT payload FROM phase8_plan_monitoring "
                        "WHERE plan_id=:plan_id ORDER BY observed_at,monitoring_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalars()
            return [
                PlanMonitoringRecord.model_validate(item) for item in rows if isinstance(item, dict)
            ]
