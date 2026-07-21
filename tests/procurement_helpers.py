from __future__ import annotations

from sanjiv.procurement.repository import InMemoryProcurementRepository
from sanjiv.procurement.service import ProcurementExecutionRequest, ProcurementService
from sanjiv.scenarios.contracts import ConfirmedScenario
from sanjiv.simulation.contracts import StartSimulationRequest
from scenario_helpers import NOW, confirmed_text, memory_service


async def solved_procurement() -> tuple[ProcurementService, object, object]:
    scenario_service = memory_service()
    confirmed = await confirmed_text(scenario_service)
    assert isinstance(confirmed, ConfirmedScenario)
    queued = await scenario_service.start(
        StartSimulationRequest(scenario_id=confirmed.scenario_id),
        idempotency_key="phase-4-run",
        now=NOW,
    )
    run = await scenario_service.execute(queued.run_id)
    service = ProcurementService(
        scenario_service=scenario_service,
        repository=InMemoryProcurementRepository(),
    )
    response = await service.create(
        run.run_id,
        ProcurementExecutionRequest(),
        idempotency_key="phase-4-procurement",
        actor_id="phase-4-test-operator",
    )
    return service, run, response
