from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sanjiv.contracts import (
    Assumption,
    AuditEvent,
    AuditOutcome,
    DataMode,
    EvidenceRecord,
    FreshnessStatus,
    MetricEnvelope,
    SourceHealthRecord,
    SourceRef,
    SourceState,
    TruthClass,
)

if TYPE_CHECKING:
    from sanjiv.main import FoundationContractSample


def build_foundation_sample(now: datetime | None = None) -> "FoundationContractSample":
    from sanjiv.main import FoundationContractSample

    timestamp = now or datetime.now(UTC)
    evidence = EvidenceRecord(
        source_id="SANJIV_FIXTURE",
        source_record_id="phase-0-sample",
        dataset="foundation-contract-sample",
        dataset_version="1.0.0",
        effective_at=timestamp,
        fetched_at=timestamp,
        mode=DataMode.FIXTURE,
        truth_class=TruthClass.ASSUMPTION,
        raw_payload_hash="0" * 64,
        transformation="fixture.identity.v1",
        confidence=1.0,
        license="Project fixture; not operational data",
    )
    assumption = Assumption(
        key="sample_inventory_cover",
        value=8.0,
        unit="day",
        rationale="Demonstrates the mandatory metric envelope only",
        source_gap="No operational inventory is included in Phase 0",
        owner="system-fixture",
        entered_at=timestamp,
        effective_at=timestamp,
    )
    metric = MetricEnvelope[float](
        value=8.0,
        unit="day",
        truth_class=TruthClass.ASSUMPTION,
        confidence=1.0,
        evidence_ids=[evidence.id],
        source_refs=[SourceRef(source_id=evidence.source_id, record_id=evidence.source_record_id)],
        effective_at=timestamp,
        fetched_at=timestamp,
        computed_at=timestamp,
        freshness_status=FreshnessStatus.CURRENT,
        transformation="fixture.identity.v1",
        model_version="foundation-contracts-0.1.0",
    )
    health = SourceHealthRecord(
        source_id="SANJIV_FIXTURE",
        state=SourceState.READY,
        checked_at=timestamp,
        last_success_at=timestamp,
        message_count=1,
        mode=DataMode.FIXTURE,
        freshness_status=FreshnessStatus.CURRENT,
    )
    audit = AuditEvent(
        occurred_at=timestamp,
        actor_id="system-fixture",
        actor_type="SERVICE",
        action="foundation.sample.created",
        resource_type="metric",
        resource_id="sample_inventory_cover",
        after_hash="0" * 64,
        correlation_id=uuid4(),
        outcome=AuditOutcome.SUCCEEDED,
    )
    return FoundationContractSample(
        metric=metric,
        evidence=evidence,
        source_health=health,
        assumption=assumption,
        audit_event=audit,
    )
