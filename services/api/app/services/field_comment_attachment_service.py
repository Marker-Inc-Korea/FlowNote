from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.api.v1.field_comment_contracts import (
    ATTACHMENT_ALLOWED_EXTENSIONS,
    ATTACHMENT_TYPES,
    FieldCommentAttachmentFileResponse,
    FieldCommentAttachmentResponse,
)
from app.core.storage import file_family_from_extension
from app.db.models import FieldCommentAttachment, FileObject
from app.services.field_comment_support import _validate_choice

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
