from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sanjiv.audit.contracts import (
    EvidenceAuditResult,
    PlanLifecycleRecord,
    PlanReviewState,
)


class AuditRepository(Protocol):
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def audit(self, plan_id: UUID, audit_fingerprint: str) -> EvidenceAuditResult | None: ...
    async def latest_audit(self, plan_id: UUID) -> EvidenceAuditResult | None: ...
    async def save_audit(self, audit: EvidenceAuditResult) -> None: ...
    async def records(self, plan_id: UUID) -> list[PlanLifecycleRecord]: ...
    async def append_record(
        self,
        record_factory: Callable[[list[PlanLifecycleRecord]], PlanLifecycleRecord],
        plan_id: UUID,
        idempotency_fingerprint: str,
    ) -> PlanLifecycleRecord: ...


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._audits: dict[tuple[UUID, str], EvidenceAuditResult] = {}
        self._records: dict[UUID, list[PlanLifecycleRecord]] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def audit(self, plan_id: UUID, audit_fingerprint: str) -> EvidenceAuditResult | None:
        return self._audits.get((plan_id, audit_fingerprint))

    async def latest_audit(self, plan_id: UUID) -> EvidenceAuditResult | None:
        values = [audit for (subject, _), audit in self._audits.items() if subject == plan_id]
        return max(values, key=lambda item: item.audited_at) if values else None

    async def save_audit(self, audit: EvidenceAuditResult) -> None:
        self._audits.setdefault((audit.plan_id, audit.audit_fingerprint), audit)

    async def records(self, plan_id: UUID) -> list[PlanLifecycleRecord]:
        return list(self._records.get(plan_id, []))

    async def append_record(
        self,
        record_factory: Callable[[list[PlanLifecycleRecord]], PlanLifecycleRecord],
        plan_id: UUID,
        idempotency_fingerprint: str,
    ) -> PlanLifecycleRecord:
        async with self._lock:
            records = self._records.setdefault(plan_id, [])
            reused = next(
                (
                    item
                    for item in records
                    if item.idempotency_fingerprint == idempotency_fingerprint
                ),
                None,
            )
            if reused is not None:
                return reused
            record = record_factory(list(records))
            records.append(record)
            return record


class PostgresAuditRepository:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        await self._engine.dispose()

    async def audit(self, plan_id: UUID, audit_fingerprint: str) -> EvidenceAuditResult | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text(
                        "SELECT payload FROM evidence_audits "
                        "WHERE plan_id=:plan_id AND audit_fingerprint=:fingerprint"
                    ),
                    {"plan_id": plan_id, "fingerprint": audit_fingerprint},
                )
            ).scalar_one_or_none()
        return EvidenceAuditResult.model_validate(payload) if isinstance(payload, dict) else None

    async def latest_audit(self, plan_id: UUID) -> EvidenceAuditResult | None:
        async with self._engine.connect() as connection:
            payload = (
                await connection.execute(
                    text(
                        "SELECT payload FROM evidence_audits WHERE plan_id=:plan_id "
                        "ORDER BY audited_at DESC, audit_id DESC LIMIT 1"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalar_one_or_none()
        return EvidenceAuditResult.model_validate(payload) if isinstance(payload, dict) else None

    async def save_audit(self, audit: EvidenceAuditResult) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO evidence_audits(
                    audit_id,plan_id,plan_kind,status,audit_fingerprint,plan_fingerprint,
                    assumption_fingerprint,evidence_fingerprint,coverage_percentage,audited_at,payload
                    ) VALUES(
                    :audit_id,:plan_id,:plan_kind,:status,:audit_fingerprint,:plan_fingerprint,
                    :assumption_fingerprint,:evidence_fingerprint,:coverage,:audited_at,
                    CAST(:payload AS jsonb)
                    ) ON CONFLICT(audit_fingerprint) DO NOTHING"""
                ),
                {
                    "audit_id": audit.audit_id,
                    "plan_id": audit.plan_id,
                    "plan_kind": audit.plan_kind.value,
                    "status": audit.status.value,
                    "audit_fingerprint": audit.audit_fingerprint,
                    "plan_fingerprint": audit.fingerprints.plan,
                    "assumption_fingerprint": audit.fingerprints.assumptions,
                    "evidence_fingerprint": audit.fingerprints.evidence,
                    "coverage": audit.evidence_coverage_percentage,
                    "audited_at": audit.audited_at,
                    "payload": audit.model_dump_json(),
                },
            )

    async def records(self, plan_id: UUID) -> list[PlanLifecycleRecord]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT payload FROM plan_lifecycle_records "
                        "WHERE plan_id=:plan_id ORDER BY occurred_at, record_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalars()
            return [
                PlanLifecycleRecord.model_validate(item) for item in rows if isinstance(item, dict)
            ]

    async def append_record(
        self,
        record_factory: Callable[[list[PlanLifecycleRecord]], PlanLifecycleRecord],
        plan_id: UUID,
        idempotency_fingerprint: str,
    ) -> PlanLifecycleRecord:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(CAST(:plan_id AS text)))"),
                {"plan_id": str(plan_id)},
            )
            rows = (
                await connection.execute(
                    text(
                        "SELECT payload FROM plan_lifecycle_records "
                        "WHERE plan_id=:plan_id ORDER BY occurred_at, record_id"
                    ),
                    {"plan_id": plan_id},
                )
            ).scalars()
            records = [
                PlanLifecycleRecord.model_validate(item) for item in rows if isinstance(item, dict)
            ]
            reused = next(
                (
                    item
                    for item in records
                    if item.idempotency_fingerprint == idempotency_fingerprint
                ),
                None,
            )
            if reused is not None:
                return reused
            record = record_factory(records)
            await connection.execute(
                text(
                    """INSERT INTO plan_lifecycle_records(
                    record_id,plan_id,plan_kind,action,previous_state,state,actor_id,actor_role,
                    occurred_at,plan_fingerprint,assumption_fingerprint,audit_fingerprint,
                    idempotency_fingerprint,payload
                    ) VALUES(
                    :record_id,:plan_id,:plan_kind,:action,:previous_state,:state,:actor_id,:actor_role,
                    :occurred_at,:plan_fingerprint,:assumption_fingerprint,:audit_fingerprint,
                    :idempotency_fingerprint,CAST(:payload AS jsonb))"""
                ),
                {
                    "record_id": record.record_id,
                    "plan_id": record.plan_id,
                    "plan_kind": record.plan_kind.value,
                    "action": record.action.value,
                    "previous_state": record.previous_state.value,
                    "state": record.state.value,
                    "actor_id": record.actor_id,
                    "actor_role": record.actor_role.value,
                    "occurred_at": record.occurred_at,
                    "plan_fingerprint": record.plan_fingerprint,
                    "assumption_fingerprint": record.assumption_fingerprint,
                    "audit_fingerprint": record.audit_fingerprint,
                    "idempotency_fingerprint": record.idempotency_fingerprint,
                    "payload": record.model_dump_json(),
                },
            )
            return record


def current_state(records: list[PlanLifecycleRecord]) -> PlanReviewState:
    return records[-1].state if records else PlanReviewState.RECOMMENDED
