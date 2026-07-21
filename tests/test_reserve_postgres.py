from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sanjiv.procurement.repository import PostgresProcurementRepository
from sanjiv.procurement.service import ProcurementExecutionRequest, ProcurementService
from sanjiv.reserve.repository import PostgresReserveRepository
from sanjiv.reserve.service import ReserveExecutionRequest, ReserveService
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
async def test_postgres_rehydrates_immutable_reserve_plan() -> None:
    settings = Settings()
    twin_service = build_default_twin_service()
    snapshot = twin_service.current()
    scenario_service = ScenarioService(
        twin_service=twin_service,
        repository=PostgresScenarioRepository(settings.database_url, snapshot),
    )
    await scenario_service.initialize()
    compiled = await scenario_service.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.DETERMINISTIC_TEXT,
            twin_snapshot_id=snapshot.snapshot_id,
            text="Reduce Hormuz capacity by 53% for 12 days.",
        ),
        idempotency_key="postgres-reserve-compile",
        now=datetime(2026, 7, 21, 17, tzinfo=UTC),
    )
    assert compiled.candidate is not None
    confirmed = await scenario_service.confirm(
        compiled.candidate.scenario_id,
        ConfirmScenarioRequest(confirming_identity="postgres-reserve-test"),
        idempotency_key="postgres-reserve-confirm",
    )
    run = await scenario_service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="postgres-reserve-run",
    )
    if run.status is not SimulationStatus.COMPLETED:
        run = await scenario_service.execute(run.run_id)
    procurement = ProcurementService(
        scenario_service=scenario_service,
        repository=PostgresProcurementRepository(settings.database_url),
    )
    procurement_response = await procurement.create(
        run.run_id,
        ProcurementExecutionRequest(),
        idempotency_key="postgres-reserve-procurement",
        actor_id="postgres-reserve-test",
    )
    repository = PostgresReserveRepository(settings.database_url)
    writer = ReserveService(
        scenario_service=scenario_service,
        procurement_service=procurement,
        repository=repository,
    )
    response = await writer.create(
        run.run_id,
        ReserveExecutionRequest(procurement_plan_id=procurement_response.plans[1].plan_id),
        idempotency_key="postgres-reserve-plan",
        actor_id="postgres-reserve-test",
    )
    plan_id = response.plans[1].plan_id
    fingerprint = response.plans[1].plan_fingerprint
    await writer.close()
    await procurement.close()
    await scenario_service.close()

    reader = PostgresReserveRepository(settings.database_url)
    restored = await reader.plan(plan_id)
    await reader.close()
    assert restored is not None
    assert restored.plan_fingerprint == fingerprint
    assert restored.result.checker is not None and restored.result.checker.passed
