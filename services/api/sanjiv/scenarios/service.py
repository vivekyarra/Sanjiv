from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.contracts import AuditEvent, AuditOutcome
from sanjiv.scenarios.compiler import (
    DisabledScenarioProvider,
    ScenarioInterpretationProvider,
    compile_scenario,
)
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmedScenario,
    ConfirmScenarioRequest,
    DisruptionTargetType,
    DisruptionType,
    DurationUnit,
    ScenarioCompileResponse,
    ScenarioFormMetadata,
    ScenarioValidationResult,
    SupportedScenarioType,
)
from sanjiv.scenarios.repository import InMemoryScenarioRepository, ScenarioRepository
from sanjiv.scenarios.validator import validate_scenario
from sanjiv.simulation.contracts import (
    SimulationFailureResult,
    SimulationProgressEvent,
    SimulationRun,
    SimulationStatus,
    StartSimulationRequest,
)
from sanjiv.simulation.engine import (
    SIMULATION_MODEL_VERSION,
    run_no_action_simulation,
    simulation_fingerprint,
)
from sanjiv.twin.service import TwinService


class ScenarioDomainError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class _BoundedIdempotencyCache(OrderedDict[tuple[str, str], object]):
    def __setitem__(self, key: tuple[str, str], value: object) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > 1024:
            self.popitem(last=False)


class ScenarioService:
    def __init__(
        self,
        *,
        twin_service: TwinService,
        repository: ScenarioRepository | None = None,
        provider: ScenarioInterpretationProvider | None = None,
    ) -> None:
        self.twin_service = twin_service
        self.repository = repository or InMemoryScenarioRepository()
        self.provider = provider or DisabledScenarioProvider()
        self._idempotency = _BoundedIdempotencyCache()
        self._cancelled: set[UUID] = set()
        self._confirmation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.repository.initialize()

    async def close(self) -> None:
        await self.repository.close()

    def supported_types(self) -> list[SupportedScenarioType]:
        return [
            SupportedScenarioType(
                disruption_type=DisruptionType.CHOKEPOINT_CLOSURE,
                target_type=DisruptionTargetType.CHOKEPOINT,
                supports_full_closure=True,
                description="Full closure of a twin chokepoint.",
            ),
            SupportedScenarioType(
                disruption_type=DisruptionType.CHOKEPOINT_CAPACITY_REDUCTION,
                target_type=DisruptionTargetType.CHOKEPOINT,
                supports_full_closure=False,
                description="Partial capacity reduction at a twin chokepoint.",
            ),
            SupportedScenarioType(
                disruption_type=DisruptionType.MARITIME_ROUTE_CAPACITY_REDUCTION,
                target_type=DisruptionTargetType.ROUTE,
                supports_full_closure=True,
                description="Partial or full capacity reduction on one canonical route.",
            ),
            SupportedScenarioType(
                disruption_type=DisruptionType.SUPPLIER_VOLUME_REDUCTION,
                target_type=DisruptionTargetType.SUPPLIER,
                supports_full_closure=True,
                description="Supplier baseline-volume availability reduction.",
            ),
            SupportedScenarioType(
                disruption_type=DisruptionType.PORT_DISRUPTION,
                target_type=DisruptionTargetType.PORT,
                supports_full_closure=True,
                description="Load-port or Indian-port capacity disruption.",
            ),
            SupportedScenarioType(
                disruption_type=DisruptionType.REFINERY_THROUGHPUT_DISRUPTION,
                target_type=DisruptionTargetType.REFINERY,
                supports_full_closure=True,
                description="Refinery throughput-capacity disruption.",
            ),
        ]

    def form_metadata(self) -> ScenarioFormMetadata:
        return ScenarioFormMetadata(
            supported_types=self.supported_types(),
            duration_units=list(DurationUnit),
            duration_min_hours=1,
            duration_max_days=90,
            maximum_compound_effects=4,
            interpreter_label="Optional provider"
            if self.provider.available
            else "Deterministic parser + structured form",
            llm_provider_available=self.provider.available,
        )

    async def compile(
        self,
        request: CompileScenarioRequest,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ScenarioCompileResponse:
        cached = self._idempotency.get(("compile", idempotency_key))
        if isinstance(cached, ScenarioCompileResponse):
            return cached
        snapshot = self.twin_service.get(request.twin_snapshot_id)
        if snapshot is None:
            raise ScenarioDomainError(
                "TWIN_SNAPSHOT_MISSING",
                "The selected twin snapshot is unavailable.",
                status_code=404,
            )
        response = await compile_scenario(request, snapshot, provider=self.provider, now=now)
        if response.candidate is not None:
            await self.repository.save_candidate(response.candidate)
        if response.validation is not None:
            await self.repository.save_validation(response.validation)
        self._idempotency[("compile", idempotency_key)] = response
        return response

    async def validate(self, scenario_id: UUID) -> ScenarioValidationResult:
        candidate = await self.repository.candidate(scenario_id)
        if candidate is None:
            raise ScenarioDomainError(
                "SCENARIO_NOT_FOUND", "Scenario candidate not found.", status_code=404
            )
        snapshot = self.twin_service.get(candidate.twin_snapshot.snapshot_id)
        validation = validate_scenario(candidate, snapshot)
        await self.repository.save_validation(validation)
        return validation

    async def validation(self, scenario_id: UUID) -> ScenarioValidationResult:
        validation = await self.repository.validation(scenario_id)
        if validation is None:
            raise ScenarioDomainError(
                "VALIDATION_NOT_FOUND", "Scenario validation result not found.", status_code=404
            )
        return validation

    async def confirm(
        self,
        scenario_id: UUID,
        request: ConfirmScenarioRequest,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ConfirmedScenario:
        async with self._confirmation_lock:
            return await self._confirm_locked(
                scenario_id, request, idempotency_key=idempotency_key, now=now
            )

    async def _confirm_locked(
        self,
        scenario_id: UUID,
        request: ConfirmScenarioRequest,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> ConfirmedScenario:
        cached = self._idempotency.get(("confirm", idempotency_key))
        if isinstance(cached, ConfirmedScenario):
            return cached
        existing = await self.repository.confirmation(scenario_id)
        if existing is not None:
            self._idempotency[("confirm", idempotency_key)] = existing
            return existing
        candidate = await self.repository.candidate(scenario_id)
        validation = await self.repository.validation(scenario_id)
        if candidate is None or validation is None:
            raise ScenarioDomainError(
                "SCENARIO_NOT_VALIDATED",
                "A scenario must have a deterministic validation result before confirmation.",
                status_code=409,
            )
        confirmed_at = (now or datetime.now(UTC)).astimezone(UTC)
        snapshot = self.twin_service.get(candidate.twin_snapshot.snapshot_id)
        validation = validate_scenario(candidate, snapshot, now=confirmed_at)
        await self.repository.save_validation(validation)
        if not validation.valid:
            raise ScenarioDomainError(
                "SCENARIO_VALIDATION_FAILED",
                "A scenario with blocking validation errors cannot be confirmed.",
                status_code=409,
            )
        if validation.scenario_fingerprint != candidate.scenario_fingerprint:
            raise ScenarioDomainError(
                "SCENARIO_CHANGED",
                "Scenario inputs changed after validation and require revalidation.",
                status_code=409,
            )
        audit_id = uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:audit:scenario-confirmed:{scenario_id}:{request.confirming_identity}:{candidate.scenario_fingerprint}",
        )
        audit = AuditEvent(
            id=audit_id,
            occurred_at=confirmed_at,
            actor_id=request.confirming_identity,
            actor_type="LOCAL_DEMO_IDENTITY",
            action="SCENARIO_CONFIRMED",
            resource_type="SCENARIO",
            resource_id=str(scenario_id),
            after_hash=candidate.scenario_fingerprint,
            reason="Human confirmation of validated hypothetical disruption inputs.",
            correlation_id=uuid5(NAMESPACE_URL, f"urn:sanjiv:correlation:scenario:{scenario_id}"),
            outcome=AuditOutcome.SUCCEEDED,
        )
        confirmed = ConfirmedScenario(
            scenario_id=scenario_id,
            scenario_fingerprint=candidate.scenario_fingerprint,
            twin_snapshot=candidate.twin_snapshot,
            candidate=candidate,
            validation=validation,
            confirmed_by=request.confirming_identity,
            confirmed_at=confirmed_at,
            audit_event=audit,
        )
        await self.repository.save_audit(audit)
        await self.repository.save_confirmation(confirmed)
        self._idempotency[("confirm", idempotency_key)] = confirmed
        return confirmed

    async def confirmed(self, scenario_id: UUID) -> ConfirmedScenario:
        value = await self.repository.confirmation(scenario_id)
        if value is None:
            raise ScenarioDomainError(
                "SCENARIO_NOT_CONFIRMED", "Confirmed scenario not found.", status_code=404
            )
        return value

    async def start(
        self,
        request: StartSimulationRequest,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> SimulationRun:
        cached = self._idempotency.get(("run", idempotency_key))
        if isinstance(cached, SimulationRun):
            latest = await self.repository.run(cached.run_id)
            return latest or cached
        confirmed = await self.repository.confirmation(request.scenario_id)
        if confirmed is None:
            raise ScenarioDomainError(
                "SCENARIO_NOT_CONFIRMED",
                "An unconfirmed scenario cannot be simulated.",
                status_code=409,
            )
        snapshot = self.twin_service.get(confirmed.twin_snapshot.snapshot_id)
        if snapshot is None or snapshot.fingerprint != confirmed.twin_snapshot.fingerprint:
            raise ScenarioDomainError(
                "TWIN_SNAPSHOT_STALE",
                "The frozen twin snapshot is unavailable or does not match its fingerprint.",
                status_code=409,
            )
        fingerprint = simulation_fingerprint(confirmed, request.configuration)
        reusable = await self.repository.run_by_fingerprint(fingerprint)
        if reusable is not None and reusable.status is SimulationStatus.COMPLETED:
            self._idempotency[("run", idempotency_key)] = reusable
            return reusable.model_copy(update={"reused_result": True})
        created_at = (now or datetime.now(UTC)).astimezone(UTC)
        run_id = uuid5(NAMESPACE_URL, f"urn:sanjiv:simulation-run:{fingerprint}")
        run = SimulationRun(
            run_id=run_id,
            scenario_id=confirmed.scenario_id,
            scenario_fingerprint=confirmed.scenario_fingerprint,
            twin_snapshot=confirmed.twin_snapshot,
            simulation_fingerprint=fingerprint,
            model_version=SIMULATION_MODEL_VERSION,
            configuration=request.configuration,
            status=SimulationStatus.QUEUED,
            created_at=created_at,
        )
        await self.repository.save_run(run)
        await self._progress(
            run_id,
            SimulationStatus.QUEUED,
            0,
            "QUEUED",
            "Simulation accepted for immediate in-process execution.",
            created_at,
        )
        self._idempotency[("run", idempotency_key)] = run
        return run

    async def execute(self, run_id: UUID) -> SimulationRun:
        run = await self.get_run(run_id)
        if run.status in {
            SimulationStatus.COMPLETED,
            SimulationStatus.CANCELLED,
            SimulationStatus.FAILED,
        }:
            return run
        if run_id in self._cancelled:
            return await self._mark_cancelled(run)
        started_at = datetime.now(UTC)
        running = run.model_copy(
            update={"status": SimulationStatus.RUNNING, "started_at": started_at}
        )
        await self.repository.save_run(running)
        await self._progress(
            run_id,
            SimulationStatus.RUNNING,
            10,
            "VALIDATING",
            "Frozen scenario and twin fingerprints verified.",
        )
        if run_id in self._cancelled:
            return await self._mark_cancelled(running)
        confirmed = await self.confirmed(run.scenario_id)
        snapshot = self.twin_service.get(run.twin_snapshot.snapshot_id)
        if snapshot is None or snapshot.fingerprint != run.twin_snapshot.fingerprint:
            return await self._mark_failed(
                running, "TWIN_SNAPSHOT_STALE", "The frozen twin snapshot is unavailable or stale."
            )
        await self._progress(
            run_id,
            SimulationStatus.RUNNING,
            35,
            "BASELINE",
            "Immutable baseline flows loaded without mutation.",
        )
        try:
            started_clock = perf_counter()
            result = run_no_action_simulation(run_id, confirmed, snapshot, run.configuration)
            runtime_ms = (perf_counter() - started_clock) * 1000
        except (ValueError, ArithmeticError) as exc:
            return await self._mark_failed(running, "SIMULATION_INVARIANT_FAILURE", str(exc))
        if run_id in self._cancelled:
            return await self._mark_cancelled(running)
        await self._progress(
            run_id,
            SimulationStatus.RUNNING,
            80,
            "INVARIANTS",
            "Physical invariants and deterministic uncertainty bounds passed.",
        )
        completed_at = datetime.now(UTC)
        completed = running.model_copy(
            update={
                "status": SimulationStatus.COMPLETED,
                "completed_at": completed_at,
                "runtime_ms": runtime_ms,
                "result": result.model_copy(update={"runtime_ms": runtime_ms}),
            }
        )
        await self.repository.save_run(completed)
        await self._progress(
            run_id,
            SimulationStatus.COMPLETED,
            100,
            "COMPLETED",
            "Auditable baseline and no-action results persisted.",
            completed_at,
        )
        return completed

    async def get_run(self, run_id: UUID) -> SimulationRun:
        run = await self.repository.run(run_id)
        if run is None:
            raise ScenarioDomainError(
                "SIMULATION_RUN_NOT_FOUND", "Simulation run not found.", status_code=404
            )
        return run

    async def progress(self, run_id: UUID) -> list[SimulationProgressEvent]:
        await self.get_run(run_id)
        return await self.repository.progress(run_id)

    async def cancel(self, run_id: UUID, *, idempotency_key: str) -> SimulationRun:
        cached = self._idempotency.get(("cancel", idempotency_key))
        if isinstance(cached, SimulationRun):
            return cached
        run = await self.get_run(run_id)
        if run.status is SimulationStatus.COMPLETED:
            raise ScenarioDomainError(
                "SIMULATION_ALREADY_COMPLETED",
                "A completed simulation cannot be cancelled.",
                status_code=409,
            )
        if run.status is SimulationStatus.FAILED:
            raise ScenarioDomainError(
                "SIMULATION_ALREADY_FAILED",
                "A failed simulation cannot be cancelled.",
                status_code=409,
            )
        self._cancelled.add(run_id)
        cancelled = await self._mark_cancelled(run)
        self._idempotency[("cancel", idempotency_key)] = cancelled
        return cancelled

    async def _mark_cancelled(self, run: SimulationRun) -> SimulationRun:
        now = datetime.now(UTC)
        cancelled = run.model_copy(
            update={
                "status": SimulationStatus.CANCELLED,
                "completed_at": now,
                "cancellation_requested_at": now,
            }
        )
        await self.repository.save_run(cancelled)
        await self._progress(
            run.run_id,
            SimulationStatus.CANCELLED,
            100,
            "CANCELLED",
            "Simulation cancelled; no result was fabricated.",
            now,
        )
        return cancelled

    async def _mark_failed(self, run: SimulationRun, code: str, message: str) -> SimulationRun:
        now = datetime.now(UTC)
        failed = run.model_copy(
            update={
                "status": SimulationStatus.FAILED,
                "completed_at": now,
                "failure": SimulationFailureResult(code=code, message=message),
            }
        )
        await self.repository.save_run(failed)
        await self._progress(run.run_id, SimulationStatus.FAILED, 100, "FAILED", message, now)
        return failed

    async def _progress(
        self,
        run_id: UUID,
        status: SimulationStatus,
        percent: float,
        phase: str,
        message: str,
        occurred_at: datetime | None = None,
    ) -> None:
        existing = await self.repository.progress(run_id)
        await self.repository.save_progress(
            SimulationProgressEvent(
                run_id=run_id,
                sequence=len(existing) + 1,
                status=status,
                progress_percent=percent,
                phase=phase,
                message=message,
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )
