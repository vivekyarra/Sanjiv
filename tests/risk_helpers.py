from datetime import UTC, datetime

from sanjiv.risk.adapters.fixture import FixtureRiskAdapter
from sanjiv.risk.contracts import CorridorRiskResult
from sanjiv.risk.engine import build_baselines, calculate_corridor_risk

AT = datetime(2026, 7, 21, 12, tzinfo=UTC)


async def fixture_risk(case_id: str) -> CorridorRiskResult:
    adapter = FixtureRiskAdapter()
    adapted = await adapter.fetch(case_id)
    raw = next(item for item in adapter.cases() if item.case_id == case_id)
    return calculate_corridor_risk(
        adapted.signals[0].corridor_id,
        raw.corridor,
        adapted.signals,
        build_baselines(adapter.baseline(), at=AT),
        adapted.failures,
        calculated_at=AT,
    )
