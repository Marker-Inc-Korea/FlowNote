from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import ROLE_SYSTEM_ADMIN, AuthenticatedUser, require_roles
from app.core.config import Settings, get_settings
from app.db.models import (
    AICallAttempt,
    AIOperationAuditEvent,
    AIOperationalPolicy,
    AIProviderOnboardingReview,
    AIPromptVersion,
    AIQuery,
    AIQueryCitation,
    AIQueryEvidenceCandidate,
    AIQueryLegalHold,
    AIRetentionAudit,
    AITransferApproval,
)
from app.db.session import get_db_session
from app.services.ai_operations import active_policy, audit_event, run_retention, utc

router = APIRouter(prefix="/ai-operations", tags=["ai-operations"])
SystemAdmin = Annotated[AuthenticatedUser, Depends(require_roles(ROLE_SYSTEM_ADMIN))]
Db = Annotated[Session, Depends(get_db_session)]
Cfg = Annotated[Settings, Depends(get_settings)]
PURPOSES = {"EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"}
SOURCE_TYPES = {
    "PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"
}
PROVIDER_CHECKLIST_KEYS = {
    "contract_terms", "data_retention", "training_use", "transfer_region", "tls",
    "timeout", "rate_limit_429", "server_error_5xx", "cost_limit", "kill_switch",
    "legal_approval", "customer_approval",
}


def _clean_list(values: list[str], allowed: set[str], name: str) -> list[str]:
    cleaned = sorted({value.strip().upper() for value in values if value.strip()})
    if not cleaned or any(value not in allowed for value in cleaned):
        raise ValueError(f"invalid {name}")
    return cleaned


def _approval_dict(row: AITransferApproval) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    status = "REVOKED" if row.revoked_at else "EXPIRED" if utc(row.expires_at) <= now else "ACTIVE"
    return {
        "approvalId": row.approval_id, "customerScope": row.customer_scope,
        "siteScope": row.site_scope, "provider": row.provider, "modelScope": row.model_scope,
        "purposes": json.loads(row.allowed_purposes or "[]"),
        "sourceTypes": json.loads(row.allowed_source_types), "status": status,
        "approvedBy": row.approved_by, "approvedAt": row.approved_at,
        "expiresAt": row.expires_at, "revokedAt": row.revoked_at, "reason": row.reason,
        "dataHandlingPolicyVersion": row.data_handling_policy_version,
    }


def _prompt_status(row: AIPromptVersion) -> str:
    if row.retired_at:
        return "RETIRED"
    if row.activated_at:
        return "ACTIVE"
    if row.approved_at:
        return "APPROVED"
    if row.reviewed_at:
        return "REVIEWED"
    return "DRAFT"


def _prompt_dict(row: AIPromptVersion) -> dict[str, object]:
    return {
        "promptVersionId": row.prompt_version_id, "name": row.name, "version": row.version,
        "templateHash": row.template_hash, "templateText": row.template_text,
        "allowedPurpose": row.allowed_purpose, "status": _prompt_status(row),
        "createdBy": row.created_by, "reviewedBy": row.reviewed_by,
        "reviewedAt": row.reviewed_at, "approvedBy": row.approved_by,
        "approvedAt": row.approved_at, "activatedAt": row.activated_at,
        "retiredAt": row.retired_at, "createdAt": row.created_at,
    }


class ApprovalCreate(BaseModel):
    customer_scope: str = Field(alias="customerScope", min_length=1, max_length=120)
    site_scope: str = Field(alias="siteScope", min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    model_scope: str = Field(alias="modelScope", min_length=1, max_length=120)
    purposes: list[str]
    source_types: list[str] = Field(alias="sourceTypes")
    data_handling_policy_version: str = Field(alias="dataHandlingPolicyVersion", min_length=1, max_length=80)
    expires_at: datetime = Field(alias="expiresAt")
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("purposes")
    @classmethod
    def purposes_valid(cls, value: list[str]) -> list[str]:
        return _clean_list(value, PURPOSES, "purposes")

    @field_validator("source_types")
    @classmethod
    def sources_valid(cls, value: list[str]) -> list[str]:
        return _clean_list(value, SOURCE_TYPES, "sourceTypes")


class ProviderChecklistItem(BaseModel):
    status: Literal["PENDING", "PASS", "FAIL"]
    note: str = Field(min_length=1, max_length=2000)
    evidence_reference: str | None = Field(default=None, alias="evidenceReference", max_length=500)


class ProviderReviewCreate(BaseModel):
    customer_scope: str = Field(alias="customerScope", min_length=1, max_length=120)
    site_scope: str = Field(alias="siteScope", min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    model_scope: str = Field(alias="modelScope", min_length=1, max_length=120)
    review_version: str = Field(alias="reviewVersion", min_length=1, max_length=80)
    allowed_purposes: list[str] = Field(alias="allowedPurposes")
    checklist: dict[str, ProviderChecklistItem]
    technical_status: Literal["PENDING", "APPROVED", "REJECTED"] = Field(alias="technicalStatus")
    security_status: Literal["PENDING", "APPROVED", "REJECTED"] = Field(alias="securityStatus")
    legal_status: Literal["PENDING", "APPROVED", "REJECTED"] = Field(alias="legalStatus")
    customer_status: Literal["PENDING", "APPROVED", "REJECTED"] = Field(alias="customerStatus")

    @field_validator("allowed_purposes")
    @classmethod
    def purposes_valid(cls, value: list[str]) -> list[str]:
        return _clean_list(value, PURPOSES, "allowedPurposes")

    @field_validator("checklist")
    @classmethod
    def checklist_complete(cls, value: dict[str, ProviderChecklistItem]) -> dict[str, ProviderChecklistItem]:
        if set(value) != PROVIDER_CHECKLIST_KEYS:
            missing = sorted(PROVIDER_CHECKLIST_KEYS - set(value))
            extra = sorted(set(value) - PROVIDER_CHECKLIST_KEYS)
            raise ValueError(f"provider checklist keys mismatch; missing={missing}, extra={extra}")
        if any(item.status == "PASS" and not item.evidence_reference for item in value.values()):
            raise ValueError("PASS provider checklist items require evidenceReference")
        return value


def _provider_review_dict(row: AIProviderOnboardingReview) -> dict[str, object]:
    statuses = {
        "technical": row.technical_status,
        "security": row.security_status,
        "legal": row.legal_status,
        "customer": row.customer_status,
    }
    checklist = json.loads(row.checklist_json)
    checklist_passed = all(item.get("status") == "PASS" for item in checklist.values())
    return {
        "reviewId": row.review_id,
        "customerScope": row.customer_scope,
        "siteScope": row.site_scope,
        "provider": row.provider,
        "modelScope": row.model_scope,
        "reviewVersion": row.review_version,
        "allowedPurposes": json.loads(row.allowed_purposes_json),
        "checklist": checklist,
        "statuses": statuses,
        "reviewedBy": {
            "technical": row.technical_reviewed_by,
            "security": row.security_reviewed_by,
            "legal": row.legal_reviewed_by,
            "customer": row.customer_reviewed_by,
        },
        "reviewedAt": {
            "technical": row.technical_reviewed_at,
            "security": row.security_reviewed_at,
            "legal": row.legal_reviewed_at,
            "customer": row.customer_reviewed_at,
        },
        "checklistPassed": checklist_passed,
        "providerStartApproved": checklist_passed and all(value == "APPROVED" for value in statuses.values()),
        "createdBy": row.created_by,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


@router.get("/provider-reviews")
def list_provider_reviews(
    _: SystemAdmin,
    session: Db,
    customer_scope: Annotated[str | None, Query(alias="customerScope")] = None,
    site_scope: Annotated[str | None, Query(alias="siteScope")] = None,
) -> list[dict[str, object]]:
    statement = select(AIProviderOnboardingReview)
    if customer_scope:
        statement = statement.where(AIProviderOnboardingReview.customer_scope == customer_scope)
    if site_scope:
        statement = statement.where(AIProviderOnboardingReview.site_scope == site_scope)
    rows = session.scalars(statement.order_by(AIProviderOnboardingReview.created_at.desc())).all()
    return [_provider_review_dict(row) for row in rows]


@router.post("/provider-reviews", status_code=201)
def create_provider_review(
    payload: ProviderReviewCreate,
    user: SystemAdmin,
    session: Db,
) -> dict[str, object]:
    duplicate = session.scalar(select(AIProviderOnboardingReview.id).where(
        AIProviderOnboardingReview.customer_scope == payload.customer_scope.strip(),
        AIProviderOnboardingReview.site_scope == payload.site_scope.strip(),
        AIProviderOnboardingReview.provider == payload.provider.strip(),
        AIProviderOnboardingReview.model_scope == payload.model_scope.strip(),
        AIProviderOnboardingReview.review_version == payload.review_version.strip(),
    ))
    if duplicate is not None:
        raise HTTPException(409, "같은 scope/provider/model/reviewVersion 심사가 이미 있습니다.")
    checklist = {
        key: item.model_dump(by_alias=True, mode="json")
        for key, item in sorted(payload.checklist.items())
    }
    if any(status == "APPROVED" for status in (
        payload.technical_status, payload.security_status, payload.legal_status, payload.customer_status
    )) and any(item["status"] != "PASS" for item in checklist.values()):
        raise HTTPException(422, "모든 체크리스트가 PASS이기 전에는 승인 상태를 기록할 수 없습니다.")
    now = datetime.now(timezone.utc)
    row = AIProviderOnboardingReview(
        review_id=f"aipr-{uuid4().hex}",
        customer_scope=payload.customer_scope.strip(), site_scope=payload.site_scope.strip(),
        provider=payload.provider.strip(), model_scope=payload.model_scope.strip(),
        review_version=payload.review_version.strip(),
        checklist_json=json.dumps(checklist, ensure_ascii=False, sort_keys=True),
        allowed_purposes_json=json.dumps(payload.allowed_purposes),
        technical_status=payload.technical_status, security_status=payload.security_status,
        legal_status=payload.legal_status, customer_status=payload.customer_status,
        technical_reviewed_by=user.user_id if payload.technical_status != "PENDING" else None,
        security_reviewed_by=user.user_id if payload.security_status != "PENDING" else None,
        legal_reviewed_by=user.user_id if payload.legal_status != "PENDING" else None,
        customer_reviewed_by=user.user_id if payload.customer_status != "PENDING" else None,
        technical_reviewed_at=now if payload.technical_status != "PENDING" else None,
        security_reviewed_at=now if payload.security_status != "PENDING" else None,
        legal_reviewed_at=now if payload.legal_status != "PENDING" else None,
        customer_reviewed_at=now if payload.customer_status != "PENDING" else None,
        created_by=user.user_id,
    )
    session.add(row)
    audit_event(
        session, event_type="PROVIDER_REVIEW_RECORDED", actor_id=user.user_id,
        customer_scope=row.customer_scope, site_scope=row.site_scope,
        target_type="PROVIDER_REVIEW", target_id=row.review_id,
        detail={"provider": row.provider, "modelScope": row.model_scope,
                "reviewVersion": row.review_version, "statuses": {
                    "technical": row.technical_status, "security": row.security_status,
                    "legal": row.legal_status, "customer": row.customer_status,
                }},
    )
    session.commit()
    return _provider_review_dict(row)


@router.get("/approvals")
def list_approvals(_: SystemAdmin, session: Db) -> list[dict[str, object]]:
    return [_approval_dict(row) for row in session.scalars(
        select(AITransferApproval).order_by(AITransferApproval.approved_at.desc())
    ).all()]


@router.post("/approvals", status_code=201)
def create_approval(payload: ApprovalCreate, user: SystemAdmin, session: Db) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    if utc(payload.expires_at) <= now:
        raise HTTPException(422, "승인 만료 시각은 현재 이후여야 합니다.")
    row = AITransferApproval(
        approval_id=f"aita-{uuid4().hex}", customer_scope=payload.customer_scope.strip(),
        site_scope=payload.site_scope.strip(), provider=payload.provider.strip(),
        model_scope=payload.model_scope.strip(), allowed_purposes=json.dumps(payload.purposes),
        allowed_source_types=json.dumps(payload.source_types),
        data_handling_policy_version=payload.data_handling_policy_version.strip(),
        approved_by=user.user_id, approved_at=now, expires_at=payload.expires_at,
        reason=payload.reason.strip(),
    )
    session.add(row)
    audit_event(session, event_type="APPROVAL_CREATED", actor_id=user.user_id,
                customer_scope=row.customer_scope, site_scope=row.site_scope,
                target_type="APPROVAL", target_id=row.approval_id,
                detail={"provider": row.provider, "modelScope": row.model_scope,
                        "purposes": payload.purposes, "sourceTypes": payload.source_types})
    session.commit()
    return _approval_dict(row)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class QueryMutationRequest(ReasonRequest):
    operation_key: str | None = Field(default=None, alias="operationKey", min_length=8, max_length=160)
    expected_state_tag: str | None = Field(default=None, alias="expectedStateTag", min_length=16, max_length=64)


@router.post("/approvals/{approval_id}/revoke")
def revoke_approval(approval_id: str, payload: ReasonRequest, user: SystemAdmin, session: Db) -> dict[str, object]:
    row = session.scalar(select(AITransferApproval).where(AITransferApproval.approval_id == approval_id))
    if row is None:
        raise HTTPException(404, "승인을 찾을 수 없습니다.")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        audit_event(session, event_type="APPROVAL_REVOKED", actor_id=user.user_id,
                    customer_scope=row.customer_scope, site_scope=row.site_scope,
                    target_type="APPROVAL", target_id=row.approval_id,
                    reason_code="APPROVAL_REVOKED", detail={"reason": payload.reason})
        session.commit()
    return _approval_dict(row)


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    template_text: str = Field(alias="templateText", min_length=1, max_length=50000)
    allowed_purpose: str = Field(alias="allowedPurpose")

    @field_validator("allowed_purpose")
    @classmethod
    def purpose_valid(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in PURPOSES:
            raise ValueError("invalid purpose")
        return cleaned


@router.get("/prompts")
def list_prompts(_: SystemAdmin, session: Db) -> list[dict[str, object]]:
    return [_prompt_dict(row) for row in session.scalars(
        select(AIPromptVersion).order_by(AIPromptVersion.created_at.desc())
    ).all()]


@router.post("/prompts", status_code=201)
def create_prompt(payload: PromptCreate, user: SystemAdmin, settings: Cfg, session: Db) -> dict[str, object]:
    template = payload.template_text.strip()
    row = AIPromptVersion(
        prompt_version_id=f"aipv-{uuid4().hex}", name=payload.name.strip(),
        version=payload.version.strip(), template_hash=hashlib.sha256(template.encode()).hexdigest(),
        template_text=template, allowed_purpose=payload.allowed_purpose, created_by=user.user_id,
    )
    session.add(row)
    audit_event(session, event_type="PROMPT_CREATED", actor_id=user.user_id,
                customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
                target_type="PROMPT", target_id=row.prompt_version_id,
                detail={"name": row.name, "version": row.version, "templateHash": row.template_hash})
    session.commit()
    return _prompt_dict(row)


def _prompt_action(prompt_version_id: str, action: Literal["review", "approve", "activate", "retire"],
                   reason: ReasonRequest, user: AuthenticatedUser, settings: Settings,
                   session: Session) -> dict[str, object]:
    row = session.scalar(select(AIPromptVersion).where(AIPromptVersion.prompt_version_id == prompt_version_id))
    if row is None:
        raise HTTPException(404, "프롬프트 버전을 찾을 수 없습니다.")
    now = datetime.now(timezone.utc)
    if action == "review":
        if row.reviewed_at or row.retired_at:
            raise HTTPException(409, "초안 상태의 프롬프트만 검토할 수 있습니다.")
        row.reviewed_by, row.reviewed_at = user.user_id, now
    elif action == "approve":
        if not row.reviewed_at or row.approved_at or row.retired_at:
            raise HTTPException(409, "검토 완료 상태의 프롬프트만 승인할 수 있습니다.")
        row.approved_by, row.approved_at = user.user_id, now
    elif action == "activate":
        if not row.approved_at or row.retired_at:
            raise HTTPException(409, "승인 완료 상태의 프롬프트만 활성화할 수 있습니다.")
        for previous in session.scalars(select(AIPromptVersion).where(
            AIPromptVersion.allowed_purpose == row.allowed_purpose,
            AIPromptVersion.activated_at.is_not(None), AIPromptVersion.retired_at.is_(None),
            AIPromptVersion.prompt_version_id != row.prompt_version_id,
        )).all():
            previous.retired_at = now
            audit_event(
                session, event_type="PROMPT_RETIRED", actor_id=user.user_id,
                customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
                target_type="PROMPT", target_id=previous.prompt_version_id,
                detail={"reason": "새 프롬프트 버전 활성화", "replacedBy": row.prompt_version_id,
                        "templateHash": previous.template_hash},
            )
        row.activated_at = now
    else:
        if row.retired_at:
            return _prompt_dict(row)
        row.retired_at = now
    event_names = {"review": "PROMPT_REVIEWED", "approve": "PROMPT_APPROVED",
                   "activate": "PROMPT_ACTIVATED", "retire": "PROMPT_RETIRED"}
    audit_event(session, event_type=event_names[action], actor_id=user.user_id,
                customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
                target_type="PROMPT", target_id=row.prompt_version_id,
                detail={"reason": reason.reason, "templateHash": row.template_hash})
    session.commit()
    return _prompt_dict(row)


@router.post("/prompts/{prompt_version_id}/review")
def review_prompt(prompt_version_id: str, payload: ReasonRequest, user: SystemAdmin, settings: Cfg, session: Db):
    return _prompt_action(prompt_version_id, "review", payload, user, settings, session)


@router.post("/prompts/{prompt_version_id}/approve")
def approve_prompt(prompt_version_id: str, payload: ReasonRequest, user: SystemAdmin, settings: Cfg, session: Db):
    return _prompt_action(prompt_version_id, "approve", payload, user, settings, session)


@router.post("/prompts/{prompt_version_id}/activate")
def activate_prompt(prompt_version_id: str, payload: ReasonRequest, user: SystemAdmin, settings: Cfg, session: Db):
    return _prompt_action(prompt_version_id, "activate", payload, user, settings, session)


@router.post("/prompts/{prompt_version_id}/retire")
def retire_prompt(prompt_version_id: str, payload: ReasonRequest, user: SystemAdmin, settings: Cfg, session: Db):
    return _prompt_action(prompt_version_id, "retire", payload, user, settings, session)


class PolicyUpdate(BaseModel):
    scope_type: Literal["GLOBAL", "SITE"] = Field(alias="scopeType")
    kill_switch_enabled: bool = Field(alias="killSwitchEnabled")
    max_requests_per_day: int = Field(alias="maxRequestsPerDay", ge=0, le=1_000_000)
    max_concurrency: int = Field(alias="maxConcurrency", ge=0, le=10_000)
    timeout_seconds: int = Field(alias="timeoutSeconds", ge=1, le=600)
    daily_cost_budget_micros: int = Field(alias="dailyCostBudgetMicros", ge=0)
    query_payload_retention_days: int = Field(alias="queryPayloadRetentionDays", ge=1, le=3650)
    response_retention_days: int = Field(alias="responseRetentionDays", ge=1, le=3650)
    audit_retention_days: int = Field(alias="auditRetentionDays", ge=30, le=3650)
    allow_audit_export: bool = Field(alias="allowAuditExport")
    reason: str = Field(min_length=1, max_length=2000)


def _policy_dict(row: AIOperationalPolicy, settings: Settings) -> dict[str, object]:
    env_name = f"FLOWNOTE_AI_{settings.ai_provider.upper().replace('-', '_')}_API_KEY"
    return {
        "policyId": row.policy_id, "scopeType": "GLOBAL" if row.site_scope == "*" else "SITE",
        "customerScope": row.customer_scope, "siteScope": row.site_scope,
        "killSwitchEnabled": row.kill_switch_enabled,
        "maxRequestsPerDay": row.max_requests_per_day, "maxConcurrency": row.max_concurrency,
        "timeoutSeconds": row.timeout_seconds, "dailyCostBudgetMicros": row.daily_cost_budget_micros,
        "queryPayloadRetentionDays": row.query_payload_retention_days,
        "responseRetentionDays": row.response_retention_days,
        "auditRetentionDays": row.audit_retention_days, "allowAuditExport": row.allow_audit_export,
        "reason": row.reason, "updatedBy": row.updated_by, "updatedAt": row.updated_at,
        "providerCredentialConfigured": bool(os.getenv(env_name)),
    }


@router.get("/policies")
def get_policies(_: SystemAdmin, settings: Cfg, session: Db) -> list[dict[str, object]]:
    global_policy, site_policy = active_policy(session, settings.ai_customer_scope, settings.ai_site_scope)
    return [_policy_dict(row, settings) for row in (global_policy, site_policy) if row]


@router.put("/policies")
def put_policy(payload: PolicyUpdate, user: SystemAdmin, settings: Cfg, session: Db) -> dict[str, object]:
    customer, site = ("*", "*") if payload.scope_type == "GLOBAL" else (
        settings.ai_customer_scope, settings.ai_site_scope
    )
    row = session.scalar(select(AIOperationalPolicy).where(
        AIOperationalPolicy.customer_scope == customer, AIOperationalPolicy.site_scope == site
    ))
    previous_kill_switch = row.kill_switch_enabled if row is not None else None
    if row is None:
        row = AIOperationalPolicy(policy_id=f"aiop-{uuid4().hex}", customer_scope=customer,
                                  site_scope=site, updated_by=user.user_id, reason=payload.reason)
        session.add(row)
    for field in ("kill_switch_enabled", "max_requests_per_day", "max_concurrency",
                  "timeout_seconds", "daily_cost_budget_micros", "query_payload_retention_days",
                  "response_retention_days", "audit_retention_days", "allow_audit_export"):
        setattr(row, field, getattr(payload, field))
    row.reason, row.updated_by, row.updated_at = payload.reason, user.user_id, datetime.now(timezone.utc)
    audit_event(session, event_type="KILL_SWITCH_CHANGED" if previous_kill_switch != payload.kill_switch_enabled else "POLICY_CHANGED",
                actor_id=user.user_id, customer_scope=customer, site_scope=site,
                target_type="POLICY", target_id=row.policy_id,
                reason_code="AI_KILL_SWITCH" if payload.kill_switch_enabled else None,
                detail={"killSwitchEnabled": payload.kill_switch_enabled, "reason": payload.reason})
    session.commit()
    return _policy_dict(row, settings)


@router.get("/audit/queries")
def query_audit(_: SystemAdmin, settings: Cfg, session: Db, status: str | None = None,
                block_code: str | None = Query(default=None, alias="blockCode"), limit: int = Query(100, ge=1, le=500)):
    statement = select(AIQuery).where(
        AIQuery.customer_scope == settings.ai_customer_scope,
        AIQuery.site_scope == settings.ai_site_scope,
    )
    if status:
        statement = statement.where(AIQuery.status == status)
    if block_code:
        statement = statement.where(AIQuery.block_code == block_code)
    rows = session.scalars(statement.order_by(AIQuery.created_at.desc()).limit(limit)).all()
    result = []
    for row in rows:
        evidence = session.scalars(select(AIQueryEvidenceCandidate).where(
            AIQueryEvidenceCandidate.query_id == row.query_id
        ).order_by(AIQueryEvidenceCandidate.rank)).all()
        citations = session.scalars(select(AIQueryCitation).where(
            AIQueryCitation.query_id == row.query_id
        ).order_by(AIQueryCitation.id)).all()
        attempts = session.scalars(select(AICallAttempt).where(
            AICallAttempt.query_id == row.query_id
        ).order_by(AICallAttempt.id)).all()
        try:
            approval_id = json.loads(row.approval_snapshot_json or "{}").get("approvalId")
        except (TypeError, ValueError):
            approval_id = None
        result.append({
            "queryId": row.query_id, "requestedBy": row.requested_by, "purpose": row.purpose,
            "customerScope": row.customer_scope, "siteScope": row.site_scope,
            "status": row.status, "blockCode": row.block_code,
            "promptVersionId": row.prompt_version_id, "approvalId": approval_id,
            "responseStored": row.response_text is not None,
            "responseHashPresent": row.response_hash is not None,
            "queryPayloadExpired": row.query_text == "[EXPIRED]",
            "createdAt": row.created_at, "completedAt": row.completed_at,
            "evidenceCount": len(evidence), "citationCount": len(citations),
            "attempts": [{"attemptId": item.attempt_id, "provider": item.provider,
                          "model": item.model, "status": item.status,
                          "errorCode": item.error_code, "httpStatus": item.http_status,
                          "costMicros": item.cost_micros} for item in attempts],
            "evidence": [{"candidateId": item.candidate_id, "sourceType": item.source_type,
                          "sourceId": item.source_id, "sourceVersionId": item.source_version_id,
                          "selected": item.selected_for_prompt, "sentExternally": item.sent_externally,
                          "eligibility": item.eligibility_result,
                          "exclusionReason": item.exclusion_reason,
                          "contentHash": item.content_hash} for item in evidence],
            "citations": [{"claimKey": item.claim_key, "candidateId": item.candidate_id,
                            "sourceType": item.source_type, "sourceId": item.source_id,
                            "sourceVersionId": item.source_version_id,
                            "contentHash": item.content_hash} for item in citations],
        })
    return result


@router.get("/audit/events")
def event_audit(_: SystemAdmin, settings: Cfg, session: Db, event_type: str | None = Query(None, alias="eventType"),
                target_id: str | None = Query(None, alias="targetId"), limit: int = Query(100, ge=1, le=500)):
    statement = select(AIOperationAuditEvent).where(
        AIOperationAuditEvent.customer_scope == settings.ai_customer_scope,
        AIOperationAuditEvent.site_scope == settings.ai_site_scope,
    )
    if event_type:
        statement = statement.where(AIOperationAuditEvent.event_type == event_type)
    if target_id:
        statement = statement.where(AIOperationAuditEvent.target_id == target_id)
    return [{"eventId": row.event_id, "eventType": row.event_type, "actorId": row.actor_id,
             "customerScope": row.customer_scope, "siteScope": row.site_scope,
             "targetType": row.target_type, "targetId": row.target_id,
             "reasonCode": row.reason_code, "detail": json.loads(row.detail_json),
             "occurredAt": row.occurred_at}
            for row in session.scalars(statement.order_by(AIOperationAuditEvent.occurred_at.desc()).limit(limit)).all()]


@router.get("/audit/export")
def export_audit(_: SystemAdmin, settings: Cfg, session: Db):
    _, site_policy = active_policy(session, settings.ai_customer_scope, settings.ai_site_scope)
    if not site_policy or not site_policy.allow_audit_export:
        raise HTTPException(403, "현장 감사 내보내기 정책이 허용되지 않았습니다.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["query_id", "requested_by", "purpose", "status", "block_code", "prompt_version_id", "created_at"])
    for row in session.scalars(select(AIQuery).where(
        AIQuery.customer_scope == settings.ai_customer_scope,
        AIQuery.site_scope == settings.ai_site_scope,
    ).order_by(AIQuery.created_at.desc())).all():
        writer.writerow([row.query_id, row.requested_by, row.purpose, row.status,
                         row.block_code or "", row.prompt_version_id or "", row.created_at.isoformat()])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=flownote-ai-audit.csv"})


@router.post("/retention/run")
def execute_retention(_: SystemAdmin, settings: Cfg, session: Db) -> dict[str, int]:
    return run_retention(
        session,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
    )


@router.get("/retention/audit")
def retention_audit(_: SystemAdmin, settings: Cfg, session: Db, limit: int = Query(100, ge=1, le=500)):
    return [{"retentionAuditId": row.retention_audit_id, "queryId": row.query_id,
             "action": row.action, "queryTextAction": row.query_text_action,
             "responseTextAction": row.response_text_action, "processedAt": row.processed_at}
            for row in session.scalars(
                select(AIRetentionAudit).join(AIQuery, AIQuery.query_id == AIRetentionAudit.query_id).where(
                    AIQuery.customer_scope == settings.ai_customer_scope,
                    AIQuery.site_scope == settings.ai_site_scope,
                ).order_by(AIRetentionAudit.processed_at.desc()).limit(limit)
            ).all()]


class LegalHoldCreate(QueryMutationRequest):
    reason: str = Field(min_length=1, max_length=2000)
    authority_reference: str = Field(alias="authorityReference", min_length=1, max_length=500)


def _scoped_query(query_id: str, settings: Settings, session: Session) -> AIQuery:
    row = session.scalar(select(AIQuery).where(
        AIQuery.query_id == query_id,
        AIQuery.customer_scope == settings.ai_customer_scope,
        AIQuery.site_scope == settings.ai_site_scope,
    ))
    if row is None:
        raise HTTPException(404, "현재 고객·현장 범위에서 AI 질의를 찾을 수 없습니다.")
    return row


def _begin_ai_mutation(session: Session) -> None:
    """Serialize cross-table hold/expiry decisions on SQLite; row locks cover server DBs."""
    if session.bind is not None and session.bind.dialect.name == "sqlite" and not session.in_transaction():
        session.execute(text("BEGIN IMMEDIATE"))


def _query_state_tag(row: AIQuery, active_hold_id: str | None) -> str:
    material = "|".join((
        row.query_id,
        "EXPIRED" if row.query_text == "[EXPIRED]" else "PRESENT",
        "STORED" if row.response_text is not None else "NOT_STORED",
        utc(row.retention_until).isoformat(),
        utc(row.response_retention_until).isoformat() if row.response_retention_until else "",
        active_hold_id or "",
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _hold_dict(hold: AIQueryLegalHold) -> dict[str, object]:
    return {
        "holdId": hold.hold_id, "queryId": hold.query_id, "status": hold.status,
        "reason": hold.reason, "authorityReference": hold.authority_reference,
        "placedBy": hold.placed_by, "placedAt": hold.placed_at,
        "releasedBy": hold.released_by, "releasedAt": hold.released_at,
        "releaseReason": hold.release_reason,
    }


def _query_detail_dict(row: AIQuery, session: Session) -> dict[str, object]:
    holds = session.scalars(select(AIQueryLegalHold).where(
        AIQueryLegalHold.query_id == row.query_id
    ).order_by(AIQueryLegalHold.placed_at.desc())).all()
    active_hold = next((hold for hold in holds if hold.status == "ACTIVE"), None)
    retention_rows = session.scalars(select(AIRetentionAudit).where(
        AIRetentionAudit.query_id == row.query_id
    ).order_by(AIRetentionAudit.processed_at.desc())).all()
    target_ids = [row.query_id, *(hold.hold_id for hold in holds)]
    events = session.scalars(select(AIOperationAuditEvent).where(
        AIOperationAuditEvent.customer_scope == row.customer_scope,
        AIOperationAuditEvent.site_scope == row.site_scope,
        AIOperationAuditEvent.target_id.in_(target_ids),
    ).order_by(AIOperationAuditEvent.occurred_at.desc())).all()
    return {
        "queryId": row.query_id, "requestedBy": row.requested_by,
        "customerScope": row.customer_scope, "siteScope": row.site_scope,
        "purpose": row.purpose, "status": row.status, "blockCode": row.block_code,
        "queryPayloadExpired": row.query_text == "[EXPIRED]",
        "responseStored": row.response_text is not None,
        "retentionUntil": row.retention_until,
        "responseRetentionUntil": row.response_retention_until,
        "createdAt": row.created_at, "completedAt": row.completed_at,
        "activeHold": _hold_dict(active_hold) if active_hold else None,
        "holds": [_hold_dict(hold) for hold in holds],
        "retentionAudits": [{
            "retentionAuditId": item.retention_audit_id, "queryId": item.query_id,
            "action": item.action, "queryTextAction": item.query_text_action,
            "responseTextAction": item.response_text_action, "processedAt": item.processed_at,
        } for item in retention_rows],
        "auditEvents": [{
            "eventId": item.event_id, "eventType": item.event_type,
            "actorId": item.actor_id, "targetType": item.target_type,
            "targetId": item.target_id, "reasonCode": item.reason_code,
            "detail": json.loads(item.detail_json), "occurredAt": item.occurred_at,
        } for item in events],
        "stateTag": _query_state_tag(row, active_hold.hold_id if active_hold else None),
    }


@router.get("/queries/{query_id}")
def get_query_detail(
    query_id: str, _: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    return _query_detail_dict(_scoped_query(query_id, settings, session), session)


def _ensure_expected_state(payload: QueryMutationRequest, row: AIQuery, session: Session) -> None:
    active_hold_id = session.scalar(select(AIQueryLegalHold.hold_id).where(
        AIQueryLegalHold.query_id == row.query_id,
        AIQueryLegalHold.status == "ACTIVE",
    ))
    current = _query_state_tag(row, active_hold_id)
    if payload.expected_state_tag and payload.expected_state_tag != current:
        raise HTTPException(409, {
            "code": "AI_QUERY_STALE_STATE",
            "message": "다른 관리자가 질의 보존 상태를 변경했습니다. 상세를 새로고침한 뒤 다시 확인하세요.",
            "currentStateTag": current,
        })


@router.post("/queries/{query_id}/expire")
def expire_query_now(
    query_id: str, payload: QueryMutationRequest, user: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    _begin_ai_mutation(session)
    row = _scoped_query(query_id, settings, session)
    replay_query = session.scalar(select(AIQuery).where(
        AIQuery.immediate_expiry_operation_key == payload.operation_key
    )) if payload.operation_key else None
    if replay_query is not None and replay_query.query_id != query_id:
        raise HTTPException(409, "동일 요청 키가 다른 질의 조작에 사용되었습니다.")
    if payload.operation_key and row.immediate_expiry_operation_key == payload.operation_key:
        if row.immediate_expiry_reason != payload.reason.strip():
            raise HTTPException(409, "동일 요청 키의 즉시 만료 사유가 최초 요청과 다릅니다.")
        audit = session.scalar(select(AIRetentionAudit).where(
            AIRetentionAudit.query_id == query_id,
            AIRetentionAudit.operation_key == payload.operation_key,
        ))
        return {"queryId": query_id, "processed": 1 if audit else 0,
                "queryPayloadsDeidentified": 1 if audit and audit.query_text_action == "DEIDENTIFIED" else 0,
                "responsesDeleted": 1 if audit and audit.response_text_action == "DELETED" else 0}
    _ensure_expected_state(payload, row, session)
    if row.immediate_expiry_operation_key or (row.query_text == "[EXPIRED]" and row.response_text is None):
        raise HTTPException(409, "이미 만료된 질의입니다. 상세를 새로고침하세요.")
    active_hold = session.scalar(select(AIQueryLegalHold.id).where(
        AIQueryLegalHold.query_id == query_id, AIQueryLegalHold.status == "ACTIVE"
    ))
    if active_hold is not None:
        raise HTTPException(409, "활성 legal hold가 있어 즉시 만료할 수 없습니다.")
    now = datetime.now(timezone.utc)
    row.retention_until = now
    row.response_retention_until = now
    row.immediate_expiry_operation_key = payload.operation_key
    row.immediate_expiry_requested_at = now
    row.immediate_expiry_reason = payload.reason.strip()
    audit_event(
        session, event_type="QUERY_IMMEDIATE_EXPIRY_REQUESTED", actor_id=user.user_id,
        customer_scope=row.customer_scope, site_scope=row.site_scope,
        target_type="AI_QUERY", target_id=row.query_id, detail={"reason": payload.reason},
    )
    session.flush()
    result = run_retention(session, now=now, query_id=query_id, operation_key=payload.operation_key)
    return {"queryId": query_id, **result}


@router.post("/queries/{query_id}/legal-holds", status_code=201)
def place_legal_hold(
    query_id: str, payload: LegalHoldCreate, user: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    _begin_ai_mutation(session)
    row = _scoped_query(query_id, settings, session)
    if payload.operation_key:
        replay = session.scalar(select(AIQueryLegalHold).where(
            AIQueryLegalHold.operation_key == payload.operation_key
        ))
        if replay is not None:
            if replay.query_id != query_id:
                raise HTTPException(409, "동일 요청 키가 다른 질의 조작에 사용되었습니다.")
            if (replay.reason != payload.reason.strip() or
                    replay.authority_reference != payload.authority_reference.strip()):
                raise HTTPException(409, "동일 요청 키의 hold 사유 또는 근거 번호가 최초 요청과 다릅니다.")
            return _hold_dict(replay)
    _ensure_expected_state(payload, row, session)
    if row.query_text == "[EXPIRED]" and row.response_text is None:
        raise HTTPException(409, "이미 만료된 질의에는 legal hold를 설정할 수 없습니다.")
    if session.scalar(select(AIQueryLegalHold.id).where(
        AIQueryLegalHold.query_id == query_id, AIQueryLegalHold.status == "ACTIVE"
    )) is not None:
        raise HTTPException(409, "이 질의에는 이미 활성 legal hold가 있습니다.")
    now = datetime.now(timezone.utc)
    hold = AIQueryLegalHold(
        hold_id=f"aihold-{uuid4().hex}", query_id=query_id, status="ACTIVE",
        reason=payload.reason.strip(), authority_reference=payload.authority_reference.strip(),
        placed_by=user.user_id, placed_at=now,
        operation_key=payload.operation_key,
    )
    session.add(hold)
    audit_event(
        session, event_type="QUERY_LEGAL_HOLD_PLACED", actor_id=user.user_id,
        customer_scope=row.customer_scope, site_scope=row.site_scope,
        target_type="AI_QUERY_LEGAL_HOLD", target_id=hold.hold_id,
        detail={"queryId": query_id, "authorityReference": hold.authority_reference},
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "다른 관리자가 먼저 legal hold를 설정했습니다. 상세를 새로고침하세요.")
    return _hold_dict(hold)


@router.post("/legal-holds/{hold_id}/release")
def release_legal_hold(
    hold_id: str, payload: QueryMutationRequest, user: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    _begin_ai_mutation(session)
    hold = session.scalar(
        select(AIQueryLegalHold).join(AIQuery, AIQuery.query_id == AIQueryLegalHold.query_id).where(
            AIQueryLegalHold.hold_id == hold_id,
            AIQuery.customer_scope == settings.ai_customer_scope,
            AIQuery.site_scope == settings.ai_site_scope,
        )
    )
    if hold is None:
        raise HTTPException(404, "현재 고객·현장 범위에서 legal hold를 찾을 수 없습니다.")
    row = _scoped_query(hold.query_id, settings, session)
    replay = session.scalar(select(AIQueryLegalHold).where(
        AIQueryLegalHold.release_operation_key == payload.operation_key
    )) if payload.operation_key else None
    if replay is not None and replay.hold_id != hold_id:
        raise HTTPException(409, "동일 요청 키가 다른 hold 해제에 사용되었습니다.")
    if payload.operation_key and hold.release_operation_key == payload.operation_key:
        if hold.release_reason != payload.reason.strip():
            raise HTTPException(409, "동일 요청 키의 hold 해제 사유가 최초 요청과 다릅니다.")
        return _hold_dict(hold)
    _ensure_expected_state(payload, row, session)
    if hold.status == "RELEASED":
        raise HTTPException(409, "이미 해제된 legal hold입니다. 상세를 새로고침하세요.")
    hold.status = "RELEASED"
    hold.released_by = user.user_id
    hold.released_at = datetime.now(timezone.utc)
    hold.release_reason = payload.reason.strip()
    hold.release_operation_key = payload.operation_key
    audit_event(
        session, event_type="QUERY_LEGAL_HOLD_RELEASED", actor_id=user.user_id,
        customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
        target_type="AI_QUERY_LEGAL_HOLD", target_id=hold.hold_id,
        detail={"queryId": hold.query_id, "reason": hold.release_reason},
    )
    session.commit()
    return _hold_dict(hold)
