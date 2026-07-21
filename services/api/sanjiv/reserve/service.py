from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.procurement.contracts import ProcurementPlanLifecycle, SolverStatus
from sanjiv.procurement.service import ProcurementService
from sanjiv.procurement.solver import default_solver_configuration
from sanjiv.reserve.contracts import (
    ReservePlan,
    ReservePlanLifecycle,
    ReservePlanResponse,
    ReservePolicyProfile,
    reserve_plan_fingerprint,
)
from sanjiv.reserve.inputs import build_reserve_input
from sanjiv.reserve.profiles import reserve_policy
from sanjiv.reserve.repository import ReserveRepository
from sanjiv.reserve.solver import solve_reserve_plan
from sanjiv.scenarios.service import ScenarioService
from sanjiv.simulation.contracts import SimulationStatus


class ReserveExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    procurement_plan_id: UUID
    profiles: list[ReservePolicyProfile] = Field(
        default_factory=lambda: list(ReservePolicyProfile), min_length=1, max_length=4
    )
    time_limit_seconds: float = Field(default=10.0, gt=0, le=60, allow_inf_nan=False)


class ReserveDomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class ReserveService:
    def __init__(
        self,
        *,
        scenario_service: ScenarioService,
        procurement_service: ProcurementService,
        repository: ReserveRepository,
    ) -> None:
        self.scenario_service = scenario_service
        self.procurement_service = procurement_service
        self.repository = repository

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def close(self) -> None:
        await self.repository.close()

    async def create(
        self, run_id: UUID, payload: ReserveExecutionRequest, *, idempotency_key: str, actor_id: str
    ) -> ReservePlanResponse:
        del idempotency_key
        run = await self.scenario_service.get_run(run_id)
        if run.status is not SimulationStatus.COMPLETED or run.result is None:
            raise ReserveDomainError(
                "SIMULATION_NOT_COMPLETED",
                "Reserve planning requires an exact completed scenario run.",
            )
        procurement = await self.procurement_service.get(payload.procurement_plan_id)
        if (
            procurement.run_id != run_id
            or procurement.lifecycle is not ProcurementPlanLifecycle.FEASIBLE
        ):
            raise ReserveDomainError(
                "PROCUREMENT_PLAN_MISMATCH",
                "The selected checked procurement plan must belong to this exact run.",
            )
        if (
            procurement.solver_result.independent_check is None
            or not procurement.solver_result.independent_check.passed
        ):
            raise ReserveDomainError(
                "PROCUREMENT_CHECK_FAILED",
                "The selected procurement plan has not passed its independent checker.",
            )
        snapshot = self.scenario_service.twin_service.get(run.twin_snapshot.snapshot_id)
        if snapshot is None or snapshot.fingerprint != run.twin_snapshot.fingerprint:
            raise ReserveDomainError(
                "TWIN_FINGERPRINT_MISMATCH", "The immutable twin snapshot cannot be reproduced."
            )
        profiles = list(dict.fromkeys(payload.profiles))
        if profiles != sorted(profiles, key=lambda item: list(ReservePolicyProfile).index(item)):
            raise ReserveDomainError(
                "PROFILE_ORDER_INVALID",
                "Profiles must use canonical reserve-policy order.",
                status_code=422,
            )
        configuration = default_solver_configuration(time_limit_seconds=payload.time_limit_seconds)
        request_fingerprint = _hash(
            {
                "run_id": str(run_id),
                "procurement_plan_fingerprint": procurement.plan_fingerprint,
                "profiles": [item.value for item in profiles],
                "policies": [reserve_policy(item).model_dump(mode="json") for item in profiles],
                "solver": configuration.model_dump(mode="json"),
            }
        )
        reused = await self.repository.response_by_fingerprint(request_fingerprint)
        if reused is not None:
            return reused.model_copy(update={"reused": True})
        results = []
        plans = []
        for profile in profiles:
            try:
                reserve_input = build_reserve_input(procurement, snapshot, reserve_policy(profile))
            except ValueError as exc:
                raise ReserveDomainError("RESERVE_INPUT_BLOCKED", str(exc)) from exc
            result = solve_reserve_plan(reserve_input, configuration)
            results.append(result)
            if result.status not in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}:
                continue
            plan_fingerprint = reserve_plan_fingerprint(reserve_input, result)
            plan_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:reserve-plan:{plan_fingerprint}")
            plans.append(
                ReservePlan(
                    plan_id=plan_id,
                    run_id=run_id,
                    procurement_plan_id=procurement.plan_id,
                    profile=profile,
                    lifecycle=ReservePlanLifecycle.FEASIBLE,
                    input=reserve_input,
                    input_fingerprint=reserve_input.input_fingerprint,
                    plan_fingerprint=plan_fingerprint,
                    result=result,
                    created_at=datetime.now(UTC),
                    audit_event_ids=[
                        uuid5(NAMESPACE_URL, f"urn:sanjiv:reserve-audit:{plan_id}:{actor_id}")
                    ],
                )
            )
        response = ReservePlanResponse(
            request_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:reserve-request:{request_fingerprint}"),
            run_id=run_id,
            procurement_plan_id=procurement.plan_id,
            results=results,
            plans=plans,
            failures=[item.failure for item in results if item.failure is not None],
        )
        await self.repository.save_response(request_fingerprint, response)
        return response

    async def get(self, plan_id: UUID) -> ReservePlan:
        plan = await self.repository.plan(plan_id)
        if plan is None:
            raise ReserveDomainError(
                "RESERVE_PLAN_NOT_FOUND", "Reserve plan not found.", status_code=404
            )
        return plan


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
