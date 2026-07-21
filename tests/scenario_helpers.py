from __future__ import annotations

from datetime import UTC, datetime

from sanjiv.scenarios.contracts import (
    CompileScenarioRequest,
    ConfirmScenarioRequest,
    ScenarioCompileMode,
)
from sanjiv.scenarios.service import ScenarioService
from sanjiv.twin.service import build_default_twin_service

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


def memory_service() -> ScenarioService:
    return ScenarioService(twin_service=build_default_twin_service())


async def confirmed_text(
    service: ScenarioService,
    text: str = "Close the Strait of Hormuz for 14 days.",
) -> object:
    snapshot = service.twin_service.current()
    compiled = await service.compile(
        CompileScenarioRequest(
            mode=ScenarioCompileMode.DETERMINISTIC_TEXT,
            twin_snapshot_id=snapshot.snapshot_id,
            text=text,
        ),
        idempotency_key=f"compile-{text}",
        now=NOW,
    )
    assert compiled.candidate is not None
    assert compiled.validation is not None and compiled.validation.valid
    return await service.confirm(
        compiled.candidate.scenario_id,
        ConfirmScenarioRequest(confirming_identity="phase-3-test-operator"),
        idempotency_key=f"confirm-{text}",
        now=NOW,
    )
