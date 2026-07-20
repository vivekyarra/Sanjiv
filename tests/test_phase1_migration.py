from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_phase_one_migration_is_reversible_and_chained() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "services/api/alembic/versions/20260720_0002_live_maritime_watch.py"
    )
    spec = spec_from_file_location("phase1_migration", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260720_0002"
    assert module.down_revision == "20260720_0001"
    assert callable(module.upgrade)
    assert callable(module.downgrade)

    text = path.read_text(encoding="utf-8")
    for table in (
        "vessels",
        "vessel_positions",
        "vessel_track_segments",
        "geofences",
        "geofence_events",
        "replay_recordings",
        "operating_mode_transitions",
        "ais_quarantine",
    ):
        assert f'"{table}"' in text
