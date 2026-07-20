from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sanjiv.contracts import (
    Assumption,
    AssumptionStatus,
    FreshnessStatus,
    MetricEnvelope,
    SourceRef,
    TruthClass,
)
from sanjiv.sample import build_foundation_sample


def test_foundation_sample_is_explicit_fixture_assumption() -> None:
    sample = build_foundation_sample(datetime(2026, 7, 20, tzinfo=UTC))
    assert sample.metric.truth_class is TruthClass.ASSUMPTION
    assert sample.metric.freshness_status is FreshnessStatus.CURRENT
    assert sample.evidence.mode.value == "FIXTURE"
    assert sample.metric.evidence_ids == [sample.evidence.id]


def test_metric_rejects_timestamp_inversion() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    with pytest.raises(ValidationError, match="effective_at must not be after fetched_at"):
        MetricEnvelope[float](
            value=1.0,
            unit="tonne",
            truth_class=TruthClass.OBSERVED,
            confidence=1.0,
            evidence_ids=[uuid4()],
            source_refs=[SourceRef(source_id="test", record_id="1")],
            effective_at=now + timedelta(seconds=1),
            fetched_at=now,
            computed_at=now,
            freshness_status=FreshnessStatus.LIVE,
            transformation="test.identity.v1",
            model_version="test-1",
        )


def test_metric_requires_evidence() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    with pytest.raises(ValidationError):
        MetricEnvelope[float](
            value=1.0,
            unit="tonne",
            truth_class=TruthClass.OBSERVED,
            confidence=1.0,
            evidence_ids=[],
            source_refs=[],
            effective_at=now,
            fetched_at=now,
            computed_at=now,
            freshness_status=FreshnessStatus.LIVE,
            transformation="test.identity.v1",
            model_version="test-1",
        )


def test_approved_assumption_requires_approver() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    with pytest.raises(ValidationError, match="approved assumptions require approved_by"):
        Assumption(
            key="reserve_floor",
            value=0.2,
            unit="fraction",
            rationale="Policy test",
            source_gap="No public operational value",
            owner="tester",
            entered_at=now,
            effective_at=now,
            status=AssumptionStatus.APPROVED,
        )
