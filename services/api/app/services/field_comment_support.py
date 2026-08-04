from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentVersion, FieldComment
from app.api.v1.field_comment_contracts import FieldCommentCreateRequest

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
