from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sanjiv.risk.contracts import (
    AlertResult,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    CorridorRiskResult,
)

ALERT_RULE = AlertRule(
    rule_id="corridor-risk-alert-rule",
    version="corridor-risk-alerts-v1",
    high_threshold=50,
    critical_threshold=75,
    minimum_confidence=0.55,
    minimum_completeness=0.65,
)


def evaluate_alert(
    risk: CorridorRiskResult,
    rule: AlertRule = ALERT_RULE,
    *,
    created_at: datetime | None = None,
) -> AlertResult:
    at = created_at or datetime.now(UTC)
    evidence_sufficient = (
        risk.confidence.value >= rule.minimum_confidence
        and risk.completeness.value >= rule.minimum_completeness
        and risk.corroboration.passed
    )
    if risk.severity.value >= rule.critical_threshold and evidence_sufficient:
        band, status = AlertSeverity.CRITICAL, AlertStatus.OPEN
    elif risk.severity.value >= rule.high_threshold and evidence_sufficient:
        band, status = AlertSeverity.HIGH, AlertStatus.OPEN
    elif risk.severity.value >= rule.high_threshold:
        band, status = AlertSeverity.WATCH, AlertStatus.SUPPRESSED
    else:
        band, status = AlertSeverity.INFO, AlertStatus.SUPPRESSED
    evidence_ids = sorted(
        {evidence for feature in risk.features for evidence in feature.evidence_ids}, key=str
    )
    explanation = (
        f"{band.value} analyst alert from structural severity {risk.severity.value:.1f}/100, "
        f"confidence {risk.confidence.value:.2f}, completeness {risk.completeness.value:.2f}. "
        f"{risk.corroboration.explanation}"
    )
    return AlertResult(
        alert_id=uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:risk-alert:{risk.fingerprint}:{rule.version}",
        ),
        risk_id=risk.risk_id,
        corridor_id=risk.corridor_id,
        severity_band=band,
        status=status,
        severity=risk.severity,
        confidence=risk.confidence,
        completeness=risk.completeness,
        contributions=risk.contributions,
        evidence_ids=evidence_ids,
        effective_at=risk.effective_at,
        created_at=at,
        model_version=risk.model_version,
        rule_version=rule.version,
        explanation=explanation,
        recommended_analyst_action=(
            "Review the linked evidence and source disagreement before operational escalation."
        ),
        risk_fingerprint=risk.fingerprint,
    )
