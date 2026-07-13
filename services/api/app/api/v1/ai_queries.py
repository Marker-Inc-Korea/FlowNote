from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, AuthenticatedUser, require_roles
from app.core.config import Settings, get_settings
from app.db.models import (
    AICallAttempt,
    AIPromptVersion,
    AIQuery,
    AIQueryCitation,
    AIQueryEvidenceCandidate,
    AISearchCandidate,
    AITransferApproval,
    Document,
    DocumentVersion,
    FieldComment,
    Report,
    ReportSource,
    WorkSequenceChangeHistory,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/ai", tags=["ai"])
AIQueryUser = Annotated[
    AuthenticatedUser, Depends(require_roles(ROLE_ADMIN, ROLE_SYSTEM_ADMIN))
]
ALLOWED_PURPOSES = {"EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"}
ALLOWED_FIELD_COMMENT_STATUSES = {"ANALYZED", "REVIEWED", "SELECTED"}
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


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _approval(settings: Settings, session: Session, now: datetime) -> AITransferApproval | None:
    approvals = session.scalars(
        select(AITransferApproval).where(
            AITransferApproval.customer_scope == settings.ai_customer_scope,
            AITransferApproval.site_scope == settings.ai_site_scope,
            AITransferApproval.provider == settings.ai_provider,
        ).order_by(AITransferApproval.approved_at.desc())
    ).all()
    for approval in approvals:
        model_allowed = approval.model_scope in {"*", settings.ai_model}
        if approval.revoked_at is None and _utc(approval.expires_at) > now and model_allowed:
            return approval
    return None


def _eligible(candidate: AISearchCandidate, session: Session) -> tuple[bool, str | None]:
    if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
        document = session.scalar(select(Document).where(Document.document_id == candidate.source_id))
        version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == candidate.source_version_id))
        valid = bool(document and version and document.status == "PUBLISHED" and document.deleted_at is None
                     and document.published_version_id == version.version_id and version.document_id == document.document_id
                     and version.version_status == "PUBLISHED" and version.is_published)
        return valid, None if valid else "DOCUMENT_NOT_PUBLISHED"
    if candidate.source_type == "FIELD_COMMENT":
        comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == candidate.source_id))
        valid = bool(comment and comment.status in ALLOWED_FIELD_COMMENT_STATUSES)
        return valid, None if valid else "FIELD_COMMENT_NOT_REVIEWED"
    if candidate.source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == candidate.source_id))
        return (history is not None), None if history else "WORK_SEQUENCE_HISTORY_MISSING"
    if candidate.source_type == "REPORT_SOURCE":
        source = session.scalar(select(ReportSource).where(ReportSource.id == int(candidate.source_id))) if candidate.source_id.isdigit() else None
        report = session.scalar(select(Report).where(Report.report_id == source.report_id)) if source else None
        valid = bool(source and report and report.status != "ARCHIVED")
        return valid, None if valid else "REPORT_SOURCE_NOT_AVAILABLE"
    return False, "SOURCE_TYPE_NOT_ALLOWED"


def _snapshot(
    session: Session, query: AIQuery, candidate_ids: list[str] | None, approval: AITransferApproval
) -> list[AIQueryEvidenceCandidate]:
    statement = select(AISearchCandidate)
    if candidate_ids is not None:
        statement = statement.where(AISearchCandidate.candidate_id.in_(candidate_ids))
    candidates = session.scalars(statement.order_by(AISearchCandidate.id).limit(100)).all()
    try:
        approved_types = set(json.loads(approval.allowed_source_types))
    except (TypeError, ValueError):
        approved_types = set()
    snapshots: list[AIQueryEvidenceCandidate] = []
    for rank, candidate in enumerate(candidates, 1):
        eligible, reason = _eligible(candidate, session)
        if candidate.source_type not in approved_types or candidate.source_type not in ALLOWED_SOURCE_TYPES:
            eligible, reason = False, "TRANSFER_SCOPE_MISMATCH"
        if not eligible:
            continue
        row = AIQueryEvidenceCandidate(
            query_id=query.query_id, candidate_id=candidate.candidate_id,
            source_type=candidate.source_type, source_id=candidate.source_id,
            source_version_id=candidate.source_version_id, trace_table=candidate.trace_table,
            trace_id=candidate.trace_id, trace_version_id=candidate.trace_version_id, rank=rank,
            selected_for_prompt=True, sent_externally=False,
            content_hash=_hash(candidate.search_text),
            eligibility_result="ELIGIBLE", exclusion_reason=None,
        )
        session.add(row)
        snapshots.append(row)
    session.flush()
    return snapshots


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
        query_text=payload.query, query_hash=_hash(payload.query), purpose=payload.purpose,
        status="RECEIVED", response_storage_mode=payload.response_storage_mode,
        retention_until=now + timedelta(days=90), regenerable_until=now + timedelta(days=90),
    )
    session.add(query)
    session.flush()
    if payload.purpose not in ALLOWED_PURPOSES:
        return _block(session, query, settings, "AI_SCOPE_NOT_ALLOWED", "허용되지 않은 AI 요청 목적입니다.", 422)
    if not settings.ai_external_call_enabled:
        return _block(session, query, settings, "AI_EXTERNAL_CALL_DISABLED", "외부 AI 호출이 비활성화되어 있습니다.", 503)
    approval = _approval(settings, session, now)
    if approval is None:
        return _block(session, query, settings, "AI_TRANSFER_NOT_APPROVED", "유효한 외부 전송 승인이 없습니다.", 403)
    prompt = session.scalar(
        select(AIPromptVersion).where(
            AIPromptVersion.allowed_purpose == payload.purpose,
            AIPromptVersion.approved_at.is_not(None), AIPromptVersion.retired_at.is_(None),
        ).order_by(AIPromptVersion.approved_at.desc())
    )
    if prompt is None:
        return _block(session, query, settings, "AI_PROMPT_NOT_APPROVED", "승인된 프롬프트 버전이 없습니다.", 409)
    query.prompt_version_id = prompt.prompt_version_id
    snapshots = _snapshot(session, query, payload.candidate_ids, approval)
    eligible = [row for row in snapshots if row.eligibility_result == "ELIGIBLE"]
    if not eligible:
        query.status = "INSUFFICIENT_EVIDENCE"
        query.completed_at = now
        session.commit()
        return {"queryId": query.query_id, "status": query.status, "grounded": False,
                "summary": None, "claims": [], "reason": "사용 가능한 근거가 없습니다.", "responseStored": False}

    provider: AIProvider | None = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        return _block(session, query, settings, "AI_PROVIDER_NOT_CONFIGURED", "외부 AI provider가 구성되지 않았습니다.", 503)
    attempt = AICallAttempt(
        attempt_id=f"aica-{uuid4().hex}", query_id=query.query_id, provider=settings.ai_provider,
        model=settings.ai_model, status="CALLING", started_at=now,
    )
    session.add(attempt)
    query.status = "CALLING"
    session.flush()
    # This is an injected boundary only. The repository contains no network provider client.
    result = provider({"purpose": payload.purpose, "queryHash": query.query_hash,
                       "promptVersionId": prompt.prompt_version_id,
                       "candidateIds": [row.candidate_id for row in eligible]})
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
