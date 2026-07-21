from pathlib import Path


def test_phase_six_migration_is_reversible_chained_and_immutable() -> None:
    migration = Path(
        "services/api/alembic/versions/20260721_0007_corridor_risk_intelligence.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260721_0006"' in migration
    for table in (
        "risk_anomaly_baselines",
        "corridor_risk_results",
        "normalized_risk_features",
        "risk_feature_contributions",
        "risk_source_failures",
        "risk_alerts",
        "risk_timeline",
        "risk_backtests",
        "risk_lifecycle_transitions",
    ):
        assert f'"{table}"' in migration
    assert "op.drop_table(table)" in migration
    assert "reject_risk_record_mutation" in migration
    assert "severity BETWEEN 0 AND 100" in migration
