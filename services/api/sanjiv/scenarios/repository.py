from __future__ import annotations

import json
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.contracts import AuditEvent
from sanjiv.scenarios.contracts import (
    ConfirmedScenario,
    ScenarioCandidate,
    ScenarioValidationResult,
)
from sanjiv.simulation.contracts import SimulationProgressEvent, SimulationRun
from sanjiv.twin.contracts import TwinSnapshot


class ScenarioRepository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def save_candidate(self, candidate: ScenarioCandidate) -> None: ...
    async def candidate(self, scenario_id: UUID) -> ScenarioCandidate | None: ...
    async def save_validation(self, validation: ScenarioValidationResult) -> None: ...
    async def validation(self, scenario_id: UUID) -> ScenarioValidationResult | None: ...
    async def save_confirmation(self, confirmed: ConfirmedScenario) -> None: ...
    async def confirmation(self, scenario_id: UUID) -> ConfirmedScenario | None: ...
    async def save_audit(self, event: AuditEvent) -> None: ...
    async def audits(self, scenario_id: UUID) -> list[AuditEvent]: ...
    async def save_run(self, run: SimulationRun) -> None: ...
    async def run(self, run_id: UUID) -> SimulationRun | None: ...
    async def run_by_fingerprint(self, fingerprint: str) -> SimulationRun | None: ...
    async def save_progress(self, event: SimulationProgressEvent) -> None: ...
    async def progress(self, run_id: UUID) -> list[SimulationProgressEvent]: ...


class InMemoryScenarioRepository:
    def __init__(self) -> None:
        self._candidates: dict[UUID, ScenarioCandidate] = {}
        self._validations: dict[UUID, ScenarioValidationResult] = {}
        self._confirmations: dict[UUID, ConfirmedScenario] = {}
        self._audits: dict[UUID, list[AuditEvent]] = {}
        self._runs: dict[UUID, SimulationRun] = {}
        self._run_fingerprints: dict[str, UUID] = {}
        self._progress: dict[UUID, list[SimulationProgressEvent]] = {}

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def save_candidate(self, candidate: ScenarioCandidate) -> None:
        self._candidates.setdefault(candidate.scenario_id, candidate)

    async def candidate(self, scenario_id: UUID) -> ScenarioCandidate | None:
        return self._candidates.get(scenario_id)

    async def save_validation(self, validation: ScenarioValidationResult) -> None:
        self._validations[validation.scenario_id] = validation

    async def validation(self, scenario_id: UUID) -> ScenarioValidationResult | None:
        return self._validations.get(scenario_id)

    async def save_confirmation(self, confirmed: ConfirmedScenario) -> None:
        self._confirmations.setdefault(confirmed.scenario_id, confirmed)

    async def confirmation(self, scenario_id: UUID) -> ConfirmedScenario | None:
        return self._confirmations.get(scenario_id)

    async def save_audit(self, event: AuditEvent) -> None:
        try:
            scenario_id = UUID(event.resource_id)
        except ValueError:
            return
        events = self._audits.setdefault(scenario_id, [])
        if not any(item.id == event.id for item in events):
            events.append(event)

    async def audits(self, scenario_id: UUID) -> list[AuditEvent]:
        return list(self._audits.get(scenario_id, []))

    async def save_run(self, run: SimulationRun) -> None:
        self._runs[run.run_id] = run
        self._run_fingerprints[run.simulation_fingerprint] = run.run_id

    async def run(self, run_id: UUID) -> SimulationRun | None:
        return self._runs.get(run_id)

    async def run_by_fingerprint(self, fingerprint: str) -> SimulationRun | None:
        run_id = self._run_fingerprints.get(fingerprint)
        return self._runs.get(run_id) if run_id else None

    async def save_progress(self, event: SimulationProgressEvent) -> None:
        events = self._progress.setdefault(event.run_id, [])
        if not any(item.sequence == event.sequence for item in events):
            events.append(event)

    async def progress(self, run_id: UUID) -> list[SimulationProgressEvent]:
        return sorted(self._progress.get(run_id, []), key=lambda item: item.sequence)


class PostgresScenarioRepository:
    """Durable JSONB repository for exact canonical Phase 3 contracts."""

    def __init__(self, database_url: str, snapshot: TwinSnapshot) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._snapshot = snapshot

    async def initialize(self) -> None:
        snapshot = self._snapshot
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO twin_snapshots (
                      snapshot_id, version, effective_at, created_at, fingerprint,
                      payload, evidence_ids, assumption_ids
                    ) VALUES (
                      :snapshot_id, :version, :effective_at, :created_at, :fingerprint,
                      CAST(:payload AS jsonb), :evidence_ids, :assumption_ids
                    ) ON CONFLICT (snapshot_id) DO NOTHING
                    """
                ),
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "version": snapshot.version,
                    "effective_at": snapshot.effective_at,
                    "created_at": snapshot.created_at,
                    "fingerprint": snapshot.fingerprint,
                    "payload": _json(snapshot),
                    "evidence_ids": [item.id for item in snapshot.evidence_records],
                    "assumption_ids": [item.id for item in snapshot.assumptions],
                },
            )

    async def close(self) -> None:
        await self._engine.dispose()

    async def save_candidate(self, candidate: ScenarioCandidate) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO scenario_candidates (
                      scenario_id, scenario_fingerprint, twin_snapshot_id,
                      twin_snapshot_fingerprint, source_mode, lifecycle, payload, created_at
                    ) VALUES (
                      :scenario_id, :fingerprint, :snapshot_id, :snapshot_fingerprint,
                      :source_mode, :lifecycle, CAST(:payload AS jsonb), :created_at
                    ) ON CONFLICT (scenario_id) DO NOTHING
                    """
                ),
                {
                    "scenario_id": candidate.scenario_id,
                    "fingerprint": candidate.scenario_fingerprint,
                    "snapshot_id": candidate.twin_snapshot.snapshot_id,
                    "snapshot_fingerprint": candidate.twin_snapshot.fingerprint,
                    "source_mode": candidate.source_mode.value,
                    "lifecycle": candidate.lifecycle.value,
                    "payload": _json(candidate),
                    "created_at": candidate.created_at,
                },
            )

    async def candidate(self, scenario_id: UUID) -> ScenarioCandidate | None:
        payload = await self._payload(
            "SELECT payload FROM scenario_candidates WHERE scenario_id = :id",
            {"id": scenario_id},
        )
        return ScenarioCandidate.model_validate(payload) if payload else None

    async def save_validation(self, validation: ScenarioValidationResult) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO scenario_validations (
                      validation_id, scenario_id, scenario_fingerprint, valid,
                      payload, validated_at
                    ) VALUES (
                      :validation_id, :scenario_id, :fingerprint, :valid,
                      CAST(:payload AS jsonb), :validated_at
                    ) ON CONFLICT (scenario_id) DO UPDATE SET
                      validation_id = EXCLUDED.validation_id,
                      scenario_fingerprint = EXCLUDED.scenario_fingerprint,
                      valid = EXCLUDED.valid,
                      payload = EXCLUDED.payload,
                      validated_at = EXCLUDED.validated_at
                    """
                ),
                {
                    "validation_id": validation.validation_id,
                    "scenario_id": validation.scenario_id,
                    "fingerprint": validation.scenario_fingerprint,
                    "valid": validation.valid,
                    "payload": _json(validation),
                    "validated_at": validation.validated_at,
                },
            )

    async def validation(self, scenario_id: UUID) -> ScenarioValidationResult | None:
        payload = await self._payload(
            "SELECT payload FROM scenario_validations WHERE scenario_id = :id",
            {"id": scenario_id},
        )
        return ScenarioValidationResult.model_validate(payload) if payload else None

    async def save_confirmation(self, confirmed: ConfirmedScenario) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO confirmed_scenarios (
                      scenario_id, scenario_fingerprint, twin_snapshot_id,
                      twin_snapshot_fingerprint, confirmed_by, confirmed_at,
                      audit_event_id, payload
                    ) VALUES (
                      :scenario_id, :fingerprint, :snapshot_id, :snapshot_fingerprint,
                      :confirmed_by, :confirmed_at, :audit_event_id, CAST(:payload AS jsonb)
                    ) ON CONFLICT (scenario_id) DO NOTHING
                    """
                ),
                {
                    "scenario_id": confirmed.scenario_id,
                    "fingerprint": confirmed.scenario_fingerprint,
                    "snapshot_id": confirmed.twin_snapshot.snapshot_id,
                    "snapshot_fingerprint": confirmed.twin_snapshot.fingerprint,
                    "confirmed_by": confirmed.confirmed_by,
                    "confirmed_at": confirmed.confirmed_at,
                    "audit_event_id": confirmed.audit_event.id,
                    "payload": _json(confirmed),
                },
            )

    async def confirmation(self, scenario_id: UUID) -> ConfirmedScenario | None:
        payload = await self._payload(
            "SELECT payload FROM confirmed_scenarios WHERE scenario_id = :id",
            {"id": scenario_id},
        )
        return ConfirmedScenario.model_validate(payload) if payload else None

    async def save_audit(self, event: AuditEvent) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                      id, occurred_at, actor_id, actor_type, action, resource_type,
                      resource_id, before_hash, after_hash, reason, correlation_id,
                      causation_id, outcome
                    ) VALUES (
                      :id, :occurred_at, :actor_id, :actor_type, :action,
                      :resource_type, :resource_id, :before_hash, :after_hash,
                      :reason, :correlation_id, :causation_id, :outcome
                    ) ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    **event.model_dump(mode="python"),
                    "outcome": event.outcome.value,
                },
            )

    async def audits(self, scenario_id: UUID) -> list[AuditEvent]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, occurred_at, actor_id, actor_type, action,
                               resource_type, resource_id, before_hash, after_hash,
                               reason, correlation_id, causation_id, outcome
                        FROM audit_events
                        WHERE resource_type = 'SCENARIO' AND resource_id = :id
                        ORDER BY occurred_at, id
                        """
                    ),
                    {"id": str(scenario_id)},
                )
            ).mappings()
            return [AuditEvent.model_validate(dict(row)) for row in rows]

    async def save_run(self, run: SimulationRun) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO simulation_runs (
                      run_id, scenario_id, simulation_fingerprint, status,
                      model_version, created_at, started_at, completed_at,
                      runtime_ms, failure_payload, payload
                    ) VALUES (
                      :run_id, :scenario_id, :fingerprint, :status, :model_version,
                      :created_at, :started_at, :completed_at, :runtime_ms,
                      CAST(:failure_payload AS jsonb), CAST(:payload AS jsonb)
                    ) ON CONFLICT (run_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      started_at = EXCLUDED.started_at,
                      completed_at = EXCLUDED.completed_at,
                      runtime_ms = EXCLUDED.runtime_ms,
                      failure_payload = EXCLUDED.failure_payload,
                      payload = EXCLUDED.payload
                    """
                ),
                {
                    "run_id": run.run_id,
                    "scenario_id": run.scenario_id,
                    "fingerprint": run.simulation_fingerprint,
                    "status": run.status.value,
                    "model_version": run.model_version,
                    "created_at": run.created_at,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "runtime_ms": run.runtime_ms,
                    "failure_payload": _json(run.failure) if run.failure else None,
                    "payload": _json(run),
                },
            )
            if run.result is not None:
                await connection.execute(
                    text(
                        """
                        INSERT INTO simulation_results (
                          result_id, run_id, simulation_fingerprint, payload, created_at
                        ) VALUES (
                          :result_id, :run_id, :fingerprint, CAST(:payload AS jsonb), :created_at
                        ) ON CONFLICT (result_id) DO NOTHING
                        """
                    ),
                    {
                        "result_id": run.result.result_id,
                        "run_id": run.run_id,
                        "fingerprint": run.simulation_fingerprint,
                        "payload": _json(run.result),
                        "created_at": run.completed_at or run.created_at,
                    },
                )

    async def run(self, run_id: UUID) -> SimulationRun | None:
        payload = await self._payload(
            "SELECT payload FROM simulation_runs WHERE run_id = :id",
            {"id": run_id},
        )
        return SimulationRun.model_validate(payload) if payload else None

    async def run_by_fingerprint(self, fingerprint: str) -> SimulationRun | None:
        payload = await self._payload(
            "SELECT payload FROM simulation_runs WHERE simulation_fingerprint = :fingerprint",
            {"fingerprint": fingerprint},
        )
        return SimulationRun.model_validate(payload) if payload else None

    async def save_progress(self, event: SimulationProgressEvent) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO simulation_progress_events (
                      run_id, sequence, status, occurred_at, payload
                    ) VALUES (
                      :run_id, :sequence, :status, :occurred_at, CAST(:payload AS jsonb)
                    ) ON CONFLICT (run_id, sequence) DO NOTHING
                    """
                ),
                {
                    "run_id": event.run_id,
                    "sequence": event.sequence,
                    "status": event.status.value,
                    "occurred_at": event.occurred_at,
                    "payload": _json(event),
                },
            )

    async def progress(self, run_id: UUID) -> list[SimulationProgressEvent]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT payload FROM simulation_progress_events
                        WHERE run_id = :id ORDER BY sequence
                        """
                    ),
                    {"id": run_id},
                )
            ).scalars()
            return [SimulationProgressEvent.model_validate(item) for item in rows]

    async def _payload(
        self, statement: str, parameters: dict[str, object]
    ) -> dict[str, object] | None:
        async with self._engine.connect() as connection:
            value = (await connection.execute(text(statement), parameters)).scalar_one_or_none()
        return value if isinstance(value, dict) else None


def _json(value: object) -> str:
    if hasattr(value, "model_dump_json"):
        return str(value.model_dump_json())
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
