from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_phase_two_migration_is_reversible_chained_and_immutable() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "services/api/alembic/versions/20260720_0003_energy_network_twin.py"
    )
    spec = spec_from_file_location("phase2_migration", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260720_0003"
    assert module.down_revision == "20260720_0002"
    assert callable(module.upgrade)
    assert callable(module.downgrade)
    text = path.read_text(encoding="utf-8")
    assert '"twin_snapshots"' in text
    assert "reject_twin_snapshot_mutation" in text
    assert "DROP TRIGGER" in text
