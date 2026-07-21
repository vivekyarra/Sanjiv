from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from risk_helpers import AT, fixture_risk
from sanjiv.risk.adapters.base import AdapterPolicy
from sanjiv.risk.adapters.live import (
    HttpRiskAdapter,
    RiskSourceRateLimited,
    live_adapter_configurations,
)
from sanjiv.risk.alerts import evaluate_alert
from sanjiv.risk.contracts import (
    AlertSeverity,
    AlertStatus,
    AnomalyBaseline,
    CorridorRiskResult,
    RiskFeatureType,
    RiskLifecycle,
    RiskLifecycleTransition,
    RiskSourceFailureCode,
)
from sanjiv.risk.engine import build_baselines


def test_baselines_are_effective_dated_deterministic_and_reject_nonfinite() -> None:
    first = build_baselines([1, 2, 3, 4, 5], at=AT)
    second = build_baselines([1, 2, 3, 4, 5], at=AT)
    assert {key: value.fingerprint for key, value in first.items()} == {
        key: value.fingerprint for key, value in second.items()
    }
    assert all(item.window_ends_at == AT for item in first.values())
    with pytest.raises(ValueError, match="finite"):
        build_baselines([1, 2, float("inf")], at=AT)
    forged = next(iter(first.values())).model_dump(mode="json")
    forged["mean"] = 99
    with pytest.raises(ValidationError, match="baseline fingerprint mismatch"):
        AnomalyBaseline.model_validate(forged)


@pytest.mark.asyncio
async def test_feature_scaling_missingness_and_confidence_are_separate() -> None:
    result = await fixture_risk("source-outage")
    missing = [item for item in result.features if item.missing]
    assert missing and all(item.normalized_value is None for item in missing)
    assert result.completeness.value < 1
    assert result.confidence.value != result.completeness.value
    assert result.severity.unit == "severity_point"
    assert result.lifecycle is RiskLifecycle.DEGRADED


@pytest.mark.asyncio
async def test_false_news_thermal_and_ais_only_are_not_corroborated() -> None:
    for case_id in ("false-news-spike", "thermal-ambiguity", "ais-without-corroboration"):
        result = await fixture_risk(case_id)
        alert = evaluate_alert(result, created_at=AT)
        assert not result.corroboration.passed
        assert alert.status is AlertStatus.SUPPRESSED
    assert (
        "not proof of closure, attack, or damage"
        in (await fixture_risk("thermal-ambiguity")).explanation
    )


@pytest.mark.asyncio
async def test_critical_alert_requires_corroborated_evidence() -> None:
    corroborated = evaluate_alert(await fixture_risk("true-disruption-escalation"), created_at=AT)
    ambiguous = evaluate_alert(await fixture_risk("false-news-spike"), created_at=AT)
    assert corroborated.severity_band is AlertSeverity.CRITICAL
    assert corroborated.status is AlertStatus.OPEN
    assert ambiguous.status is AlertStatus.SUPPRESSED
    assert corroborated.risk_fingerprint


@pytest.mark.asyncio
async def test_source_disagreement_and_staleness_are_visible() -> None:
    disagreement = await fixture_risk("conflicting-sources")
    stale = await fixture_risk("stale-market-data")
    assert disagreement.corroboration.disagreeing_features
    assert RiskFeatureType.MARKET_STRESS in stale.corroboration.stale_or_missing_features
    assert any(item.code is RiskSourceFailureCode.STALE for item in stale.source_failures)


@pytest.mark.asyncio
async def test_result_fingerprint_detects_forgery() -> None:
    result = await fixture_risk("true-disruption-escalation")
    payload = result.model_dump(mode="json")
    payload["severity"]["value"] = 1
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        CorridorRiskResult.model_validate(payload)


def test_invalid_lifecycle_transition_is_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid risk lifecycle transition"):
        RiskLifecycleTransition(
            risk_id="00000000-0000-0000-0000-000000000001",
            current=RiskLifecycle.CREATED,
            target=RiskLifecycle.SUPERSEDED,
            occurred_at=datetime.now(UTC),
            reason="invalid direct transition",
        )


@pytest.mark.asyncio
async def test_live_adapter_rate_limit_and_credentials_are_typed_and_redacted() -> None:
    configuration = live_adapter_configurations()[2]
    missing = await HttpRiskAdapter(configuration, credential=None, fetcher=None).fetch("unused")
    assert missing.failures[0].code is RiskSourceFailureCode.CREDENTIAL_MISSING

    async def limited(_: str | None, __: str | None, ___: float) -> list[object]:
        raise RiskSourceRateLimited("secret provider response")

    adapter = HttpRiskAdapter(
        configuration,
        credential="secret",
        fetcher=limited,  # type: ignore[arg-type]
        policy=AdapterPolicy(
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
            expected_cadence_seconds=60,
            stale_after_seconds=120,
            rate_limit_per_minute=1,
        ),
    )
    result = await adapter.fetch("unused")
    assert result.failures[0].code is RiskSourceFailureCode.RATE_LIMITED
    assert "secret" not in result.failures[0].message
