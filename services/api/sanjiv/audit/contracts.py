from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import to_jsonable_python

SHA256_PATTERN = r"^[a-f0-9]{64}$"


class PlanKind(StrEnum):
    PROCUREMENT = "PROCUREMENT"
    RESERVE = "RESERVE"


class EvidenceAuditStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class AuditFailureCode(StrEnum):
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_HASH_MISMATCH = "EVIDENCE_HASH_MISMATCH"
    EVIDENCE_PARENT_MISSING = "EVIDENCE_PARENT_MISSING"
    ASSUMPTION_MISSING = "ASSUMPTION_MISSING"
    ASSUMPTION_HASH_MISMATCH = "ASSUMPTION_HASH_MISMATCH"
    ASSUMPTION_NOT_APPROVED = "ASSUMPTION_NOT_APPROVED"
    ASSUMPTION_EXPIRED = "ASSUMPTION_EXPIRED"
    ASSUMPTION_SUPERSEDED = "ASSUMPTION_SUPERSEDED"
    ASSUMPTION_SCOPE_MISMATCH = "ASSUMPTION_SCOPE_MISMATCH"
    METRIC_PROVENANCE_MISSING = "METRIC_PROVENANCE_MISSING"
    METRIC_STALE = "METRIC_STALE"
    TRUTH_TRANSITION_INVALID = "TRUTH_TRANSITION_INVALID"
    SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"
    TRANSFORMATION_INCOMPLETE = "TRANSFORMATION_INCOMPLETE"
    VERSION_MISSING = "VERSION_MISSING"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    RECOMPUTATION_MISMATCH = "RECOMPUTATION_MISMATCH"
    SOLVER_NOT_USABLE = "SOLVER_NOT_USABLE"
    CHECKER_FAILED = "CHECKER_FAILED"
    SANCTIONS_EXCLUSION_FAILED = "SANCTIONS_EXCLUSION_FAILED"
    COMPATIBILITY_EXCLUSION_FAILED = "COMPATIBILITY_EXCLUSION_FAILED"
    CLAIM_POLICY_FAILED = "CLAIM_POLICY_FAILED"


class AuditFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: AuditFailureCode
    path: str = Field(min_length=1, max_length=500)
    message: str = Field(min_length=1, max_length=1000)
    blocking: Literal[True] = True


class AuditedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(min_length=1, max_length=500)
    value: int | float | str | bool
    unit: str
    truth_class: str
    freshness_status: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID]
    source_count: int = Field(ge=0)
    transformation: str
    model_version: str
    recomputation_hash: str = Field(pattern=SHA256_PATTERN)
    status: EvidenceAuditStatus
    failures: list[AuditFailure] = Field(default_factory=list)


class AuditFingerprintSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan: str = Field(pattern=SHA256_PATTERN)
    assumptions: str = Field(pattern=SHA256_PATTERN)
    evidence: str = Field(pattern=SHA256_PATTERN)
    scenario: str = Field(pattern=SHA256_PATTERN)
    simulation: str = Field(pattern=SHA256_PATTERN)
    twin: str = Field(pattern=SHA256_PATTERN)
    procurement: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reserve: str | None = Field(default=None, pattern=SHA256_PATTERN)


class EvidenceAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    audit_id: UUID
    plan_id: UUID
    plan_kind: PlanKind
    status: EvidenceAuditStatus
    audited_at: datetime
    auditor_version: Literal["evidence-auditor-v1"] = "evidence-auditor-v1"
    formula_registry_version: Literal["decision-formulas-v1"] = "decision-formulas-v1"
    claim_policy_version: Literal["claim-language-policy-v1"] = "claim-language-policy-v1"
    fingerprints: AuditFingerprintSet
    metrics: list[AuditedMetric]
    failures: list[AuditFailure]
    evidence_count: int = Field(ge=0)
    assumption_count: int = Field(ge=0)
    covered_metric_count: int = Field(ge=0)
    total_metric_count: int = Field(ge=0)
    evidence_coverage_percentage: float = Field(ge=0, le=100)
    solver_status: str
    solver_version: str
    model_version: str
    checker_version: str
    checker_passed: bool
    sanctions_exclusion_passed: bool
    compatibility_exclusion_passed: bool
    recomputation_passed: bool
    claim_language_passed: bool
    usable: bool
    approval_allowed: bool
    export_allowed: bool
    definitive_narrative_allowed: bool
    audit_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_status(self) -> EvidenceAuditResult:
        passed = not self.failures and all(
            item.status is EvidenceAuditStatus.PASSED for item in self.metrics
        )
        if (self.status is EvidenceAuditStatus.PASSED) != passed:
            raise ValueError("audit status must match structured failures")
        if (
            any(
                (
                    self.usable,
                    self.approval_allowed,
                    self.export_allowed,
                    self.definitive_narrative_allowed,
                )
            )
            != passed
        ):
            raise ValueError("failed audit must block every decision presentation path")
        payload = self.model_dump(
            mode="json", exclude={"audit_fingerprint", "audit_id", "audited_at"}
        )
        if self.audit_fingerprint != canonical_hash(payload):
            raise ValueError("audit fingerprint mismatch")
        return self


class ExplanationConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    satisfied: bool
    detail: str


class ExplanationAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    subject_id: UUID
    reason_codes: list[str]
    explanation: str


class PlanExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: UUID
    plan_kind: PlanKind
    audit_id: UUID
    audit_fingerprint: str = Field(pattern=SHA256_PATTERN)
    usable: bool
    blocked_reasons: list[str]
    summary: str
    hard_constraints: list[ExplanationConstraint]
    objective_components: dict[str, float]
    profile_weights: dict[str, float]
    primary_tradeoffs: list[str]
    allocation_rationale: list[str]
    rejected_alternatives: list[ExplanationAlternative]
    evidence_ids: list[UUID]
    assumption_ids: list[UUID]
    sensitivity_drivers: list[str]
    residual_shortage: float | None
    residual_shortage_unit: str | None
    difference_from_no_action: str
    model_version: str
    solver_version: str
    checker_version: str
    auditor_version: str
    deterministic: Literal[True] = True
    generated_at: datetime
    no_execution_notice: str = (
        "Decision support only: Sanjiv does not place orders, charter vessels, "
        "release reserves, or control operations."
    )


class GovernanceRole(StrEnum):
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    ADMINISTRATOR = "administrator"


class PlanReviewState(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class LifecycleAction(StrEnum):
    SUBMIT_FOR_REVIEW = "SUBMIT_FOR_REVIEW"
    REVIEW = "REVIEW"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    SUPERSEDE = "SUPERSEDE"


class PlanLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    assumption_fingerprint: str = Field(pattern=SHA256_PATTERN)
    audit_fingerprint: str = Field(pattern=SHA256_PATTERN)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRequest(PlanLifecycleRequest):
    action: Literal[LifecycleAction.SUBMIT_FOR_REVIEW, LifecycleAction.REVIEW]


class ApprovalRequest(PlanLifecycleRequest):
    comment: str = Field(min_length=3, max_length=2000)


class RejectionRequest(PlanLifecycleRequest):
    comment: str = Field(min_length=3, max_length=2000)


class SupersedeRequest(PlanLifecycleRequest):
    comment: str = Field(min_length=3, max_length=2000)
    superseding_plan_id: UUID


class PlanLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    record_id: UUID
    plan_id: UUID
    plan_kind: PlanKind
    action: LifecycleAction
    previous_state: PlanReviewState
    state: PlanReviewState
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: GovernanceRole
    occurred_at: datetime
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    assumption_fingerprint: str = Field(pattern=SHA256_PATTERN)
    audit_fingerprint: str = Field(pattern=SHA256_PATTERN)
    comment: str | None = Field(default=None, max_length=2000)
    superseding_plan_id: UUID | None = None
    idempotency_fingerprint: str = Field(pattern=SHA256_PATTERN)


class PlanGovernanceState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: UUID
    state: PlanReviewState
    records: list[PlanLifecycleRecord]
    latest_audit: EvidenceAuditResult
    superseded_warning: str | None = None
    no_execution_notice: str = (
        "Approval records a human decision only; it does not execute procurement "
        "or reserve actions."
    )


def canonical_hash(value: Any) -> str:
    payload = to_jsonable_python(value, serialize_unknown=True)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
