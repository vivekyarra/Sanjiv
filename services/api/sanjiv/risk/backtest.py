from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sanjiv.risk.adapters.fixture import FixtureRiskAdapter
from sanjiv.risk.alerts import evaluate_alert
from sanjiv.risk.contracts import (
    AlertSeverity,
    AlertStatus,
    BacktestCaseResult,
    BacktestResult,
    backtest_fingerprint,
)
from sanjiv.risk.engine import MODEL_VERSION, build_baselines, calculate_corridor_risk


async def run_fixture_backtest(adapter: FixtureRiskAdapter) -> BacktestResult:
    started = time.perf_counter()
    at = datetime(2026, 7, 21, 12, tzinfo=UTC)
    baselines = build_baselines(adapter.baseline(), at=at)
    cases = []
    for raw in adapter.cases():
        case_started = time.perf_counter()
        case_id = raw.case_id
        result = await adapter.fetch(case_id)
        corridor_id = result.signals[0].corridor_id
        risk = calculate_corridor_risk(
            corridor_id,
            raw.corridor,
            result.signals,
            baselines,
            result.failures,
            calculated_at=at,
        )
        alert = evaluate_alert(risk, created_at=at)
        actual = alert.status is AlertStatus.OPEN and alert.severity_band in {
            AlertSeverity.HIGH,
            AlertSeverity.CRITICAL,
        }
        expected = raw.expected_alert
        cases.append(
            BacktestCaseResult(
                case_id=case_id,
                label=raw.label,
                expected_alert=expected,
                actual_alert=actual,
                severity=risk.severity,
                confidence=risk.confidence,
                completeness=risk.completeness,
                lead_time_hours=raw.lead_hours if actual and expected else 0.0,
                runtime_ms=(time.perf_counter() - case_started) * 1000,
                stable=actual == expected,
            )
        )
    true_positives = sum(item.expected_alert and item.actual_alert for item in cases)
    emitted = sum(item.actual_alert for item in cases)
    false_positives = sum(not item.expected_alert and item.actual_alert for item in cases)
    detected_leads = [
        item.lead_time_hours for item in cases if item.expected_alert and item.actual_alert
    ]
    manifest = adapter.manifest
    payload = {
        "backtest_id": uuid5(
            NAMESPACE_URL,
            f"urn:sanjiv:risk-backtest:{manifest.checksum_sha256}:{MODEL_VERSION}",
        ),
        "library_id": manifest.dataset_id,
        "classification": manifest.classification,
        "checksum_sha256": manifest.checksum_sha256,
        "model_version": MODEL_VERSION,
        "cases": cases,
        "detection_lead_time_hours": (
            sum(detected_leads) / len(detected_leads) if detected_leads else 0.0
        ),
        "precision": true_positives / emitted if emitted else 0.0,
        "false_positives": false_positives,
        "mean_completeness": sum(item.completeness.value for item in cases) / len(cases),
        "source_failure_case_count": sum(item.completeness.value < 1 for item in cases),
        "alert_stability": sum(item.stable for item in cases) / len(cases),
        "runtime_ms": (time.perf_counter() - started) * 1000,
        "fixture_evidence_only": True,
    }
    return BacktestResult(**payload, fingerprint=backtest_fingerprint(payload))
