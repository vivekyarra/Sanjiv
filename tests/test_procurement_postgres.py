from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sanjiv.procurement.repository import PostgresProcurementRepository
from sanjiv.procurement.service import ProcurementExecutionRequest, ProcurementService
from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmScenarioRequest,
    ScenarioCompileMode,
)
from sanjiv.scenarios.repository import PostgresScenarioRepository
from sanjiv.scenarios.service import ScenarioService
from sanjiv.settings import Settings
from sanjiv.simulation.contracts import SimulationStatus, StartSimulationRequest
from sanjiv.twin.service import build_default_twin_service


@pytest.mark.asyncio
async def test_postgres_rehydrates_immutable_procurement_plan() -> None:
    settings = Settings()
    twin_service = build_default_twin_service()
    snapshot = twin_service.current()
    scenario_repository = PostgresScenarioRepository(settings.database_url, snapshot)
    scenario_service = ScenarioService(
        twin_service=twin_service,
        repository=scenario_repository,
    )
    await scenario_service.initialize()
    compiled = await scenario_service.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.DETERMINISTIC_TEXT,
            twin_snapshot_id=snapshot.snapshot_id,
            text="Reduce Hormuz capacity by 47% for 11 days.",
        ),
        idempotency_key="postgres-procurement-compile",
        now=datetime(2026, 7, 21, 16, tzinfo=UTC),
    )
    assert compiled.candidate is not None
    confirmed = await scenario_service.confirm(
        compiled.candidate.scenario_id,
        ConfirmScenarioRequest(confirming_identity="postgres-procurement-test"),
        idempotency_key="postgres-procurement-confirm",
    )
    run = await scenario_service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="postgres-procurement-run",
    )
    if run.status is not SimulationStatus.COMPLETED:
        run = await scenario_service.execute(run.run_id)
    repository = PostgresProcurementRepository(settings.database_url)
    writer = ProcurementService(
        scenario_service=scenario_service,
        repository=repository,
    )
    response = await writer.create(
        run.run_id,
        ProcurementExecutionRequest(),
        idempotency_key="postgres-procurement-plan",
        actor_id="postgres-procurement-test",
    )
    plan_id = response.plans[0].plan_id
    fingerprint = response.plans[0].plan_fingerprint
    await writer.close()
    await scenario_service.close()

    reader = PostgresProcurementRepository(settings.database_url)
    restored = await reader.plan(plan_id)
    await reader.close()
    assert restored is not None
    assert restored.plan_fingerprint == fingerprint
    assert restored.solver_result.independent_check is not None
    assert restored.solver_result.independent_check.passed
