from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (
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
    FileObject,
    ReportSource,
    TagDefinition,
    UserAccount,
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
STATUSES = {"NEW", "NEEDS_REVIEW", "ANALYZED", "REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"}
PRIMARY_WORKFLOW_STATUSES = {"NEW", "ANALYZED", "REVIEWED", "SELECTED"}
ALLOWED_TRANSITIONS = {
    "NEW": {"ANALYZED", "NEEDS_REVIEW", "EXCLUDED"},
    "NEEDS_REVIEW": {"NEW", "ANALYZED", "EXCLUDED"},
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


class FieldCommentBulkReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    comment_ids: list[str] = Field(alias="commentIds", min_length=1, max_length=200)
    status: str | None = None
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    review_due_at: datetime | None = Field(default=None, alias="reviewDueAt")
    transition_reason: str | None = Field(default=None, alias="transitionReason")


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
    selected_at: datetime | None
    source_hash_sha256: str
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    analyzed_at: datetime | None


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


def _field_comment_response(note: FieldComment) -> FieldCommentResponse:
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
        status=note.status,
        reviewed_by=note.reviewed_by,
        analyzed_by=note.analyzed_by,
        assigned_to=note.assigned_to,
        review_due_at=note.review_due_at,
        last_transition_reason=note.last_transition_reason,
        selected_at=note.selected_at,
        source_hash_sha256=_source_hash(note),
        created_at=note.created_at,
        updated_at=note.updated_at,
        reviewed_at=note.reviewed_at,
        analyzed_at=note.analyzed_at,
    )


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


def _source_hash(note: FieldComment) -> str:
    payload = json.dumps(_source_snapshot(note), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _review_snapshot(note: FieldComment) -> dict:
    return {
        "source_hash_sha256": _source_hash(note),
        "status": note.status,
        "normalized_content": note.normalized_content,
        "analysis_content": note.analysis_content,
        "assigned_to": note.assigned_to,
        "review_due_at": note.review_due_at.isoformat() if note.review_due_at else None,
        "analyzed_by": note.analyzed_by,
        "reviewed_by": note.reviewed_by,
    }


def _load_user_id(session: Session, value: str | None, field_name: str) -> str | None:
    user_id = _clean_optional(value)
    if user_id is None:
        return None
    if session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id)) is None:
        raise HTTPException(status_code=422, detail=f"{field_name} must reference an existing user_id.")
    return user_id


def _validate_transition(note: FieldComment, target: str, reason: str | None, actor_role: str) -> str:
    if target == note.status:
        return _clean_optional(reason) or note.last_transition_reason or "상태 유지"
    if target not in ALLOWED_TRANSITIONS[note.status]:
        raise HTTPException(status_code=409, detail=f"Transition {note.status} -> {target} is not allowed.")
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
) -> None:
    before = _review_snapshot(note)
    if isinstance(request, FieldCommentReviewRequest):
        if request.normalized_content is not None:
            note.normalized_content = _clean_optional(request.normalized_content)
        if request.analysis_content is not None:
            note.analysis_content = _clean_optional(request.analysis_content)
    if request.assigned_to is not None:
        note.assigned_to = _load_user_id(session, request.assigned_to, "assignedTo")
    if request.review_due_at is not None:
        note.review_due_at = request.review_due_at

    reason = None
    if request.status is not None:
        target = _validate_choice(request.status, STATUSES, "status")
        reason = _validate_transition(note, target, request.transition_reason, actor_role)
        if target != note.status:
            note.status = target
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
        reported_by=_clean_optional(request.reported_by) or current_user.display_name,
        operator_id=_clean_optional(request.operator_id),
        entry_source=request.entry_source.strip() or "field_user",
        device_id=_clean_optional(request.device_id),
        location_code=_clean_optional(request.location_code),
        category=_clean_optional(request.category),
        priority=request.priority,
        status="NEW",
    )
    session.add(note)
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
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
) -> FieldCommentAttachmentResponse:
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
    has_attachments: Annotated[bool | None, Query(alias="hasAttachments")] = None,
    report_linked: Annotated[bool | None, Query(alias="reportLinked")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldCommentResponse]:
    statement = select(FieldComment).order_by(desc(FieldComment.created_at), desc(FieldComment.id)).limit(limit)
    if document_id is not None:
        statement = statement.where(FieldComment.document_id == document_id)
    if comment_status is not None:
        _validate_choice(comment_status, STATUSES, "status")
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
    return [_field_comment_response(note) for note in session.scalars(statement).all()]


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
        _apply_review_change(session, note, request, current_user.user_id, current_user.role)
    try:
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bulk FieldComment review could not be saved.") from exc
    return [_field_comment_response(note) for note in ordered]


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
        exists_comment = session.scalar(
            select(FieldComment.id).where(FieldComment.comment_id == source.source_id)
        )
        if exists_comment is None:
            result.append(FieldCommentQualityItemResponse(
                issue_type="MISSING_REPORT_SOURCE",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서 source가 존재하지 않는 FieldComment를 참조함",
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
    linked = session.scalar(
        select(func.count(func.distinct(ReportSource.source_id))).where(
            ReportSource.source_type == "FIELD_COMMENT"
        )
    ) or 0
    return {
        "total": total,
        "status_distribution": distribution(FieldComment.status),
        "signal_distribution": distribution(FieldComment.signal_level),
        "actor_distribution": distribution(FieldComment.author_id),
        "line_distribution": distribution(FieldComment.location_code),
        "error_type_distribution": distribution(FieldComment.category),
        "report_linked_count": linked,
        "report_link_rate": round(linked / total, 4) if total else 0.0,
    }


@router.get("/{comment_id}/audit", response_model=list[FieldCommentAuditResponse])
def list_field_comment_audit(
    comment_id: str,
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentAuditResponse]:
    if session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id)) is None:
        raise HTTPException(status_code=404, detail="Field comment not found.")
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


@router.get("/{comment_id}", response_model=FieldCommentResponse)
def get_field_comment(
    comment_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")
    return _field_comment_response(note)


@router.patch("/{comment_id}", response_model=FieldCommentResponse)
def review_field_comment(
    comment_id: str,
    request: FieldCommentReviewRequest,
    current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    _apply_review_change(session, note, request, current_user.user_id, current_user.role)

    try:
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment could not be updated because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_comment_response(note)
