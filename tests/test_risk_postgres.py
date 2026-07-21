import pytest
from sanjiv.risk.adapters.fixture import FixtureRiskAdapter
from sanjiv.risk.repository import PostgresRiskRepository
from sanjiv.risk.service import RiskService
from sanjiv.settings import Settings
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_postgres_rehydrates_immutable_risk_alert_timeline_and_backtest() -> None:
    settings = Settings()
    writer = RiskService(
        repository=PostgresRiskRepository(settings.database_url),
        adapter=FixtureRiskAdapter(settings.sanjiv_risk_replay_manifest),
    )
    await writer.initialize()
    risks = (await writer.overview()).risks
    fingerprint = risks[0].fingerprint
    corridor_id = risks[0].corridor_id
    await writer.close()

    engine = create_async_engine(settings.database_url)
    with pytest.raises(DBAPIError, match="immutable"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE corridor_risk_results SET severity=0 WHERE risk_id=:risk_id"
                ),
                {"risk_id": risks[0].risk_id},
            )
    await engine.dispose()

    reader = RiskService(
        repository=PostgresRiskRepository(settings.database_url),
        adapter=FixtureRiskAdapter(settings.sanjiv_risk_replay_manifest),
    )
    await reader.initialize()
    restored = await reader.get(risks[0].risk_id)
    assert restored.fingerprint == fingerprint
    assert await reader.alerts()
    assert await reader.timeline(corridor_id)
    backtests = await reader.backtests()
    assert backtests and backtests[0].fixture_evidence_only is True
    await reader.close()
