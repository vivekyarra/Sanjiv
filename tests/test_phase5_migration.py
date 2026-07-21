from pathlib import Path


def test_phase_five_migration_is_reversible_chained_and_immutable() -> None:
    migration = Path(
        "services/api/alembic/versions/20260721_0006_strategic_reserve_optimiser.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260721_0005"' in migration
    for table in (
        "reserve_plan_requests",
        "reserve_plans",
        "reserve_plan_actions",
        "reserve_inventory_timeline",
    ):
        assert f'"{table}"' in migration
        assert f'op.drop_table("{table}")' in migration
    assert "reject_reserve_terminal_mutation" in migration
    assert "checker_passed" in migration
