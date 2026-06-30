from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import DocumentWriteUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.storage import resolve_storage_root, store_upload_file
from app.db.models import ActivityHistory, Document, DocumentTag, DocumentVersion, FileObject
from app.db.models import TagDefinition, UserAccount
from app.db.session import get_db_session

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)])

DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}
CREATABLE_DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "ARCHIVED"}
VERSION_STATUSES = {"WORKING", "IN_REVIEW", "APPROVED", "PUBLISHED", "ARCHIVED"}


class FileObjectResponse(BaseModel):
    storage_type: str
    storage_key: str
    original_filename: str
    extension: str | None
    mime_type: str | None
    file_family: str | None
    size_bytes: int | None
    hash_sha256: str | None


class DocumentVersionResponse(BaseModel):
    version_id: str
    document_id: str
    version_no: int
    version_label: str | None
    change_reason: str
    version_status: str
    is_latest: bool
    is_published: bool
    created_by: str | None
    created_at: datetime
    file: FileObjectResponse


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    description: str | None
    document_type: str
    owner_id: str | None
    category_id: str | None
    status: str
    latest_version_id: str | None
    published_version_id: str | None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    latest_version: DocumentVersionResponse | None = None
    published_version: DocumentVersionResponse | None = None


class DocumentListItem(BaseModel):
    document_id: str
    title: str
    document_type: str
    status: str
    latest_version_id: str | None
    latest_version_no: int | None = None
    latest_filename: str | None = None
    published_version_id: str | None = None
    published_version_no: int | None = None
    published_filename: str | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class DocumentStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1)
    change_reason: str | None = Field(default=None, alias="changeReason")


class DocumentVersionStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1)
    change_reason: str | None = Field(default=None, alias="changeReason")


class DocumentVersionPublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_reason: str | None = Field(default=None, alias="changeReason")


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _validate_change_reason(change_reason: str) -> str:
    cleaned = change_reason.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="changeReason is required.",
        )
    return cleaned


def _clean_change_reason(change_reason: str | None) -> str | None:
    if change_reason is None:
        return None
    cleaned = change_reason.strip()
    return cleaned or None


def _validate_status(value: str, allowed: set[str], field_name: str = "status") -> str:
    cleaned = value.strip().upper()
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return cleaned


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


def _normalize_tag_code(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _clean_tags(values: list[str] | None) -> list[str]:
    if not values:
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in value.split(","):
            cleaned = item.strip()
            if not cleaned:
                continue
            key = _normalize_tag_code(cleaned)
            if key in seen:
                continue
            seen.add(key)
            tags.append(cleaned)
    return tags


def _tag_response(session: Session, document_id: str) -> list[str]:
    rows = session.execute(
        select(TagDefinition.name)
        .join(DocumentTag, DocumentTag.tag_id == TagDefinition.tag_id)
        .where(DocumentTag.document_id == document_id, TagDefinition.is_active.is_(True))
        .order_by(TagDefinition.name)
    ).all()
    return [row[0] for row in rows]


def _ensure_tag(session: Session, name: str, *, tag_type: str = "custom") -> TagDefinition:
    code = _normalize_tag_code(name)
    existing = session.scalar(
        select(TagDefinition).where(TagDefinition.tag_type == tag_type, TagDefinition.code == code)
    )
    if existing is not None:
        if existing.name != name:
            existing.name = name
        if not existing.is_active:
            existing.is_active = True
        return existing

    tag = TagDefinition(
        tag_id=_new_public_id("tag"),
        tag_type=tag_type,
        code=code,
        name=name,
    )
    session.add(tag)
    session.flush()
    return tag


def _replace_document_tags(session: Session, document_id: str, tags: list[str]) -> None:
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    for name in tags:
        tag = _ensure_tag(session, name)
        session.add(DocumentTag(document_id=document_id, tag_id=tag.tag_id))


def _validate_user_id(session: Session, user_id: str | None, field_name: str) -> str | None:
    if user_id is None:
        return None
    exists = session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must reference an existing user_id.",
        )
    return user_id


def _record_activity(
    session: Session,
    *,
    event_type: str,
    actor_id: str | None,
    target_type: str,
    target_id: str | None,
    target_title: str | None,
    message: str,
    before_value: str | None = None,
    after_value: str | None = None,
    change_reason: str | None = None,
) -> None:
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type=event_type,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            target_title=target_title,
            message=message,
            before_value=before_value,
            after_value=after_value,
            change_reason=change_reason,
        )
    )


def _delete_stored_file(storage_root: Path, storage_key: str) -> None:
    target_path = (storage_root / Path(storage_key)).resolve()
    try:
        target_path.relative_to(storage_root)
    except ValueError:
        return
    if target_path.exists() and target_path.is_file():
        target_path.unlink()


def _file_response(file_object: FileObject) -> FileObjectResponse:
    return FileObjectResponse(
        storage_type=file_object.storage_type,
        storage_key=file_object.storage_key,
        original_filename=file_object.original_filename,
        extension=file_object.extension,
        mime_type=file_object.mime_type,
        file_family=file_object.file_family,
        size_bytes=file_object.size_bytes,
        hash_sha256=file_object.hash_sha256,
    )


def _version_response(version: DocumentVersion, file_object: FileObject) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        version_id=version.version_id,
        document_id=version.document_id,
        version_no=version.version_no,
        version_label=version.version_label,
        change_reason=version.change_reason,
        version_status=version.version_status,
        is_latest=version.is_latest,
        is_published=version.is_published,
        created_by=version.created_by,
        created_at=version.created_at,
        file=_file_response(file_object),
    )


def _latest_version_for_document(
    session: Session,
    document_id: str,
) -> tuple[DocumentVersion, FileObject] | None:
    row = session.execute(
        select(DocumentVersion, FileObject)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.is_latest.is_(True))
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def _published_version_for_document(
    session: Session,
    document_id: str,
) -> tuple[DocumentVersion, FileObject] | None:
    row = session.execute(
        select(DocumentVersion, FileObject)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_published.is_(True),
            DocumentVersion.version_status == "PUBLISHED",
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def _document_response(session: Session, document: Document) -> DocumentResponse:
    latest = _latest_version_for_document(session, document.document_id)
    latest_response = _version_response(*latest) if latest is not None else None
    published = _published_version_for_document(session, document.document_id)
    published_response = _version_response(*published) if published is not None else None
    tags = _tag_response(session, document.document_id)
    return DocumentResponse(
        document_id=document.document_id,
        title=document.title,
        description=document.description,
        document_type=document.document_type,
        owner_id=document.owner_id,
        category_id=document.category_id,
        status=document.status,
        latest_version_id=document.latest_version_id,
        published_version_id=document.published_version_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        tags=tags,
        latest_version=latest_response,
        published_version=published_response,
    )


async def _save_file_object(
    upload: UploadFile,
    *,
    app_settings: Settings,
    document_id: str,
    version_no: int,
) -> FileObject:
    storage_root = resolve_storage_root(app_settings.storage_root)
    stored = await store_upload_file(
        upload,
        storage_root=storage_root,
        document_id=document_id,
        version_no=version_no,
    )
    return FileObject(
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        extension=stored.extension,
        mime_type=stored.mime_type,
        file_family=stored.file_family,
        size_bytes=stored.size_bytes,
        hash_sha256=stored.hash_sha256,
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1)],
    document_type: Annotated[str, Form(alias="documentType", min_length=1)],
    change_reason: Annotated[str, Form(alias="changeReason", min_length=1)],
    _current_user: DocumentWriteUser,
    description: Annotated[str | None, Form()] = None,
    owner_id: Annotated[str | None, Form(alias="ownerId")] = None,
    category_id: Annotated[str | None, Form(alias="categoryId")] = None,
    version_label: Annotated[str | None, Form(alias="versionLabel")] = None,
    document_status: Annotated[
        str,
        Form(alias="status", pattern="^(WORKING|IN_REVIEW|ARCHIVED)$"),
    ] = "WORKING",
    tags: Annotated[list[str] | None, Form()] = None,
    created_by: Annotated[str | None, Form(alias="createdBy")] = None,
    idempotency_key: Annotated[str | None, Form(alias="idempotencyKey")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
) -> DocumentResponse:
    change_reason = _validate_change_reason(change_reason)
    document_status = _validate_status(
        document_status,
        CREATABLE_DOCUMENT_STATUSES,
        "status",
    )
    cleaned_tags = _clean_tags(tags)
    owner_id = _validate_user_id(session, _clean_optional(owner_id), "ownerId")
    created_by = _validate_user_id(session, _clean_optional(created_by), "createdBy")
    idempotency_key = _clean_idempotency_key(idempotency_key)
    if idempotency_key is not None:
        existing = session.scalar(
            select(Document).where(
                Document.idempotency_key == idempotency_key,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            return _document_response(session, existing)

    document_id = _new_public_id("doc")
    version_id = _new_public_id("ver")
    version_no = 1
    storage_root = resolve_storage_root(app_settings.storage_root)

    file_object = await _save_file_object(
        file,
        app_settings=app_settings,
        document_id=document_id,
        version_no=version_no,
    )
    session.add(file_object)
    session.flush()

    document = Document(
        document_id=document_id,
        idempotency_key=idempotency_key,
        title=title.strip(),
        description=_clean_optional(description),
        document_type=document_type.strip(),
        owner_id=owner_id,
        category_id=_clean_optional(category_id),
        status=document_status,
        latest_version_id=version_id,
        published_version_id=None,
    )
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        file_object_id=file_object.id,
        version_no=version_no,
        version_label=version_label.strip() if version_label else "v1",
        change_reason=change_reason,
        version_status="WORKING",
        is_latest=True,
        is_published=False,
        published_at=None,
        created_by=created_by or owner_id,
    )
    session.add(document)
    session.add(version)
    _replace_document_tags(session, document_id, cleaned_tags)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _delete_stored_file(storage_root, file_object.storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document could not be saved because of a database constraint.",
        ) from exc
    session.refresh(document)
    return _document_response(session, document)


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    session: Annotated[Session, Depends(get_db_session)],
) -> list[DocumentListItem]:
    rows = session.execute(
        select(Document, DocumentVersion, FileObject)
        .join(DocumentVersion, Document.latest_version_id == DocumentVersion.version_id)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(Document.deleted_at.is_(None))
        .order_by(desc(Document.updated_at), desc(Document.id))
    ).all()
    items: list[DocumentListItem] = []
    for document, version, file_object in rows:
        published = _published_version_for_document(session, document.document_id)
        published_version = published[0] if published is not None else None
        published_file = published[1] if published is not None else None
        items.append(
            DocumentListItem(
                document_id=document.document_id,
                title=document.title,
                document_type=document.document_type,
                status=document.status,
                latest_version_id=document.latest_version_id,
                latest_version_no=version.version_no,
                latest_filename=file_object.original_filename,
                published_version_id=document.published_version_id,
                published_version_no=published_version.version_no if published_version else None,
                published_filename=published_file.original_filename if published_file else None,
                tags=_tag_response(session, document.document_id),
                updated_at=document.updated_at,
            )
        )
    return items


@router.get("/published", response_model=list[DocumentListItem])
def list_published_documents(
    session: Annotated[Session, Depends(get_db_session)],
) -> list[DocumentListItem]:
    rows = session.execute(
        select(Document, DocumentVersion, FileObject)
        .join(DocumentVersion, Document.published_version_id == DocumentVersion.version_id)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(
            Document.deleted_at.is_(None),
            Document.status == "PUBLISHED",
            DocumentVersion.is_published.is_(True),
            DocumentVersion.version_status == "PUBLISHED",
        )
        .order_by(desc(Document.updated_at), desc(Document.id))
    ).all()
    items: list[DocumentListItem] = []
    for document, version, file_object in rows:
        items.append(
            DocumentListItem(
                document_id=document.document_id,
                title=document.title,
                document_type=document.document_type,
                status=document.status,
                latest_version_id=document.latest_version_id,
                latest_version_no=None,
                latest_filename=None,
                published_version_id=document.published_version_id,
                published_version_no=version.version_no,
                published_filename=file_object.original_filename,
                tags=_tag_response(session, document.document_id),
                updated_at=document.updated_at,
            )
        )
    return items


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    document = session.scalar(
        select(Document).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return _document_response(session, document)


@router.get("/{document_id}/published", response_model=DocumentVersionResponse)
def get_published_document_version(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentVersionResponse:
    document = session.scalar(
        select(Document).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    published = _published_version_for_document(session, document_id)
    if document.status != "PUBLISHED" or published is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published document version not found.",
        )
    return _version_response(*published)


@router.put("/{document_id}/tags", response_model=DocumentResponse)
def replace_document_tags(
    document_id: str,
    tags: list[str],
    _current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    document = session.scalar(
        select(Document).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    _replace_document_tags(session, document_id, _clean_tags(tags))
    session.commit()
    session.refresh(document)
    return _document_response(session, document)


@router.patch("/{document_id}/status", response_model=DocumentResponse)
def update_document_status(
    document_id: str,
    payload: DocumentStatusUpdateRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    target_status = _validate_status(payload.status, DOCUMENT_STATUSES)
    document = session.scalar(
        select(Document).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    before = document.status
    if before != target_status:
        if target_status == "PUBLISHED" and document.published_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Document cannot be set to PUBLISHED without a published version.",
            )
        document.status = target_status
        _record_activity(
            session,
            event_type="document.status_changed",
            actor_id=current_user.user_id,
            target_type="document",
            target_id=document.document_id,
            target_title=document.title,
            message=f"Document status changed from {before} to {target_status}.",
            before_value=before,
            after_value=target_status,
            change_reason=_clean_change_reason(payload.change_reason),
        )
    session.commit()
    session.refresh(document)
    return _document_response(session, document)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
def list_document_versions(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[DocumentVersionResponse]:
    document_exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    rows = session.execute(
        select(DocumentVersion, FileObject)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(DocumentVersion.document_id == document_id)
        .order_by(desc(DocumentVersion.version_no))
    ).all()
    return [_version_response(version, file_object) for version, file_object in rows]


@router.patch("/{document_id}/versions/{version_id}/status", response_model=DocumentVersionResponse)
def update_document_version_status(
    document_id: str,
    version_id: str,
    payload: DocumentVersionStatusUpdateRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentVersionResponse:
    target_status = _validate_status(payload.status, VERSION_STATUSES)
    row = session.execute(
        select(Document, DocumentVersion, FileObject)
        .join(DocumentVersion, Document.document_id == DocumentVersion.document_id)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(
            Document.document_id == document_id,
            Document.deleted_at.is_(None),
            DocumentVersion.version_id == version_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")

    document, version, file_object = row
    if target_status == "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use the publish endpoint to publish a document version.",
        )

    before = version.version_status
    if version.is_published and target_status != "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Published versions must be changed through the publish endpoint.",
        )
    if before != target_status:
        version.version_status = target_status
        _record_activity(
            session,
            event_type="document.version_status_changed",
            actor_id=current_user.user_id,
            target_type="document_version",
            target_id=version.version_id,
            target_title=document.title,
            message=(
                f"Document version v{version.version_no} status changed "
                f"from {before} to {target_status}."
            ),
            before_value=before,
            after_value=target_status,
            change_reason=_clean_change_reason(payload.change_reason),
        )
    session.commit()
    session.refresh(version)
    return _version_response(version, file_object)


@router.post("/{document_id}/versions/{version_id}/publish", response_model=DocumentResponse)
def publish_document_version(
    document_id: str,
    version_id: str,
    payload: DocumentVersionPublishRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    row = session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, Document.document_id == DocumentVersion.document_id)
        .where(
            Document.document_id == document_id,
            Document.deleted_at.is_(None),
            DocumentVersion.version_id == version_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")

    document, version = row
    previous_document_status = document.status
    previous_published_version_id = document.published_version_id
    now = datetime.now(timezone.utc)

    session.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id,
        DocumentVersion.is_published.is_(True),
    ).update(
        {
            "is_published": False,
            "published_at": None,
            "version_status": "SUPERSEDED",
        },
        synchronize_session=False,
    )

    version.is_published = True
    version.version_status = "PUBLISHED"
    version.published_at = now
    document.published_version_id = version.version_id
    document.status = "PUBLISHED"

    _record_activity(
        session,
        event_type="document.version_published",
        actor_id=current_user.user_id,
        target_type="document_version",
        target_id=version.version_id,
        target_title=document.title,
        message=f"Document version v{version.version_no} was published.",
        before_value=previous_published_version_id,
        after_value=version.version_id,
        change_reason=_clean_change_reason(payload.change_reason),
    )
    if previous_document_status != "PUBLISHED":
        _record_activity(
            session,
            event_type="document.status_changed",
            actor_id=current_user.user_id,
            target_type="document",
            target_id=document.document_id,
            target_title=document.title,
            message=f"Document status changed from {previous_document_status} to PUBLISHED.",
            before_value=previous_document_status,
            after_value="PUBLISHED",
            change_reason=_clean_change_reason(payload.change_reason),
        )

    session.commit()
    session.refresh(document)
    return _document_response(session, document)


@router.post(
    "/{document_id}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_version(
    document_id: str,
    file: Annotated[UploadFile, File()],
    change_reason: Annotated[str, Form(alias="changeReason", min_length=1)],
    _current_user: DocumentWriteUser,
    version_label: Annotated[str | None, Form(alias="versionLabel")] = None,
    created_by: Annotated[str | None, Form(alias="createdBy")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
) -> DocumentVersionResponse:
    change_reason = _validate_change_reason(change_reason)
    created_by = _validate_user_id(session, _clean_optional(created_by), "createdBy")
    document = session.scalar(
        select(Document).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    latest_version_no = session.scalar(
        select(DocumentVersion.version_no)
        .where(DocumentVersion.document_id == document_id)
        .order_by(desc(DocumentVersion.version_no))
        .limit(1)
    )
    version_no = (latest_version_no or 0) + 1
    version_id = _new_public_id("ver")
    storage_root = resolve_storage_root(app_settings.storage_root)
    file_object = await _save_file_object(
        file,
        app_settings=app_settings,
        document_id=document_id,
        version_no=version_no,
    )
    session.add(file_object)
    session.flush()

    session.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id,
        DocumentVersion.is_latest.is_(True),
    ).update(
        {
            "is_latest": False,
            "version_status": case(
                (DocumentVersion.is_published.is_(True), "PUBLISHED"),
                else_="SUPERSEDED",
            ),
        },
        synchronize_session=False,
    )

    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        file_object_id=file_object.id,
        version_no=version_no,
        version_label=version_label.strip() if version_label else f"v{version_no}",
        change_reason=change_reason,
        version_status="WORKING",
        is_latest=True,
        is_published=False,
        created_by=created_by or document.owner_id,
    )
    document.latest_version_id = version_id
    session.add(version)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _delete_stored_file(storage_root, file_object.storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document version could not be saved because of a database constraint.",
        ) from exc
    session.refresh(version)
    return _version_response(version, file_object)
