from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    ROLE_ADMIN,
    ROLE_ASSISTANT_MANAGER,
    ROLE_DEPARTMENT_MANAGER,
    ROLE_DOCUMENT_ADMIN,
    ROLE_MANAGER,
    ROLE_SYSTEM_ADMIN,
    AuthenticatedUser,
    require_roles,
)
from app.core.config import Settings, get_settings
from app.db.models import (
    AICallAttempt,
    AIPromptVersion,
    AIQuery,
    AIQueryCitation,
    AIQueryEvidenceCandidate,
    AISearchCandidate,
    AITransferApproval,
)
from app.db.session import get_db_session
from app.services.ai_provider_gate import (
    AISourceAccessPolicy,
    ProviderBoundaryPayload,
    ProviderEvidence,
    approval_block_code,
    load_sensitive_filter,
    minimal_excerpt,
    sha256_text,
)
from app.services.ai_readiness import database_scope, scope_readiness

router = APIRouter(prefix="/ai", tags=["ai"])
AIQueryUser = Annotated[
    AuthenticatedUser,
    Depends(
        require_roles(
            ROLE_ADMIN,
            ROLE_SYSTEM_ADMIN,
            ROLE_DOCUMENT_ADMIN,
            ROLE_MANAGER,
            ROLE_ASSISTANT_MANAGER,
            ROLE_DEPARTMENT_MANAGER,
        )
    ),
]
ALLOWED_PURPOSES = {"EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"}
ALLOWED_SOURCE_TYPES = {
    "PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"
}


class AIProvider(Protocol):
    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AIQueryCreateRequest(BaseModel):
    purpose: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=8000)
    candidate_ids: list[str] | None = Field(default=None, alias="candidateIds", max_length=100)
    response_storage_mode: str = Field(default="DO_NOT_STORE", alias="responseStorageMode")

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("response_storage_mode")
    @classmethod
    def validate_storage_mode(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in {"DO_NOT_STORE", "STORE_90_DAYS"}:
            raise ValueError("must be DO_NOT_STORE or STORE_90_DAYS")
        return cleaned


def _hash(value: str) -> str:
    return sha256_text(value)


def _error(query_id: str, status_code: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"queryId": query_id, "error": {"code": code, "message": message}, "retryable": retryable},
    )


def _block(
    session: Session, query: AIQuery, settings: Settings, code: str, message: str, status_code: int
) -> JSONResponse:
    now = datetime.now(timezone.utc)
    query.status = "BLOCKED"
    query.block_code = code
    query.completed_at = now
    session.add(
        AICallAttempt(
            attempt_id=f"aica-{uuid4().hex}", query_id=query.query_id,
            provider=settings.ai_provider, model=settings.ai_model, status="BLOCKED",
            started_at=now, finished_at=now, error_code=code,
            sanitized_error_message=message,
        )
    )
    session.commit()
    return _error(query.query_id, status_code, code, message, status_code >= 500)


def _approval(settings: Settings, session: Session) -> AITransferApproval | None:
    return session.scalar(
        select(AITransferApproval).where(
            AITransferApproval.customer_scope == settings.ai_customer_scope,
            AITransferApproval.site_scope == settings.ai_site_scope,
            AITransferApproval.provider == settings.ai_provider,
        ).order_by(AITransferApproval.approved_at.desc())
    )


def _snapshot(
    session: Session,
    query: AIQuery,
    current_user: AuthenticatedUser,
    candidate_ids: list[str] | None,
    approval: AITransferApproval,
    settings: Settings,
) -> tuple[list[AIQueryEvidenceCandidate], list[ProviderEvidence]]:
    statement = select(AISearchCandidate)
    if candidate_ids is not None:
        statement = statement.where(AISearchCandidate.candidate_id.in_(candidate_ids))
    candidates = session.scalars(statement.order_by(AISearchCandidate.id).limit(100)).all()
    try:
        approved_types = set(json.loads(approval.allowed_source_types))
    except (TypeError, ValueError):
        approved_types = set()
    access_policy = AISourceAccessPolicy(session, current_user)
    content_filter = load_sensitive_filter(session, settings)
    snapshots: list[AIQueryEvidenceCandidate] = []
    evidence: list[ProviderEvidence] = []
    for rank, candidate in enumerate(candidates, 1):
        policy_result = access_policy.evaluate(candidate)
        eligible, reason = policy_result.allowed, policy_result.reason_code
        if candidate.source_type not in approved_types or candidate.source_type not in ALLOWED_SOURCE_TYPES:
            eligible, reason = False, "SOURCE_FORBIDDEN"
        filtered_text: str | None = None
        if eligible and policy_result.source_text is not None:
            filtered = content_filter.filter(policy_result.source_text)
            eligible, reason = filtered.allowed, filtered.reason_code
            filtered_text = filtered.text
        selected = eligible and filtered_text is not None and len(evidence) < settings.ai_provider_max_sources
        row = AIQueryEvidenceCandidate(
            query_id=query.query_id, candidate_id=candidate.candidate_id,
            source_type=candidate.source_type, source_id=candidate.source_id,
            source_version_id=candidate.source_version_id, trace_table=candidate.trace_table,
            trace_id=candidate.trace_id, trace_version_id=candidate.trace_version_id, rank=rank,
            selected_for_prompt=selected, sent_externally=False,
            content_hash=policy_result.content_hash,
            eligibility_result="ELIGIBLE" if eligible else "EXCLUDED", exclusion_reason=reason,
        )
        session.add(row)
        snapshots.append(row)
        if selected:
            evidence.append(
                ProviderEvidence(
                    candidate_id=candidate.candidate_id,
                    source_type=candidate.source_type,
                    source_id=candidate.source_id,
                    source_version_id=candidate.source_version_id,
                    trace_id=candidate.trace_id,
                    trace_version_id=candidate.trace_version_id,
                    content_hash=policy_result.content_hash,
                    rank=rank,
                    excerpt=minimal_excerpt(
                        filtered_text, query.query_text, settings.ai_provider_excerpt_max_chars
                    ),
                )
            )
    session.flush()
    return snapshots, evidence


@router.post("/queries")
def create_ai_query(
    payload: AIQueryCreateRequest,
    request: Request,
    current_user: AIQueryUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> Any:
    now = datetime.now(timezone.utc)
    query = AIQuery(
        query_id=f"aiq-{uuid4().hex}", requested_by=current_user.user_id,
        query_text="[PENDING_FILTER]", query_hash=_hash(payload.query), purpose=payload.purpose,
        status="RECEIVED", response_storage_mode=payload.response_storage_mode,
        retention_until=now + timedelta(days=90), regenerable_until=now + timedelta(days=90),
    )
    session.add(query)
    session.flush()
    if payload.purpose not in ALLOWED_PURPOSES:
        return _block(session, query, settings, "AI_SCOPE_NOT_ALLOWED", "허용되지 않은 AI 요청 목적입니다.", 422)
    if not settings.ai_external_call_enabled:
        return _block(session, query, settings, "AI_EXTERNAL_CALL_DISABLED", "외부 AI 호출이 비활성화되어 있습니다.", 503)
    if settings.ai_readiness_gate_enabled:
        readiness = scope_readiness(
            session,
            customer_scope=settings.ai_customer_scope,
            site_scope=settings.ai_site_scope,
            line_scope=None,
            database_scope_value=database_scope(settings.database_url),
        )
        if not readiness["provider_start_ready"]:
            gaps = readiness["source_gaps"]
            gap_text = ", ".join(f"{key} {value}" for key, value in gaps.items() if value)
            message = (
                f"AI 근거 준비도 미달: 질문 {readiness['ground_truth_gap']}건 부족"
                + (f", 원천 부족 {gap_text}" if gap_text else "")
            )
            return _block(session, query, settings, "AI_READINESS_NOT_MET", message, 409)
    approval = _approval(settings, session)
    if approval_block_code(approval, settings, now):
        return _block(session, query, settings, "APPROVAL_REVOKED", "유효한 외부 전송 승인이 없습니다.", 403)
    assert approval is not None
    query_filter = load_sensitive_filter(session, settings)
    filtered_query = query_filter.filter(payload.query)
    if not filtered_query.allowed or filtered_query.text is None:
        query.query_text = "[REDACTED]"
        return _block(session, query, settings, "CONTENT_RESTRICTED", "질의에 외부 전송 금지 정보가 포함되어 있습니다.", 422)
    query.query_text = filtered_query.text
    prompt = session.scalar(
        select(AIPromptVersion).where(
            AIPromptVersion.allowed_purpose == payload.purpose,
            AIPromptVersion.approved_at.is_not(None), AIPromptVersion.retired_at.is_(None),
        ).order_by(AIPromptVersion.approved_at.desc())
    )
    if prompt is None:
        return _block(session, query, settings, "AI_PROMPT_NOT_APPROVED", "승인된 프롬프트 버전이 없습니다.", 409)
    query.prompt_version_id = prompt.prompt_version_id
    snapshots, provider_evidence = _snapshot(
        session, query, current_user, payload.candidate_ids, approval, settings
    )
    eligible = [row for row in snapshots if row.selected_for_prompt]
    if not provider_evidence:
        query.status = "INSUFFICIENT_EVIDENCE"
        query.block_code = "INSUFFICIENT_EVIDENCE"
        query.completed_at = now
        session.commit()
        return {"queryId": query.query_id, "status": query.status, "grounded": False,
                "summary": None, "claims": [], "reason": "사용 가능한 근거가 없습니다.", "responseStored": False}

    provider: AIProvider | None = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        return _block(session, query, settings, "AI_PROVIDER_NOT_CONFIGURED", "외부 AI provider가 구성되지 않았습니다.", 503)
    session.expire(approval)
    current_approval = session.scalar(
        select(AITransferApproval).where(AITransferApproval.approval_id == approval.approval_id)
    )
    if approval_block_code(current_approval, settings, datetime.now(timezone.utc)):
        return _block(session, query, settings, "APPROVAL_REVOKED", "외부 전송 승인이 철회되었습니다.", 403)
    attempt = AICallAttempt(
        attempt_id=f"aica-{uuid4().hex}", query_id=query.query_id, provider=settings.ai_provider,
        model=settings.ai_model, status="CALLING", started_at=now,
    )
    session.add(attempt)
    query.status = "CALLING"
    session.flush()
    provider_payload = ProviderBoundaryPayload(
        purpose=payload.purpose,
        query=filtered_query.text,
        query_hash=query.query_hash,
        prompt_version_id=prompt.prompt_version_id,
        prompt_version=f"{prompt.name}/{prompt.version}",
        trace_id=query.query_id,
        sources=tuple(provider_evidence),
    )
    # This is an injected boundary only. The repository contains no network provider client.
    result = provider(provider_payload.as_dict())
    response_text = str(result.get("response", ""))
    snapshot_by_id = {row.candidate_id: row for row in eligible}
    claims = result.get("claims")
    if not isinstance(claims, list) or not claims:
        query.status = "CITATION_VALIDATION_FAILED"
        query.completed_at = datetime.now(timezone.utc)
        attempt.status = "FAILED"
        attempt.finished_at = query.completed_at
        attempt.error_code = "CITATION_VALIDATION_FAILED"
        attempt.sanitized_error_message = "응답 인용 검증에 실패했습니다."
        session.commit()
        return _error(query.query_id, 502, "CITATION_VALIDATION_FAILED", "응답 인용 검증에 실패했습니다.")
    response_claims: list[dict[str, Any]] = []
    for claim in claims:
        citation_ids = claim.get("candidateIds") if isinstance(claim, dict) else None
        if not isinstance(citation_ids, list) or not citation_ids or any(item not in snapshot_by_id for item in citation_ids):
            query.status = "CITATION_VALIDATION_FAILED"
            query.completed_at = datetime.now(timezone.utc)
            attempt.status = "FAILED"
            attempt.finished_at = query.completed_at
            attempt.error_code = "CITATION_VALIDATION_FAILED"
            attempt.sanitized_error_message = "응답 인용 검증에 실패했습니다."
            session.commit()
            return _error(query.query_id, 502, "CITATION_VALIDATION_FAILED", "응답 인용 검증에 실패했습니다.")
        claim_key = str(claim.get("claimKey", ""))[:80] or f"claim-{len(response_claims) + 1}"
        citations: list[dict[str, Any]] = []
        for candidate_id in citation_ids:
            row = snapshot_by_id[candidate_id]
            uri = f"flownote://{row.trace_table}/{row.trace_id}"
            session.add(AIQueryCitation(
                citation_id=f"aicit-{uuid4().hex}", query_id=query.query_id,
                claim_key=claim_key, candidate_id=row.candidate_id, source_type=row.source_type,
                source_id=row.source_id, source_version_id=row.source_version_id,
                trace_table=row.trace_table, trace_id=row.trace_id,
                trace_version_id=row.trace_version_id, internal_source_uri=uri,
                content_hash=row.content_hash, validated_at=datetime.now(timezone.utc),
            ))
            citations.append({"candidateId": row.candidate_id, "sourceType": row.source_type,
                              "sourceId": row.source_id, "sourceVersionId": row.source_version_id,
                              "traceTable": row.trace_table, "traceId": row.trace_id,
                              "traceVersionId": row.trace_version_id, "internalSourceUri": uri})
        response_claims.append({"claimKey": claim_key, "text": str(claim.get("text", "")), "citations": citations})
    query.response_hash = _hash(response_text)
    query.response_text = response_text if payload.response_storage_mode == "STORE_90_DAYS" else None
    query.status = "SUCCEEDED"
    query.completed_at = datetime.now(timezone.utc)
    attempt.status = "SUCCEEDED"
    attempt.finished_at = query.completed_at
    for row in eligible:
        row.sent_externally = True
    session.commit()
    return {"queryId": query.query_id, "status": query.status, "grounded": True,
            "summary": response_text, "claims": response_claims,
            "responseStored": query.response_text is not None,
            "promptVersion": f"{prompt.name}/{prompt.version}"}


@router.get("/queries/{query_id}")
def get_ai_query(
    query_id: str, current_user: AIQueryUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> Any:
    query = session.scalar(select(AIQuery).where(AIQuery.query_id == query_id))
    if query is None:
        return _error(query_id, 404, "AI_QUERY_NOT_FOUND", "AI 질의를 찾을 수 없습니다.")
    evidence = session.scalars(select(AIQueryEvidenceCandidate).where(AIQueryEvidenceCandidate.query_id == query_id)).all()
    return {"queryId": query.query_id, "status": query.status, "purpose": query.purpose,
            "responseStored": query.response_text is not None, "responseHash": query.response_hash,
            "blockCode": query.block_code,
            "evidence": [{"candidateId": row.candidate_id, "sourceType": row.source_type,
                          "sourceId": row.source_id, "sourceVersionId": row.source_version_id,
                          "traceTable": row.trace_table, "traceId": row.trace_id,
                          "traceVersionId": row.trace_version_id,
                          "eligibilityResult": row.eligibility_result,
                          "exclusionReason": row.exclusion_reason} for row in evidence]}
