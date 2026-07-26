from __future__ import annotations

from datetime import datetime, timedelta, timezone
from copy import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    FIELD_COMMENT_DECIDE_ROLES,
    FieldCommentAnalyzeUser,
    FieldCommentCreateUser,
    get_current_user,
)
from app.core.config import Settings, get_settings
from app.core.storage import UploadTooLargeError, file_family_from_extension
from app.core.storage import resolve_storage_root, store_upload_file_at
from app.db.models import (
    ActivityHistory,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    FieldCommentAttachment,
    FieldCommentReviewMutationReceipt,
    FileObject,
    NotificationChannel,
    NotificationChannelMember,
    ReportSource,
    Report,
    TagDefinition,
    UserAccount,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/field-comments", tags=["field-comments"], dependencies=[Depends(get_current_user)])
document_field_comments_router = APIRouter(
    prefix="/documents",
    tags=["field-comments"],
    dependencies=[Depends(get_current_user)],
)

COMMENT_TYPES = {"experience", "work_evaluation", "issue"}
INPUT_MODES = {"signal", "free_text", "template", "template_with_text", "admin_proxy", "mes_integration"}
STATUSES = {"NEW", "ASSIGNED", "NEEDS_REVIEW", "ANALYZED", "REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"}
PRIMARY_WORKFLOW_STATUSES = {"NEW", "ASSIGNED", "ANALYZED", "REVIEWED", "SELECTED"}
ALLOWED_TRANSITIONS = {
    "NEW": {"ASSIGNED", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED"},
    "ASSIGNED": {"NEW", "ANALYZED", "NEEDS_REVIEW", "EXCLUDED"},
    "NEEDS_REVIEW": {"NEW", "ASSIGNED", "ANALYZED", "EXCLUDED"},
    "ANALYZED": {"NEW", "NEEDS_REVIEW", "REVIEWED", "EXCLUDED"},
    "REVIEWED": {"ANALYZED", "SELECTED", "EXCLUDED"},
    "SELECTED": {"REVIEWED", "EXCLUDED", "ARCHIVED"},
    "EXCLUDED": {"NEW", "ARCHIVED"},
    "ARCHIVED": {"EXCLUDED"},
}
ATTACHMENT_TYPES = {"photo", "document", "other"}
ATTACHMENT_ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".pdf",
    ".txt",
    ".md",
}


class FieldCommentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: str | None = Field(default=None, alias="documentId")
    document_version_id: str | None = Field(default=None, alias="documentVersionId")
    structure_item_id: str | None = Field(default=None, alias="structureItemId")
    work_record_id: str | None = Field(default=None, alias="workRecordId")
    comment_type: str = Field(default="issue", alias="commentType")
    input_mode: str = Field(default="free_text", alias="inputMode")
    signal_level: str | None = Field(default=None, alias="signalLevel")
    template_id: str | None = Field(default=None, alias="templateId")
    raw_content: str = Field(alias="rawContent", min_length=1)
    author_id: str | None = Field(default=None, alias="authorId")
    reported_by: str | None = Field(default=None, alias="reportedBy")
    operator_id: str | None = Field(default=None, alias="operatorId")
    entry_source: str = Field(default="field_user", alias="entrySource")
    device_id: str | None = Field(default=None, alias="deviceId")
    location_code: str | None = Field(default=None, alias="locationCode")
    category: str | None = None
    priority: int | None = None
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class FieldCommentReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    normalized_content: str | None = Field(default=None, alias="normalizedContent")
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    reviewed_by: str | None = Field(default=None, alias="reviewedBy")
    analyzed_by: str | None = Field(default=None, alias="analyzedBy")
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")
    conflict_flag: bool | None = Field(default=None, alias="conflictFlag")
    conflict_basis: str | None = Field(default=None, alias="conflictBasis")
    base_review_revision: int | None = Field(default=None, alias="baseReviewRevision", ge=1)
    mutation_key: str | None = Field(default=None, alias="mutationKey", max_length=160)


class FieldCommentBulkReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    comment_ids: list[str] = Field(alias="commentIds", min_length=1, max_length=200)
    status: str | None = None
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")


class FieldCommentBulkReviewItemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    comment_id: str = Field(alias="commentId", min_length=1)
    base_review_revision: int = Field(alias="baseReviewRevision", ge=1)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)


class FieldCommentBulkReviewV2Request(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[FieldCommentBulkReviewItemRequest] = Field(min_length=1, max_length=200)
    status: str | None = None
    normalized_content: str | None = Field(default=None, alias="normalizedContent")
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")
    conflict_flag: bool | None = Field(default=None, alias="conflictFlag")
    conflict_basis: str | None = Field(default=None, alias="conflictBasis")


class FieldCommentBulkReviewItemResponse(BaseModel):
    comment_id: str
    allowed: bool
    success: bool | None = None
    from_status: str | None = None
    target_status: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    review_revision: int | None = None
    receipt: str | None = None
    field_comment: "FieldCommentResponse | None" = None


class FieldCommentBulkReviewResponse(BaseModel):
    requested_count: int
    success_count: int
    failure_count: int
    items: list[FieldCommentBulkReviewItemResponse]


class FieldCommentAuditResponse(BaseModel):
    history_id: str
    event_type: str
    actor_id: str | None
    before_snapshot: dict | None
    after_snapshot: dict | None
    change_reason: str | None
    created_at: datetime


class FieldCommentQualityItemResponse(BaseModel):
    issue_type: str
    comment_id: str | None
    report_id: str | None = None
    age_days: int | None = None
    detail: str


class FieldCommentResponse(BaseModel):
    comment_id: str
    document_id: str | None
    document_version_id: str | None
    structure_item_id: str | None
    work_record_id: str | None
    comment_type: str
    input_mode: str
    signal_level: str | None
    template_id: str | None
    raw_content: str
    normalized_content: str | None
    analysis_content: str | None
    author_id: str | None
    reported_by: str | None
    operator_id: str | None
    entry_source: str
    device_id: str | None
    location_code: str | None
    category: str | None
    priority: int | None
    status: str
    reviewed_by: str | None
    analyzed_by: str | None
    assigned_to: str | None
    review_due_at: datetime | None
    last_transition_reason: str | None
    conflict_flag: bool
    conflict_basis: str | None
    selected_at: datetime | None
    source_hash_sha256: str
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    analyzed_at: datetime | None
    review_revision: int
    workbench_flags: list[str] = Field(default_factory=list)
    workbench_priority: int = 0
    attachment_count: int = 0
    channel_access: str = "NOT_LINKED"


class FieldCommentTraceDocumentResponse(BaseModel):
    document_id: str
    title: str
    status: str
    latest_version_id: str | None
    published_version_id: str | None
    generated_version_ids: list[str]


class FieldCommentTraceReportResponse(BaseModel):
    report_id: str
    report_type: str
    title: str
    status: str
    relation_type: str | None
    source_version_id: str | None
    generated_document: FieldCommentTraceDocumentResponse | None


class FieldCommentTraceResponse(BaseModel):
    field_comment: FieldCommentResponse
    audit: list[FieldCommentAuditResponse]
    reports: list[FieldCommentTraceReportResponse]


class FieldCommentAttachmentFileResponse(BaseModel):
    storage_type: str
    storage_key: str
    original_filename: str
    extension: str | None
    mime_type: str | None
    file_family: str | None
    size_bytes: int | None
    hash_sha256: str | None


class FieldCommentAttachmentResponse(BaseModel):
    attachment_id: str
    comment_id: str
    attachment_type: str
    caption: str | None
    captured_at: datetime | None
    created_by: str | None
    created_at: datetime
    file: FieldCommentAttachmentFileResponse


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_idempotency_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    if cleaned is None:
        return None
    if len(cleaned) > 160:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="idempotencyKey is too long.",
        )
    return cleaned


def _validate_choice(value: str, allowed: set[str], field_name: str) -> str:
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return value


def _validate_target(session: Session, request: FieldCommentCreateRequest) -> None:
    if not (request.document_id or request.structure_item_id or request.work_record_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A field comment must reference documentId, structureItemId, or workRecordId.",
        )

    if request.document_id is not None:
        document_exists = session.scalar(
            select(Document.id).where(
                Document.document_id == request.document_id,
                Document.deleted_at.is_(None),
            )
        )
        if document_exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if request.document_version_id is not None:
        version = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.version_id == request.document_version_id,
            )
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="documentVersionId must reference an existing version_id.",
            )
        if request.document_id is not None and version.document_id != request.document_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="documentVersionId must belong to documentId.",
            )


def _field_comment_response(
    note: FieldComment,
    *,
    workbench_flags: list[str] | None = None,
    workbench_priority: int = 0,
    attachment_count: int = 0,
    channel_access: str = "NOT_LINKED",
) -> FieldCommentResponse:
    return FieldCommentResponse(
        comment_id=note.comment_id,
        document_id=note.document_id,
        document_version_id=note.document_version_id,
        structure_item_id=note.structure_item_id,
        work_record_id=note.work_record_id,
        comment_type=note.comment_type,
        input_mode=note.input_mode,
        signal_level=note.signal_level,
        template_id=note.template_id,
        raw_content=note.raw_content,
        normalized_content=note.normalized_content,
        analysis_content=note.analysis_content,
        author_id=note.author_id,
        reported_by=note.reported_by,
        operator_id=note.operator_id,
        entry_source=note.entry_source,
        device_id=note.device_id,
        location_code=note.location_code,
        category=note.category,
        priority=note.priority,
        status=_effective_status(note),
        reviewed_by=note.reviewed_by,
        analyzed_by=note.analyzed_by,
        assigned_to=note.assigned_to,
        review_due_at=note.review_due_at,
        last_transition_reason=note.last_transition_reason,
        conflict_flag=note.conflict_flag,
        conflict_basis=note.conflict_basis,
        selected_at=note.selected_at,
        source_hash_sha256=_source_hash(note),
        created_at=note.created_at,
        updated_at=note.updated_at,
        reviewed_at=note.reviewed_at,
        analyzed_at=note.analyzed_at,
        review_revision=note.review_revision,
        workbench_flags=workbench_flags or [],
        workbench_priority=workbench_priority,
        attachment_count=attachment_count,
        channel_access=channel_access,
    )


def _attachment_count(session: Session, comment_id: str) -> int:
    return session.scalar(select(func.count()).select_from(FieldCommentAttachment).where(
        FieldCommentAttachment.comment_id == comment_id
    )) or 0


def _channel_access(session: Session, note: FieldComment, current_user: CurrentUser) -> str:
    channel_ids = list(session.scalars(select(NotificationChannel.channel_id).where(
        NotificationChannel.status == "ACTIVE",
        NotificationChannel.source_type == "FIELD_COMMENT",
        NotificationChannel.source_id == note.comment_id,
    )).all())
    if not channel_ids:
        return "NOT_LINKED"
    if current_user.role in {"admin", "system-admin"}:
        return "ALLOWED"
    membership = session.scalar(select(NotificationChannelMember.id).where(
        NotificationChannelMember.channel_id.in_(channel_ids),
        NotificationChannelMember.user_id == current_user.user_id,
        NotificationChannelMember.status == "ACTIVE",
    ).limit(1))
    return "ALLOWED" if membership is not None else "DENIED"


def _workbench_flags(session: Session, note: FieldComment, now: datetime) -> list[str]:
    flags: list[str] = []
    active = note.status not in {"SELECTED", "EXCLUDED", "ARCHIVED"}
    if note.status in {"NEW", "NEEDS_REVIEW"}:
        flags.append("UNREVIEWED")
    if note.conflict_flag:
        flags.append("CONFLICT")
    due_at = note.review_due_at
    if due_at is not None:
        normalized_due = due_at.replace(tzinfo=timezone.utc) if due_at.tzinfo is None else due_at
        if active and normalized_due < now:
            flags.append("OVERDUE")
    if active and note.assigned_to is None:
        flags.append("UNASSIGNED")
    if not note.document_version_id or not note.author_id or not _clean_optional(note.analysis_content):
        flags.append("MISSING_EVIDENCE")
    duplicate = session.scalar(
        select(FieldComment.id).where(
            FieldComment.comment_id != note.comment_id,
            FieldComment.raw_content == note.raw_content,
        ).limit(1)
    )
    if duplicate is not None:
        flags.append("DUPLICATE_SUSPECTED")
    linked = session.scalar(
        select(ReportSource.id).where(
            ReportSource.source_type == "FIELD_COMMENT",
            ReportSource.source_id == note.comment_id,
        ).limit(1)
    )
    if linked is None:
        flags.append("REPORT_UNLINKED")
    return flags


WORKBENCH_FLAG_WEIGHTS = {
    "CONFLICT": 128,
    "OVERDUE": 64,
    "UNASSIGNED": 32,
    "MISSING_EVIDENCE": 16,
    "DUPLICATE_SUSPECTED": 8,
    "UNREVIEWED": 4,
    "REPORT_UNLINKED": 2,
}


def _workbench_priority(flags: list[str]) -> int:
    return sum(WORKBENCH_FLAG_WEIGHTS[flag] for flag in flags)


def _source_snapshot(note: FieldComment) -> dict:
    return {
        "comment_id": note.comment_id,
        "document_id": note.document_id,
        "document_version_id": note.document_version_id,
        "structure_item_id": note.structure_item_id,
        "work_record_id": note.work_record_id,
        "comment_type": note.comment_type,
        "input_mode": note.input_mode,
        "signal_level": note.signal_level,
        "template_id": note.template_id,
        "raw_content": note.raw_content,
        "author_id": note.author_id,
        "reported_by": note.reported_by,
        "operator_id": note.operator_id,
        "entry_source": note.entry_source,
        "device_id": note.device_id,
        "location_code": note.location_code,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


def _effective_status(note: FieldComment) -> str:
    # ASSIGNED is a workflow state over the immutable legacy status constraint.
    # Existing SQLite installations keep NEW in the physical column and assignment
    # identity in assigned_to; API/audit clients see the logical ASSIGNED state.
    if note.status == "NEW" and _clean_optional(note.assigned_to):
        return "ASSIGNED"
    return note.status


def _source_hash(note: FieldComment) -> str:
    payload = json.dumps(_source_snapshot(note), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    receipt = session.scalar(
        select(FieldCommentReviewMutationReceipt).where(
            FieldCommentReviewMutationReceipt.mutation_key == mutation_key
        )
    )
    if receipt is None:
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
    request: FieldCommentReviewRequest | FieldCommentBulkReviewRequest,
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


def _delete_stored_file(storage_root: Path, storage_key: str) -> None:
    target_path = (storage_root / Path(storage_key)).resolve()
    try:
        target_path.relative_to(storage_root)
    except ValueError:
        return
    if target_path.exists() and target_path.is_file():
        target_path.unlink()


def _clean_attachment_type(value: str | None, extension: str, mime_type: str | None) -> str:
    if value is not None and value.strip():
        cleaned = value.strip()
        return _validate_choice(cleaned, ATTACHMENT_TYPES, "attachmentType")

    family = file_family_from_extension(extension, mime_type)
    if family == "image":
        return "photo"
    if family in {"pdf", "text"}:
        return "document"
    return "other"


def _validate_attachment_file(upload: UploadFile) -> None:
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ATTACHMENT_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Attachment file type is not allowed.",
        )


def _attachment_file_response(file_object: FileObject) -> FieldCommentAttachmentFileResponse:
    return FieldCommentAttachmentFileResponse(
        storage_type=file_object.storage_type,
        storage_key=file_object.storage_key,
        original_filename=file_object.original_filename,
        extension=file_object.extension,
        mime_type=file_object.mime_type,
        file_family=file_object.file_family,
        size_bytes=file_object.size_bytes,
        hash_sha256=file_object.hash_sha256,
    )


def _attachment_response(
    attachment: FieldCommentAttachment,
    file_object: FileObject,
) -> FieldCommentAttachmentResponse:
    return FieldCommentAttachmentResponse(
        attachment_id=attachment.attachment_id,
        comment_id=attachment.comment_id,
        attachment_type=attachment.attachment_type,
        caption=attachment.caption,
        captured_at=attachment.captured_at,
        created_by=attachment.created_by,
        created_at=attachment.created_at,
        file=_attachment_file_response(file_object),
    )


@router.post("", response_model=FieldCommentResponse, status_code=status.HTTP_201_CREATED)
def create_field_comment(
    request: FieldCommentCreateRequest,
    current_user: FieldCommentCreateUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    request.document_id = _clean_optional(request.document_id)
    request.document_version_id = _clean_optional(request.document_version_id)
    request.structure_item_id = _clean_optional(request.structure_item_id)
    request.work_record_id = _clean_optional(request.work_record_id)
    request.raw_content = request.raw_content.strip()
    request.idempotency_key = _clean_idempotency_key(request.idempotency_key)
    _validate_choice(request.comment_type, COMMENT_TYPES, "commentType")
    _validate_choice(request.input_mode, INPUT_MODES, "inputMode")
    _validate_target(session, request)
    is_proxy_entry = request.input_mode == "admin_proxy" or request.entry_source.strip() == "admin_proxy"
    if is_proxy_entry and not (_clean_optional(request.reported_by) or _clean_optional(request.operator_id)):
        raise HTTPException(
            status_code=422,
            detail="admin_proxy requires reportedBy or operatorId so the actual reporter/operator is distinct from the entering account.",
        )

    if request.idempotency_key is not None:
        existing = session.scalar(
            select(FieldComment).where(FieldComment.idempotency_key == request.idempotency_key)
        )
        if existing is not None:
            return _field_comment_response(existing)

    note = FieldComment(
        comment_id=_new_public_id("comment"),
        idempotency_key=request.idempotency_key,
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        structure_item_id=request.structure_item_id,
        work_record_id=request.work_record_id,
        comment_type=request.comment_type,
        input_mode=request.input_mode,
        signal_level=_clean_optional(request.signal_level),
        template_id=_clean_optional(request.template_id),
        raw_content=request.raw_content,
        author_id=_clean_optional(request.author_id) or current_user.user_id,
        reported_by=_clean_optional(request.reported_by) if is_proxy_entry else (_clean_optional(request.reported_by) or current_user.display_name),
        operator_id=_clean_optional(request.operator_id),
        entry_source=request.entry_source.strip() or "field_user",
        device_id=_clean_optional(request.device_id),
        location_code=_clean_optional(request.location_code),
        category=_clean_optional(request.category),
        priority=request.priority,
        status="NEW",
    )
    session.add(note)
    session.flush()
    if is_proxy_entry:
        session.add(ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="field_comment.proxy_created",
            actor_id=current_user.user_id,
            target_type="field_comment",
            target_id=note.comment_id,
            target_title=note.comment_id,
            message="관리자 대리 입력: 입력자와 실제 전달자/작업자를 분리 기록",
            after_value=json.dumps({
                "entered_by": current_user.user_id,
                "reported_by": note.reported_by,
                "operator_id": note.operator_id,
                "entry_source": note.entry_source,
                "source_hash_sha256": _source_hash(note),
            }, ensure_ascii=False, sort_keys=True),
            change_reason="관리자 대리 입력 원천 생성",
        ))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment could not be saved because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_comment_response(note)


@router.post(
    "/{comment_id}/attachments",
    response_model=FieldCommentAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_field_comment_attachment(
    comment_id: str,
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db_session)],
    attachment_type: Annotated[str | None, Form(alias="attachmentType")] = None,
    caption: Annotated[str | None, Form()] = None,
    captured_at: Annotated[datetime | None, Form(alias="capturedAt")] = None,
    created_by: Annotated[str | None, Form(alias="createdBy")] = None,
    idempotency_key: Annotated[str | None, Form(alias="idempotencyKey")] = None,
    parent_comment_id: Annotated[str | None, Form(alias="parentCommentId")] = None,
    file_sha256: Annotated[str | None, Form(alias="fileSha256")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
) -> FieldCommentAttachmentResponse:
    if parent_comment_id is not None and parent_comment_id.strip() != comment_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "ATTACHMENT_PARENT_MISMATCH", "message": "첨부 부모 FieldComment가 요청 경로와 다릅니다."},
        )
    expected_hash = _clean_optional(file_sha256)
    if expected_hash is not None and (len(expected_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_hash)):
        raise HTTPException(status_code=422, detail="fileSha256 must be a 64-character SHA-256 hex value.")
    comment_exists = session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id))
    if comment_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    idempotency_key = _clean_idempotency_key(idempotency_key)
    if idempotency_key is not None:
        existing = session.scalar(
            select(FieldCommentAttachment).where(
                FieldCommentAttachment.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            if existing.comment_id != comment_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotencyKey is already used by another field comment.",
                )
            existing_file = session.get(FileObject, existing.file_object_id)
            if existing_file is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotent field comment attachment has no file object.",
                )
            if expected_hash is not None and (
                not existing_file.hash_sha256
                or existing_file.hash_sha256.lower() != expected_hash.lower()
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "같은 첨부 멱등키의 파일 SHA-256이 다릅니다."},
                )
            return _attachment_response(existing, existing_file)

    _validate_attachment_file(file)
    storage_root = resolve_storage_root(app_settings.storage_root)
    try:
        stored = await store_upload_file_at(
            file,
            storage_root=storage_root,
            path_parts=("field-comments", comment_id, "attachments"),
            max_size_bytes=app_settings.field_comment_attachment_max_bytes,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment file is too large.",
        ) from exc
    if expected_hash is not None and stored.hash_sha256.lower() != expected_hash.lower():
        _delete_stored_file(storage_root, stored.storage_key)
        raise HTTPException(
            status_code=409,
            detail={"code": "ATTACHMENT_FILE_HASH_MISMATCH", "message": "업로드 파일 SHA-256이 클라이언트 값과 다릅니다."},
        )

    file_object = FileObject(
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        extension=stored.extension,
        mime_type=stored.mime_type,
        file_family=stored.file_family,
        size_bytes=stored.size_bytes,
        hash_sha256=stored.hash_sha256,
    )
    session.add(file_object)
    session.flush()

    attachment = FieldCommentAttachment(
        attachment_id=_new_public_id("att"),
        idempotency_key=idempotency_key,
        comment_id=comment_id,
        file_object_id=file_object.id,
        attachment_type=_clean_attachment_type(attachment_type, stored.extension, stored.mime_type),
        caption=_clean_optional(caption),
        captured_at=captured_at,
        created_by=_clean_optional(created_by),
    )
    session.add(attachment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _delete_stored_file(storage_root, stored.storage_key)
        if idempotency_key is not None:
            existing = session.scalar(
                select(FieldCommentAttachment).where(
                    FieldCommentAttachment.idempotency_key == idempotency_key
                )
            )
            if existing is not None and existing.comment_id == comment_id:
                existing_file = session.get(FileObject, existing.file_object_id)
                if existing_file is not None:
                    return _attachment_response(existing, existing_file)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment attachment could not be saved because of a database constraint.",
        ) from exc
    session.refresh(attachment)
    return _attachment_response(attachment, file_object)


@router.get("/{comment_id}/attachments", response_model=list[FieldCommentAttachmentResponse])
def list_field_comment_attachments(
    comment_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentAttachmentResponse]:
    comment_exists = session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id))
    if comment_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    rows = session.execute(
        select(FieldCommentAttachment, FileObject)
        .join(FileObject, FieldCommentAttachment.file_object_id == FileObject.id)
        .where(FieldCommentAttachment.comment_id == comment_id)
        .order_by(desc(FieldCommentAttachment.created_at), desc(FieldCommentAttachment.id))
    ).all()
    return [_attachment_response(attachment, file_object) for attachment, file_object in rows]


@router.get("", response_model=list[FieldCommentResponse])
def list_field_comments(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    document_id: Annotated[str | None, Query(alias="documentId")] = None,
    comment_status: Annotated[str | None, Query(alias="status")] = None,
    document_text: Annotated[str | None, Query(alias="documentText")] = None,
    author_text: Annotated[str | None, Query(alias="author")] = None,
    assigned_to: Annotated[str | None, Query(alias="assignedTo")] = None,
    tag_text: Annotated[str | None, Query(alias="tag")] = None,
    line_text: Annotated[str | None, Query(alias="line")] = None,
    equipment_text: Annotated[str | None, Query(alias="equipment")] = None,
    process_text: Annotated[str | None, Query(alias="process")] = None,
    error_type_text: Annotated[str | None, Query(alias="errorType")] = None,
    created_from: Annotated[datetime | None, Query(alias="createdFrom")] = None,
    created_to: Annotated[datetime | None, Query(alias="createdTo")] = None,
    old_new_days: Annotated[int | None, Query(alias="oldNewDays", ge=1, le=3650)] = None,
    unreviewed: Annotated[bool | None, Query(alias="unreviewed")] = None,
    overdue: Annotated[bool | None, Query(alias="overdue")] = None,
    unassigned: Annotated[bool | None, Query(alias="unassigned")] = None,
    missing_evidence: Annotated[bool | None, Query(alias="missingEvidence")] = None,
    duplicate_suspected: Annotated[bool | None, Query(alias="duplicateSuspected")] = None,
    conflict: Annotated[bool | None, Query(alias="conflict")] = None,
    priority_min: Annotated[int | None, Query(alias="priorityMin", ge=0)] = None,
    priority_max: Annotated[int | None, Query(alias="priorityMax", ge=0)] = None,
    has_attachments: Annotated[bool | None, Query(alias="hasAttachments")] = None,
    report_linked: Annotated[bool | None, Query(alias="reportLinked")] = None,
    priority_order: Annotated[bool, Query(alias="priorityOrder")] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldCommentResponse]:
    statement = select(FieldComment)
    if document_id is not None:
        statement = statement.where(FieldComment.document_id == document_id)
    if comment_status is not None:
        _validate_choice(comment_status, STATUSES, "status")
        if comment_status == "ASSIGNED":
            statement = statement.where(FieldComment.status == "NEW", FieldComment.assigned_to.is_not(None))
        elif comment_status == "NEW":
            statement = statement.where(FieldComment.status == "NEW", FieldComment.assigned_to.is_(None))
        else:
            statement = statement.where(FieldComment.status == comment_status)
    if document_text := _clean_optional(document_text):
        pattern = f"%{document_text}%"
        document_ids = select(Document.document_id).where(
            Document.deleted_at.is_(None),
            or_(Document.document_id.ilike(pattern), Document.title.ilike(pattern)),
        )
        statement = statement.where(FieldComment.document_id.in_(document_ids))
    if author_text := _clean_optional(author_text):
        pattern = f"%{author_text}%"
        statement = statement.where(
            or_(
                FieldComment.author_id.ilike(pattern),
                FieldComment.reported_by.ilike(pattern),
                FieldComment.operator_id.ilike(pattern),
            )
        )
    if assigned_to := _clean_optional(assigned_to):
        statement = statement.where(FieldComment.assigned_to == assigned_to)
    if tag_text := _clean_optional(tag_text):
        pattern = f"%{tag_text}%"
        tagged_document_ids = (
            select(DocumentTag.document_id)
            .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
            .where(
                TagDefinition.is_active.is_(True),
                or_(TagDefinition.name.ilike(pattern), TagDefinition.code.ilike(pattern)),
            )
        )
        statement = statement.where(FieldComment.document_id.in_(tagged_document_ids))
    for tag_type, value in (
        ("line", line_text),
        ("equipment", equipment_text),
        ("process", process_text),
        ("error_type", error_type_text),
    ):
        if cleaned := _clean_optional(value):
            pattern = f"%{cleaned}%"
            matching_documents = (
                select(DocumentTag.document_id)
                .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
                .where(
                    TagDefinition.is_active.is_(True),
                    TagDefinition.tag_type == tag_type,
                    or_(TagDefinition.name.ilike(pattern), TagDefinition.code.ilike(pattern)),
                )
            )
            statement = statement.where(FieldComment.document_id.in_(matching_documents))
    if created_from is not None:
        statement = statement.where(FieldComment.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(FieldComment.created_at <= created_to)
    if old_new_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=old_new_days)
        statement = statement.where(FieldComment.status == "NEW", FieldComment.created_at <= cutoff)
    if unreviewed is not None:
        condition = FieldComment.status.in_({"NEW", "NEEDS_REVIEW"})
        statement = statement.where(condition if unreviewed else ~condition)
    if overdue is not None:
        condition = (
            FieldComment.review_due_at.is_not(None)
            & (FieldComment.review_due_at < datetime.now(timezone.utc))
            & ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"})
        )
        statement = statement.where(condition if overdue else ~condition)
    if unassigned is not None:
        condition = FieldComment.assigned_to.is_(None)
        statement = statement.where(condition if unassigned else ~condition)
    if missing_evidence is not None:
        condition = or_(
            FieldComment.document_version_id.is_(None),
            FieldComment.author_id.is_(None),
            FieldComment.analysis_content.is_(None),
            func.trim(FieldComment.analysis_content) == "",
        )
        statement = statement.where(condition if missing_evidence else ~condition)
    attachment_exists = exists(select(FieldCommentAttachment.id).where(FieldCommentAttachment.comment_id == FieldComment.comment_id))
    if has_attachments is not None:
        statement = statement.where(attachment_exists if has_attachments else ~attachment_exists)
    report_source_exists = exists(
        select(ReportSource.id).where(
            ReportSource.source_type == "FIELD_COMMENT",
            ReportSource.source_id == FieldComment.comment_id,
        )
    )
    if report_linked is not None:
        statement = statement.where(report_source_exists if report_linked else ~report_source_exists)
    if conflict is not None:
        statement = statement.where(FieldComment.conflict_flag.is_(conflict))
    if priority_min is not None:
        statement = statement.where(FieldComment.priority >= priority_min)
    if priority_max is not None:
        statement = statement.where(FieldComment.priority <= priority_max)
    statement = statement.order_by(desc(FieldComment.created_at), desc(FieldComment.id))
    if not priority_order and duplicate_suspected is None:
        statement = statement.limit(limit)
    notes = list(session.scalars(statement).all())
    now = datetime.now(timezone.utc)
    rows = []
    for note in notes:
        flags = _workbench_flags(session, note, now)
        if duplicate_suspected is not None and (("DUPLICATE_SUSPECTED" in flags) != duplicate_suspected):
            continue
        rows.append(_field_comment_response(
            note,
            workbench_flags=flags,
            workbench_priority=_workbench_priority(flags),
            attachment_count=_attachment_count(session, note.comment_id),
            channel_access=_channel_access(session, note, current_user),
        ))
    if priority_order:
        rows.sort(
            key=lambda item: (item.workbench_priority, item.created_at, item.comment_id),
            reverse=True,
        )
    return rows[:limit]


@document_field_comments_router.get("/{document_id}/field-comments", response_model=list[FieldCommentResponse])
def list_document_field_comments(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldCommentResponse]:
    document_exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    notes = session.scalars(
        select(FieldComment)
        .where(FieldComment.document_id == document_id)
        .order_by(desc(FieldComment.created_at), desc(FieldComment.id))
        .limit(limit)
    ).all()
    return [_field_comment_response(note) for note in notes]


@router.post("/bulk-review", response_model=list[FieldCommentResponse])
def bulk_review_field_comments(
    request: FieldCommentBulkReviewRequest,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentResponse]:
    comment_ids = list(dict.fromkeys(_clean_optional(item) for item in request.comment_ids))
    if any(item is None for item in comment_ids):
        raise HTTPException(status_code=422, detail="commentIds cannot contain blank values.")
    notes = session.scalars(select(FieldComment).where(FieldComment.comment_id.in_(comment_ids))).all()
    by_id = {note.comment_id: note for note in notes}
    missing = [item for item in comment_ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Field comments not found: {', '.join(missing)}")
    ordered = [by_id[item] for item in comment_ids]
    for note in ordered:
        _claim_review_revision(session, note, note.review_revision)
        _apply_review_change(
            session,
            note,
            request,
            current_user.user_id,
            current_user.role,
            app_settings.field_comment_independent_review_required,
        )
    try:
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bulk FieldComment review could not be saved.") from exc
    return [_field_comment_response(note) for note in ordered]


@router.post("/bulk-review/preview", response_model=FieldCommentBulkReviewResponse)
def preview_bulk_review_field_comments(
    request: FieldCommentBulkReviewV2Request,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentBulkReviewResponse:
    results: list[FieldCommentBulkReviewItemResponse] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for item in request.items:
        cleaned_id = item.comment_id.strip()
        review_request = _bulk_item_review_request(request, item)
        failure: tuple[str, str] | None = None
        note = session.scalar(select(FieldComment).where(FieldComment.comment_id == cleaned_id))
        if cleaned_id in seen_ids:
            failure = ("DUPLICATE_COMMENT_ID", "같은 일괄 요청에서 FieldComment를 중복 선택할 수 없습니다.")
        elif item.mutation_key in seen_keys:
            failure = ("DUPLICATE_MUTATION_KEY", "각 항목에는 서로 다른 mutation key가 필요합니다.")
        elif note is None:
            failure = ("FIELD_COMMENT_NOT_FOUND", "FieldComment를 찾을 수 없습니다.")
        else:
            try:
                replay = _review_idempotent_response(
                    session,
                    cleaned_id,
                    item.mutation_key,
                    _review_intent_hash(cleaned_id, review_request),
                )
                if replay is None:
                    _preview_review_change(
                        session,
                        note,
                        review_request,
                        current_user.user_id,
                        current_user.role,
                        app_settings.field_comment_independent_review_required,
                    )
            except HTTPException as exc:
                failure = _bulk_failure(exc)
        seen_ids.add(cleaned_id)
        seen_keys.add(item.mutation_key)
        results.append(FieldCommentBulkReviewItemResponse(
            comment_id=cleaned_id,
            allowed=failure is None,
            from_status=_effective_status(note) if note is not None else None,
            target_status=request.status,
            failure_code=failure[0] if failure else None,
            failure_reason=failure[1] if failure else None,
            review_revision=note.review_revision if note is not None else None,
            receipt=item.mutation_key,
        ))
    failures = sum(not result.allowed for result in results)
    return FieldCommentBulkReviewResponse(
        requested_count=len(results),
        success_count=0,
        failure_count=failures,
        items=results,
    )


@router.post("/bulk-review/execute", response_model=FieldCommentBulkReviewResponse)
def execute_bulk_review_field_comments(
    request: FieldCommentBulkReviewV2Request,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentBulkReviewResponse:
    results: list[FieldCommentBulkReviewItemResponse] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for item in request.items:
        cleaned_id = item.comment_id.strip()
        review_request = _bulk_item_review_request(request, item)
        failure: tuple[str, str] | None = None
        response: FieldCommentResponse | None = None
        from_status: str | None = None
        try:
            if cleaned_id in seen_ids:
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_COMMENT_ID", "message": "같은 일괄 요청에서 FieldComment를 중복 선택할 수 없습니다."})
            if item.mutation_key in seen_keys:
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_MUTATION_KEY", "message": "각 항목에는 서로 다른 mutation key가 필요합니다."})
            intent_hash = _review_intent_hash(cleaned_id, review_request)
            response = _review_idempotent_response(session, cleaned_id, item.mutation_key, intent_hash)
            if response is None:
                note = session.scalar(select(FieldComment).where(FieldComment.comment_id == cleaned_id))
                if note is None:
                    raise HTTPException(status_code=404, detail={"code": "FIELD_COMMENT_NOT_FOUND", "message": "FieldComment를 찾을 수 없습니다."})
                from_status = _effective_status(note)
                _preview_review_change(
                    session,
                    note,
                    review_request,
                    current_user.user_id,
                    current_user.role,
                    app_settings.field_comment_independent_review_required,
                )
                _claim_review_revision(session, note, item.base_review_revision)
                _apply_review_change(
                    session,
                    note,
                    review_request,
                    current_user.user_id,
                    current_user.role,
                    app_settings.field_comment_independent_review_required,
                )
                session.flush()
                response = _field_comment_response(note)
                session.add(FieldCommentReviewMutationReceipt(
                    mutation_key=item.mutation_key,
                    intent_hash_sha256=intent_hash,
                    comment_id=cleaned_id,
                    review_revision=note.review_revision,
                    response_json=response.model_dump_json(),
                ))
                session.commit()
            else:
                from_status = response.status
        except HTTPException as exc:
            session.rollback()
            failure = _bulk_failure(exc)
        except (IntegrityError, ValueError) as exc:
            session.rollback()
            failure = ("FIELD_COMMENT_BULK_ITEM_CONSTRAINT", str(exc))
        seen_ids.add(cleaned_id)
        seen_keys.add(item.mutation_key)
        results.append(FieldCommentBulkReviewItemResponse(
            comment_id=cleaned_id,
            allowed=failure is None,
            success=failure is None,
            from_status=from_status,
            target_status=request.status,
            failure_code=failure[0] if failure else None,
            failure_reason=failure[1] if failure else None,
            review_revision=response.review_revision if response is not None else None,
            receipt=item.mutation_key,
            field_comment=response,
        ))
    success_count = sum(result.success is True for result in results)
    return FieldCommentBulkReviewResponse(
        requested_count=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        items=results,
    )


@router.get("/quality-workbench", response_model=list[FieldCommentQualityItemResponse])
def field_comment_quality_workbench(
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
    aging_days: Annotated[int, Query(alias="agingDays", ge=1, le=3650)] = 7,
) -> list[FieldCommentQualityItemResponse]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=aging_days)
    result: list[FieldCommentQualityItemResponse] = []
    old_notes = session.scalars(
        select(FieldComment).where(FieldComment.status == "NEW", FieldComment.created_at <= cutoff)
    ).all()
    for note in old_notes:
        created = note.created_at.replace(tzinfo=timezone.utc) if note.created_at.tzinfo is None else note.created_at
        result.append(FieldCommentQualityItemResponse(
            issue_type="OLD_NEW",
            comment_id=note.comment_id,
            age_days=max((now - created).days, 0),
            detail="검토 기한 없이 오래 대기한 신규 FieldComment",
        ))

    selected = session.scalars(select(FieldComment).where(FieldComment.status == "SELECTED")).all()
    for note in selected:
        attachment_count = session.scalar(
            select(func.count()).select_from(FieldCommentAttachment).where(
                FieldCommentAttachment.comment_id == note.comment_id
            )
        ) or 0
        audit_count = session.scalar(
            select(func.count()).select_from(ActivityHistory).where(
                ActivityHistory.target_type == "field_comment",
                ActivityHistory.target_id == note.comment_id,
                ActivityHistory.event_type == "field_comment.review_changed",
            )
        ) or 0
        missing = []
        if not note.document_version_id:
            missing.append("문서 버전")
        if not note.author_id:
            missing.append("작성자")
        if not note.analysis_content:
            missing.append("분석")
        if attachment_count == 0:
            missing.append("첨부")
        if audit_count < 3:
            missing.append("단계별 검토 이력")
        if missing:
            result.append(FieldCommentQualityItemResponse(
                issue_type="WEAK_SELECTED",
                comment_id=note.comment_id,
                detail=f"SELECTED 근거 보강 필요: {', '.join(missing)}",
            ))

    sources = session.scalars(select(ReportSource).where(ReportSource.source_type == "FIELD_COMMENT")).all()
    for source in sources:
        source_comment = session.scalar(
            select(FieldComment).where(FieldComment.comment_id == source.source_id)
        )
        if source_comment is None:
            result.append(FieldCommentQualityItemResponse(
                issue_type="MISSING_REPORT_SOURCE",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서 source가 존재하지 않는 FieldComment를 참조함",
            ))
            continue
        if not source.trace_id or not source.source_version_id or source.source_revision is None:
            result.append(FieldCommentQualityItemResponse(
                issue_type="INCOMPLETE_REPORT_TRACE",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서 source의 trace ID, 관찰 문서 버전 또는 선정 revision이 누락됨",
            ))
        if source.source_hash_sha256 != _source_hash(source_comment):
            result.append(FieldCommentQualityItemResponse(
                issue_type="SOURCE_HASH_MISMATCH",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서에 고정한 원천 hash와 현재 FieldComment 원천 hash가 다름",
            ))
        if source.source_revision is not None and source.source_revision != source_comment.review_revision:
            result.append(FieldCommentQualityItemResponse(
                issue_type="SOURCE_REVISION_MISMATCH",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서에 고정한 선정 revision과 현재 FieldComment 검토 revision이 다름",
            ))
    return result


@router.get("/quality-metrics")
def field_comment_quality_metrics(
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict:
    def distribution(column) -> dict[str, int]:
        return {str(key or "(없음)"): count for key, count in session.execute(
            select(column, func.count()).group_by(column).order_by(column)
        ).all()}

    total = session.scalar(select(func.count()).select_from(FieldComment)) or 0
    logical_status_distribution = dict(sorted(Counter(
        "ASSIGNED" if row.status == "NEW" and _clean_optional(row.assigned_to) else row.status
        for row in session.scalars(select(FieldComment)).all()
    ).items()))
    now = datetime.now(timezone.utc)
    overdue_count = session.scalar(select(func.count()).select_from(FieldComment).where(
        FieldComment.review_due_at.is_not(None),
        FieldComment.review_due_at < now,
        ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"}),
    )) or 0
    unassigned_count = session.scalar(select(func.count()).select_from(FieldComment).where(
        FieldComment.assigned_to.is_(None),
        ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"}),
    )) or 0
    linked = session.scalar(
        select(func.count(func.distinct(ReportSource.source_id))).where(
            ReportSource.source_type == "FIELD_COMMENT"
        )
    ) or 0
    document_total = session.scalar(
        select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
    ) or 0
    documents_with_comments = session.scalar(
        select(func.count(func.distinct(FieldComment.document_id))).where(FieldComment.document_id.is_not(None))
    ) or 0
    source_type_count = session.scalar(
        select(func.count(func.distinct(ReportSource.source_type)))
    ) or 0
    report_total = session.scalar(select(func.count()).select_from(Report)) or 0
    multi_source_reports = session.scalar(
        select(func.count()).select_from(
            select(ReportSource.report_id)
            .group_by(ReportSource.report_id)
            .having(func.count(func.distinct(ReportSource.source_type)) >= 2)
            .subquery()
        )
    ) or 0
    work_sequence_source_count = session.scalar(
        select(func.count()).select_from(ReportSource).where(
            ReportSource.source_type.in_({"WORK_SEQUENCE_ITEM", "WORK_SEQUENCE_HISTORY"})
        )
    ) or 0
    report_source_total = session.scalar(select(func.count()).select_from(ReportSource)) or 0
    def source_origin_exists(source: ReportSource) -> bool:
        model_and_key = {
            "FIELD_COMMENT": (FieldComment, FieldComment.comment_id),
            "DOCUMENT": (Document, Document.document_id),
            "WORK_SEQUENCE_ITEM": (WorkSequenceItem, WorkSequenceItem.item_id),
            "WORK_SEQUENCE_HISTORY": (WorkSequenceChangeHistory, WorkSequenceChangeHistory.change_id),
            "WORK_RECORD": (WorkRecord, WorkRecord.work_record_id),
            "WORK_RECORD_VERSION": (WorkRecordVersion, WorkRecordVersion.version_id),
        }.get(source.source_type)
        if model_and_key is None:
            return False
        model, key = model_and_key
        return session.scalar(select(func.count()).select_from(model).where(key == source.source_id)) > 0

    report_sources = session.scalars(select(ReportSource)).all()
    orphan_count = sum(
        1
        for source in report_sources
        if session.scalar(select(Report.id).where(Report.report_id == source.report_id)) is None
        or not source_origin_exists(source)
    )
    incomplete_trace_count = sum(
        1 for source in report_sources
        if not source.trace_id or not source.source_version_id or not source.source_hash_sha256
        or (source.source_type == "FIELD_COMMENT" and source.source_revision is None)
    )
    field_comment_hash_mismatch_count = 0
    field_comment_revision_mismatch_count = 0
    for source in report_sources:
        if source.source_type != "FIELD_COMMENT" or not source.source_hash_sha256:
            continue
        comment = session.scalar(
            select(FieldComment).where(FieldComment.comment_id == source.source_id)
        )
        if comment is not None and source.source_hash_sha256 != _source_hash(comment):
            field_comment_hash_mismatch_count += 1
        if comment is not None and source.source_revision is not None and source.source_revision != comment.review_revision:
            field_comment_revision_mismatch_count += 1
    duplicate_report_source_count = session.scalar(
        select(func.count()).select_from(
            select(ReportSource.report_id)
            .group_by(
                ReportSource.report_id,
                ReportSource.source_type,
                ReportSource.source_id,
                ReportSource.source_version_id,
            )
            .having(func.count() > 1)
            .subquery()
        )
    ) or 0
    tag_axis_coverage: dict[str, dict[str, int | float]] = {}
    for axis in ("line", "equipment", "item", "process", "error_type"):
        tagged_documents = session.scalar(
            select(func.count(func.distinct(DocumentTag.document_id)))
            .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
            .where(TagDefinition.is_active.is_(True), TagDefinition.tag_type == axis)
        ) or 0
        tag_axis_coverage[axis] = {
            "document_count": tagged_documents,
            "document_rate": round(tagged_documents / document_total, 4) if document_total else 0.0,
        }
    return {
        "total": total,
        "status_distribution": logical_status_distribution,
        "sla": {"overdue_count": overdue_count, "unassigned_active_count": unassigned_count},
        "signal_distribution": distribution(FieldComment.signal_level),
        "actor_distribution": distribution(FieldComment.author_id),
        "line_distribution": distribution(FieldComment.location_code),
        "error_type_distribution": distribution(FieldComment.category),
        "report_linked_count": linked,
        "report_link_rate": round(linked / total, 4) if total else 0.0,
        "connection_quality": {
            "document_total": document_total,
            "documents_with_field_comments": documents_with_comments,
            "document_field_comment_rate": round(documents_with_comments / document_total, 4) if document_total else 0.0,
            "field_comment_total": total,
            "field_comments_linked_to_reports": linked,
            "field_comment_report_rate": round(linked / total, 4) if total else 0.0,
            "work_sequence_report_source_count": work_sequence_source_count,
            "report_total": report_total,
            "reports_with_two_or_more_source_types": multi_source_reports,
            "multi_source_report_rate": round(multi_source_reports / report_total, 4) if report_total else 0.0,
            "report_source_total": report_source_total,
            "report_source_type_count": source_type_count,
            "orphan_report_source_count": orphan_count,
            "orphan_report_source_rate": round(orphan_count / report_source_total, 4) if report_source_total else 0.0,
            "incomplete_report_trace_count": incomplete_trace_count,
            "field_comment_source_hash_mismatch_count": field_comment_hash_mismatch_count,
            "field_comment_source_revision_mismatch_count": field_comment_revision_mismatch_count,
            "duplicate_report_source_count": duplicate_report_source_count,
        },
        "tag_axis_coverage": tag_axis_coverage,
    }


def _audit_responses(session: Session, comment_id: str) -> list[FieldCommentAuditResponse]:
    rows = session.scalars(
        select(ActivityHistory).where(
            ActivityHistory.target_type == "field_comment",
            ActivityHistory.target_id == comment_id,
        ).order_by(ActivityHistory.created_at, ActivityHistory.id)
    ).all()
    return [FieldCommentAuditResponse(
        history_id=row.history_id,
        event_type=row.event_type,
        actor_id=row.actor_id,
        before_snapshot=json.loads(row.before_value) if row.before_value else None,
        after_snapshot=json.loads(row.after_value) if row.after_value else None,
        change_reason=row.change_reason,
        created_at=row.created_at,
    ) for row in rows]


@router.get("/{comment_id}/traceability", response_model=FieldCommentTraceResponse)
def get_field_comment_traceability(
    comment_id: str,
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentTraceResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=404, detail="Field comment not found.")
    source_rows = session.execute(
        select(ReportSource, Report)
        .join(Report, Report.report_id == ReportSource.report_id)
        .where(ReportSource.source_type == "FIELD_COMMENT", ReportSource.source_id == comment_id)
        .order_by(Report.created_at, Report.report_id)
    ).all()
    reports: list[FieldCommentTraceReportResponse] = []
    for source, report in source_rows:
        document_response = None
        if report.generated_document_id:
            document = session.scalar(
                select(Document).where(Document.document_id == report.generated_document_id)
            )
            if document is not None:
                version_ids = list(session.scalars(
                    select(DocumentVersion.version_id)
                    .where(DocumentVersion.document_id == document.document_id)
                    .order_by(DocumentVersion.version_no)
                ).all())
                document_response = FieldCommentTraceDocumentResponse(
                    document_id=document.document_id,
                    title=document.title,
                    status=document.status,
                    latest_version_id=document.latest_version_id,
                    published_version_id=document.published_version_id,
                    generated_version_ids=version_ids,
                )
        reports.append(FieldCommentTraceReportResponse(
            report_id=report.report_id,
            report_type=report.report_type,
            title=report.title,
            status=report.status,
            relation_type=source.relation_type,
            source_version_id=source.source_version_id,
            generated_document=document_response,
        ))
    flags = _workbench_flags(session, note, datetime.now(timezone.utc))
    return FieldCommentTraceResponse(
        field_comment=_field_comment_response(
            note,
            workbench_flags=flags,
            workbench_priority=_workbench_priority(flags),
        ),
        audit=_audit_responses(session, comment_id),
        reports=reports,
    )


@router.get("/{comment_id}/audit", response_model=list[FieldCommentAuditResponse])
def list_field_comment_audit(
    comment_id: str,
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentAuditResponse]:
    if session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id)) is None:
        raise HTTPException(status_code=404, detail="Field comment not found.")
    return _audit_responses(session, comment_id)


@router.get("/{comment_id}", response_model=FieldCommentResponse)
def get_field_comment(
    comment_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")
    return _field_comment_response(
        note,
        attachment_count=_attachment_count(session, note.comment_id),
        channel_access=_channel_access(session, note, current_user),
    )


@router.patch("/{comment_id}", response_model=FieldCommentResponse)
def review_field_comment(
    comment_id: str,
    request: FieldCommentReviewRequest,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    mutation_key = _clean_idempotency_key(request.mutation_key)
    intent_hash = _review_intent_hash(comment_id, request)
    replay = _review_idempotent_response(session, comment_id, mutation_key, intent_hash)
    if replay is not None:
        return replay

    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

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
            session.add(FieldCommentReviewMutationReceipt(
                mutation_key=mutation_key,
                intent_hash_sha256=intent_hash,
                comment_id=comment_id,
                review_revision=note.review_revision,
                response_json=response.model_dump_json(),
            ))
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment could not be updated because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_comment_response(note)
