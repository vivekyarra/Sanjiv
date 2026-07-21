from __future__ import annotations

from procurement_helpers import solved_procurement
from sanjiv.reserve.repository import InMemoryReserveRepository
from sanjiv.reserve.service import ReserveExecutionRequest, ReserveService


async def solved_reserve() -> tuple[ReserveService, object, object, object]:
    procurement_service, run, procurement_response = await solved_procurement()
    service = ReserveService(
        scenario_service=procurement_service.scenario_service,
        procurement_service=procurement_service,
        repository=InMemoryReserveRepository(),
    )
    response = await service.create(
        run.run_id,
        ReserveExecutionRequest(procurement_plan_id=procurement_response.plans[1].plan_id),
        idempotency_key="phase-5-reserve",
        actor_id="phase-5-test-operator",
    )
    return service, run, procurement_response.plans[1], response
