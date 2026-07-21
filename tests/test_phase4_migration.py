from pathlib import Path


def test_phase_four_migration_is_reversible_chained_and_immutable() -> None:
    migration = Path(
        "services/api/alembic/versions/20260721_0005_procurement_optimiser.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260721_0004"' in migration
    for table in (
        "procurement_plan_requests",
        "procurement_plans",
        "procurement_plan_actions",
        "procurement_rejected_options",
    ):
        assert f'"{table}"' in migration
        assert f'op.drop_table("{table}")' in migration
    assert "reject_procurement_terminal_mutation" in migration
    assert "checker_passed" in migration
