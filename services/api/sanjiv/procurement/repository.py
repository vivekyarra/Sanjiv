from __future__ import annotations

import json
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.procurement.contracts import ProcurementPlan, ProcurementPlanResponse


class ProcurementRepository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def response_by_fingerprint(self, fingerprint: str) -> ProcurementPlanResponse | None: ...
    async def save_response(self, fingerprint: str, response: ProcurementPlanResponse) -> None: ...
    async def plan(self, plan_id: UUID) -> ProcurementPlan | None: ...


class InMemoryProcurementRepository:
    def __init__(self) -> None:
        self._responses: dict[str, ProcurementPlanResponse] = {}
        self._plans: dict[UUID, ProcurementPlan] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def response_by_fingerprint(self, fingerprint: str) -> ProcurementPlanResponse | None:
        return self._responses.get(fingerprint)

    async def save_response(self, fingerprint: str, response: ProcurementPlanResponse) -> None:
        self._responses.setdefault(fingerprint, response)
        for plan in response.plans:
            self._plans.setdefault(plan.plan_id, plan)

    async def plan(self, plan_id: UUID) -> ProcurementPlan | None:
        return self._plans.get(plan_id)


class PostgresProcurementRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        await self._engine.dispose()

    async def response_by_fingerprint(self, fingerprint: str) -> ProcurementPlanResponse | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text(
                        "SELECT response_payload FROM procurement_plan_requests "
                        "WHERE request_fingerprint = :fingerprint AND lifecycle = 'COMPLETED'"
                    ),
                    {"fingerprint": fingerprint},
                )
            ).scalar_one_or_none()
        return (
            ProcurementPlanResponse.model_validate(payload) if isinstance(payload, dict) else None
        )

    async def save_response(self, fingerprint: str, response: ProcurementPlanResponse) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("""
                    INSERT INTO procurement_plan_requests (
                      request_id, run_id, request_fingerprint, lifecycle,
                      response_payload, created_at
                    ) VALUES (
                      :request_id, :run_id, :fingerprint, 'COMPLETED',
                      CAST(:payload AS jsonb), now()
                    ) ON CONFLICT (request_fingerprint) DO NOTHING
                """),
                {
                    "request_id": response.request_id,
                    "run_id": response.run_id,
                    "fingerprint": fingerprint,
                    "payload": _json(response),
                },
            )
            for plan in response.plans:
                await connection.execute(
                    text("""
                        INSERT INTO procurement_plans (
                          plan_id, request_id, run_id, profile, lifecycle,
                          input_fingerprint, plan_fingerprint, solver_status,
                          checker_passed, runtime_seconds, payload, created_at
                        ) VALUES (
                          :plan_id, :request_id, :run_id, :profile, :lifecycle,
                          :input_fingerprint, :plan_fingerprint, :solver_status,
                          :checker_passed, :runtime_seconds, CAST(:payload AS jsonb), :created_at
                        ) ON CONFLICT (plan_id) DO NOTHING
                    """),
                    {
                        "plan_id": plan.plan_id,
                        "request_id": response.request_id,
                        "run_id": plan.run_id,
                        "profile": plan.profile.value,
                        "lifecycle": plan.lifecycle.value,
                        "input_fingerprint": plan.fingerprint_inputs.optimisation_input_fingerprint,
                        "plan_fingerprint": plan.plan_fingerprint,
                        "solver_status": plan.solver_result.status.value,
                        "checker_passed": bool(
                            plan.solver_result.independent_check
                            and plan.solver_result.independent_check.passed
                        ),
                        "runtime_seconds": plan.solver_result.metadata.runtime.value
                        if plan.solver_result.metadata.runtime
                        else 0.0,
                        "payload": _json(plan),
                        "created_at": plan.created_at,
                    },
                )
                for action in plan.solver_result.actions:
                    await connection.execute(
                        text("""
                            INSERT INTO procurement_plan_actions (
                              action_id, plan_id, option_id, payload
                            ) VALUES (
                              :action_id, :plan_id, :option_id, CAST(:payload AS jsonb)
                            ) ON CONFLICT (action_id) DO NOTHING
                        """),
                        {
                            "action_id": action.action_id,
                            "plan_id": plan.plan_id,
                            "option_id": action.option_id,
                            "payload": _json(action),
                        },
                    )
                for rejected in plan.solver_result.rejected_options:
                    await connection.execute(
                        text("""
                            INSERT INTO procurement_rejected_options (
                              plan_id, option_id, payload
                            ) VALUES (
                              :plan_id, :option_id, CAST(:payload AS jsonb)
                            ) ON CONFLICT (plan_id, option_id) DO NOTHING
                        """),
                        {
                            "plan_id": plan.plan_id,
                            "option_id": rejected.option_id,
                            "payload": _json(rejected),
                        },
                    )

    async def plan(self, plan_id: UUID) -> ProcurementPlan | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text("SELECT payload FROM procurement_plans WHERE plan_id = :plan_id"),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
        return ProcurementPlan.model_validate(payload) if isinstance(payload, dict) else None


def _json(value: object) -> str:
    if hasattr(value, "model_dump_json"):
        return str(value.model_dump_json())
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
