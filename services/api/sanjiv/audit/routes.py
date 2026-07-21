from __future__ import annotations

import secrets
from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request

from sanjiv.audit.contracts import (
    ApprovalRequest,
    EvidenceAuditResult,
    GovernanceRole,
    LifecycleAction,
    PlanExplanation,
    PlanGovernanceState,
    PlanLifecycleRecord,
    RejectionRequest,
    ReviewRequest,
    SupersedeRequest,
)
from sanjiv.audit.service import AuditDomainError, AuditService
from sanjiv.contracts import Assumption, EvidenceRecord
from sanjiv.scenarios.routes import DomainErrorResponse
from sanjiv.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["evidence-auditor"])


def _service(request: Request) -> AuditService:
    service: AuditService = request.app.state.audit_service
    return service


def _raise(error: AuditDomainError) -> NoReturn:
    payload = DomainErrorResponse(
        code=error.code, message=error.message, correlation_id=uuid4(), details={}
    )
    raise HTTPException(status_code=error.status_code, detail=payload.model_dump(mode="json"))


def resolve_governance_identity(
    request: Request, supplied_identity: str | None, supplied_key: str | None
) -> tuple[str, GovernanceRole]:
    settings: Settings = request.app.state.settings
    if settings.sanjiv_env in {"development", "test"}:
        actor = supplied_identity or settings.sanjiv_demo_identity
        configured_role = settings.demo_identities.get(actor)
        if configured_role is None:
            raise AuditDomainError(
                "IDENTITY_UNAUTHENTICATED", "Unknown configured demo identity.", status_code=401
            )
        try:
            return actor, GovernanceRole(configured_role)
        except ValueError as exc:
            raise AuditDomainError(
                "ROLE_CONFIGURATION_INVALID", "Invalid configured demo role.", status_code=503
            ) from exc
    configured = settings.governance_api_keys
    if not configured:
        raise AuditDomainError(
            "IDENTITY_CONFIGURATION_MISSING",
            (
                "Production governance fails closed until authenticated identities "
                "and roles are configured."
            ),
            status_code=503,
        )
    if supplied_key is None:
        raise AuditDomainError(
            "IDENTITY_UNAUTHENTICATED", "Governance credential required.", status_code=401
        )
    identity: dict[str, str] | None = None
    for key, value in configured.items():
        if secrets.compare_digest(key, supplied_key):
            identity = value
    if identity is None:
        raise AuditDomainError(
            "IDENTITY_UNAUTHENTICATED", "Invalid governance credential.", status_code=401
        )
    try:
        return identity["actor_id"], GovernanceRole(identity["role"])
    except (KeyError, ValueError) as exc:
        raise AuditDomainError(
            "IDENTITY_CONFIGURATION_INVALID",
            "Invalid configured governance identity.",
            status_code=503,
        ) from exc


@router.get("/evidence/{evidence_id}", response_model=EvidenceRecord)
async def evidence(evidence_id: UUID, request: Request) -> EvidenceRecord:
    try:
        return await _service(request).evidence(evidence_id)
    except AuditDomainError as error:
        _raise(error)


@router.get("/plans/{plan_id}/assumptions", response_model=list[Assumption])
async def assumptions(plan_id: UUID, request: Request) -> list[Assumption]:
    try:
        return await _service(request).assumptions(plan_id)
    except AuditDomainError as error:
        _raise(error)


@router.get("/plans/{plan_id}/audit", response_model=EvidenceAuditResult)
async def audit(plan_id: UUID, request: Request) -> EvidenceAuditResult:
    try:
        return await _service(request).audit_plan(plan_id)
    except (AuditDomainError, ValueError) as error:
        if isinstance(error, AuditDomainError):
            _raise(error)
        _raise(AuditDomainError("AUDIT_INPUT_INVALID", str(error), status_code=422))


@router.get("/plans/{plan_id}/explanation", response_model=PlanExplanation)
async def explanation(plan_id: UUID, request: Request) -> PlanExplanation:
    try:
        return await _service(request).explanation(plan_id)
    except AuditDomainError as error:
        _raise(error)


@router.get("/plans/{plan_id}/governance", response_model=PlanGovernanceState)
async def governance(plan_id: UUID, request: Request) -> PlanGovernanceState:
    try:
        return await _service(request).lifecycle(plan_id)
    except AuditDomainError as error:
        _raise(error)


@router.get("/plans/{plan_id}/reviews", response_model=list[PlanLifecycleRecord])
async def reviews(plan_id: UUID, request: Request) -> list[PlanLifecycleRecord]:
    return (await governance(plan_id, request)).records


async def _act(
    plan_id: UUID,
    payload: ReviewRequest | ApprovalRequest | RejectionRequest | SupersedeRequest,
    request: Request,
    action: LifecycleAction,
    idempotency_key: str,
    demo_identity: str | None,
    governance_key: str | None,
    superseding_plan_id: UUID | None = None,
) -> PlanLifecycleRecord:
    try:
        actor_id, actor_role = resolve_governance_identity(request, demo_identity, governance_key)
        return await _service(request).act(
            plan_id,
            payload,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            idempotency_key=idempotency_key,
            superseding_plan_id=superseding_plan_id,
        )
    except AuditDomainError as error:
        _raise(error)


@router.post("/plans/{plan_id}/reviews", response_model=PlanLifecycleRecord)
async def create_review(
    plan_id: UUID,
    payload: ReviewRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    demo_identity: str | None = Header(default=None, alias="X-Sanjiv-Demo-Identity"),
    governance_key: str | None = Header(default=None, alias="X-Sanjiv-Governance-Key"),
) -> PlanLifecycleRecord:
    return await _act(
        plan_id, payload, request, payload.action, idempotency_key, demo_identity, governance_key
    )


@router.post("/plans/{plan_id}/approvals", response_model=PlanLifecycleRecord)
async def approve(
    plan_id: UUID,
    payload: ApprovalRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    demo_identity: str | None = Header(default=None, alias="X-Sanjiv-Demo-Identity"),
    governance_key: str | None = Header(default=None, alias="X-Sanjiv-Governance-Key"),
) -> PlanLifecycleRecord:
    return await _act(
        plan_id,
        payload,
        request,
        LifecycleAction.APPROVE,
        idempotency_key,
        demo_identity,
        governance_key,
    )


@router.post("/plans/{plan_id}/rejections", response_model=PlanLifecycleRecord)
async def reject(
    plan_id: UUID,
    payload: RejectionRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    demo_identity: str | None = Header(default=None, alias="X-Sanjiv-Demo-Identity"),
    governance_key: str | None = Header(default=None, alias="X-Sanjiv-Governance-Key"),
) -> PlanLifecycleRecord:
    return await _act(
        plan_id,
        payload,
        request,
        LifecycleAction.REJECT,
        idempotency_key,
        demo_identity,
        governance_key,
    )


@router.post("/plans/{plan_id}/supersessions", response_model=PlanLifecycleRecord)
async def supersede(
    plan_id: UUID,
    payload: SupersedeRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    demo_identity: str | None = Header(default=None, alias="X-Sanjiv-Demo-Identity"),
    governance_key: str | None = Header(default=None, alias="X-Sanjiv-Governance-Key"),
) -> PlanLifecycleRecord:
    return await _act(
        plan_id,
        payload,
        request,
        LifecycleAction.SUPERSEDE,
        idempotency_key,
        demo_identity,
        governance_key,
        payload.superseding_plan_id,
    )
