from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import FieldNoteCreateUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.storage import UploadTooLargeError, file_family_from_extension
from app.core.storage import resolve_storage_root, store_upload_file_at
from app.db.models import Document, DocumentVersion, FieldNote, FieldNoteAttachment, FileObject
from app.db.session import get_db_session

router = APIRouter(prefix="/field-notes", tags=["field-notes"], dependencies=[Depends(get_current_user)])
document_field_notes_router = APIRouter(
    prefix="/documents",
    tags=["field-notes"],
    dependencies=[Depends(get_current_user)],
)

NOTE_TYPES = {"experience", "work_evaluation", "issue"}
INPUT_MODES = {"signal", "free_text", "template", "template_with_text", "admin_proxy", "mes_integration"}
STATUSES = {"NEW", "NEEDS_REVIEW", "ANALYZED", "REVIEWED", "SELECTED", "EXCLUDED", "ARCHIVED"}
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


class FieldNoteCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: str | None = Field(default=None, alias="documentId")
    document_version_id: str | None = Field(default=None, alias="documentVersionId")
    structure_item_id: str | None = Field(default=None, alias="structureItemId")
    work_record_id: str | None = Field(default=None, alias="workRecordId")
    note_type: str = Field(default="issue", alias="noteType")
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


class FieldNoteReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    normalized_content: str | None = Field(default=None, alias="normalizedContent")
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    reviewed_by: str | None = Field(default=None, alias="reviewedBy")
    analyzed_by: str | None = Field(default=None, alias="analyzedBy")


class FieldNoteResponse(BaseModel):
    note_id: str
    document_id: str | None
    document_version_id: str | None
    structure_item_id: str | None
    work_record_id: str | None
    note_type: str
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
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    analyzed_at: datetime | None


class FieldNoteAttachmentFileResponse(BaseModel):
    storage_type: str
    storage_key: str
    original_filename: str
    extension: str | None
    mime_type: str | None
    file_family: str | None
    size_bytes: int | None
    hash_sha256: str | None


class FieldNoteAttachmentResponse(BaseModel):
    attachment_id: str
    note_id: str
    attachment_type: str
    caption: str | None
    captured_at: datetime | None
    created_by: str | None
    created_at: datetime
    file: FieldNoteAttachmentFileResponse


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_choice(value: str, allowed: set[str], field_name: str) -> str:
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return value


def _validate_target(session: Session, request: FieldNoteCreateRequest) -> None:
    if not (request.document_id or request.structure_item_id or request.work_record_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A field note must reference documentId, structureItemId, or workRecordId.",
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


def _field_note_response(note: FieldNote) -> FieldNoteResponse:
    return FieldNoteResponse(
        note_id=note.note_id,
        document_id=note.document_id,
        document_version_id=note.document_version_id,
        structure_item_id=note.structure_item_id,
        work_record_id=note.work_record_id,
        note_type=note.note_type,
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
        created_at=note.created_at,
        updated_at=note.updated_at,
        reviewed_at=note.reviewed_at,
        analyzed_at=note.analyzed_at,
    )


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


def _attachment_file_response(file_object: FileObject) -> FieldNoteAttachmentFileResponse:
    return FieldNoteAttachmentFileResponse(
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
    attachment: FieldNoteAttachment,
    file_object: FileObject,
) -> FieldNoteAttachmentResponse:
    return FieldNoteAttachmentResponse(
        attachment_id=attachment.attachment_id,
        note_id=attachment.note_id,
        attachment_type=attachment.attachment_type,
        caption=attachment.caption,
        captured_at=attachment.captured_at,
        created_by=attachment.created_by,
        created_at=attachment.created_at,
        file=_attachment_file_response(file_object),
    )


@router.post("", response_model=FieldNoteResponse, status_code=status.HTTP_201_CREATED)
def create_field_note(
    request: FieldNoteCreateRequest,
    _current_user: FieldNoteCreateUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldNoteResponse:
    request.document_id = _clean_optional(request.document_id)
    request.document_version_id = _clean_optional(request.document_version_id)
    request.structure_item_id = _clean_optional(request.structure_item_id)
    request.work_record_id = _clean_optional(request.work_record_id)
    request.raw_content = request.raw_content.strip()
    _validate_choice(request.note_type, NOTE_TYPES, "noteType")
    _validate_choice(request.input_mode, INPUT_MODES, "inputMode")
    _validate_target(session, request)

    note = FieldNote(
        note_id=_new_public_id("note"),
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        structure_item_id=request.structure_item_id,
        work_record_id=request.work_record_id,
        note_type=request.note_type,
        input_mode=request.input_mode,
        signal_level=_clean_optional(request.signal_level),
        template_id=_clean_optional(request.template_id),
        raw_content=request.raw_content,
        author_id=_clean_optional(request.author_id),
        reported_by=_clean_optional(request.reported_by),
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
            detail="Field note could not be saved because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_note_response(note)


@router.post(
    "/{note_id}/attachments",
    response_model=FieldNoteAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_field_note_attachment(
    note_id: str,
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db_session)],
    attachment_type: Annotated[str | None, Form(alias="attachmentType")] = None,
    caption: Annotated[str | None, Form()] = None,
    captured_at: Annotated[datetime | None, Form(alias="capturedAt")] = None,
    created_by: Annotated[str | None, Form(alias="createdBy")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
) -> FieldNoteAttachmentResponse:
    note_exists = session.scalar(select(FieldNote.id).where(FieldNote.note_id == note_id))
    if note_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field note not found.")

    _validate_attachment_file(file)
    storage_root = resolve_storage_root(app_settings.storage_root)
    try:
        stored = await store_upload_file_at(
            file,
            storage_root=storage_root,
            path_parts=("field-notes", note_id, "attachments"),
            max_size_bytes=app_settings.field_note_attachment_max_bytes,
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

    attachment = FieldNoteAttachment(
        attachment_id=_new_public_id("att"),
        note_id=note_id,
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field note attachment could not be saved because of a database constraint.",
        ) from exc
    session.refresh(attachment)
    return _attachment_response(attachment, file_object)


@router.get("/{note_id}/attachments", response_model=list[FieldNoteAttachmentResponse])
def list_field_note_attachments(
    note_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldNoteAttachmentResponse]:
    note_exists = session.scalar(select(FieldNote.id).where(FieldNote.note_id == note_id))
    if note_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field note not found.")

    rows = session.execute(
        select(FieldNoteAttachment, FileObject)
        .join(FileObject, FieldNoteAttachment.file_object_id == FileObject.id)
        .where(FieldNoteAttachment.note_id == note_id)
        .order_by(desc(FieldNoteAttachment.created_at), desc(FieldNoteAttachment.id))
    ).all()
    return [_attachment_response(attachment, file_object) for attachment, file_object in rows]


@router.get("", response_model=list[FieldNoteResponse])
def list_field_notes(
    session: Annotated[Session, Depends(get_db_session)],
    document_id: Annotated[str | None, Query(alias="documentId")] = None,
    note_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldNoteResponse]:
    statement = select(FieldNote).order_by(desc(FieldNote.created_at), desc(FieldNote.id)).limit(limit)
    if document_id is not None:
        statement = statement.where(FieldNote.document_id == document_id)
    if note_status is not None:
        _validate_choice(note_status, STATUSES, "status")
        statement = statement.where(FieldNote.status == note_status)
    return [_field_note_response(note) for note in session.scalars(statement).all()]


@document_field_notes_router.get("/{document_id}/field-notes", response_model=list[FieldNoteResponse])
def list_document_field_notes(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldNoteResponse]:
    document_exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    notes = session.scalars(
        select(FieldNote)
        .where(FieldNote.document_id == document_id)
        .order_by(desc(FieldNote.created_at), desc(FieldNote.id))
        .limit(limit)
    ).all()
    return [_field_note_response(note) for note in notes]


@router.get("/{note_id}", response_model=FieldNoteResponse)
def get_field_note(
    note_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldNoteResponse:
    note = session.scalar(select(FieldNote).where(FieldNote.note_id == note_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field note not found.")
    return _field_note_response(note)


@router.patch("/{note_id}", response_model=FieldNoteResponse)
def review_field_note(
    note_id: str,
    request: FieldNoteReviewRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldNoteResponse:
    note = session.scalar(select(FieldNote).where(FieldNote.note_id == note_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field note not found.")

    if request.status is not None:
        note.status = _validate_choice(request.status, STATUSES, "status")
    if request.normalized_content is not None:
        note.normalized_content = _clean_optional(request.normalized_content)
    if request.analysis_content is not None:
        note.analysis_content = _clean_optional(request.analysis_content)
    if request.reviewed_by is not None:
        note.reviewed_by = _clean_optional(request.reviewed_by)
        note.reviewed_at = datetime.utcnow()
    if request.analyzed_by is not None:
        note.analyzed_by = _clean_optional(request.analyzed_by)
        note.analyzed_at = datetime.utcnow()

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field note could not be updated because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_note_response(note)
