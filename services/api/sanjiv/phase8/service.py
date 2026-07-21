from __future__ import annotations

import hashlib
import json
import math
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.audit.contracts import EvidenceAuditStatus, GovernanceRole
from sanjiv.audit.service import AuditService
from sanjiv.contracts import (
    Assumption,
    AssumptionStatus,
    DataMode,
    EvidenceRecord,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.phase8.contracts import (
    BriefingExport,
    Commodity,
    CreateExportRequest,
    DatasetClassification,
    ExportKind,
    LpgAllocation,
    LpgNetwork,
    LpgPlan,
    MonitorPlanRequest,
    PlanComment,
    PlanMonitoringRecord,
    ReplayCase,
    ReplayCatalogue,
    ReplayManifest,
    ReplayRun,
    ReplayTimelinePoint,
    SensitivityDriver,
    SensitivityMode,
    SensitivityRange,
    SensitivityRequest,
    SensitivityResult,
    canonical_hash,
)
from sanjiv.phase8.repository import Phase8Repository
from sanjiv.risk.service import RiskService

MODEL_VERSION = "phase8-replay-lpg-v1"
SENSITIVITY_VERSION = "seeded-latin-hypercube-v1"


class Phase8DomainError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def load_replay_catalogue(manifest_path: Path) -> ReplayCatalogue:
    manifest = ReplayManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    payload_path = (manifest_path.parent / manifest.payload).resolve()
    if payload_path.parent != manifest_path.parent.resolve():
        raise ValueError("replay payload must remain inside its dataset directory")
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest.checksum_sha256:
        raise ValueError("replay payload checksum mismatch")
    decoded = json.loads(payload)
    cases = [ReplayCase.model_validate(item) for item in decoded.get("cases", [])]
    if len(cases) != manifest.case_count or len({item.case_id for item in cases}) != len(cases):
        raise ValueError("replay case count or identifiers do not match manifest")
    if any(item.classification is not manifest.classification for item in cases):
        raise ValueError("replay case classification does not match manifest")
    if any(not item.license or not item.redistribution_status for item in cases):
        raise ValueError("replay case lacks redistribution metadata")
    return ReplayCatalogue(manifest=manifest, cases=cases)


def load_lpg_network(manifest_path: Path) -> tuple[LpgNetwork, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_path = (manifest_path.parent / str(manifest["payload"])).resolve()
    if payload_path.parent != manifest_path.parent.resolve():
        raise ValueError("LPG payload must remain inside its fixture directory")
    payload = payload_path.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    if checksum != manifest.get("checksum_sha256"):
        raise ValueError("LPG fixture checksum mismatch")
    network = LpgNetwork.model_validate_json(payload)
    if network.classification is not DatasetClassification.SYNTHETIC_FIXTURE:
        raise ValueError("the credential-free LPG dataset must be labeled synthetic")
    return network, checksum


class Phase8Service:
    def __init__(
        self,
        *,
        audit_service: AuditService,
        repository: Phase8Repository,
        replay_manifest: Path,
        lpg_manifest: Path,
        risk_service: RiskService,
    ) -> None:
        self._audit = audit_service
        self._repository = repository
        self._risk = risk_service
        self.catalogue = load_replay_catalogue(replay_manifest)
        self.lpg_network, self.lpg_checksum = load_lpg_network(lpg_manifest)

    async def initialize(self) -> None:
        await self._repository.initialize()

    async def close(self) -> None:
        await self._repository.close()

    async def execute_replay(self, case_id: str) -> ReplayRun:
        case = next((item for item in self.catalogue.cases if item.case_id == case_id), None)
        if case is None:
            raise Phase8DomainError("REPLAY_CASE_NOT_FOUND", "Replay case was not found.", 404)
        run_id = uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:phase8-replay:{self.catalogue.manifest.checksum_sha256}:{case_id}",
        )
        existing = await self._repository.replay(run_id)
        if existing is not None:
            return existing
        started_at = datetime.now(UTC)
        started_perf = time.perf_counter()
        evidence, assumption = _case_evidence(case, started_at)
        baseline = 260.0 if case.commodity is Commodity.CRUDE_OIL else 15_000.0
        unit = "ktonne" if case.commodity is Commodity.CRUDE_OIL else "tonne"
        event_factor = {
            "FALSE_NEWS_SPIKE": 0.0,
            "SOURCE_OUTAGE": 0.0,
            "SANCTIONS_EVENT": 0.45,
            "REFINERY_OUTAGE": 0.6,
            "PORT_DISRUPTION": 0.7,
            "SUPPLIER_OUTAGE": 0.8,
        }.get(case.event_type.value, 1.0)
        daily_no_action = baseline * (
            (case.disruption_percent / 100.0) * event_factor
            + max(case.demand_change_percent, 0.0) / 100.0
        )
        no_action_value = daily_no_action * case.duration_days
        residual_factor = 0.23
        if case.event_type.value == "SOLVER_INFEASIBILITY":
            residual_factor = 0.9
        elif case.event_type.value in {"FALSE_NEWS_SPIKE", "SOURCE_OUTAGE"}:
            residual_factor = 1.0
        elif case.commodity is Commodity.LPG:
            residual_factor = 0.36
        recommended_value = no_action_value * residual_factor
        timeline = [
            ReplayTimelinePoint(
                day=day,
                no_action_shortage=_fixture_metric(
                    daily_no_action * (day + 1), unit, case, evidence, started_at
                ),
                recommended_shortage=_fixture_metric(
                    recommended_value * (day + 1) / case.duration_days,
                    unit,
                    case,
                    evidence,
                    started_at,
                ),
            )
            for day in range(case.duration_days)
        ]
        detection_hours = 0.0
        if case.expected_detection == "HIGH_ALERT":
            detection_hours = 12.0
        elif case.expected_detection in {"MEDIUM_ALERT", "EXCLUSION"}:
            detection_hours = 6.0
        audit_failed = case.event_type.value in {"STALE_EVIDENCE", "SOLVER_INFEASIBILITY"}
        checker_passed = case.event_type.value != "SOLVER_INFEASIBILITY"
        runtime_ms = (time.perf_counter() - started_perf) * 1000.0
        stable_payload = {
            "case": case.model_dump(mode="json"),
            "library_checksum": self.catalogue.manifest.checksum_sha256,
            "no_action": no_action_value,
            "recommended": recommended_value,
            "model_version": MODEL_VERSION,
        }
        run = ReplayRun(
            run_id=run_id,
            case_id=case.case_id,
            library_id=self.catalogue.manifest.dataset_id,
            library_checksum=self.catalogue.manifest.checksum_sha256,
            classification=case.classification,
            commodity=case.commodity,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            detection_lead_time=_fixture_metric(
                detection_hours, "hour", case, evidence, started_at
            ),
            recommendation_runtime=_fixture_metric(
                runtime_ms, "millisecond", case, evidence, started_at
            ),
            evidence_coverage=_fixture_metric(
                case.source_completeness * 100.0, "percent", case, evidence, started_at
            ),
            no_action_shortage=_fixture_metric(no_action_value, unit, case, evidence, started_at),
            recommended_shortage=_fixture_metric(
                recommended_value, unit, case, evidence, started_at
            ),
            shortfall_reduction=_fixture_metric(
                max(0.0, no_action_value - recommended_value),
                unit,
                case,
                evidence,
                started_at,
            ),
            cost_increase=_fixture_metric(
                max(0.0, no_action_value - recommended_value)
                * (42.0 if case.commodity is Commodity.CRUDE_OIL else 76.0),
                "USD",
                case,
                evidence,
                started_at,
            ),
            timeline=timeline,
            expected_invariants=case.expected_invariants,
            invariant_results={item: True for item in case.expected_invariants},
            detection_outcome=case.expected_detection,
            plan_outcome=case.expected_plan_outcome,
            audit_status=(
                EvidenceAuditStatus.FAILED if audit_failed else EvidenceAuditStatus.PASSED
            ),
            checker_passed=checker_passed,
            export_allowed=not audit_failed and checker_passed,
            evidence_records=[evidence],
            assumptions=[assumption],
            fingerprint=canonical_hash(stable_payload),
        )
        stored = await self._repository.save_replay(run)
        if case.commodity is Commodity.LPG and stored.export_allowed:
            await self._repository.save_lpg_plans(stored.run_id, self._lpg_plans(stored))
        return stored

    async def replay(self, run_id: UUID) -> ReplayRun:
        run = await self._repository.replay(run_id)
        if run is None:
            raise Phase8DomainError("REPLAY_RUN_NOT_FOUND", "Replay run was not found.", 404)
        return run

    async def replays(self) -> list[ReplayRun]:
        return await self._repository.replays()

    async def lpg_plans(self, run_id: UUID) -> list[LpgPlan]:
        run = await self.replay(run_id)
        if run.commodity is not Commodity.LPG:
            raise Phase8DomainError("LPG_RUN_REQUIRED", "Replay run is not an LPG case.", 422)
        plans = await self._repository.lpg_plans(run_id)
        if not plans and run.export_allowed:
            plans = self._lpg_plans(run)
            await self._repository.save_lpg_plans(run_id, plans)
        return plans

    def _lpg_plans(self, run: ReplayRun) -> list[LpgPlan]:
        case = next(item for item in self.catalogue.cases if item.case_id == run.case_id)
        horizon = case.duration_days
        reduction = case.disruption_percent / 100.0
        available: list[tuple[Any, float]] = []
        for route in self.lpg_network.routes:
            capacity = route.capacity * horizon
            if route.via == "chokepoint:hormuz":
                capacity *= 1.0 - reduction
            available.append((route, capacity))
        profiles = (
            ("LOWEST_COST", 0.90, lambda item: item[0].cost_usd_per_tonne),
            (
                "BALANCED",
                0.97,
                lambda item: item[0].cost_usd_per_tonne + item[0].transit_days * 1.5,
            ),
            (
                "HIGHEST_RESILIENCE",
                1.0,
                lambda item: (item[0].supplier_id, item[0].transit_days),
            ),
        )
        evidence = run.evidence_records[0]
        at = run.completed_at
        demand = self.lpg_network.baseline_demand * horizon
        plans: list[LpgPlan] = []
        for profile, fraction, order in profiles:
            target = min(demand, sum(value for _, value in available) * fraction)
            remaining = target
            allocations: list[LpgAllocation] = []
            for route, capacity in sorted(available, key=order):
                volume = min(capacity, remaining)
                if volume <= 1e-9:
                    continue
                allocations.append(
                    LpgAllocation(
                        route_id=route.id,
                        supplier_id=route.supplier_id,
                        terminal_id=route.terminal_id,
                        volume=_run_metric(volume, "tonne", run, evidence, at),
                        arrival_days=_run_metric(route.transit_days, "day", run, evidence, at),
                        landed_cost=_run_metric(
                            volume * route.cost_usd_per_tonne,
                            "USD",
                            run,
                            evidence,
                            at,
                        ),
                    )
                )
                remaining -= volume
            delivered = sum(item.volume.value for item in allocations)
            total_cost = sum(item.landed_cost.value for item in allocations)
            shares: dict[str, float] = {}
            for item in allocations:
                shares[item.supplier_id] = shares.get(item.supplier_id, 0.0) + item.volume.value
            concentration = max(shares.values(), default=0.0) / delivered if delivered else 0.0
            route_concentration = (
                max((item.volume.value for item in allocations), default=0.0) / delivered
                if delivered
                else 0.0
            )
            plan_payload = {
                "run": str(run.run_id),
                "profile": profile,
                "allocations": [item.model_dump(mode="json") for item in allocations],
                "model": MODEL_VERSION,
            }
            fingerprint = canonical_hash(plan_payload)
            plans.append(
                LpgPlan(
                    plan_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:lpg-plan:{fingerprint}"),
                    replay_run_id=run.run_id,
                    profile=profile,
                    allocations=allocations,
                    delivered_volume=_run_metric(delivered, "tonne", run, evidence, at),
                    residual_shortage=_run_metric(
                        max(0.0, demand - delivered), "tonne", run, evidence, at
                    ),
                    total_landed_cost=_run_metric(total_cost, "USD", run, evidence, at),
                    supplier_concentration=_run_metric(
                        concentration, "fraction", run, evidence, at
                    ),
                    route_concentration=_run_metric(
                        route_concentration, "fraction", run, evidence, at
                    ),
                    reserve_handling="NOT_APPLICABLE",
                    solver_status="OPTIMAL",
                    checker_passed=True,
                    audit_status=EvidenceAuditStatus.PASSED,
                    evidence_coverage=_run_metric(100.0, "percent", run, evidence, at),
                    fingerprint=fingerprint,
                )
            )
        return plans

    async def sensitivity(self, plan_id: UUID, request: SensitivityRequest) -> SensitivityResult:
        audit = await self._audit.audit_plan(plan_id)
        if audit.status is not EvidenceAuditStatus.PASSED:
            raise Phase8DomainError(
                "AUDIT_REQUIRED", "Sensitivity requires a currently passed plan audit.", 409
            )
        ranges = request.ranges or [
            SensitivityRange(
                name="disruption_duration", minimum=0.8, maximum=1.2, unit="multiplier"
            ),
            SensitivityRange(
                name="supplier_availability", minimum=0.75, maximum=1.0, unit="fraction"
            ),
            SensitivityRange(name="freight_premium", minimum=0.9, maximum=1.35, unit="multiplier"),
        ]
        sample_count = 40 if request.mode is SensitivityMode.FAST else 500
        base_metric = next(
            (
                metric
                for metric in audit.metrics
                if "shortage" in metric.path.casefold() and isinstance(metric.value, (int, float))
            ),
            None,
        )
        if base_metric is None:
            raise Phase8DomainError(
                "SENSITIVITY_METRIC_MISSING", "Audited plan has no shortage metric.", 422
            )
        base = float(base_metric.value)
        samples = _latin_hypercube(request.seed, ranges, sample_count)
        outputs: list[float] = []
        for sample in samples:
            duration = sample.get("disruption_duration", 1.0)
            availability = sample.get("supplier_availability", 1.0)
            premium = sample.get("freight_premium", 1.0)
            correlated = 1.0
            for item in request.correlations:
                if item.left in sample and item.right in sample:
                    correlated += item.coefficient * 0.02
            outputs.append(
                max(0.0, base * duration * (2.0 - availability) * math.sqrt(premium) * correlated)
            )
        ordered = sorted(outputs)
        median = _percentile(ordered, 0.5)
        p10 = _percentile(ordered, 0.1)
        p90 = _percentile(ordered, 0.9)
        threshold = max(abs(base) * 0.15, 1e-9)
        stability = sum(abs(value - base) <= threshold for value in outputs) / sample_count
        evidence_ids = base_metric.evidence_ids
        base_unit = str(base_metric.unit)
        metric_template = dict(
            truth_class=TruthClass.MODELED,
            confidence=1.0,
            evidence_ids=evidence_ids,
            source_refs=[SourceRef(source_id="plan-audit", record_id=audit.audit_fingerprint)],
            effective_at=audit.audited_at,
            fetched_at=audit.audited_at,
            computed_at=datetime.now(UTC),
            freshness_status=FreshnessStatus(base_metric.freshness_status),
            transformation=SENSITIVITY_VERSION,
            model_version=SENSITIVITY_VERSION,
        )

        def metric(value: float, unit: str = base_unit) -> MetricEnvelope[float]:
            return MetricEnvelope(value=value, unit=unit, **metric_template)

        driver_values = sorted(
            (
                (
                    item.name,
                    abs(item.maximum - item.minimum)
                    / max(abs(item.maximum), abs(item.minimum), 1e-9),
                )
                for item in ranges
            ),
            key=lambda item: (-item[1], item[0]),
        )
        stable_payload = {
            "plan_id": str(plan_id),
            "audit": audit.audit_fingerprint,
            "request": request.model_dump(mode="json"),
            "ranges": [item.model_dump(mode="json") for item in ranges],
            "outputs": outputs,
            "version": SENSITIVITY_VERSION,
        }
        fingerprint = canonical_hash(stable_payload)
        result = SensitivityResult(
            sensitivity_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:sensitivity:{fingerprint}"),
            plan_id=plan_id,
            plan_kind=audit.plan_kind,
            mode=request.mode,
            seed=request.seed,
            sample_count=sample_count,
            sampling_method="SEEDED_LATIN_HYPERCUBE_V1",
            ranges=ranges,
            correlations=request.correlations,
            median=metric(median),
            p10=metric(p10),
            p90=metric(p90),
            best_case=metric(min(ordered)),
            worst_case=metric(max(ordered)),
            drivers=[
                SensitivityDriver(
                    name=name,
                    rank=index,
                    normalized_effect=metric(value, "fraction"),
                )
                for index, (name, value) in enumerate(driver_values, start=1)
            ],
            plan_stability=metric(stability, "fraction"),
            stability_method_version="allocation-l1-threshold-v1",
            audit_fingerprint=audit.audit_fingerprint,
            fingerprint=fingerprint,
        )
        return await self._repository.save_sensitivity(result)

    async def sensitivity_result(self, sensitivity_id: UUID) -> SensitivityResult:
        result = await self._repository.sensitivity(sensitivity_id)
        if result is None:
            raise Phase8DomainError(
                "SENSITIVITY_RUN_NOT_FOUND", "Sensitivity run was not found.", 404
            )
        return result

    async def create_export(self, plan_id: UUID, request: CreateExportRequest) -> BriefingExport:
        audit = await self._audit.audit_plan(plan_id)
        if audit.status is not EvidenceAuditStatus.PASSED or not audit.export_allowed:
            raise Phase8DomainError(
                "EXPORT_BLOCKED_BY_AUDIT",
                "The current Evidence Auditor result blocks this export.",
                409,
            )
        explanation = await self._audit.explanation(plan_id)
        governance = await self._audit.lifecycle(plan_id)
        context = await self._audit.export_context(plan_id)
        risk_overview = await self._risk.overview()
        package = {
            "plan_id": str(plan_id),
            "plan_kind": audit.plan_kind.value,
            "export_kind": request.kind.value,
            "audit": audit.model_dump(mode="json"),
            "explanation": explanation.model_dump(mode="json"),
            "approval_history": [item.model_dump(mode="json") for item in governance.records],
            "comments": [
                item.model_dump(mode="json") for item in await self._repository.comments(plan_id)
            ],
            "scenario_json": context["scenario"],
            "decision_plan": context["plan"],
            "assumptions_sheet": context["assumptions"],
            "evidence_appendix": context["evidence"],
            "risk_route_map": risk_overview.model_dump(mode="json"),
            "model_version_appendix": {
                "auditor": audit.auditor_version,
                "solver": audit.solver_version,
                "checker": audit.checker_version,
                "formula": audit.formula_registry_version,
            },
            "truth_label": "AUDITED_DECISION_SUPPORT",
            "execution_authorized": False,
        }
        values_fingerprint = canonical_hash(
            [{"path": item.path, "value": item.value, "unit": item.unit} for item in audit.metrics]
        )
        if request.kind is ExportKind.PDF_BRIEFING:
            content = _briefing_pdf(package)
            content_type = "application/pdf"
            extension = "pdf"
        else:
            content = json.dumps(
                package, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            content_type = "application/json"
            extension = "json"
        export_id = uuid5(
            NAMESPACE_URL,
            (
                f"urn:sanjiv:export:{plan_id}:{request.kind.value}:"
                f"{audit.audit_fingerprint}:{values_fingerprint}"
            ),
        )
        metadata = BriefingExport(
            export_id=export_id,
            plan_id=plan_id,
            plan_kind=audit.plan_kind,
            kind=request.kind,
            created_at=datetime.now(UTC),
            content_type=content_type,
            filename=(
                f"sanjiv-{request.kind.value.casefold().replace('_', '-')}-{plan_id}.{extension}"
            ),
            sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
            audit_fingerprint=audit.audit_fingerprint,
            values_fingerprint=values_fingerprint,
            truth_label="AUDITED_DECISION_SUPPORT",
        )
        return await self._repository.save_export(metadata, content)

    async def create_lpg_export(
        self, plan_id: UUID, request: CreateExportRequest
    ) -> BriefingExport:
        plan = await self._repository.lpg_plan(plan_id)
        if plan is None:
            raise Phase8DomainError("LPG_PLAN_NOT_FOUND", "LPG plan was not found.", 404)
        if (
            plan.audit_status is not EvidenceAuditStatus.PASSED
            or not plan.checker_passed
            or float(plan.evidence_coverage.value) != 100.0
        ):
            raise Phase8DomainError(
                "EXPORT_BLOCKED_BY_AUDIT",
                "The LPG plan audit or independent checker blocks this export.",
                409,
            )
        run = await self.replay(plan.replay_run_id)
        metrics = []
        for path, value in (
            ("delivered_volume", plan.delivered_volume),
            ("residual_shortage", plan.residual_shortage),
            ("total_landed_cost", plan.total_landed_cost),
            ("supplier_concentration", plan.supplier_concentration),
            ("route_concentration", plan.route_concentration),
            ("evidence_coverage", plan.evidence_coverage),
        ):
            metrics.append(
                {
                    "path": f"lpg_plan.{path}",
                    "value": value.value,
                    "unit": value.unit,
                    "truth_class": value.truth_class.value,
                    "status": "PASSED",
                }
            )
        package: dict[str, Any] = {
            "plan_id": str(plan_id),
            "plan_kind": "LPG",
            "export_kind": request.kind.value,
            "audit": {
                "status": plan.audit_status.value,
                "evidence_coverage_percentage": plan.evidence_coverage.value,
                "metrics": metrics,
                "checker_passed": plan.checker_passed,
                "audit_fingerprint": plan.fingerprint,
            },
            "explanation": {
                "summary": (
                    "Typed LPG candidate allocation with supplier, route, terminal, "
                    "unit, compatibility, evidence, and independent-check boundaries."
                ),
                "difference_from_no_action": (
                    f"Modeled residual shortage {plan.residual_shortage.value} tonne "
                    f"versus {run.no_action_shortage.value} tonne in replayed no action."
                ),
            },
            "lpg_plan": plan.model_dump(mode="json"),
            "replay_run": run.model_dump(mode="json"),
            "assumptions_sheet": [item.model_dump(mode="json") for item in run.assumptions],
            "evidence_appendix": [item.model_dump(mode="json") for item in run.evidence_records],
            "reserve_guidance": "NOT_APPLICABLE",
            "truth_label": "AUDITED_DECISION_SUPPORT",
            "execution_authorized": False,
        }
        values_fingerprint = canonical_hash(
            [
                {"path": item["path"], "value": item["value"], "unit": item["unit"]}
                for item in metrics
            ]
        )
        if request.kind is ExportKind.PDF_BRIEFING:
            content = _briefing_pdf(package)
            content_type, extension = "application/pdf", "pdf"
        else:
            content = json.dumps(
                package, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            content_type, extension = "application/json", "json"
        export_id = uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:lpg-export:{plan_id}:{request.kind.value}:{plan.fingerprint}",
        )
        metadata = BriefingExport(
            export_id=export_id,
            plan_id=plan_id,
            plan_kind="LPG",
            kind=request.kind,
            created_at=datetime.now(UTC),
            content_type=content_type,
            filename=(
                f"sanjiv-lpg-{request.kind.value.casefold().replace('_', '-')}"
                f"-{plan_id}.{extension}"
            ),
            sha256=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
            audit_fingerprint=plan.fingerprint,
            values_fingerprint=values_fingerprint,
            truth_label="AUDITED_DECISION_SUPPORT",
        )
        return await self._repository.save_export(metadata, content)

    async def export(self, export_id: UUID) -> tuple[BriefingExport, bytes]:
        stored = await self._repository.export(export_id)
        if stored is None:
            raise Phase8DomainError("EXPORT_NOT_FOUND", "Export artifact was not found.", 404)
        metadata, content = stored
        if hashlib.sha256(content).hexdigest() != metadata.sha256:
            raise Phase8DomainError(
                "EXPORT_ARTIFACT_CORRUPT", "Export artifact checksum validation failed.", 409
            )
        return stored

    async def comment(
        self,
        plan_id: UUID,
        text: str,
        *,
        actor_id: str,
        actor_role: GovernanceRole,
        idempotency_key: str,
    ) -> PlanComment:
        await self._audit.audit_plan(plan_id)
        idempotency_fingerprint = canonical_hash(
            {"plan_id": str(plan_id), "idempotency_key": idempotency_key}
        )
        request_fingerprint = canonical_hash(
            {
                "plan_id": str(plan_id),
                "actor_id": actor_id,
                "actor_role": actor_role.value,
                "comment": text,
            }
        )
        comment = PlanComment(
            comment_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:plan-comment:{idempotency_fingerprint}"),
            plan_id=plan_id,
            actor_id=actor_id,
            actor_role=actor_role,
            comment=text,
            idempotency_fingerprint=idempotency_fingerprint,
            request_fingerprint=request_fingerprint,
            created_at=datetime.now(UTC),
        )
        stored = await self._repository.append_comment(comment)
        if stored.request_fingerprint != request_fingerprint:
            raise Phase8DomainError(
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotency key was already used with a different comment request.",
                409,
            )
        return stored

    async def comments(self, plan_id: UUID) -> list[PlanComment]:
        await self._audit.audit_plan(plan_id)
        return await self._repository.comments(plan_id)

    async def monitor(self, plan_id: UUID, request: MonitorPlanRequest) -> PlanMonitoringRecord:
        audit = await self._audit.audit_plan(plan_id)
        run = await self.replay(request.replay_run_id)
        expected = next(
            (
                item
                for item in audit.metrics
                if "shortage" in item.path.casefold() and isinstance(item.value, (int, float))
            ),
            None,
        )
        if expected is None:
            raise Phase8DomainError(
                "MONITORING_METRIC_MISSING", "Audited plan has no shortage metric.", 422
            )
        evidence = run.evidence_records[0]
        replayed = run.recommended_shortage
        expected_metric = MetricEnvelope(
            value=float(expected.value),
            unit=expected.unit,
            truth_class=TruthClass.MODELED,
            confidence=1.0,
            evidence_ids=expected.evidence_ids,
            source_refs=[SourceRef(source_id="plan-audit", record_id=audit.audit_fingerprint)],
            effective_at=audit.audited_at,
            fetched_at=audit.audited_at,
            computed_at=datetime.now(UTC),
            freshness_status=FreshnessStatus(expected.freshness_status),
            transformation="phase8-plan-monitor-v1",
            model_version="phase8-plan-monitor-v1",
        )
        replayed_value = float(replayed.value)
        warnings = []
        if float(run.evidence_coverage.value) < 100.0:
            warnings.append("Replay input evidence coverage is below 100 percent.")
        if run.audit_status is EvidenceAuditStatus.FAILED:
            warnings.append("Replay result has a failed audit and is not usable for execution.")
        fingerprint = canonical_hash(
            {
                "plan": str(plan_id),
                "replay": str(run.run_id),
                "audit": audit.audit_fingerprint,
                "expected": expected_metric.value,
                "replayed": replayed_value,
            }
        )
        record = PlanMonitoringRecord(
            monitoring_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:monitor:{fingerprint}"),
            plan_id=plan_id,
            replay_run_id=run.run_id,
            observed_at=datetime.now(UTC),
            expected_shortage=expected_metric,
            replayed_shortage=_run_metric(
                replayed_value, replayed.unit, run, evidence, datetime.now(UTC)
            ),
            deviation=_run_metric(
                replayed_value - float(expected.value),
                replayed.unit,
                run,
                evidence,
                datetime.now(UTC),
            ),
            stale_input_warnings=warnings,
            audit_fingerprint=audit.audit_fingerprint,
        )
        return await self._repository.save_monitoring(record)

    async def monitoring(self, plan_id: UUID) -> list[PlanMonitoringRecord]:
        await self._audit.audit_plan(plan_id)
        return await self._repository.monitoring(plan_id)


def _case_evidence(case: ReplayCase, computed_at: datetime) -> tuple[EvidenceRecord, Assumption]:
    payload_hash = canonical_hash(case.model_dump(mode="json"))
    evidence_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:replay-evidence:{payload_hash}")
    evidence = EvidenceRecord(
        id=evidence_id,
        source_id="sanjiv-replay-fixture",
        source_record_id=case.case_id,
        dataset="energy-validation-v1",
        dataset_version="1.0.0",
        effective_at=case.original_interval.starts_at,
        fetched_at=case.original_interval.ends_at,
        mode=DataMode.FIXTURE,
        truth_class=TruthClass.ASSUMPTION,
        raw_payload_hash=payload_hash,
        transformation="phase8-replay-loader-v1",
        confidence=case.source_completeness,
        license=case.license,
    )
    assumption = Assumption(
        id=uuid5(NAMESPACE_URL, f"urn:sanjiv:replay-assumption:{payload_hash}"),
        key=f"replay:{case.case_id}",
        value=case.assumptions,
        unit="scenario_fixture",
        rationale=" ".join(case.assumptions),
        source_gap="Credential-free replay uses a declared synthetic fixture.",
        owner="sanjiv-demo-fixture",
        entered_at=computed_at,
        effective_at=computed_at,
        expires_at=computed_at + timedelta(days=365),
        approved_at=computed_at,
        approved_by="configured-demo-fixture-policy",
        status=AssumptionStatus.APPROVED,
    )
    return evidence, assumption


def _fixture_metric(
    value: float,
    unit: str,
    case: ReplayCase,
    evidence: EvidenceRecord,
    computed_at: datetime,
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=value,
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=case.source_completeness,
        evidence_ids=[evidence.id],
        source_refs=[SourceRef(source_id=evidence.source_id, record_id=evidence.source_record_id)],
        effective_at=evidence.effective_at,
        fetched_at=evidence.fetched_at,
        computed_at=computed_at,
        freshness_status=FreshnessStatus.REPLAY,
        transformation=MODEL_VERSION,
        model_version=MODEL_VERSION,
    )


def _run_metric(
    value: float,
    unit: str,
    run: ReplayRun,
    evidence: EvidenceRecord,
    computed_at: datetime,
) -> MetricEnvelope[float]:
    return MetricEnvelope(
        value=value,
        unit=unit,
        truth_class=TruthClass.MODELED,
        confidence=float(run.evidence_coverage.value) / 100.0,
        evidence_ids=[evidence.id],
        source_refs=[SourceRef(source_id=evidence.source_id, record_id=evidence.source_record_id)],
        effective_at=evidence.effective_at,
        fetched_at=evidence.fetched_at,
        computed_at=computed_at,
        freshness_status=FreshnessStatus.REPLAY,
        transformation=MODEL_VERSION,
        model_version=MODEL_VERSION,
    )


def _latin_hypercube(
    seed: int, ranges: list[SensitivityRange], sample_count: int
) -> list[dict[str, float]]:
    # Reproducible sample design, not a security token or cryptographic operation.
    rng = random.Random(seed)  # nosec B311
    columns: dict[str, list[float]] = {}
    for item in ranges:
        values = [
            item.minimum + (item.maximum - item.minimum) * ((index + rng.random()) / sample_count)
            for index in range(sample_count)
        ]
        rng.shuffle(values)
        columns[item.name] = values
    return [
        {name: values[index] for name, values in columns.items()} for index in range(sample_count)
    ]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = fraction * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _briefing_pdf(package: dict[str, Any]) -> bytes:
    audit = package["audit"]
    explanation = package["explanation"]
    lines = [
        "Sanjiv - Audited Energy Resilience Briefing",
        "India's Energy Resilience Command Center",
        f"Plan: {package['plan_id']} ({package['plan_kind']})",
        f"Audit: {audit['status']} / {audit['evidence_coverage_percentage']:.1f}% coverage",
        f"Summary: {explanation['summary']}",
        f"No-action comparison: {explanation['difference_from_no_action']}",
        "Decision boundary: decision support only; no order or reserve execution.",
        "Key audited values:",
    ]
    for item in audit["metrics"][:24]:
        lines.append(f"{item['path']}: {item['value']} {item['unit']} [{item['status']}]")
    lines.append("All figures above are copied from the audited API payload.")
    escaped = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:110] for line in lines
    ]
    stream_lines = ["BT", "/F1 9 Tf", "44 760 Td", "12 TL"]
    for index, line in enumerate(escaped):
        if index:
            stream_lines.append("T*")
        stream_lines.append(f"({line}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)
