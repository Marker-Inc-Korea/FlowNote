from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ProviderTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import (
    ROLE_ADMIN,
    ROLE_ASSISTANT_MANAGER,
    ROLE_DEPARTMENT_MANAGER,
    ROLE_DOCUMENT_ADMIN,
    ROLE_MANAGER,
    ROLE_SYSTEM_ADMIN,
    AuthenticatedUser,
    CurrentUser,
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
    AuthSession,
    UserAccount,
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
from app.services.ai_provider_adapters import (
    AIProviderAdapter,
    CallableProviderAdapter,
    ProviderAdapterError,
)
from app.services.ai_response_validation import (
    ResponseValidationError,
    parse_provider_response,
    semantic_grounding,
)
from app.services.ai_readiness import database_scope, scope_readiness
from app.services.ai_operations import active_policy, audit_event

router = APIRouter(prefix="/ai", tags=["ai"])
AIQueryUser = CurrentUser
AI_QUERY_ROLES = {
    ROLE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_DOCUMENT_ADMIN, ROLE_MANAGER,
    ROLE_ASSISTANT_MANAGER, ROLE_DEPARTMENT_MANAGER,
}
ALLOWED_PURPOSES = {"EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"}
ALLOWED_SOURCE_TYPES = {
    "PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"
}


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


def utc_iso(value: datetime) -> str:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat()


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
    calling_attempt = session.scalar(
        select(AICallAttempt).where(
            AICallAttempt.query_id == query.query_id,
            AICallAttempt.status == "CALLING",
        ).order_by(AICallAttempt.id.desc())
    )
    if calling_attempt is not None:
        calling_attempt.status = "FAILED"
        calling_attempt.finished_at = now
        calling_attempt.error_code = code
        calling_attempt.sanitized_error_message = message
    else:
        session.add(AICallAttempt(
            attempt_id=f"aica-{uuid4().hex}", query_id=query.query_id,
            provider=settings.ai_provider, model=settings.ai_model, status="BLOCKED",
            started_at=now, finished_at=now, error_code=code,
            sanitized_error_message=message,
        ))
    audit_event(
        session,
        event_type="AI_QUERY_BLOCKED",
        actor_id=query.requested_by,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        target_type="QUERY",
        target_id=query.query_id,
        reason_code=code,
        detail={"statusCode": status_code},
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


def _operations_block(
    session: Session, settings: Settings, now: datetime
) -> tuple[str, str, int] | None:
    global_policy, site_policy = active_policy(
        session, settings.ai_customer_scope, settings.ai_site_scope
    )
    if global_policy and global_policy.kill_switch_enabled:
        return "AI_GLOBAL_KILL_SWITCH", "전역 외부 AI 즉시 중지가 활성화되어 있습니다.", 503
    if site_policy is None:
        return None
    if site_policy.kill_switch_enabled:
        return "AI_SITE_KILL_SWITCH", "현장 외부 AI 즉시 중지가 활성화되어 있습니다.", 503
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if site_policy.max_requests_per_day == 0:
        return "AI_REQUEST_LIMIT", "현장 일일 요청 한도가 0으로 설정되어 있습니다.", 429
    request_count = session.scalar(
        select(func.count()).select_from(AIQuery).where(
            AIQuery.created_at >= day_start,
            AIQuery.customer_scope == settings.ai_customer_scope,
            AIQuery.site_scope == settings.ai_site_scope,
        )
    ) or 0
    if request_count > site_policy.max_requests_per_day:
        return "AI_REQUEST_LIMIT", "현장 일일 요청 한도를 초과했습니다.", 429
    if site_policy.max_concurrency == 0:
        return "AI_CONCURRENCY_LIMIT", "현장 동시 호출 한도가 0으로 설정되어 있습니다.", 429
    calling = session.scalar(
        select(func.count()).select_from(AIQuery).where(
            AIQuery.status == "CALLING",
            AIQuery.customer_scope == settings.ai_customer_scope,
            AIQuery.site_scope == settings.ai_site_scope,
        )
    ) or 0
    if calling >= site_policy.max_concurrency:
        return "AI_CONCURRENCY_LIMIT", "현장 동시 호출 한도를 초과했습니다.", 429
    spent = session.scalar(
        select(func.coalesce(func.sum(AICallAttempt.cost_micros), 0))
        .join(AIQuery, AIQuery.query_id == AICallAttempt.query_id)
        .where(
            AICallAttempt.started_at >= day_start,
            AIQuery.customer_scope == settings.ai_customer_scope,
            AIQuery.site_scope == settings.ai_site_scope,
        )
    ) or 0
    if site_policy.daily_cost_budget_micros == 0 or spent >= site_policy.daily_cost_budget_micros:
        return "AI_COST_BUDGET", "현장 일일 비용 예산을 사용할 수 없습니다.", 429
    return None


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


def _provider_adapter(provider: Any) -> AIProviderAdapter:
    if hasattr(provider, "invoke") and callable(provider.invoke):
        return provider
    return CallableProviderAdapter(provider)


def _invoke_provider(
    session: Session,
    query: AIQuery,
    settings: Settings,
    provider: Any,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> tuple[Any | None, AICallAttempt | None, tuple[str, str, int] | None]:
    adapter = _provider_adapter(provider)
    for attempt_number in range(1, settings.ai_provider_max_attempts + 1):
        started = datetime.now(timezone.utc)
        attempt = AICallAttempt(
            attempt_id=f"aica-{uuid4().hex}", query_id=query.query_id,
            provider=settings.ai_provider, model=settings.ai_model, status="CALLING",
            started_at=started,
        )
        session.add(attempt)
        query.status = "CALLING"
        # Persist the boundary state before network work so audit survives process/provider failure
        # and local document operations are not held behind this transaction.
        session.commit()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(adapter.invoke, payload)
        error: ProviderAdapterError | None = None
        try:
            raw = future.result(timeout=timeout_seconds)
        except ProviderTimeoutError:
            error = ProviderAdapterError("AI_PROVIDER_TIMEOUT", retryable=True)
            executor.shutdown(wait=False, cancel_futures=True)
        except ProviderAdapterError as exc:
            error = exc
        except Exception:
            error = ProviderAdapterError("AI_PROVIDER_ERROR", retryable=False)
        finally:
            if future.done():
                executor.shutdown(wait=True)
        if error is None:
            return raw, attempt, None
        attempt.http_status = error.http_status
        if error.retryable and attempt_number < settings.ai_provider_max_attempts:
            attempt.status = "FAILED"
            attempt.finished_at = datetime.now(timezone.utc)
            attempt.error_code = error.code
            attempt.sanitized_error_message = "provider 호출이 완료되지 않았습니다."
            session.commit()
            continue
        status_code = 504 if error.code == "AI_PROVIDER_TIMEOUT" else 502
        message = (
            "외부 AI 호출 제한 시간을 초과했습니다."
            if error.code == "AI_PROVIDER_TIMEOUT"
            else "외부 AI 호출이 실패했습니다."
        )
        return None, attempt, (error.code, message, status_code)
    return None, None, ("AI_PROVIDER_ERROR", "외부 AI 호출이 실패했습니다.", 502)


def _hold_response(
    session: Session,
    query: AIQuery,
    attempt: AICallAttempt | None,
    settings: Settings,
    *,
    code: str,
    reason: str,
    human_review_required: bool = False,
) -> dict[str, Any]:
    completed = datetime.now(timezone.utc)
    query.status = "INSUFFICIENT_EVIDENCE"
    query.block_code = code
    query.completed_at = completed
    query.response_text = None
    query.response_hash = None
    if attempt is not None:
        attempt.status = "FAILED"
        attempt.finished_at = completed
        attempt.error_code = code
        attempt.sanitized_error_message = reason[:255]
    audit_event(
        session,
        event_type="AI_RESPONSE_WITHHELD",
        actor_id=query.requested_by,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        target_type="QUERY",
        target_id=query.query_id,
        reason_code=code,
        detail={"humanReviewRequired": human_review_required},
    )
    session.commit()
    return {
        "queryId": query.query_id,
        "status": query.status,
        "grounded": False,
        "summary": None,
        "claims": [],
        "reason": reason,
        "responseStored": False,
        "humanReviewRequired": human_review_required,
    }


def _validation_failure(
    session: Session,
    query: AIQuery,
    attempt: AICallAttempt,
    code: str,
) -> JSONResponse:
    completed = datetime.now(timezone.utc)
    query.status = "CITATION_VALIDATION_FAILED" if code == "CITATION_VALIDATION_FAILED" else "FAILED"
    query.block_code = code
    query.completed_at = completed
    query.response_text = None
    query.response_hash = None
    attempt.status = "FAILED"
    attempt.finished_at = completed
    attempt.error_code = code
    attempt.sanitized_error_message = "provider 응답 검증에 실패했습니다."
    session.commit()
    return _error(query.query_id, 502, code, "외부 AI 응답을 안전하게 검증할 수 없어 폐기했습니다.")


def _post_call_evidence_is_current(
    session: Session,
    current_user: AuthenticatedUser,
    eligible: list[AIQueryEvidenceCandidate],
) -> bool:
    session.expire_all()
    account = session.scalar(
        select(UserAccount).where(UserAccount.user_id == current_user.user_id)
    )
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.session_id == current_user.session_id)
    )
    if (
        account is None
        or not account.is_active
        or account.status != "ACTIVE"
        or account.role not in AI_QUERY_ROLES
        or auth_session is None
        or auth_session.status != "ACTIVE"
        or auth_session.access_token_id != current_user.access_token_id
    ):
        return False
    refreshed_user = AuthenticatedUser(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        session_id=auth_session.session_id,
        access_token_id=auth_session.access_token_id,
        must_change_password=account.must_change_password,
    )
    policy = AISourceAccessPolicy(session, refreshed_user)
    for snapshot in eligible:
        candidate = session.scalar(
            select(AISearchCandidate).where(AISearchCandidate.candidate_id == snapshot.candidate_id)
        )
        if candidate is None:
            return False
        result = policy.evaluate(candidate)
        if not result.allowed or result.content_hash != snapshot.content_hash:
            return False
    return True


@router.post("/queries")
def create_ai_query(
    payload: AIQueryCreateRequest,
    request: Request,
    current_user: AIQueryUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> Any:
    now = datetime.now(timezone.utc)
    _, retention_policy = active_policy(session, settings.ai_customer_scope, settings.ai_site_scope)
    query_retention_days = retention_policy.query_payload_retention_days if retention_policy else 90
    response_retention_days = retention_policy.response_retention_days if retention_policy else 90
    query = AIQuery(
        query_id=f"aiq-{uuid4().hex}", requested_by=current_user.user_id,
        customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
        query_text="[PENDING_FILTER]", query_hash=_hash(payload.query), purpose=payload.purpose,
        status="RECEIVED", response_storage_mode=payload.response_storage_mode,
        retention_until=now + timedelta(days=query_retention_days),
        response_retention_until=now + timedelta(days=response_retention_days),
        regenerable_until=now + timedelta(days=query_retention_days),
    )
    session.add(query)
    session.flush()
    if current_user.role not in AI_QUERY_ROLES:
        return _block(session, query, settings, "AI_ROLE_NOT_ALLOWED", "현재 역할은 외부 AI 질의를 사용할 수 없습니다.", 403)
    if payload.purpose not in ALLOWED_PURPOSES:
        return _block(session, query, settings, "AI_SCOPE_NOT_ALLOWED", "허용되지 않은 AI 요청 목적입니다.", 422)
    if not settings.ai_external_call_enabled:
        return _block(session, query, settings, "AI_EXTERNAL_CALL_DISABLED", "외부 AI 호출이 비활성화되어 있습니다.", 503)
    operations_block = _operations_block(session, settings, now)
    if operations_block:
        code, message, status_code = operations_block
        return _block(session, query, settings, code, message, status_code)
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
    try:
        allowed_purposes = set(json.loads(approval.allowed_purposes or "[]"))
    except (TypeError, ValueError):
        allowed_purposes = set()
    if payload.purpose not in allowed_purposes:
        return _block(session, query, settings, "APPROVAL_SCOPE_MISMATCH", "요청 목적이 전송 승인 범위에 포함되지 않습니다.", 403)
    query_filter = load_sensitive_filter(session, settings)
    filtered_query = query_filter.filter(payload.query)
    if not filtered_query.allowed or filtered_query.text is None:
        query.query_text = "[REDACTED]"
        return _block(session, query, settings, "CONTENT_RESTRICTED", "질의에 외부 전송 금지 정보가 포함되어 있습니다.", 422)
    query.query_text = filtered_query.text
    prompt = session.scalar(
        select(AIPromptVersion).where(
            AIPromptVersion.allowed_purpose == payload.purpose,
            AIPromptVersion.approved_at.is_not(None),
            AIPromptVersion.activated_at.is_not(None),
            AIPromptVersion.retired_at.is_(None),
        ).order_by(AIPromptVersion.activated_at.desc(), AIPromptVersion.approved_at.desc())
    )
    if prompt is None:
        return _block(session, query, settings, "AI_PROMPT_NOT_APPROVED", "승인된 프롬프트 버전이 없습니다.", 409)
    query.prompt_version_id = prompt.prompt_version_id
    query.prompt_snapshot_json = json.dumps(
        {"promptVersionId": prompt.prompt_version_id, "name": prompt.name,
         "version": prompt.version, "templateHash": prompt.template_hash,
         "templateText": prompt.template_text, "allowedPurpose": prompt.allowed_purpose},
        ensure_ascii=False, sort_keys=True,
    )
    query.approval_snapshot_json = json.dumps(
        {"approvalId": approval.approval_id, "customerScope": approval.customer_scope,
         "siteScope": approval.site_scope, "provider": approval.provider,
         "modelScope": approval.model_scope, "purposes": sorted(allowed_purposes),
         "sourceTypes": sorted(json.loads(approval.allowed_source_types)),
         "expiresAt": utc_iso(approval.expires_at)},
        ensure_ascii=False, sort_keys=True,
    )
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

    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        return _block(session, query, settings, "AI_PROVIDER_NOT_CONFIGURED", "외부 AI provider가 구성되지 않았습니다.", 503)
    session.expire(approval)
    current_approval = session.scalar(
        select(AITransferApproval).where(AITransferApproval.approval_id == approval.approval_id)
    )
    if approval_block_code(current_approval, settings, datetime.now(timezone.utc)):
        return _block(session, query, settings, "APPROVAL_REVOKED", "외부 전송 승인이 철회되었습니다.", 403)
    final_operations_block = _operations_block(session, settings, datetime.now(timezone.utc))
    if final_operations_block:
        code, message, status_code = final_operations_block
        return _block(session, query, settings, code, message, status_code)
    provider_payload = ProviderBoundaryPayload(
        purpose=payload.purpose,
        query=filtered_query.text,
        query_hash=query.query_hash,
        prompt_version_id=prompt.prompt_version_id,
        prompt_version=f"{prompt.name}/{prompt.version}",
        trace_id=query.query_id,
        sources=tuple(provider_evidence),
    )
    for row in eligible:
        row.sent_externally = True
    session.flush()
    _, site_policy = active_policy(session, settings.ai_customer_scope, settings.ai_site_scope)
    timeout_seconds = site_policy.timeout_seconds if site_policy else 30
    raw_result, attempt, provider_error = _invoke_provider(
        session,
        query,
        settings,
        provider,
        provider_payload.as_dict(),
        timeout_seconds,
    )
    if provider_error:
        code, message, status_code = provider_error
        return _block(session, query, settings, code, message, status_code)
    assert attempt is not None
    try:
        validated = parse_provider_response(
            raw_result,
            max_bytes=settings.ai_provider_response_max_bytes,
        )
    except ResponseValidationError as exc:
        return _validation_failure(session, query, attempt, exc.code)

    # The provider result is disposable until approval, source state and user access all pass again.
    session.expire_all()
    current_approval = session.scalar(
        select(AITransferApproval).where(AITransferApproval.approval_id == approval.approval_id)
    )
    if approval_block_code(current_approval, settings, datetime.now(timezone.utc)):
        return _hold_response(
            session, query, attempt, settings,
            code="APPROVAL_CHANGED_AFTER_CALL",
            reason="응답 생성 중 외부 전송 승인이 변경되어 결과를 폐기했습니다.",
        )
    final_operations_block = _operations_block(session, settings, datetime.now(timezone.utc))
    if final_operations_block:
        code, _, _ = final_operations_block
        return _hold_response(
            session, query, attempt, settings,
            code=f"{code}_AFTER_CALL",
            reason="응답 생성 중 운영 통제 상태가 변경되어 결과를 폐기했습니다.",
        )
    if not _post_call_evidence_is_current(session, current_user, eligible):
        return _hold_response(
            session, query, attempt, settings,
            code="SOURCE_STATE_CHANGED_AFTER_CALL",
            reason="응답 생성 중 근거 상태 또는 열람 권한이 변경되어 결과를 폐기했습니다.",
        )

    snapshot_by_id = {row.candidate_id: row for row in eligible}
    evidence_by_id = {item.candidate_id: item.excerpt for item in provider_evidence}
    for claim in validated.claims:
        if any(item not in snapshot_by_id for item in claim.candidate_ids):
            return _validation_failure(session, query, attempt, "CITATION_VALIDATION_FAILED")
        semantic = semantic_grounding(
            claim.text,
            [evidence_by_id[item] for item in claim.candidate_ids],
        )
        if not semantic.accepted:
            return _hold_response(
                session, query, attempt, settings,
                code=semantic.reason_code or "CLAIM_GROUNDING_LOW_CONFIDENCE",
                reason="주장과 인용 근거의 의미 일치를 보수적으로 확인할 수 없어 답변을 보류했습니다.",
                human_review_required=semantic.human_review_required,
            )
    summary_evidence_ids = {
        candidate_id for claim in validated.claims for candidate_id in claim.candidate_ids
    }
    summary_semantic = semantic_grounding(
        validated.response,
        [evidence_by_id[item] for item in summary_evidence_ids],
    )
    if not summary_semantic.accepted:
        return _hold_response(
            session, query, attempt, settings,
            code=summary_semantic.reason_code or "CLAIM_GROUNDING_LOW_CONFIDENCE",
            reason="요약과 인용 근거의 의미 일치를 보수적으로 확인할 수 없어 답변을 보류했습니다.",
            human_review_required=summary_semantic.human_review_required,
        )

    response_claims: list[dict[str, Any]] = []
    for claim in validated.claims:
        citations: list[dict[str, Any]] = []
        for candidate_id in claim.candidate_ids:
            row = snapshot_by_id[candidate_id]
            uri = f"flownote://{row.trace_table}/{row.trace_id}"
            session.add(AIQueryCitation(
                citation_id=f"aicit-{uuid4().hex}", query_id=query.query_id,
                claim_key=claim.claim_key, candidate_id=row.candidate_id, source_type=row.source_type,
                source_id=row.source_id, source_version_id=row.source_version_id,
                trace_table=row.trace_table, trace_id=row.trace_id,
                trace_version_id=row.trace_version_id, internal_source_uri=uri,
                content_hash=row.content_hash, validated_at=datetime.now(timezone.utc),
            ))
            citations.append({"candidateId": row.candidate_id, "sourceType": row.source_type,
                              "sourceId": row.source_id, "sourceVersionId": row.source_version_id,
                              "traceTable": row.trace_table, "traceId": row.trace_id,
                              "traceVersionId": row.trace_version_id, "internalSourceUri": uri})
        response_claims.append({"claimKey": claim.claim_key, "text": claim.text, "citations": citations})
    response_text = validated.response
    query.response_hash = _hash(response_text)
    query.response_text = response_text if payload.response_storage_mode == "STORE_90_DAYS" else None
    query.status = "SUCCEEDED"
    query.completed_at = datetime.now(timezone.utc)
    attempt.status = "SUCCEEDED"
    attempt.finished_at = query.completed_at
    attempt.provider_request_id = validated.provider_request_id
    attempt.cost_micros = validated.cost_micros
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
