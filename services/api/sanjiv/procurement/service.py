from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from sanjiv.procurement.contracts import (
    ProcurementPlan,
    ProcurementPlanFingerprintInputs,
    ProcurementPlanLifecycle,
    ProcurementPlanResponse,
    ProcurementProfile,
    SolverStatus,
    procurement_plan_fingerprint,
)
from sanjiv.procurement.costs import CostConfiguration
from sanjiv.procurement.fixture import load_commercial_fixture
from sanjiv.procurement.inputs import PlanningHorizon, build_procurement_input
from sanjiv.procurement.profiles import objective_weights
from sanjiv.procurement.repository import ProcurementRepository
from sanjiv.procurement.solver import (
    MODEL_VERSION,
    default_solver_configuration,
    solve_procurement_profile,
)
from sanjiv.scenarios.service import ScenarioService
from sanjiv.simulation.contracts import SimulationStatus


class ProcurementExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profiles: list[ProcurementProfile] = Field(
        default_factory=lambda: list(ProcurementProfile), min_length=1, max_length=3
    )
    time_limit_seconds: float = Field(default=10.0, gt=0, le=60, allow_inf_nan=False)


class ProcurementDomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProcurementService:
    def __init__(
        self, *, scenario_service: ScenarioService, repository: ProcurementRepository
    ) -> None:
        self.scenario_service = scenario_service
        self.repository = repository

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def close(self) -> None:
        await self.repository.close()

    async def create(
        self,
        run_id: UUID,
        payload: ProcurementExecutionRequest,
        *,
        idempotency_key: str,
        actor_id: str,
    ) -> ProcurementPlanResponse:
        del idempotency_key  # Exact immutable fingerprints, not caller keys, own reuse.
        run = await self.scenario_service.get_run(run_id)
        if run.status is not SimulationStatus.COMPLETED or run.result is None:
            raise ProcurementDomainError(
                "SIMULATION_NOT_COMPLETED",
                "Procurement planning requires an exact completed scenario run.",
            )
        confirmed = await self.scenario_service.confirmed(run.scenario_id)
        snapshot = self.scenario_service.twin_service.get(run.twin_snapshot.snapshot_id)
        if snapshot is None or snapshot.fingerprint != run.twin_snapshot.fingerprint:
            raise ProcurementDomainError(
                "TWIN_FINGERPRINT_MISMATCH",
                "The immutable twin snapshot cannot be reproduced.",
            )
        horizon = PlanningHorizon(
            starts_at=run.result.timeline[0].starts_at,
            ends_at=run.result.timeline[-1].ends_at,
            interval_hours=24,
        )
        fixture = load_commercial_fixture(snapshot, at=horizon.starts_at)
        built = build_procurement_input(
            run,
            run.result,
            confirmed,
            snapshot,
            profile=ProcurementProfile.LOWEST_COST,
            horizon=horizon,
            reserve_policy=fixture.reserve_policy,
            hard_constraints=fixture.hard_constraints,
            cost_configuration=CostConfiguration(
                version="landed-cost-v1",
                tolerance=1e-9,
                emissions_enabled=True,
            ),
            commercial_inputs=fixture.commercial_inputs,
            commercial_assumptions=fixture.assumptions,
        )
        if built.input is None:
            raise ProcurementDomainError(
                "PROCUREMENT_INPUT_BLOCKED",
                "; ".join(built.blocking_errors) or "Procurement input validation failed.",
            )
        if sum(item.required_volume.value for item in built.input.demands) <= 1e-9:
            raise ProcurementDomainError(
                "NO_PROCUREMENT_DEMAND",
                "The completed scenario has no modeled procurement shortfall.",
            )
        profiles = list(dict.fromkeys(payload.profiles))
        if profiles != sorted(profiles, key=lambda item: list(ProcurementProfile).index(item)):
            raise ProcurementDomainError(
                "PROFILE_ORDER_INVALID",
                "Profiles must be requested in LOWEST_COST, BALANCED, HIGHEST_RESILIENCE order.",
                status_code=422,
            )
        configuration = default_solver_configuration(time_limit_seconds=payload.time_limit_seconds)
        request_fingerprint = _hash(
            {
                "run_id": str(run_id),
                "input_fingerprint": built.input.input_fingerprint,
                "profiles": [item.value for item in profiles],
                "weights": [objective_weights(item).model_dump(mode="json") for item in profiles],
                "solver": configuration.model_dump(mode="json"),
                "model_version": MODEL_VERSION,
            }
        )
        reused = await self.repository.response_by_fingerprint(request_fingerprint)
        if reused is not None:
            return reused.model_copy(update={"reused": True})
        results = []
        plans = []
        for profile in profiles:
            weights = objective_weights(profile)
            result = solve_procurement_profile(built.input, weights, configuration)
            results.append(result)
            if result.status not in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}:
                continue
            fingerprint_inputs = ProcurementPlanFingerprintInputs(
                model_version=MODEL_VERSION,
                profile=profile,
                objective_weights=weights,
                solver_configuration=configuration,
                optimisation_input=built.input,
                optimisation_input_fingerprint=built.input.input_fingerprint,
                simulation_run=built.input.provenance.simulation_run,
                simulation_result=built.input.provenance.simulation_result,
                confirmed_scenario=built.input.provenance.confirmed_scenario,
                twin_snapshot=built.input.provenance.twin_snapshot,
                hard_constraint_version=built.input.hard_constraints.version,
                reserve_policy_fingerprint=built.input.reserve_policy.policy_fingerprint,
                evidence=built.input.provenance.evidence,
                assumptions=built.input.provenance.assumptions,
            )
            plan_fingerprint = procurement_plan_fingerprint(fingerprint_inputs, result)
            plan_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:procurement-plan:{plan_fingerprint}")
            audit_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:procurement-audit:{plan_id}:{actor_id}")
            plans.append(
                ProcurementPlan(
                    plan_id=plan_id,
                    run_id=run_id,
                    profile=profile,
                    lifecycle=ProcurementPlanLifecycle.FEASIBLE,
                    fingerprint_inputs=fingerprint_inputs,
                    plan_fingerprint=plan_fingerprint,
                    solver_result=result,
                    created_at=datetime.now(UTC),
                    audit_event_ids=[audit_id],
                )
            )
        response = ProcurementPlanResponse(
            request_id=uuid5(
                NAMESPACE_URL, f"urn:sanjiv:procurement-request:{request_fingerprint}"
            ),
            run_id=run_id,
            results=results,
            plans=plans,
            failures=[item.failure for item in results if item.failure is not None],
        )
        await self.repository.save_response(request_fingerprint, response)
        return response

    async def get(self, plan_id: UUID) -> ProcurementPlan:
        plan = await self.repository.plan(plan_id)
        if plan is None:
            raise ProcurementDomainError(
                "PROCUREMENT_PLAN_NOT_FOUND", "Procurement plan not found.", status_code=404
            )
        return plan


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
