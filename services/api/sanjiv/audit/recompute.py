from __future__ import annotations

from sanjiv.audit.contracts import canonical_hash
from sanjiv.procurement.contracts import ProcurementPlan, procurement_plan_fingerprint
from sanjiv.reserve.contracts import ReservePlan, reserve_plan_fingerprint


def procurement_reconciliation(plan: ProcurementPlan) -> tuple[bool, str]:
    result = plan.solver_result
    objective = result.objective
    checker = result.independent_check
    passed = bool(
        objective
        and checker
        and checker.passed
        and abs(sum(objective.weighted_contributions.values()) - objective.total.value) <= 1e-6
        and procurement_plan_fingerprint(plan.fingerprint_inputs, result) == plan.plan_fingerprint
    )
    return passed, canonical_hash(
        {
            "objective": objective.model_dump(mode="json") if objective else None,
            "checker": checker.model_dump(mode="json") if checker else None,
            "plan_fingerprint": plan.plan_fingerprint,
        }
    )


def reserve_reconciliation(plan: ReservePlan) -> tuple[bool, str]:
    result = plan.result
    objective = result.objective
    checker = result.checker
    passed = bool(
        objective
        and checker
        and checker.passed
        and abs(sum(objective.weighted_contributions.values()) - objective.total.value) <= 1e-6
        and reserve_plan_fingerprint(plan.input, result) == plan.plan_fingerprint
    )
    return passed, canonical_hash(
        {
            "objective": objective.model_dump(mode="json") if objective else None,
            "checker": checker.model_dump(mode="json") if checker else None,
            "plan_fingerprint": plan.plan_fingerprint,
        }
    )
