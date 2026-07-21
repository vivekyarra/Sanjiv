from __future__ import annotations

import importlib.metadata
import math
import time
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

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
from sanjiv.procurement.checker import independent_check
from sanjiv.procurement.contracts import (
    ObjectiveWeights,
    ProcurementAction,
    ProcurementFailure,
    ProcurementFailureStage,
    ProcurementOptimisationInput,
    ProcurementOption,
    ProcurementProfile,
    RefineryAllocation,
    RejectedOption,
    RejectedOptionReasonCode,
    RouteAllocation,
    SolverConfiguration,
    SolverMetadata,
    SolverQuantity,
    SolverResult,
    SolverStatus,
    SupplierAllocation,
)

MODEL_VERSION = "procurement-pyomo-highs-v1"
MAX_MODEL_OPTIONS = 500
MAX_MODEL_CONSTRAINTS = 10_000


def default_solver_configuration(*, time_limit_seconds: float = 10.0) -> SolverConfiguration:
    return SolverConfiguration(
        solver_version=importlib.metadata.version("highspy"),
        time_limit=SolverQuantity(value=time_limit_seconds, unit="second"),
        relative_mip_gap=SolverQuantity(value=0.0, unit="fraction"),
        thread_count=1,
        random_seed=0,
    )


def solve_procurement_profile(
    optimisation_input: ProcurementOptimisationInput,
    weights: ObjectiveWeights,
    configuration: SolverConfiguration,
) -> SolverResult:
    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    profile = weights.profile
    if len(optimisation_input.options) > MAX_MODEL_OPTIONS:
        return _failed(
            profile,
            weights,
            configuration,
            started_at,
            timer,
            SolverStatus.ERROR,
            "MODEL_SIZE_LIMIT",
            "Procurement model exceeds the bounded option limit.",
        )
    try:
        model = _build_model(optimisation_input, weights)
        if (
            sum(1 for _ in model.component_data_objects(Constraint, active=True))
            > MAX_MODEL_CONSTRAINTS
        ):
            return _failed(
                profile,
                weights,
                configuration,
                started_at,
                timer,
                SolverStatus.ERROR,
                "MODEL_SIZE_LIMIT",
                "Procurement model exceeds the bounded constraint limit.",
            )
        solver = SolverFactory("highs")
        solver.options["time_limit"] = configuration.time_limit.value
        solver.options["threads"] = configuration.thread_count
        solver.options["random_seed"] = configuration.random_seed
        solver.options["mip_rel_gap"] = configuration.relative_mip_gap.value
        outcome = solver.solve(model, tee=False, load_solutions=True)
    except Exception:
        return _failed(
            profile,
            weights,
            configuration,
            started_at,
            timer,
            SolverStatus.ERROR,
            "SOLVER_ERROR",
            "HiGHS could not complete the bounded procurement model.",
        )
    termination = outcome.solver.termination_condition
    if termination in {TerminationCondition.infeasible, TerminationCondition.infeasibleOrUnbounded}:
        quantities = {item.option_id: 0.0 for item in optimisation_input.options}
        shortages = {item.refinery_id: 0.0 for item in optimisation_input.demands}
        _, _, report = independent_check(optimisation_input, weights, quantities, shortages, 0.0)
        return SolverResult(
            result_id=_result_id(optimisation_input, profile),
            profile=profile,
            status=SolverStatus.INFEASIBLE,
            metadata=_metadata(weights, configuration, started_at, timer),
            constraints=report,
            rejected_options=_all_rejected(
                optimisation_input, RejectedOptionReasonCode.CAPACITY_EXHAUSTED
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
        return _failed(
            profile,
            weights,
            configuration,
            started_at,
            timer,
            SolverStatus.ERROR,
            "SOLVER_TERMINATION",
            "HiGHS returned a non-usable procurement termination state.",
        )
    try:
        quantities = {
            UUID(option_id): max(0.0, float(value(model.x[option_id])))
            for option_id in model.OPTIONS
        }
        shortages = {
            UUID(refinery_id): max(0.0, float(value(model.shortage[refinery_id])))
            for refinery_id in model.REFINERIES
        }
        reported = float(value(model.objective))
        if not math.isfinite(reported):
            raise ValueError("non-finite objective")
        check, breakdown, report = independent_check(
            optimisation_input, weights, quantities, shortages, reported
        )
    except Exception:
        return _failed(
            profile,
            weights,
            configuration,
            started_at,
            timer,
            SolverStatus.ERROR,
            "CHECKER_ERROR",
            "Independent procurement verification could not reproduce the solution.",
        )
    if not check.passed:
        return SolverResult(
            result_id=_result_id(optimisation_input, profile),
            profile=profile,
            status=SolverStatus.ERROR,
            metadata=_metadata(weights, configuration, started_at, timer),
            constraints=report,
            independent_check=check,
            failure=ProcurementFailure(
                code="INDEPENDENT_CHECK_FAILED",
                message="Independent verification rejected the solver output.",
                stage=ProcurementFailureStage.INDEPENDENT_CHECK,
            ),
        )
    actions = _actions(optimisation_input, profile, quantities, check.checked_at)
    if not actions:
        return _failed(
            profile,
            weights,
            configuration,
            started_at,
            timer,
            SolverStatus.ERROR,
            "NO_ACTIONS",
            "The completed scenario has no positive procurement requirement.",
        )
    status = SolverStatus.FEASIBLE if timed_out else SolverStatus.OPTIMAL
    delivered = sum(quantities.values())
    shortage = sum(shortages.values())
    return SolverResult(
        result_id=_result_id(optimisation_input, profile),
        profile=profile,
        status=status,
        metadata=_metadata(weights, configuration, started_at, timer),
        objective=breakdown,
        actions=actions,
        supplier_allocations=[item.supplier for item in actions],
        route_allocations=[item.route for item in actions],
        refinery_allocations=[item.refinery for item in actions],
        constraints=report,
        rejected_options=_unused_rejections(optimisation_input, quantities),
        independent_check=check,
        delivered_volume=_metric(delivered, "ktonne", check.checked_at, optimisation_input),
        shortage=_metric(shortage, "ktonne", check.checked_at, optimisation_input),
    )


def _build_model(
    optimisation_input: ProcurementOptimisationInput, weights: ObjectiveWeights
) -> ConcreteModel:
    options = {str(item.option_id): item for item in optimisation_input.options}
    demand = {
        str(item.refinery_id): item.required_volume.value for item in optimisation_input.demands
    }
    total_demand = sum(demand.values())
    model = ConcreteModel(name="sanjiv_procurement")
    model.OPTIONS = Set(initialize=sorted(options), ordered=True)
    model.REFINERIES = Set(initialize=sorted(demand), ordered=True)
    suppliers = sorted({str(item.supplier_id) for item in options.values()})
    corridors = sorted({str(item.route_id) for item in options.values()})
    model.SUPPLIERS = Set(initialize=suppliers, ordered=True)
    model.CORRIDORS = Set(initialize=corridors, ordered=True)
    model.x = Var(model.OPTIONS, domain=NonNegativeReals)
    model.shortage = Var(model.REFINERIES, domain=NonNegativeReals)
    model.supplier_peak = Var(domain=NonNegativeReals)
    model.corridor_peak = Var(domain=NonNegativeReals)
    model.hard = ConstraintList()
    for option_id, option in options.items():
        cap = min(
            option.supplier_capacity.value,
            option.commercially_available_volume.value,
            option.route_capacity.value,
            option.refinery_receiving_capacity.value,
        )
        model.hard.add(
            model.x[option_id] <= cap
            if option.sanctions_permitted and option.compatibility_permitted
            else model.x[option_id] == 0
        )
    for refinery_id, required in demand.items():
        model.hard.add(
            sum(
                model.x[key]
                for key, option in options.items()
                if str(option.refinery_id) == refinery_id
            )
            + model.shortage[refinery_id]
            == required
        )
    for supplier_id in suppliers:
        subset = [
            (key, option)
            for key, option in options.items()
            if str(option.supplier_id) == supplier_id
        ]
        model.hard.add(
            sum(model.x[key] for key, _ in subset)
            <= max(option.supplier_capacity.value for _, option in subset)
        )
        model.hard.add(
            sum(model.x[key] for key, _ in subset)
            <= optimisation_input.hard_constraints.supplier_concentration_limit.value * total_demand
        )
        model.hard.add(
            sum(model.x[key] for key, _ in subset) <= model.supplier_peak * max(total_demand, 1.0)
        )
    for corridor_id in corridors:
        subset = [
            (key, option) for key, option in options.items() if str(option.route_id) == corridor_id
        ]
        model.hard.add(
            sum(model.x[key] for key, _ in subset)
            <= optimisation_input.hard_constraints.corridor_concentration_limit.value * total_demand
        )
        model.hard.add(
            sum(model.x[key] for key, _ in subset) <= model.corridor_peak * max(total_demand, 1.0)
        )
    segments = sorted(
        {segment for item in options.values() for segment in item.route_segment_ids}, key=str
    )
    for segment in segments:
        subset = [
            (key, option) for key, option in options.items() if segment in option.route_segment_ids
        ]
        model.hard.add(
            sum(model.x[key] for key, _ in subset)
            <= min(option.route_segment_capacities[segment] for _, option in subset)
        )
    for port_attr in ("load_port_id", "receiving_port_id"):
        ports = sorted(
            {getattr(item, port_attr) for item in options.values() if getattr(item, port_attr)},
            key=str,
        )
        for port_id in ports:
            subset = [
                (key, option)
                for key, option in options.items()
                if getattr(option, port_attr) == port_id
            ]
            model.hard.add(
                sum(model.x[key] for key, _ in subset)
                <= max(
                    max(option.route_segment_capacities.values(), default=0.0)
                    for _, option in subset
                )
            )
    for refinery_id in demand:
        subset = [
            (key, option)
            for key, option in options.items()
            if str(option.refinery_id) == refinery_id
        ]
        if subset:
            model.hard.add(
                sum(model.x[key] for key, _ in subset)
                <= max(option.refinery_receiving_capacity.value for _, option in subset)
            )
    model.hard.add(
        sum(model.x[key] * _cost(option) * 1_000 for key, option in options.items())
        <= optimisation_input.hard_constraints.budget_limit.value
    )
    landed = sum(model.x[key] * _cost(option) / 1_000 for key, option in options.items())
    shortfall = sum(model.shortage[key] for key in model.REFINERIES)
    delay = sum(
        model.x[key] * (option.transit_time.value if option.transit_time else 0) / 1_000
        for key, option in options.items()
    )
    route_risk = sum(
        model.x[key] * (option.route_distance.value if option.route_distance else 0) / 1_000_000
        for key, option in options.items()
    )
    compatibility = sum(
        model.x[key] * option.landed_cost.compatibility_penalty.value / 1_000
        for key, option in options.items()
        if option.landed_cost
    )
    emissions = sum(
        model.x[key] * option.landed_cost.emissions.value / 1_000
        for key, option in options.items()
        if option.landed_cost
    )
    model.objective = Objective(
        expr=weights.landed_cost.value * landed
        + weights.shortfall.value * shortfall
        + weights.delay.value * delay
        + weights.route_risk.value * route_risk
        + weights.supplier_concentration.value * model.supplier_peak
        + weights.corridor_concentration.value * model.corridor_peak
        + weights.compatibility_penalty.value * compatibility
        + weights.emissions.value * emissions,
        sense=minimize,
    )
    return model


def _actions(
    optimisation_input: ProcurementOptimisationInput,
    profile: ProcurementProfile,
    quantities: dict[UUID, float],
    at: datetime,
) -> list[ProcurementAction]:
    output: list[ProcurementAction] = []
    for option in optimisation_input.options:
        quantity = quantities.get(option.option_id, 0.0)
        if quantity <= 1e-7 or option.landed_cost is None:
            continue
        metric = _metric(quantity, "ktonne", at, optimisation_input)
        output.append(
            ProcurementAction(
                action_id=uuid5(
                    NAMESPACE_URL,
                    f"urn:sanjiv:procurement-action:{optimisation_input.input_fingerprint}:{profile.value}:{option.option_id}",
                ),
                option_id=option.option_id,
                supplier=SupplierAllocation(
                    supplier_id=option.supplier_id, grade_id=option.grade_id, volume=metric
                ),
                route=RouteAllocation(route_id=option.route_id, volume=metric),
                refinery=RefineryAllocation(
                    refinery_id=option.refinery_id, grade_id=option.grade_id, volume=metric
                ),
                delivery_window_start=option.delivery_window_start,
                delivery_window_end=option.delivery_window_end,
                landed_cost=option.landed_cost,
                evidence_ids=option.evidence_ids,
                assumption_ids=option.assumption_ids,
                option_fingerprint=option.option_fingerprint,
                load_port_id=option.load_port_id,
                receiving_port_id=option.receiving_port_id,
                route_segment_ids=option.route_segment_ids,
            )
        )
    return output


def _metadata(
    weights: ObjectiveWeights,
    configuration: SolverConfiguration,
    started_at: datetime,
    timer: float,
) -> SolverMetadata:
    completed = datetime.now(UTC)
    return SolverMetadata(
        solver_version=configuration.solver_version,
        model_version=MODEL_VERSION,
        objective_weight_version=weights.version,
        hard_constraint_version="procurement-hard-constraints-v1",
        configuration=configuration,
        started_at=started_at,
        completed_at=completed,
        runtime=SolverQuantity(value=max(0.0, time.perf_counter() - timer), unit="second"),
    )


def _failed(
    profile: ProcurementProfile,
    weights: ObjectiveWeights,
    configuration: SolverConfiguration,
    started_at: datetime,
    timer: float,
    status: SolverStatus,
    code: str,
    message: str,
) -> SolverResult:
    return SolverResult(
        result_id=uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:procurement-failure:{profile.value}:{started_at.isoformat()}",
        ),
        profile=profile,
        status=status,
        metadata=_metadata(weights, configuration, started_at, timer),
        failure=ProcurementFailure(
            code=code, message=message, stage=ProcurementFailureStage.SOLVER
        ),
    )


def _result_id(
    optimisation_input: ProcurementOptimisationInput, profile: ProcurementProfile
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"urn:sanjiv:procurement-result:{optimisation_input.input_fingerprint}:{profile.value}",
    )


def _all_rejected(
    optimisation_input: ProcurementOptimisationInput, reason: RejectedOptionReasonCode
) -> list[RejectedOption]:
    return [
        RejectedOption(
            option_id=item.option_id,
            reason_codes=[reason],
            violated_constraint_ids=[f"option:{item.option_id}:capacity"],
            explanation="The option cannot contribute to a feasible checked solution.",
        )
        for item in optimisation_input.options
    ]


def _unused_rejections(
    optimisation_input: ProcurementOptimisationInput, quantities: dict[UUID, float]
) -> list[RejectedOption]:
    return [
        RejectedOption(
            option_id=item.option_id,
            reason_codes=[
                RejectedOptionReasonCode.ROUTE_CLOSED
                if item.route_capacity.value <= 1e-9
                else RejectedOptionReasonCode.HIGHER_OBJECTIVE
            ],
            violated_constraint_ids=[
                f"option:{item.option_id}:route-capacity"
                if item.route_capacity.value <= 1e-9
                else "objective:profile-ranking"
            ],
            explanation=(
                "Option was excluded by disrupted route capacity or the profile objective; "
                "no order, cargo, or tanker has been secured."
            ),
        )
        for item in optimisation_input.options
        if quantities.get(item.option_id, 0.0) <= 1e-7
    ]


def _cost(option: ProcurementOption) -> float:
    landed = option.landed_cost
    if landed is None:
        raise ValueError("eligible option is missing landed cost")
    return float(landed.total.value)


def _metric(
    value_: float, unit: str, at: datetime, optimisation_input: ProcurementOptimisationInput
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=float(value_),
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=1.0,
        evidence_ids=[item.evidence_id for item in optimisation_input.provenance.evidence],
        source_refs=[SourceRef(source_id="procurement-solver", record_id=MODEL_VERSION)],
        effective_at=at,
        fetched_at=at,
        computed_at=at,
        freshness_status=FreshnessStatus.CURRENT,
        transformation=MODEL_VERSION,
        model_version=MODEL_VERSION,
    )
