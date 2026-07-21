from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sanjiv.contracts import FreshnessStatus, SourceState, TruthClass
from sanjiv.risk.adapters import RawRiskSignal
from sanjiv.risk.contracts import (
    AnomalyBaseline,
    CorridorRiskResult,
    CorroborationResult,
    DataCompleteness,
    EvidenceConfidence,
    FeatureContribution,
    NormalizedRiskFeature,
    RiskFeatureType,
    RiskLifecycle,
    RiskSeverity,
    RiskSourceFailure,
    canonical_hash,
    corridor_risk_fingerprint,
)

MODEL_VERSION = "corridor-risk-structural-v1"
BASELINE_VERSION = "risk-baseline-effective-window-v1"
NORMALIZER_VERSION = "risk-feature-normalizer-v1"
WEIGHTS: dict[RiskFeatureType, float] = {
    RiskFeatureType.TRANSIT_ANOMALY: 0.25,
    RiskFeatureType.GEOPOLITICAL_SEVERITY: 0.20,
    RiskFeatureType.AIS_BEHAVIORAL_ANOMALY: 0.15,
    RiskFeatureType.MARKET_STRESS: 0.15,
    RiskFeatureType.SANCTIONS_EXPOSURE: 0.10,
    RiskFeatureType.INFRASTRUCTURE_PHYSICAL_SIGNAL: 0.15,
}


def build_baselines(
    observations: list[float], *, at: datetime
) -> dict[RiskFeatureType, AnomalyBaseline]:
    if len(observations) < 3 or any(not math.isfinite(value) for value in observations):
        raise ValueError("risk baseline requires at least three finite observations")
    values = [float(value) for value in observations]
    mean = statistics.fmean(values)
    deviation = statistics.pstdev(values)
    if deviation <= 0:
        raise ValueError("risk baseline requires non-zero variance")
    output = {}
    for feature in RiskFeatureType:
        payload = {
            "feature_type": feature,
            "window_starts_at": at - timedelta(days=len(observations)),
            "window_ends_at": at,
            "observations": values,
            "mean": mean,
            "standard_deviation": deviation,
            "version": BASELINE_VERSION,
        }
        output[feature] = AnomalyBaseline(
            **payload,
            fingerprint=canonical_hash(payload),
        )
    return output


def calculate_corridor_risk(
    corridor_id: UUID,
    corridor_name: str,
    signals: list[RawRiskSignal],
    baselines: dict[RiskFeatureType, AnomalyBaseline],
    failures: list[RiskSourceFailure],
    *,
    calculated_at: datetime | None = None,
) -> CorridorRiskResult:
    at = calculated_at or max(
        (item.fetched_at for item in signals),
        default=datetime.now(UTC),
    )
    by_type = {item.feature_type: item for item in signals if item.corridor_id == corridor_id}
    features: list[NormalizedRiskFeature] = []
    contributions: list[FeatureContribution] = []
    present_weight = 0.0
    weighted_score = 0.0
    completeness_score = 0.0
    confidence_score = 0.0
    for feature_type in RiskFeatureType:
        signal = by_type.get(feature_type)
        baseline = baselines[feature_type]
        missing = signal is None or signal.raw_value is None
        normalized = (
            None
            if signal is None or signal.raw_value is None
            else _normalize(signal.raw_value, baseline)
        )
        freshness_factor = (
            0.0
            if signal is None or signal.raw_value is None
            else 0.25
            if signal.freshness is FreshnessStatus.STALE
            else 1.0
        )
        weight = WEIGHTS[feature_type]
        if signal is not None and not missing and normalized is not None:
            present_weight += weight
            weighted_score += normalized * weight
            completeness_score += weight * freshness_factor
            confidence_score += weight * signal.confidence * freshness_factor
        feature = NormalizedRiskFeature(
            feature_id=uuid5(
                NAMESPACE_URL,
                f"urn:sanjiv:risk-feature:{corridor_id}:{feature_type.value}:{at.isoformat()}",
            ),
            corridor_id=corridor_id,
            feature_type=feature_type,
            raw_value=None if signal is None else signal.raw_value,
            normalized_value=normalized,
            unit="severity_point",
            missing=missing,
            truth_class=TruthClass.DERIVED,
            confidence=EvidenceConfidence(value=0.0 if signal is None else signal.confidence),
            source_id="UNAVAILABLE" if signal is None else signal.source_id,
            source_state=SourceState.UNAVAILABLE if signal is None else signal.source_state,
            freshness=FreshnessStatus.UNAVAILABLE if signal is None else signal.freshness,
            effective_at=at if signal is None else signal.effective_at,
            fetched_at=at if signal is None else signal.fetched_at,
            evidence_ids=[] if signal is None else signal.evidence_ids,
            baseline_fingerprint=baseline.fingerprint,
            transformation=NORMALIZER_VERSION,
        )
        features.append(feature)
        contributions.append(
            FeatureContribution(
                feature_type=feature_type,
                normalized_value=normalized or 0.0,
                weight=weight,
                weighted_contribution=0.0 if normalized is None else normalized * weight,
                present=not missing,
            )
        )
    severity_value = 0.0 if present_weight <= 0 else weighted_score / present_weight
    completeness = DataCompleteness(value=min(1.0, completeness_score))
    confidence = EvidenceConfidence(
        value=0.0 if present_weight <= 0 else min(1.0, confidence_score / present_weight)
    )
    corroboration = _corroborate(features)
    lifecycle = (
        RiskLifecycle.DEGRADED if failures or completeness.value < 1.0 else RiskLifecycle.CALCULATED
    )
    payload = {
        "risk_id": uuid5(
            NAMESPACE_URL, f"urn:sanjiv:risk:{corridor_id}:{at.isoformat()}:{MODEL_VERSION}"
        ),
        "corridor_id": corridor_id,
        "corridor_name": corridor_name,
        "severity": RiskSeverity(value=severity_value),
        "confidence": confidence,
        "completeness": completeness,
        "features": features,
        "contributions": contributions,
        "corroboration": corroboration,
        "source_failures": failures,
        "effective_at": max((item.effective_at for item in features), default=at),
        "calculated_at": at,
        "lifecycle": lifecycle,
        "model_version": MODEL_VERSION,
        "baseline_version": BASELINE_VERSION,
        "explanation": _explanation(
            severity_value, confidence.value, completeness.value, corroboration
        ),
    }
    return CorridorRiskResult(**payload, fingerprint=corridor_risk_fingerprint(payload))


def _normalize(value: float, baseline: AnomalyBaseline) -> float:
    if not math.isfinite(value):
        raise ValueError("risk feature value must be finite")
    z_score = (value - baseline.mean) / baseline.standard_deviation
    return min(100.0, max(0.0, z_score * 25.0))


def _corroborate(features: list[NormalizedRiskFeature]) -> CorroborationResult:
    fresh = [
        item
        for item in features
        if not item.missing
        and item.normalized_value is not None
        and item.normalized_value >= 50
        and item.freshness is not FreshnessStatus.STALE
    ]
    operational = {
        RiskFeatureType.TRANSIT_ANOMALY,
        RiskFeatureType.AIS_BEHAVIORAL_ANOMALY,
        RiskFeatureType.INFRASTRUCTURE_PHYSICAL_SIGNAL,
    }
    info_high = {
        item.feature_type
        for item in fresh
        if item.feature_type
        in {RiskFeatureType.GEOPOLITICAL_SEVERITY, RiskFeatureType.MARKET_STRESS}
    }
    operational_high = {item.feature_type for item in fresh if item.feature_type in operational}
    passed = len({item.source_id for item in fresh}) >= 2 and bool(operational_high)
    disagreements = sorted(info_high, key=str) if info_high and not operational_high else []
    stale_or_missing = [
        item.feature_type
        for item in features
        if item.missing or item.freshness in {FreshnessStatus.STALE, FreshnessStatus.UNAVAILABLE}
    ]
    return CorroborationResult(
        passed=passed,
        independent_source_count=len({item.source_id for item in fresh}),
        corroborating_features=sorted((item.feature_type for item in fresh), key=str),
        disagreeing_features=disagreements,
        stale_or_missing_features=stale_or_missing,
        explanation=(
            "Independent operational and contextual signals corroborate the elevated score."
            if passed
            else (
                "Evidence is uncorroborated, stale, incomplete, or disagrees across "
                "source families."
            )
        ),
    )


def _explanation(
    severity: float, confidence: float, completeness: float, corroboration: CorroborationResult
) -> str:
    return (
        f"Structural corridor severity is {severity:.1f}/100; evidence confidence is "
        f"{confidence:.2f} and data completeness is {completeness:.2f}. "
        f"{corroboration.explanation} Media events and thermal detections remain signals, "
        "not proof of closure, attack, or damage."
    )
