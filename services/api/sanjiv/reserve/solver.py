from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from pyomo.contrib.solver.common.util import NoFeasibleSolutionError  # type: ignore[import-untyped]
from pyomo.environ import (  # type: ignore[import-untyped]
    ConcreteModel,
    Constraint,
    ConstraintList,
    NonNegativeReals,
    Objective,
    Set,
    SolverFactory,
    Var,
    minimize,
    value,
)
from pyomo.opt import SolverStatus as PyomoSolverStatus  # type: ignore[import-untyped]
from pyomo.opt import TerminationCondition

from sanjiv.contracts import FreshnessStatus, MetricEnvelope, SourceRef, TruthClass
from sanjiv.procurement.contracts import (
    SolverConfiguration,
    SolverMetadata,
    SolverQuantity,
    SolverStatus,
)
from sanjiv.reserve.checker import independent_reserve_check
from sanjiv.reserve.contracts import (
    ReserveAction,
    ReserveFailure,
    ReserveInventoryPoint,
    ReserveOptimisationInput,
    ReservePolicyProfile,
    ReserveRejectedOption,
    ReserveRejectedReason,
    ReserveSolverResult,
)

MODEL_VERSION = "reserve-pyomo-highs-v1"
MAX_SITES = 100
MAX_CONSTRAINTS = 5000


def solve_reserve_plan(
    optimisation_input: ReserveOptimisationInput, configuration: SolverConfiguration
) -> ReserveSolverResult:
    started = datetime.now(UTC)
    timer = time.perf_counter()
    if len(optimisation_input.sites) > MAX_SITES:
        return _failure(
            optimisation_input,
            configuration,
            started,
            timer,
            SolverStatus.ERROR,
            "MODEL_SIZE_LIMIT",
            "Reserve model exceeds the bounded site limit.",
        )
    try:
        model = _build_model(optimisation_input)
        if sum(1 for _ in model.component_data_objects(Constraint, active=True)) > MAX_CONSTRAINTS:
            return _failure(
                optimisation_input,
                configuration,
                started,
                timer,
                SolverStatus.ERROR,
                "MODEL_SIZE_LIMIT",
                "Reserve model exceeds the bounded constraint limit.",
            )
        solver = SolverFactory("highs")
        solver.options["time_limit"] = configuration.time_limit.value
        solver.options["threads"] = configuration.thread_count
        solver.options["random_seed"] = configuration.random_seed
        solver.options["mip_rel_gap"] = configuration.relative_mip_gap.value
        outcome = solver.solve(model, tee=False, load_solutions=True)
    except NoFeasibleSolutionError:
        return ReserveSolverResult(
            result_id=_result_id(optimisation_input),
            profile=optimisation_input.policy.profile,
            status=SolverStatus.INFEASIBLE,
            metadata=_metadata(optimisation_input, configuration, started, timer),
            failure=ReserveFailure(
                code="INFEASIBLE",
                message="No reserve plan satisfies all physical and policy constraints.",
                stage="SOLVER",
            ),
        )
    except Exception:
        return _failure(
            optimisation_input,
            configuration,
            started,
            timer,
            SolverStatus.ERROR,
            "SOLVER_ERROR",
            "HiGHS could not complete the bounded reserve model.",
        )
    termination = outcome.solver.termination_condition
    if termination in {TerminationCondition.infeasible, TerminationCondition.infeasibleOrUnbounded}:
        return ReserveSolverResult(
            result_id=_result_id(optimisation_input),
            profile=optimisation_input.policy.profile,
            status=SolverStatus.INFEASIBLE,
            metadata=_metadata(optimisation_input, configuration, started, timer),
            constraints=None,
            failure=ReserveFailure(
                code="INFEASIBLE",
                message="No reserve plan satisfies all physical and policy constraints.",
                stage="SOLVER",
            ),
        )
    timed_out = termination in {
        TerminationCondition.maxTimeLimit,
        TerminationCondition.maxIterations,
        TerminationCondition.resourceInterrupt,
    }
    acceptable = termination in {
        TerminationCondition.optimal,
        TerminationCondition.feasible,
        TerminationCondition.maxTimeLimit,
        TerminationCondition.maxIterations,
    }
    if not acceptable or outcome.solver.status not in {
        PyomoSolverStatus.ok,
        PyomoSolverStatus.warning,
    }:
        return _failure(
            optimisation_input,
            configuration,
            started,
            timer,
            SolverStatus.ERROR,
            "SOLVER_TERMINATION",
            "HiGHS returned a non-usable reserve termination state.",
        )
    try:
        dispatch = {UUID(key): max(0.0, float(value(model.dispatch[key]))) for key in model.SITES}
        shortages = {
            UUID(key): max(0.0, float(value(model.shortage[key]))) for key in model.REFINERIES
        }
        reported = float(value(model.objective))
        if not math.isfinite(reported):
            raise ValueError("non-finite objective")
        check, objective, report = independent_reserve_check(
            optimisation_input, dispatch, shortages, reported
        )
    except Exception:
        return _failure(
            optimisation_input,
            configuration,
            started,
            timer,
            SolverStatus.ERROR,
            "CHECKER_ERROR",
            "Independent reserve verification could not reproduce the solution.",
        )
    if not check.passed:
        return ReserveSolverResult(
            result_id=_result_id(optimisation_input),
            profile=optimisation_input.policy.profile,
            status=SolverStatus.ERROR,
            metadata=_metadata(optimisation_input, configuration, started, timer),
            constraints=report,
            checker=check,
            failure=ReserveFailure(
                code="INDEPENDENT_CHECK_FAILED",
                message="Independent verification rejected the reserve output.",
                stage="CHECKER",
            ),
        )
    actions, timeline = _outputs(optimisation_input, dispatch, check.checked_at)
    residual = sum(shortages.values())
    return ReserveSolverResult(
        result_id=_result_id(optimisation_input),
        profile=optimisation_input.policy.profile,
        status=SolverStatus.FEASIBLE if timed_out else SolverStatus.OPTIMAL,
        metadata=_metadata(optimisation_input, configuration, started, timer),
        actions=actions,
        timeline=timeline,
        objective=objective,
        constraints=report,
        checker=check,
        residual_shortage=_metric(residual, "ktonne", check.checked_at, optimisation_input),
        rejected_options=[
            ReserveRejectedOption(
                site_id=site.site_id,
                reason=ReserveRejectedReason.NO_RESERVE_USE,
                constraint_id=f"site:{site.site_id}:no-reserve-use",
                explanation="The selected policy fixes reserve dispatch at zero.",
            )
            for site in optimisation_input.sites
        ]
        if optimisation_input.policy.profile is ReservePolicyProfile.NO_RESERVE_USE
        else [],
    )


def _build_model(optimisation_input: ReserveOptimisationInput) -> ConcreteModel:
    sites = {str(item.site_id): item for item in optimisation_input.sites}
    demand = {
        str(item.refinery_id): item.required_volume.value for item in optimisation_input.demands
    }
    days = (optimisation_input.ends_at - optimisation_input.starts_at).total_seconds() / 86400
    model = ConcreteModel(name="sanjiv_reserve")
    model.SITES = Set(initialize=sorted(sites), ordered=True)
    model.REFINERIES = Set(initialize=sorted(demand), ordered=True)
    model.dispatch = Var(model.SITES, domain=NonNegativeReals)
    model.shortage = Var(model.REFINERIES, domain=NonNegativeReals)
    model.hard = ConstraintList()
    for key, site in sites.items():
        opening = site.opening_inventory.value if site.opening_inventory else 0.0
        replenishment = site.replenishment.value if site.replenishment else 0.0
        release_cap = min(
            max(0.0, opening + replenishment - site.minimum_policy_floor.value),
            site.draw_rate_limit.value * days,
            site.route_capacity.value * days,
            max(
                0.0,
                site.refinery_receipt_capacity.value - site.procurement_committed_receipts.value,
            ),
        )
        model.hard.add(model.dispatch[key] <= release_cap)
        model.hard.add(
            opening + replenishment - model.dispatch[key] >= site.minimum_policy_floor.value
        )
        model.hard.add(opening + replenishment - model.dispatch[key] <= site.capacity.value)
        if (
            site.transit_time.value > days
            or optimisation_input.policy.profile is ReservePolicyProfile.NO_RESERVE_USE
        ):
            model.hard.add(model.dispatch[key] == 0)
    for refinery_id, required in demand.items():
        model.hard.add(
            sum(
                model.dispatch[key]
                for key, site in sites.items()
                if str(site.refinery_id) == refinery_id
            )
            + model.shortage[refinery_id]
            == required
        )
    shortage = sum(model.shortage[key] for key in model.REFINERIES)
    depletion = sum(model.dispatch[key] for key in model.SITES)
    logistics = sum(
        model.dispatch[key] * sites[key].logistics_cost.value / 1000.0 for key in model.SITES
    )
    vulnerability = sum(
        model.dispatch[key] / max(sites[key].capacity.value, 1.0) for key in model.SITES
    )
    weights = optimisation_input.policy
    model.objective = Objective(
        expr=weights.shortage * shortage
        + weights.reserve_depletion * depletion
        + weights.logistics_cost * logistics
        + weights.future_vulnerability * vulnerability,
        sense=minimize,
    )
    return model


def _outputs(
    optimisation_input: ReserveOptimisationInput, dispatch: dict[UUID, float], at: datetime
) -> tuple[list[ReserveAction], list[ReserveInventoryPoint]]:
    actions: list[ReserveAction] = []
    timeline: list[ReserveInventoryPoint] = []
    for site in optimisation_input.sites:
        quantity = dispatch.get(site.site_id, 0.0)
        opening = site.opening_inventory.value if site.opening_inventory else 0.0
        replenishment = site.replenishment.value if site.replenishment else 0.0
        remaining = opening + replenishment - quantity
        demand = next(
            (
                item.required_volume.value
                for item in optimisation_input.demands
                if item.refinery_id == site.refinery_id
            ),
            0.0,
        )
        cover = remaining / max(
            demand
            / max(
                (optimisation_input.ends_at - optimisation_input.starts_at).total_seconds() / 86400,
                1.0,
            ),
            1e-9,
        )
        opening_cover = opening / max(
            demand
            / max(
                (optimisation_input.ends_at - optimisation_input.starts_at).total_seconds() / 86400,
                1.0,
            ),
            1e-9,
        )
        receipt_at = optimisation_input.starts_at + timedelta(days=site.transit_time.value)
        if quantity > optimisation_input.tolerance:
            actions.append(
                ReserveAction(
                    action_id=uuid5(
                        NAMESPACE_URL,
                        f"urn:sanjiv:reserve-action:{optimisation_input.input_fingerprint}:{site.site_id}",
                    ),
                    site_id=site.site_id,
                    refinery_id=site.refinery_id,
                    route_id=site.route_id,
                    dispatch=_metric(quantity, "ktonne", at, optimisation_input),
                    in_transit=_metric(quantity, "ktonne", at, optimisation_input),
                    receipt=_metric(quantity, "ktonne", at, optimisation_input),
                    remaining_inventory=_metric(remaining, "ktonne", at, optimisation_input),
                    remaining_cover=_metric(cover, "day", at, optimisation_input),
                    dispatch_at=optimisation_input.starts_at,
                    receipt_at=receipt_at,
                    evidence_ids=site.evidence_ids,
                    assumption_ids=site.assumption_ids,
                )
            )
        timeline.extend(
            [
                ReserveInventoryPoint(
                    site_id=site.site_id,
                    at=optimisation_input.starts_at,
                    inventory=_metric(opening, "ktonne", at, optimisation_input),
                    cover=_metric(opening_cover, "day", at, optimisation_input),
                ),
                ReserveInventoryPoint(
                    site_id=site.site_id,
                    at=optimisation_input.ends_at,
                    inventory=_metric(remaining, "ktonne", at, optimisation_input),
                    cover=_metric(cover, "day", at, optimisation_input),
                ),
            ]
        )
    return actions, timeline


def _metadata(
    optimisation_input: ReserveOptimisationInput,
    configuration: SolverConfiguration,
    started: datetime,
    timer: float,
) -> SolverMetadata:
    return SolverMetadata(
        solver_version=configuration.solver_version,
        model_version=MODEL_VERSION,
        objective_weight_version=optimisation_input.policy.version,
        hard_constraint_version="reserve-hard-constraints-v1",
        configuration=configuration,
        started_at=started,
        completed_at=datetime.now(UTC),
        runtime=SolverQuantity(value=max(0.0, time.perf_counter() - timer), unit="second"),
    )


def _failure(
    optimisation_input: ReserveOptimisationInput,
    configuration: SolverConfiguration,
    started: datetime,
    timer: float,
    status: SolverStatus,
    code: str,
    message: str,
) -> ReserveSolverResult:
    return ReserveSolverResult(
        result_id=_result_id(optimisation_input),
        profile=optimisation_input.policy.profile,
        status=status,
        metadata=_metadata(optimisation_input, configuration, started, timer),
        failure=ReserveFailure(code=code, message=message, stage="SOLVER"),
    )


def _result_id(optimisation_input: ReserveOptimisationInput) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:sanjiv:reserve-result:{optimisation_input.input_fingerprint}")


def _metric(
    value_: float, unit: str, at: datetime, optimisation_input: ReserveOptimisationInput
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=max(0.0, float(value_)),
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=1.0,
        evidence_ids=[item.evidence_id for item in optimisation_input.provenance.evidence],
        source_refs=[SourceRef(source_id="reserve-solver", record_id=MODEL_VERSION)],
        effective_at=at,
        fetched_at=at,
        computed_at=at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=MODEL_VERSION,
        model_version=MODEL_VERSION,
    )
