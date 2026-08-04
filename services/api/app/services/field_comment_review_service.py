from __future__ import annotations

import hashlib
import json
from copy import copy
from datetime import datetime, timezone
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.field_comment_contracts import (
    ALLOWED_TRANSITIONS,
    STATUSES,
    FieldCommentBulkReviewItemRequest,
    FieldCommentBulkReviewResponse,
    FieldCommentBulkReviewV2Request,
    FieldCommentReviewRequest,
    FieldCommentResponse,
)
from app.core.auth import AuthenticatedUser, FIELD_COMMENT_DECIDE_ROLES
from app.core.config import Settings
from app.db.models import (
    ActivityHistory,
    FieldComment,
    FieldCommentReviewMutationReceipt,
    UserAccount,
)
from app.services.field_comment_support import (
    _clean_optional,
    _effective_status,
    _new_public_id,
    _source_hash,
    _validate_choice,
)
from app.services.field_comment_query_service import _field_comment_response
from app.services.mutation_receipts import (
    MutationTrace,
    canonical_hash,
    check_common_mutation_replay,
    record_common_mutation_result,
)
from app.services.mutation_outcomes import MutationOutcome


class ReviewRequest(Protocol):
    status: str | None
    normalized_content: str | None
    analysis_content: str | None
    assigned_to: str | None
    review_due_at: datetime | None
    transition_reason: str | None
    conflict_flag: bool | None
    conflict_basis: str | None


def bulk_review_outcome(
    response: FieldCommentBulkReviewResponse,
) -> MutationOutcome[FieldCommentBulkReviewResponse]:
    retry_item_ids = tuple(
        item.comment_id for item in response.items if item.success is not True
    )
    guidance = {
        "responsible_role": "FieldComment 검토 담당자",
        "action_route": "/field-comments?retry=failed",
    }
    if response.failure_count == 0:
        return MutationOutcome.success(
            response,
            code="FIELD_COMMENT_BULK_APPLIED",
            message="선택한 FieldComment 검토 변경을 모두 저장했습니다.",
            **guidance,
        )
    if response.success_count:
        return MutationOutcome.partial_success(
            response,
            code="FIELD_COMMENT_BULK_PARTIAL_SUCCESS",
            message="일부 변경만 저장했습니다. 실패 항목만 다시 시도하세요.",
            retry_item_ids=retry_item_ids,
            **guidance,
        )
    return MutationOutcome.rejected(
        value=response,
        code="FIELD_COMMENT_BULK_REJECTED",
        message="선택한 FieldComment를 변경하지 못했습니다.",
        responsible_role=guidance["responsible_role"],
        action_route=guidance["action_route"],
        retry_item_ids=retry_item_ids,
    )


def _review_snapshot(note: FieldComment) -> dict:
    return {
        "source_hash_sha256": _source_hash(note),
        "status": _effective_status(note),
        "normalized_content": note.normalized_content,
        "analysis_content": note.analysis_content,
        "assigned_to": note.assigned_to,
        "review_due_at": note.review_due_at.isoformat() if note.review_due_at else None,
        "analyzed_by": note.analyzed_by,
        "reviewed_by": note.reviewed_by,
        "review_revision": note.review_revision,
        "conflict_flag": note.conflict_flag,
        "conflict_basis": note.conflict_basis,
    }


def _review_intent_hash(comment_id: str, request: FieldCommentReviewRequest) -> str:
    payload = {
        "commentId": comment_id,
        **request.model_dump(by_alias=True, exclude={"mutation_key"}),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _review_idempotent_response(
    session: Session,
    comment_id: str,
    mutation_key: str | None,
    intent_hash: str,
) -> FieldCommentResponse | None:
    if mutation_key is None:
        return None
    common_receipt = check_common_mutation_replay(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type="field_comment.review_changed",
        target_type="field_comment",
        target_id=comment_id,
    )
    receipt = session.scalar(
        select(FieldCommentReviewMutationReceipt).where(
            FieldCommentReviewMutationReceipt.mutation_key == mutation_key
        )
    )
    if receipt is None:
        if common_receipt is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COMMON_RECEIPT_LINK_BROKEN",
                    "message": "공통 receipt와 FieldComment receipt 연결이 끊어졌습니다.",
                },
            )
        return None
    if receipt.comment_id != comment_id or receipt.intent_hash_sha256 != intent_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_KEY_REUSED",
                "message": "같은 mutation key를 다른 FieldComment 검토에 사용할 수 없습니다.",
            },
        )
    return FieldCommentResponse.model_validate_json(receipt.response_json)


def _claim_review_revision(session: Session, note: FieldComment, base_revision: int) -> int:
    next_revision = base_revision + 1
    result = session.execute(
        update(FieldComment)
        .where(
            FieldComment.comment_id == note.comment_id,
            FieldComment.review_revision == base_revision,
        )
        .values(review_revision=next_revision, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        session.rollback()
        current_revision = session.scalar(
            select(FieldComment.review_revision).where(FieldComment.comment_id == note.comment_id)
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELD_COMMENT_STALE_REVIEW_REVISION",
                "message": "다른 사용자가 FieldComment 검토를 먼저 변경했습니다. 새로고침 후 다시 검토하세요.",
                "expectedRevision": base_revision,
                "currentRevision": current_revision,
            },
        )
    note.review_revision = next_revision
    return next_revision


def _load_user_id(session: Session, value: str | None, field_name: str) -> str | None:
    user_id = _clean_optional(value)
    if user_id is None:
        return None
    if session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id)) is None:
        raise HTTPException(status_code=422, detail=f"{field_name} must reference an existing user_id.")
    return user_id


def _validate_transition(note: FieldComment, target: str, reason: str | None, actor_role: str) -> str:
    current = _effective_status(note)
    if target == current:
        return _clean_optional(reason) or note.last_transition_reason or "상태 유지"
    if target not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(status_code=409, detail=f"Transition {current} -> {target} is not allowed.")
    if target in {"REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"} and actor_role not in FIELD_COMMENT_DECIDE_ROLES:
        raise HTTPException(status_code=403, detail="Current user role cannot make this FieldComment decision.")
    cleaned_reason = _clean_optional(reason)
    if cleaned_reason is None or len(cleaned_reason) < 3:
        raise HTTPException(status_code=422, detail="transitionReason of at least 3 characters is required.")
    if target in {"ANALYZED", "REVIEWED", "SELECTED"} and not _clean_optional(note.analysis_content):
        raise HTTPException(status_code=422, detail="analysisContent is required for analyzed or later status.")
    if target in {"REVIEWED", "SELECTED"} and not _clean_optional(note.normalized_content):
        raise HTTPException(status_code=422, detail="normalizedContent is required for reviewed or selected status.")
    if target == "SELECTED" and (not note.document_version_id or not note.author_id):
        raise HTTPException(status_code=422, detail="SELECTED requires documentVersionId and authorId trace evidence.")
    return cleaned_reason


def _ensure_independent_decision(
    note: FieldComment,
    target: str,
    actor_id: str,
    policy_enabled: bool,
) -> None:
    high_risk = note.signal_level == "red" or note.conflict_flag
    is_decision = target in {"REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"}
    if (
        policy_enabled
        and high_risk
        and is_decision
        and note.analyzed_by is not None
        and note.analyzed_by == actor_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INDEPENDENT_REVIEW_REQUIRED",
                "message": "위험 신호 또는 상충 FieldComment는 분석자와 다른 결정자가 검토해야 합니다.",
            },
        )


def _record_review_audit(
    session: Session,
    note: FieldComment,
    actor_id: str,
    before: dict,
    reason: str | None,
) -> None:
    after = _review_snapshot(note)
    if before == after:
        return
    if before["source_hash_sha256"] != after["source_hash_sha256"]:
        raise HTTPException(status_code=409, detail="FieldComment source snapshot changed during review.")
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="field_comment.review_changed",
            actor_id=actor_id,
            target_type="field_comment",
            target_id=note.comment_id,
            target_title=note.comment_id,
            message=f"FieldComment 검토 변경: {before['status']} → {after['status']}",
            before_value=json.dumps(before, ensure_ascii=False, sort_keys=True),
            after_value=json.dumps(after, ensure_ascii=False, sort_keys=True),
            change_reason=reason,
        )
    )


def _apply_review_change(
    session: Session,
    note: FieldComment,
    request: ReviewRequest,
    actor_id: str,
    actor_role: str,
    independent_review_required: bool,
) -> None:
    before = _review_snapshot(note)
    if isinstance(request, FieldCommentReviewRequest):
        interpretation_changed = any((
            request.normalized_content is not None and _clean_optional(request.normalized_content) != note.normalized_content,
            request.analysis_content is not None and _clean_optional(request.analysis_content) != note.analysis_content,
            request.conflict_flag is not None and request.conflict_flag != note.conflict_flag,
            request.conflict_basis is not None and _clean_optional(request.conflict_basis) != note.conflict_basis,
        ))
        if _effective_status(note) == "SELECTED" and interpretation_changed and request.status not in {"REVIEWED", "EXCLUDED"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SELECTED_SOURCE_REVIEW_REQUIRED",
                    "message": "선정된 FieldComment 해석을 바꾸려면 REVIEWED로 되돌린 뒤 재검토해야 합니다.",
                },
            )
        if request.normalized_content is not None:
            note.normalized_content = _clean_optional(request.normalized_content)
        if request.analysis_content is not None:
            note.analysis_content = _clean_optional(request.analysis_content)
        if request.conflict_flag is not None:
            note.conflict_flag = request.conflict_flag
        if request.conflict_basis is not None:
            note.conflict_basis = _clean_optional(request.conflict_basis)
    if request.assigned_to is not None:
        note.assigned_to = _load_user_id(session, request.assigned_to, "assignedTo")
    if request.review_due_at is not None:
        note.review_due_at = request.review_due_at

    reason = None
    if request.status is not None:
        target = _validate_choice(request.status, STATUSES, "status")
        if target == "ASSIGNED" and not _clean_optional(note.assigned_to):
            raise HTTPException(status_code=422, detail="ASSIGNED requires assignedTo.")
        if note.conflict_flag and target in {"REVIEWED", "SELECTED", "EXCLUDED"} and not _clean_optional(note.conflict_basis):
            raise HTTPException(status_code=422, detail="conflictBasis is required before resolving a conflicting record.")
        transition_note = copy(note)
        transition_note.assigned_to = before["assigned_to"]
        reason = _validate_transition(transition_note, target, request.transition_reason, actor_role)
        _ensure_independent_decision(
            transition_note,
            target,
            actor_id,
            independent_review_required,
        )
        if target != before["status"]:
            note.status = "NEW" if target == "ASSIGNED" else target
            note.last_transition_reason = reason
            now = datetime.now(timezone.utc)
            if target == "ANALYZED":
                note.analyzed_by = actor_id
                note.analyzed_at = now
            elif target == "REVIEWED":
                note.reviewed_by = actor_id
                note.reviewed_at = now
            elif target == "SELECTED":
                note.selected_at = now
    _record_review_audit(session, note, actor_id, before, reason or _clean_optional(request.transition_reason))


def _bulk_item_review_request(
    request: FieldCommentBulkReviewV2Request,
    item: FieldCommentBulkReviewItemRequest,
) -> FieldCommentReviewRequest:
    return FieldCommentReviewRequest(
        status=request.status,
        normalizedContent=request.normalized_content,
        analysisContent=request.analysis_content,
        assignedTo=request.assigned_to,
        reviewDueAt=request.review_due_at,
        transitionReason=request.transition_reason,
        conflictFlag=request.conflict_flag,
        conflictBasis=request.conflict_basis,
        baseReviewRevision=item.base_review_revision,
        mutationKey=item.mutation_key,
    )


def _preview_review_change(
    session: Session,
    note: FieldComment,
    request: FieldCommentReviewRequest,
    actor_id: str,
    actor_role: str,
    independent_review_required: bool,
) -> None:
    if request.base_review_revision != note.review_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELD_COMMENT_STALE_REVIEW_REVISION",
                "message": "다른 사용자가 FieldComment 검토를 먼저 변경했습니다.",
                "expectedRevision": request.base_review_revision,
                "currentRevision": note.review_revision,
            },
        )
    interpretation_changed = any((
        request.normalized_content is not None and _clean_optional(request.normalized_content) != note.normalized_content,
        request.analysis_content is not None and _clean_optional(request.analysis_content) != note.analysis_content,
        request.conflict_flag is not None and request.conflict_flag != note.conflict_flag,
        request.conflict_basis is not None and _clean_optional(request.conflict_basis) != note.conflict_basis,
    ))
    if _effective_status(note) == "SELECTED" and interpretation_changed and request.status not in {"REVIEWED", "EXCLUDED"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SELECTED_SOURCE_REVIEW_REQUIRED",
                "message": "선정된 FieldComment 해석을 바꾸려면 REVIEWED로 되돌린 뒤 재검토해야 합니다.",
            },
        )
    preview = copy(note)
    if request.normalized_content is not None:
        preview.normalized_content = _clean_optional(request.normalized_content)
    if request.analysis_content is not None:
        preview.analysis_content = _clean_optional(request.analysis_content)
    if request.assigned_to is not None:
        preview.assigned_to = _load_user_id(session, request.assigned_to, "assignedTo")
    if request.conflict_flag is not None:
        preview.conflict_flag = request.conflict_flag
    if request.conflict_basis is not None:
        preview.conflict_basis = _clean_optional(request.conflict_basis)
    if request.status is None:
        return
    target = _validate_choice(request.status, STATUSES, "status")
    if target == "ASSIGNED" and not _clean_optional(preview.assigned_to):
        raise HTTPException(status_code=422, detail="ASSIGNED requires assignedTo.")
    if preview.conflict_flag and target in {"REVIEWED", "SELECTED", "EXCLUDED"} and not _clean_optional(preview.conflict_basis):
        raise HTTPException(status_code=422, detail="conflictBasis is required before resolving a conflicting record.")
    transition_preview = copy(preview)
    transition_preview.assigned_to = note.assigned_to
    _validate_transition(transition_preview, target, request.transition_reason, actor_role)
    _ensure_independent_decision(
        transition_preview,
        target,
        actor_id,
        independent_review_required,
    )


def _bulk_failure(exc: HTTPException) -> tuple[str, str]:
    if isinstance(exc.detail, dict):
        return str(exc.detail.get("code") or f"HTTP_{exc.status_code}"), str(exc.detail.get("message") or exc.detail)
    return f"HTTP_{exc.status_code}", str(exc.detail)


def _apply_field_comment_review_mutation(
    *,
    comment_id: str,
    request: FieldCommentReviewRequest,
    current_user: AuthenticatedUser,
    app_settings: Settings,
    session: Session,
    mutation_key: str | None,
    intent_hash: str,
    trace: MutationTrace,
    reason: str | None,
) -> FieldCommentResponse:
    replay = _review_idempotent_response(session, comment_id, mutation_key, intent_hash)
    if replay is not None:
        return replay

    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    before_hash = canonical_hash(_review_snapshot(note))
    base_revision = request.base_review_revision or note.review_revision
    _claim_review_revision(session, note, base_revision)
    _apply_review_change(
        session,
        note,
        request,
        current_user.user_id,
        current_user.role,
        app_settings.field_comment_independent_review_required,
    )

    try:
        session.flush()
        response = _field_comment_response(note)
        if mutation_key is not None:
            receipt = FieldCommentReviewMutationReceipt(
                mutation_key=mutation_key,
                intent_hash_sha256=intent_hash,
                comment_id=comment_id,
                review_revision=note.review_revision,
                response_json=response.model_dump_json(),
            )
            session.add(receipt)
            session.flush()
            record_common_mutation_result(
                session,
                operation_key=mutation_key,
                intent_hash=intent_hash,
                event_type="field_comment.review_changed",
                trace=trace,
                target_type="field_comment",
                target_id=comment_id,
                target_version_id=note.document_version_id,
                target_revision=note.review_revision,
                reason=reason,
                before_hash=before_hash,
                after_hash=canonical_hash(_review_snapshot(note)),
                result="SUCCESS",
                result_code="APPLIED",
                http_status=status.HTTP_200_OK,
                response_detail={
                    "code": "APPLIED",
                    "targetId": comment_id,
                    "targetVersionId": note.document_version_id,
                    "targetRevision": note.review_revision,
                },
                domain_receipt_type="field_comment_review_mutation_receipts",
                domain_receipt_id=str(receipt.id),
            )
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment could not be updated because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_comment_response(note)
