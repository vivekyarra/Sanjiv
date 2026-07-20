from datetime import UTC, datetime
from pathlib import Path

from sanjiv.contracts import DataMode
from sanjiv.maritime.adapters.replay import ReplayAISAdapter
from sanjiv.maritime.contracts import RawAISMessage
from sanjiv.maritime.geofences import GeofenceEngine, load_geofences
from sanjiv.maritime.recording import RawBatchRecorder
from sanjiv.maritime.repository import InMemoryMaritimeRepository
from sanjiv.maritime.service import MaritimeWatchService

ROOT = Path(__file__).resolve().parents[1]
GEOFENCES = ROOT / "data/fixtures/maritime/geofences.geojson"
REPLAY_MANIFEST = ROOT / "data/replay/maritime-watch-v1/manifest.json"


def raw_position(
    *,
    record_id: str = "test-1",
    mmsi: str = "999123456",
    latitude: float = 25.0,
    longitude: float = 55.0,
    source_timestamp: datetime | None = None,
    fetched_at: datetime | None = None,
    mode: DataMode = DataMode.LIVE,
    payload_override: dict[str, object] | None = None,
) -> RawAISMessage:
    source_time = source_timestamp or datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    fetched = fetched_at or datetime(2026, 7, 20, 10, 0, 2, tzinfo=UTC)
    payload: dict[str, object] = {
        "position": {
            "MMSI": mmsi,
            "Latitude": latitude,
            "Longitude": longitude,
            "Sog": 0,
            "Cog": 90,
            "TrueHeading": 90,
            "Type": 80,
            "Name": "SYNTHETIC TEST VESSEL",
            "Destination": "JAMNAGAR",
        }
    }
    if payload_override is not None:
        payload = payload_override
    return RawAISMessage(
        source_id="TEST_AIS",
        source_record_id=record_id,
        source_timestamp=source_time,
        fetched_at=fetched,
        mode=mode,
        payload=payload,
        dataset="Unit test fixture",
        dataset_version="1.0",
        license="Test-only synthetic fixture",
    )


def build_service(tmp_path: Path, *, live_adapter: object | None = None) -> MaritimeWatchService:
    geofences = load_geofences(GEOFENCES)
    return MaritimeWatchService(
        repository=InMemoryMaritimeRepository(),
        geofence_engine=GeofenceEngine(geofences),
        live_adapter=live_adapter,  # type: ignore[arg-type]
        replay_adapter=ReplayAISAdapter(REPLAY_MANIFEST, speed=1000),
        recorder=RawBatchRecorder(tmp_path / "recordings"),
    )
