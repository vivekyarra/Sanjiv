from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmScenarioRequest,
    ScenarioCompileMode,
)
from sanjiv.scenarios.repository import PostgresScenarioRepository
from sanjiv.scenarios.service import ScenarioService
from sanjiv.settings import Settings
from sanjiv.simulation.contracts import StartSimulationRequest
from sanjiv.twin.service import build_default_twin_service


@pytest.mark.asyncio
async def test_postgres_rehydrates_confirmed_scenario_result_and_progress() -> None:
    settings = Settings()
    twin_service = build_default_twin_service()
    snapshot = twin_service.current()
    repository = PostgresScenarioRepository(settings.database_url, snapshot)
    writer = ScenarioService(twin_service=twin_service, repository=repository)
    await writer.initialize()
    compiled = await writer.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.DETERMINISTIC_TEXT,
            twin_snapshot_id=snapshot.snapshot_id,
            text="Reduce Hormuz capacity by 35% for 9 days.",
        ),
        idempotency_key="postgres-compile-phase3",
        now=datetime(2026, 7, 21, 15, tzinfo=UTC),
    )
    assert compiled.candidate is not None
    confirmed = await writer.confirm(
        compiled.candidate.scenario_id,
        ConfirmScenarioRequest(confirming_identity="postgres-test"),
        idempotency_key="postgres-confirm-phase3",
    )
    queued = await writer.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="postgres-run-phase3",
    )
    completed = await writer.execute(queued.run_id)
    await writer.close()

    reader_repository = PostgresScenarioRepository(settings.database_url, snapshot)
    reader = ScenarioService(twin_service=twin_service, repository=reader_repository)
    await reader.initialize()
    rehydrated = await reader.get_run(completed.run_id)
    progress = await reader.progress(completed.run_id)
    restored_confirmation = await reader.confirmed(confirmed.scenario_id)
    await reader.close()

    assert rehydrated.result is not None
    assert rehydrated.result.provenance.simulation_fingerprint == completed.simulation_fingerprint
    assert progress[-1].status.value == "COMPLETED"
    assert restored_confirmation.scenario_fingerprint == confirmed.scenario_fingerprint
