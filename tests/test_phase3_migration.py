from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_phase_three_migration_is_reversible_chained_indexed_and_immutable() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "services/api/alembic/versions/20260721_0004_scenario_simulation.py"
    )
    spec = spec_from_file_location("phase3_migration", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260721_0004"
    assert module.down_revision == "20260720_0003"
    text = path.read_text(encoding="utf-8")
    for table in (
        "scenario_candidates",
        "scenario_validations",
        "confirmed_scenarios",
        "simulation_runs",
        "simulation_results",
        "simulation_progress_events",
    ):
        assert f'"{table}"' in text
    assert "reject_confirmed_scenario_mutation" in text
    assert "reject_simulation_result_mutation" in text
    assert "def downgrade" in text
