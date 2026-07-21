from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.audit.claims import blocked_claim_codes
from sanjiv.audit.contracts import (
    AuditedMetric,
    AuditFailure,
    AuditFailureCode,
    AuditFingerprintSet,
    EvidenceAuditResult,
    EvidenceAuditStatus,
    ExplanationAlternative,
    ExplanationConstraint,
    GovernanceRole,
    LifecycleAction,
    PlanExplanation,
    PlanGovernanceState,
    PlanKind,
    PlanLifecycleRecord,
    PlanLifecycleRequest,
    PlanReviewState,
    canonical_hash,
)
from sanjiv.audit.coverage import iter_metrics
from sanjiv.audit.policies import BLOCKING_FRESHNESS, truth_transition_allowed
from sanjiv.audit.recompute import procurement_reconciliation, reserve_reconciliation
from sanjiv.audit.repository import AuditRepository, current_state
from sanjiv.contracts import (
    Assumption,
    AssumptionStatus,
    EvidenceRecord,
    MetricEnvelope,
)
from sanjiv.procurement.contracts import ProcurementPlan, SolverStatus
from sanjiv.procurement.fixture import load_commercial_fixture
from sanjiv.procurement.service import ProcurementService
from sanjiv.reserve.contracts import ReservePlan
from sanjiv.reserve.inputs import load_reserve_fixture_assumptions
from sanjiv.reserve.service import ReserveService
from sanjiv.scenarios.service import ScenarioDomainError, ScenarioService

Plan = ProcurementPlan | ReservePlan


class AuditDomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class AuditService:
    def __init__(
        self,
        *,
        scenario_service: ScenarioService,
        procurement_service: ProcurementService,
        reserve_service: ReserveService,
        repository: AuditRepository,
    ) -> None:
        self.scenario_service = scenario_service
        self.procurement_service = procurement_service
        self.reserve_service = reserve_service
        self.repository = repository

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def close(self) -> None:
        await self.repository.close()

    async def audit_plan(self, plan_id: UUID, *, at: datetime | None = None) -> EvidenceAuditResult:
        plan, kind = await self._plan(plan_id)
        audited_at = (at or datetime.now(UTC)).astimezone(UTC)
        evidence, assumptions = await self._records(plan, kind)
        evidence_by_id = {item.id: item for item in evidence}
        assumption_by_id = {item.id: item for item in assumptions}
        evidence_refs, assumption_refs = _references(plan)
        failures: list[AuditFailure] = []

        for reference in evidence_refs:
            record = evidence_by_id.get(reference.evidence_id)
            if record is None:
                failures.append(
                    _failure(
                        AuditFailureCode.EVIDENCE_MISSING,
                        f"evidence.{reference.evidence_id}",
                        "Referenced evidence record does not exist.",
                    )
                )
                continue
            if record.raw_payload_hash.lower() != reference.raw_payload_hash.lower():
                failures.append(
                    _failure(
                        AuditFailureCode.EVIDENCE_HASH_MISMATCH,
                        f"evidence.{record.id}",
                        "Immutable evidence hash does not match the plan fingerprint.",
                    )
                )
            for parent_id in record.parent_evidence_ids:
                if parent_id not in evidence_by_id:
                    failures.append(
                        _failure(
                            AuditFailureCode.EVIDENCE_PARENT_MISSING,
                            f"evidence.{record.id}",
                            f"Parent evidence {parent_id} is missing.",
                        )
                    )

        scenario_id = _scenario_id(plan)
        for reference in assumption_refs:
            assumption = assumption_by_id.get(reference.assumption_id)
            path = f"assumption.{reference.assumption_id}"
            if assumption is None:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_MISSING,
                        path,
                        "Referenced assumption record does not exist.",
                    )
                )
                continue
            if canonical_hash(assumption.model_dump(mode="json")) != reference.assumption_hash:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_HASH_MISMATCH,
                        path,
                        "Immutable assumption hash does not match the plan fingerprint.",
                    )
                )
            if assumption.status is AssumptionStatus.SUPERSEDED:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_SUPERSEDED,
                        path,
                        "Superseded assumption cannot support a decision claim.",
                    )
                )
            elif assumption.status is not AssumptionStatus.APPROVED:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_NOT_APPROVED,
                        path,
                        "Decision assumptions must be explicitly approved.",
                    )
                )
            if assumption.expires_at is not None and assumption.expires_at <= audited_at:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_EXPIRED,
                        path,
                        "Assumption expired before this audit.",
                    )
                )
            if assumption.scenario_id is not None and assumption.scenario_id != scenario_id:
                failures.append(
                    _failure(
                        AuditFailureCode.ASSUMPTION_SCOPE_MISMATCH,
                        path,
                        "Assumption is scoped to a different scenario.",
                    )
                )

        audited_metrics: list[AuditedMetric] = []
        referenced_ids = {item.evidence_id for item in evidence_refs}
        for path, metric in iter_metrics(plan):
            metric_failures = self._audit_metric(path, metric, evidence_by_id, referenced_ids)
            audited_metrics.append(
                AuditedMetric(
                    path=path,
                    value=metric.value,
                    unit=metric.unit,
                    truth_class=metric.truth_class.value,
                    freshness_status=metric.freshness_status.value,
                    confidence=metric.confidence,
                    evidence_ids=metric.evidence_ids,
                    source_count=len(metric.source_refs),
                    transformation=metric.transformation,
                    model_version=metric.model_version,
                    recomputation_hash=canonical_hash(metric.model_dump(mode="json")),
                    status=EvidenceAuditStatus.FAILED
                    if metric_failures
                    else EvidenceAuditStatus.PASSED,
                    failures=metric_failures,
                )
            )
            failures.extend(metric_failures)

        solver = _solver_details(plan)
        if solver[0] not in {SolverStatus.OPTIMAL.value, SolverStatus.FEASIBLE.value}:
            failures.append(
                _failure(
                    AuditFailureCode.SOLVER_NOT_USABLE,
                    "plan.solver",
                    "Solver state is not feasible or optimal.",
                )
            )
        if not solver[4]:
            failures.append(
                _failure(
                    AuditFailureCode.CHECKER_FAILED,
                    "plan.checker",
                    "Independent checker did not pass.",
                )
            )
        if not solver[5]:
            failures.append(
                _failure(
                    AuditFailureCode.SANCTIONS_EXCLUSION_FAILED,
                    "plan.sanctions",
                    "Sanctions exclusions were not independently verified.",
                )
            )
        if not solver[6]:
            failures.append(
                _failure(
                    AuditFailureCode.COMPATIBILITY_EXCLUSION_FAILED,
                    "plan.compatibility",
                    "Compatibility exclusions were not independently verified.",
                )
            )

        recomputation_passed, _ = (
            procurement_reconciliation(plan)
            if isinstance(plan, ProcurementPlan)
            else reserve_reconciliation(plan)
        )
        if not recomputation_passed:
            failures.append(
                _failure(
                    AuditFailureCode.RECOMPUTATION_MISMATCH,
                    "plan.recomputation",
                    "Objective, checker, or canonical plan fingerprint did not reconcile.",
                )
            )

        fingerprints = _fingerprints(plan, evidence_refs, assumption_refs)
        coverage = (
            100.0 * sum(not item.failures for item in audited_metrics) / len(audited_metrics)
            if audited_metrics
            else 0.0
        )
        unique_failures = list(
            {(item.code, item.path, item.message): item for item in failures}.values()
        )
        passed = not unique_failures and coverage == 100.0
        base: dict[str, Any] = {
            "plan_id": plan_id,
            "plan_kind": kind,
            "status": EvidenceAuditStatus.PASSED if passed else EvidenceAuditStatus.FAILED,
            "auditor_version": "evidence-auditor-v1",
            "formula_registry_version": "decision-formulas-v1",
            "claim_policy_version": "claim-language-policy-v1",
            "fingerprints": fingerprints,
            "metrics": audited_metrics,
            "failures": unique_failures,
            "evidence_count": len(evidence_refs),
            "assumption_count": len(assumption_refs),
            "covered_metric_count": sum(not item.failures for item in audited_metrics),
            "total_metric_count": len(audited_metrics),
            "evidence_coverage_percentage": coverage,
            "solver_status": solver[0],
            "solver_version": solver[1],
            "model_version": solver[2],
            "checker_version": solver[3],
            "checker_passed": solver[4],
            "sanctions_exclusion_passed": solver[5],
            "compatibility_exclusion_passed": solver[6],
            "recomputation_passed": recomputation_passed,
            "claim_language_passed": True,
            "usable": passed,
            "approval_allowed": passed,
            "export_allowed": passed,
            "definitive_narrative_allowed": passed,
        }
        audit_fingerprint = canonical_hash(base)
        existing = await self.repository.audit(plan_id, audit_fingerprint)
        if existing is not None:
            return existing
        audit_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:evidence-audit:{audit_fingerprint}")
        audit = EvidenceAuditResult.model_validate(
            {
                **base,
                "audit_id": audit_id,
                "audited_at": audited_at,
                "audit_fingerprint": audit_fingerprint,
            }
        )
        await self.repository.save_audit(audit)
        return audit

    def _audit_metric(
        self,
        path: str,
        metric: MetricEnvelope[Any],
        evidence: dict[UUID, EvidenceRecord],
        referenced_ids: set[UUID],
    ) -> list[AuditFailure]:
        failures: list[AuditFailure] = []
        if not metric.evidence_ids:
            failures.append(
                _failure(
                    AuditFailureCode.METRIC_PROVENANCE_MISSING,
                    path,
                    "Decision metric has no evidence reference.",
                )
            )
        if not metric.source_refs:
            failures.append(
                _failure(
                    AuditFailureCode.SOURCE_INCOMPLETE,
                    path,
                    "Decision metric has no source reference.",
                )
            )
        if not metric.transformation.strip():
            failures.append(
                _failure(
                    AuditFailureCode.TRANSFORMATION_INCOMPLETE,
                    path,
                    "Decision metric has no transformation.",
                )
            )
        if not metric.model_version.strip():
            failures.append(
                _failure(
                    AuditFailureCode.VERSION_MISSING,
                    path,
                    "Decision metric has no formula/model version.",
                )
            )
        if metric.freshness_status in BLOCKING_FRESHNESS:
            failures.append(
                _failure(
                    AuditFailureCode.METRIC_STALE,
                    path,
                    f"Metric freshness is {metric.freshness_status.value}.",
                )
            )
        for evidence_id in metric.evidence_ids:
            record = evidence.get(evidence_id)
            if record is None or evidence_id not in referenced_ids:
                failures.append(
                    _failure(
                        AuditFailureCode.EVIDENCE_MISSING,
                        path,
                        f"Metric evidence {evidence_id} is not bound to the plan.",
                    )
                )
            elif not truth_transition_allowed(metric.truth_class, record.truth_class):
                failures.append(
                    _failure(
                        AuditFailureCode.TRUTH_TRANSITION_INVALID,
                        path,
                        f"{record.truth_class.value} evidence cannot support "
                        f"{metric.truth_class.value} under the truth policy.",
                    )
                )
        return failures

    async def explanation(self, plan_id: UUID) -> PlanExplanation:
        plan, kind = await self._plan(plan_id)
        audit = await self.audit_plan(plan_id)
        if isinstance(plan, ProcurementPlan):
            procurement_result = plan.solver_result
            procurement_objective = procurement_result.objective
            rejected = [
                ExplanationAlternative(
                    subject_id=item.option_id,
                    reason_codes=[code.value for code in item.reason_codes],
                    explanation=item.explanation,
                )
                for item in procurement_result.rejected_options
            ]
            constraints = [
                ExplanationConstraint(
                    name=family.value,
                    satisfied=bool(
                        procurement_result.constraints and procurement_result.constraints.feasible
                    ),
                    detail="Independently checked hard constraint family.",
                )
                for family in (
                    procurement_result.constraints.checked_families
                    if procurement_result.constraints
                    else []
                )
            ]
            rationale = [
                f"Candidate allocation {item.action_id} routes "
                f"{item.supplier.volume.value:.3f} {item.supplier.volume.unit} "
                "through an assumption-backed eligible option."
                for item in procurement_result.actions
            ]
            components = (
                procurement_objective.weighted_contributions if procurement_objective else {}
            )
            weights = procurement_objective.weights if procurement_objective else {}
            shortage = procurement_result.shortage
            no_action = sum(
                item.required_volume.value
                for item in plan.fingerprint_inputs.optimisation_input.demands
            )
            difference = (
                f"Modeled residual shortage {shortage.value:.3f} {shortage.unit} "
                f"versus {no_action:.3f} ktonne no-action procurement demand."
                if shortage
                else "No residual-shortage metric was produced."
            )
            drivers = [
                "supplier capacity",
                "delivery timing",
                "route risk",
                "refinery compatibility",
                "supplier and corridor concentration",
            ]
        else:
            reserve_result = plan.result
            reserve_objective = reserve_result.objective
            rejected = [
                ExplanationAlternative(
                    subject_id=item.site_id,
                    reason_codes=[item.reason.value],
                    explanation=item.explanation,
                )
                for item in reserve_result.rejected_options
            ]
            constraints = [
                ExplanationConstraint(
                    name=item,
                    satisfied=bool(
                        reserve_result.constraints and reserve_result.constraints.feasible
                    ),
                    detail="Independently checked reserve constraint.",
                )
                for item in (
                    reserve_result.constraints.checked if reserve_result.constraints else []
                )
            ]
            rationale = [
                f"Modeled reserve guidance {item.action_id} coordinates site "
                f"{item.site_id} with refinery {item.refinery_id}; no release is executed."
                for item in reserve_result.actions
            ]
            components = reserve_objective.weighted_contributions if reserve_objective else {}
            weights = reserve_objective.weights if reserve_objective else {}
            shortage = reserve_result.residual_shortage
            no_action = sum(item.required_volume.value for item in plan.input.demands)
            difference = (
                f"Modeled residual shortage {shortage.value:.3f} {shortage.unit} "
                f"versus {no_action:.3f} ktonne before reserve guidance."
                if shortage
                else "No residual-shortage metric was produced."
            )
            drivers = [
                "assumed opening inventory",
                "minimum reserve floor",
                "draw rate",
                "transit time",
                "refinery receipt capacity",
            ]
        summary = (
            "Audited deterministic decision-support explanation; all important "
            "figures remain traceable."
            if audit.usable
            else "BLOCKED: this plan failed evidence audit and cannot be presented as usable."
        )
        claim_failures = blocked_claim_codes(summary + " " + difference + " " + " ".join(rationale))
        if claim_failures:
            raise AuditDomainError("EXPLANATION_CLAIM_BLOCKED", ", ".join(claim_failures))
        evidence_refs, assumption_refs = _references(plan)
        return PlanExplanation(
            plan_id=plan_id,
            plan_kind=kind,
            audit_id=audit.audit_id,
            audit_fingerprint=audit.audit_fingerprint,
            usable=audit.usable,
            blocked_reasons=[f"{item.code.value}: {item.message}" for item in audit.failures],
            summary=summary,
            hard_constraints=constraints,
            objective_components=dict(components),
            profile_weights=dict(weights),
            primary_tradeoffs=[
                "Cost, delivery time, concentration, route exposure, and residual "
                "shortage are weighted by the selected profile."
            ],
            allocation_rationale=rationale,
            rejected_alternatives=rejected,
            evidence_ids=[item.evidence_id for item in evidence_refs],
            assumption_ids=[item.assumption_id for item in assumption_refs],
            sensitivity_drivers=drivers,
            residual_shortage=shortage.value if shortage else None,
            residual_shortage_unit=shortage.unit if shortage else None,
            difference_from_no_action=difference,
            model_version=audit.model_version,
            solver_version=audit.solver_version,
            checker_version=audit.checker_version,
            auditor_version=audit.auditor_version,
            generated_at=datetime.now(UTC),
        )

    async def lifecycle(self, plan_id: UUID) -> PlanGovernanceState:
        await self._plan(plan_id)
        records = await self.repository.records(plan_id)
        audit = await self.audit_plan(plan_id)
        state = current_state(records)
        warning = (
            "This plan has been superseded and must not be used."
            if state is PlanReviewState.SUPERSEDED
            else None
        )
        return PlanGovernanceState(
            plan_id=plan_id,
            state=state,
            records=records,
            latest_audit=audit,
            superseded_warning=warning,
        )

    async def act(
        self,
        plan_id: UUID,
        payload: PlanLifecycleRequest,
        *,
        action: LifecycleAction,
        actor_id: str,
        actor_role: GovernanceRole,
        idempotency_key: str,
        superseding_plan_id: UUID | None = None,
    ) -> PlanLifecycleRecord:
        plan, kind = await self._plan(plan_id)
        audit = await self.audit_plan(plan_id)
        self._authorize(action, actor_role)
        if payload.plan_fingerprint != _plan_fingerprint(plan):
            raise AuditDomainError(
                "STALE_PLAN_FINGERPRINT", "Plan fingerprint changed after review."
            )
        if payload.assumption_fingerprint != audit.fingerprints.assumptions:
            raise AuditDomainError(
                "STALE_ASSUMPTION_FINGERPRINT", "Assumption fingerprint changed after review."
            )
        if payload.audit_fingerprint != audit.audit_fingerprint:
            raise AuditDomainError(
                "STALE_AUDIT_FINGERPRINT", "Audit fingerprint changed after review."
            )
        if (
            action in {LifecycleAction.SUBMIT_FOR_REVIEW, LifecycleAction.APPROVE}
            and not audit.approval_allowed
        ):
            raise AuditDomainError(
                "AUDIT_FAILED", "A failed Evidence Audit blocks review submission and approval."
            )
        if action is LifecycleAction.SUPERSEDE:
            if superseding_plan_id is None or superseding_plan_id == plan_id:
                raise AuditDomainError(
                    "SUPERSEDING_PLAN_INVALID",
                    "A different existing plan is required.",
                    status_code=422,
                )
            await self._plan(superseding_plan_id)
        idempotency_fingerprint = canonical_hash({"key": idempotency_key, "plan_id": str(plan_id)})

        def make(records: list[PlanLifecycleRecord]) -> PlanLifecycleRecord:
            previous = current_state(records)
            target = _transition(previous, action)
            return PlanLifecycleRecord(
                record_id=uuid5(
                    NAMESPACE_URL, f"urn:sanjiv:plan-lifecycle:{idempotency_fingerprint}"
                ),
                plan_id=plan_id,
                plan_kind=kind,
                action=action,
                previous_state=previous,
                state=target,
                actor_id=actor_id,
                actor_role=actor_role,
                occurred_at=datetime.now(UTC),
                plan_fingerprint=payload.plan_fingerprint,
                assumption_fingerprint=payload.assumption_fingerprint,
                audit_fingerprint=payload.audit_fingerprint,
                comment=payload.comment,
                superseding_plan_id=superseding_plan_id,
                idempotency_fingerprint=idempotency_fingerprint,
            )

        try:
            record = await self.repository.append_record(make, plan_id, idempotency_fingerprint)
            if (
                record.action is not action
                or record.actor_id != actor_id
                or record.plan_fingerprint != payload.plan_fingerprint
                or record.assumption_fingerprint != payload.assumption_fingerprint
                or record.audit_fingerprint != payload.audit_fingerprint
                or record.comment != payload.comment
                or record.superseding_plan_id != superseding_plan_id
            ):
                raise AuditDomainError(
                    "IDEMPOTENCY_KEY_CONFLICT",
                    "Idempotency key was already used with a different lifecycle request.",
                )
            return record
        except ValueError as exc:
            raise AuditDomainError("INVALID_LIFECYCLE_TRANSITION", str(exc)) from exc

    async def evidence(self, evidence_id: UUID) -> EvidenceRecord:
        snapshot = self.scenario_service.twin_service.current()
        item = next((value for value in snapshot.evidence_records if value.id == evidence_id), None)
        if item is None:
            raise AuditDomainError(
                "EVIDENCE_NOT_FOUND", "Evidence record not found.", status_code=404
            )
        return item

    async def assumptions(self, plan_id: UUID) -> list[Assumption]:
        plan, kind = await self._plan(plan_id)
        _, assumptions = await self._records(plan, kind)
        wanted = {item.assumption_id for item in _references(plan)[1]}
        return [item for item in assumptions if item.id in wanted]

    async def _plan(self, plan_id: UUID) -> tuple[Plan, PlanKind]:
        procurement = await self.procurement_service.repository.plan(plan_id)
        if procurement is not None:
            return procurement, PlanKind.PROCUREMENT
        reserve = await self.reserve_service.repository.plan(plan_id)
        if reserve is not None:
            return reserve, PlanKind.RESERVE
        raise AuditDomainError("PLAN_NOT_FOUND", "Plan not found.", status_code=404)

    async def _records(
        self, plan: Plan, kind: PlanKind
    ) -> tuple[list[EvidenceRecord], list[Assumption]]:
        snapshot_id = _snapshot_id(plan)
        snapshot = self.scenario_service.twin_service.get(snapshot_id)
        if snapshot is None:
            return [], []
        evidence = list(snapshot.evidence_records)
        assumptions = list(snapshot.assumptions)
        starts_at = _starts_at(plan)
        commercial = load_commercial_fixture(snapshot, at=starts_at)
        assumptions.extend(commercial.assumptions.values())
        try:
            confirmed = await self.scenario_service.confirmed(_scenario_id(plan))
            assumptions.extend(confirmed.candidate.parameters.assumptions)
        except ScenarioDomainError:
            pass
        if kind is PlanKind.RESERVE:
            assumptions.extend(load_reserve_fixture_assumptions(at=starts_at))
        return evidence, list({item.id: item for item in assumptions}.values())

    @staticmethod
    def _authorize(action: LifecycleAction, role: GovernanceRole) -> None:
        allowed = {
            LifecycleAction.SUBMIT_FOR_REVIEW: {
                GovernanceRole.OPERATOR,
                GovernanceRole.REVIEWER,
                GovernanceRole.ADMINISTRATOR,
            },
            LifecycleAction.REVIEW: {GovernanceRole.REVIEWER, GovernanceRole.ADMINISTRATOR},
            LifecycleAction.APPROVE: {GovernanceRole.APPROVER, GovernanceRole.ADMINISTRATOR},
            LifecycleAction.REJECT: {GovernanceRole.APPROVER, GovernanceRole.ADMINISTRATOR},
            LifecycleAction.SUPERSEDE: {GovernanceRole.APPROVER, GovernanceRole.ADMINISTRATOR},
        }
        if role not in allowed[action]:
            raise AuditDomainError(
                "ROLE_FORBIDDEN",
                f"Role {role.value} cannot perform {action.value}.",
                status_code=403,
            )


def _failure(code: AuditFailureCode, path: str, message: str) -> AuditFailure:
    return AuditFailure(code=code, path=path, message=message)


def _references(plan: Plan) -> tuple[list[Any], list[Any]]:
    if isinstance(plan, ProcurementPlan):
        return plan.fingerprint_inputs.evidence, plan.fingerprint_inputs.assumptions
    return plan.input.provenance.evidence, plan.input.provenance.assumptions


def _scenario_id(plan: Plan) -> UUID:
    return (
        plan.fingerprint_inputs.confirmed_scenario.scenario_id
        if isinstance(plan, ProcurementPlan)
        else plan.input.provenance.confirmed_scenario.scenario_id
    )


def _snapshot_id(plan: Plan) -> UUID:
    return (
        plan.fingerprint_inputs.twin_snapshot.snapshot_id
        if isinstance(plan, ProcurementPlan)
        else plan.input.provenance.twin_snapshot.snapshot_id
    )


def _starts_at(plan: Plan) -> datetime:
    if isinstance(plan, ProcurementPlan):
        return min(
            item.interval_start for item in plan.fingerprint_inputs.optimisation_input.demands
        )
    return plan.input.starts_at


def _plan_fingerprint(plan: Plan) -> str:
    return plan.plan_fingerprint


def _fingerprints(
    plan: Plan, evidence_refs: list[Any], assumption_refs: list[Any]
) -> AuditFingerprintSet:
    if isinstance(plan, ProcurementPlan):
        procurement_provenance = plan.fingerprint_inputs.optimisation_input.provenance
        return AuditFingerprintSet(
            plan=plan.plan_fingerprint,
            assumptions=canonical_hash([item.model_dump(mode="json") for item in assumption_refs]),
            evidence=canonical_hash([item.model_dump(mode="json") for item in evidence_refs]),
            scenario=procurement_provenance.confirmed_scenario.scenario_fingerprint,
            simulation=procurement_provenance.simulation_run.simulation_fingerprint,
            twin=procurement_provenance.twin_snapshot.fingerprint,
            procurement=plan.fingerprint_inputs.optimisation_input_fingerprint,
        )
    reserve_provenance = plan.input.provenance
    return AuditFingerprintSet(
        plan=plan.plan_fingerprint,
        assumptions=canonical_hash([item.model_dump(mode="json") for item in assumption_refs]),
        evidence=canonical_hash([item.model_dump(mode="json") for item in evidence_refs]),
        scenario=reserve_provenance.confirmed_scenario.scenario_fingerprint,
        simulation=reserve_provenance.simulation_run.simulation_fingerprint,
        twin=reserve_provenance.twin_snapshot.fingerprint,
        procurement=reserve_provenance.procurement_plan_fingerprint,
        reserve=plan.input_fingerprint,
    )


def _solver_details(plan: Plan) -> tuple[str, str, str, str, bool, bool, bool]:
    if isinstance(plan, ProcurementPlan):
        procurement_result = plan.solver_result
        procurement_check = procurement_result.independent_check
        return (
            procurement_result.status.value,
            procurement_result.metadata.solver_version,
            procurement_result.metadata.model_version,
            procurement_check.checker_version if procurement_check else "missing",
            bool(procurement_check and procurement_check.passed),
            bool(procurement_check and procurement_check.sanctions_exclusion_passed),
            bool(procurement_check and procurement_check.compatibility_exclusion_passed),
        )
    reserve_result = plan.result
    reserve_check = reserve_result.checker
    return (
        reserve_result.status.value,
        reserve_result.metadata.solver_version,
        reserve_result.metadata.model_version,
        reserve_check.checker_version if reserve_check else "missing",
        bool(reserve_check and reserve_check.passed),
        bool(reserve_check and reserve_check.passed),
        bool(reserve_check and reserve_check.passed),
    )


def _transition(current: PlanReviewState, action: LifecycleAction) -> PlanReviewState:
    allowed: dict[tuple[PlanReviewState, LifecycleAction], PlanReviewState] = {
        (
            PlanReviewState.RECOMMENDED,
            LifecycleAction.SUBMIT_FOR_REVIEW,
        ): PlanReviewState.UNDER_REVIEW,
        (PlanReviewState.UNDER_REVIEW, LifecycleAction.REVIEW): PlanReviewState.UNDER_REVIEW,
        (PlanReviewState.UNDER_REVIEW, LifecycleAction.APPROVE): PlanReviewState.APPROVED,
        (PlanReviewState.UNDER_REVIEW, LifecycleAction.REJECT): PlanReviewState.REJECTED,
        (PlanReviewState.APPROVED, LifecycleAction.SUPERSEDE): PlanReviewState.SUPERSEDED,
    }
    target = allowed.get((current, action))
    if target is None:
        raise ValueError(f"{action.value} is not allowed from {current.value}")
    return target
