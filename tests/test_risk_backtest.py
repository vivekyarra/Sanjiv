from pathlib import Path

import pytest
from sanjiv.risk.adapters.fixture import FixtureRiskAdapter
from sanjiv.risk.backtest import run_fixture_backtest
from sanjiv.risk.contracts import BacktestResult


@pytest.mark.asyncio
async def test_replay_library_is_checksummed_complete_and_deterministic() -> None:
    adapter = FixtureRiskAdapter()
    first = await run_fixture_backtest(adapter)
    second = await run_fixture_backtest(adapter)
    assert len(first.cases) == 10
    assert first.fingerprint == second.fingerprint
    assert first.classification == "SYNTHETIC_FIXTURE"
    assert first.fixture_evidence_only is True
    assert first.precision == 1
    assert first.false_positives == 0
    assert first.alert_stability == 1
    assert first.source_failure_case_count >= 2


def test_replay_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    source = Path("data/replay/risk-intelligence-v1")
    (tmp_path / "cases.json").write_text(
        (source / "cases.json").read_text(encoding="utf-8") + " ", encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        (source / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        FixtureRiskAdapter(tmp_path / "manifest.json")


@pytest.mark.asyncio
async def test_backtest_fingerprint_survives_runtime_variance() -> None:
    result = await run_fixture_backtest(FixtureRiskAdapter())
    payload = result.model_dump(mode="json")
    payload["runtime_ms"] += 10
    payload["cases"][0]["runtime_ms"] += 10
    assert BacktestResult.model_validate(payload).fingerprint == result.fingerprint
