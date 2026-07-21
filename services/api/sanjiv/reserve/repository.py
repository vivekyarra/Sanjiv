from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.reserve.contracts import ReservePlan, ReservePlanResponse


class ReserveRepository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def response_by_fingerprint(self, fingerprint: str) -> ReservePlanResponse | None: ...
    async def save_response(self, fingerprint: str, response: ReservePlanResponse) -> None: ...
    async def plan(self, plan_id: UUID) -> ReservePlan | None: ...


class InMemoryReserveRepository:
    def __init__(self) -> None:
        self._responses: dict[str, ReservePlanResponse] = {}
        self._plans: dict[UUID, ReservePlan] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def response_by_fingerprint(self, fingerprint: str) -> ReservePlanResponse | None:
        return self._responses.get(fingerprint)

    async def save_response(self, fingerprint: str, response: ReservePlanResponse) -> None:
        self._responses.setdefault(fingerprint, response)
        for plan in response.plans:
            self._plans.setdefault(plan.plan_id, plan)

    async def plan(self, plan_id: UUID) -> ReservePlan | None:
        return self._plans.get(plan_id)


class PostgresReserveRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        await self._engine.dispose()

    async def response_by_fingerprint(self, fingerprint: str) -> ReservePlanResponse | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text(
                        "SELECT response_payload FROM reserve_plan_requests "
                        "WHERE request_fingerprint=:fingerprint AND lifecycle='COMPLETED'"
                    ),
                    {"fingerprint": fingerprint},
                )
            ).scalar_one_or_none()
        return ReservePlanResponse.model_validate(payload) if isinstance(payload, dict) else None

    async def save_response(self, fingerprint: str, response: ReservePlanResponse) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("""INSERT INTO reserve_plan_requests(
                  request_id, run_id, procurement_plan_id, request_fingerprint,
                  lifecycle, response_payload, created_at
                ) VALUES(
                  :request_id, :run_id, :procurement_plan_id, :fingerprint,
                  'COMPLETED', CAST(:payload AS jsonb), now()
                ) ON CONFLICT(request_fingerprint) DO NOTHING"""),
                {
                    "request_id": response.request_id,
                    "run_id": response.run_id,
                    "procurement_plan_id": response.procurement_plan_id,
                    "fingerprint": fingerprint,
                    "payload": response.model_dump_json(),
                },
            )
            for plan in response.plans:
                await connection.execute(
                    text("""INSERT INTO reserve_plans(
                      plan_id, request_id, run_id, procurement_plan_id, profile,
                      lifecycle, input_fingerprint, plan_fingerprint, solver_status,
                      checker_passed, runtime_seconds, payload, created_at
                    ) VALUES(
                      :plan_id, :request_id, :run_id, :procurement_plan_id, :profile,
                      :lifecycle, :input_fingerprint, :plan_fingerprint, :solver_status,
                      :checker_passed, :runtime_seconds, CAST(:payload AS jsonb), :created_at
                    ) ON CONFLICT(plan_id) DO NOTHING"""),
                    {
                        "plan_id": plan.plan_id,
                        "request_id": response.request_id,
                        "run_id": plan.run_id,
                        "procurement_plan_id": plan.procurement_plan_id,
                        "profile": plan.profile.value,
                        "lifecycle": plan.lifecycle.value,
                        "input_fingerprint": plan.input_fingerprint,
                        "plan_fingerprint": plan.plan_fingerprint,
                        "solver_status": plan.result.status.value,
                        "checker_passed": bool(plan.result.checker and plan.result.checker.passed),
                        "runtime_seconds": plan.result.metadata.runtime.value
                        if plan.result.metadata.runtime
                        else 0.0,
                        "payload": plan.model_dump_json(),
                        "created_at": plan.created_at,
                    },
                )
                for action in plan.result.actions:
                    await connection.execute(
                        text(
                            "INSERT INTO reserve_plan_actions(action_id,plan_id,site_id,payload) "
                            "VALUES(:action_id,:plan_id,:site_id,CAST(:payload AS jsonb)) "
                            "ON CONFLICT(action_id) DO NOTHING"
                        ),
                        {
                            "action_id": action.action_id,
                            "plan_id": plan.plan_id,
                            "site_id": action.site_id,
                            "payload": action.model_dump_json(),
                        },
                    )
                for point in plan.result.timeline:
                    await connection.execute(
                        text(
                            "INSERT INTO reserve_inventory_timeline("
                            "plan_id,site_id,effective_at,payload) "
                            "VALUES(:plan_id,:site_id,:effective_at,CAST(:payload AS jsonb)) "
                            "ON CONFLICT(plan_id,site_id,effective_at) DO NOTHING"
                        ),
                        {
                            "plan_id": plan.plan_id,
                            "site_id": point.site_id,
                            "effective_at": point.at,
                            "payload": point.model_dump_json(),
                        },
                    )

    async def plan(self, plan_id: UUID) -> ReservePlan | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM reserve_plans WHERE plan_id=:plan_id"),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
        return ReservePlan.model_validate(payload) if isinstance(payload, dict) else None
