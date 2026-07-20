from pathlib import Path

import pytest
from maritime_helpers import GEOFENCES, raw_position
from sanjiv.maritime.contracts import VesselOperationalView
from sanjiv.maritime.geofences import load_geofences
from sanjiv.maritime.inference import assess_india_bound
from sanjiv.maritime.normalization import normalize_ais_position
from sanjiv.maritime.repository import PostgresMaritimeRepository
from sanjiv.maritime.sanctions import SanctionsMatcher
from sanjiv.settings import Settings


@pytest.mark.asyncio
async def test_postgres_persists_and_rehydrates_vessel_history(tmp_path: Path) -> None:
    settings = Settings()
    geofences = load_geofences(GEOFENCES)
    raw = raw_position(record_id="postgres-integration-1", mmsi="999876543")
    observation = normalize_ais_position(raw, computed_at=raw.fetched_at)
    view = VesselOperationalView(
        position=observation.position,
        recent_track=[(observation.position.longitude, observation.position.latitude)],
        india_bound=assess_india_bound(
            observation.position, computed_at=observation.position.computed_at
        ),
        sanctions=SanctionsMatcher().assess(observation.position),
    )

    writer = PostgresMaritimeRepository(settings.database_url)
    await writer.initialize(geofences)
    await writer.save_observation(observation.evidence, view)
    await writer.close()

    reader = PostgresMaritimeRepository(settings.database_url)
    await reader.initialize(geofences)
    hydrated = await reader.latest_views()
    history = await reader.history(observation.position.vessel_id, 100)
    await reader.close()

    assert any(item.position.vessel_id == observation.position.vessel_id for item in hydrated)
    assert history is not None
    assert history.positions[-1].evidence_ids == [observation.evidence.id]
    assert history.positions[-1].confidence == 1.0
