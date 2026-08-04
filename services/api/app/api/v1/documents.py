from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import case, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.document_tag_mutations import apply_document_tag_mutation
from app.api.v1.document_approvals import record_publication, validate_publication_approval
from app.api.v1.document_support import (
    CREATABLE_DOCUMENT_STATUSES,
    DOCUMENT_STATUSES,
    VERSION_STATUSES,
    DocumentDeleteRequest,
    DocumentListItem,
    DocumentResponse,
    DocumentStatusUpdateRequest,
    DocumentTagMutationRequest,
    DocumentVersionPublishRequest,
    DocumentVersionResponse,
    DocumentVersionStatusUpdateRequest,
    claim_revision as _claim_revision,
    clean_change_reason as _clean_change_reason,
    clean_idempotency_key as _clean_idempotency_key,
    clean_optional as _clean_optional,
    clean_tags as _clean_tags,
    conflict as _conflict,
    delete_stored_file as _delete_stored_file,
    document_mutation_intent_hash as _document_mutation_intent_hash,
    document_authority_hash as _document_authority_hash,
    document_mutation_event_type as _document_mutation_event_type,
    document_mutation_replay as _document_mutation_replay,
    document_response as _document_response,
    latest_version_for_document as _latest_version_for_document,
    new_public_id as _new_public_id,
    path_sha256 as _path_sha256,
    published_version_for_document as _published_version_for_document,
    record_activity as _record_activity,
    record_document_tag_revision as _record_document_tag_revision,
    replace_document_tags as _replace_document_tags,
    require_live_document as _require_live_document,
    save_file_object as _save_file_object,
    store_document_mutation_receipt as _store_document_mutation_receipt,
    tag_response as _tag_response,
    upload_sha256 as _upload_sha256,
    validate_change_reason as _validate_change_reason,
    validate_document_status_transition as _validate_document_status_transition,
    validate_status as _validate_status,
    validate_user_id as _validate_user_id,
    version_response as _version_response,
)
from app.core.auth import DocumentGovernanceUser, DocumentWriteUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.storage import resolve_storage_root
from app.db.models import Document, DocumentVersion, FileObject
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    mutation_trace,
    record_common_mutation_failure,
    sanitize_audit_text,
)

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)])


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
    file_hash_sha256: Annotated[str | None, Form(alias="fileHashSha256")] = None,
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
    actual_upload_hash = await _upload_sha256(file)
    if file_hash_sha256 and actual_upload_hash.lower() != file_hash_sha256.strip().lower():
        raise _conflict(
            "FILE_HASH_MISMATCH",
            "The uploaded file SHA-256 does not match fileHashSha256.",
            extra={"expectedFileHash": file_hash_sha256, "actualFileHash": actual_upload_hash},
        )
    if idempotency_key is not None:
        existing = session.scalar(
            select(Document).where(
                Document.idempotency_key == idempotency_key,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            existing_version = _latest_version_for_document(session, existing.document_id)
            existing_hash = existing_version[1].hash_sha256 if existing_version else None
            if (
                existing.title != title.strip()
                or existing.document_type != document_type.strip()
                or existing_hash != actual_upload_hash
            ):
                raise _conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was retried with different metadata or file content.",
                    document=existing,
                    extra={"existingFileHash": existing_hash, "requestFileHash": actual_upload_hash},
                )
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
    _record_document_tag_revision(session, document_id, 1, cleaned_tags)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _delete_stored_file(storage_root, file_object.storage_key)
        raise _conflict(
            "DOCUMENT_WRITE_CONFLICT",
            "Document could not be saved because of a database constraint.",
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
                revision=document.revision,
                latest_version_id=document.latest_version_id,
                latest_version_no=version.version_no,
                latest_filename=file_object.original_filename,
                published_version_id=document.published_version_id,
                publication_approval_id=document.publication_approval_id,
                publication_origin=document.publication_origin,
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
                revision=document.revision,
                latest_version_id=document.latest_version_id,
                latest_version_no=None,
                latest_filename=None,
                published_version_id=document.published_version_id,
                publication_approval_id=document.publication_approval_id,
                publication_origin=document.publication_origin,
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
def merge_document_tags(
    request: Request,
    document_id: str,
    payload: DocumentTagMutationRequest | list[str],
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
    base_revision: Annotated[int | None, Query(alias="baseRevision", ge=1)] = None,
    mutation_key: Annotated[str | None, Query(alias="mutationKey")] = None,
) -> DocumentResponse:
    return apply_document_tag_mutation(
        session,
        document_id=document_id,
        payload=payload,
        current_user=current_user,
        trace=mutation_trace(current_user, request),
        legacy_base_revision=base_revision,
        legacy_mutation_key=mutation_key,
    )


@router.patch("/{document_id}/status", response_model=DocumentResponse)
def update_document_status(
    request: Request,
    document_id: str,
    payload: DocumentStatusUpdateRequest,
    current_user: DocumentGovernanceUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    mutation_key = _clean_idempotency_key(payload.mutation_key)
    target_status_for_intent = payload.status.strip().upper()
    raw_reason = _clean_change_reason(payload.change_reason)
    reason = sanitize_audit_text(raw_reason)
    intent_hash = _document_mutation_intent_hash(
        "UPDATE_STATUS",
        document_id,
        {
            "baseRevision": payload.base_revision,
            "changeReason": raw_reason,
            "status": target_status_for_intent,
        },
    )
    trace = mutation_trace(current_user, request)
    try:
        target_status = _validate_status(payload.status, DOCUMENT_STATUSES)
        replay = _document_mutation_replay(
            session, mutation_key, "UPDATE_STATUS", document_id, intent_hash
        )
        if replay is not None:
            return replay
        document = _require_live_document(session, document_id)
        before_hash = _document_authority_hash(session, document)
        before = document.status
        if before != target_status:
            _validate_document_status_transition(before, target_status)
            _claim_revision(
                session,
                document,
                payload.base_revision,
                local_request=payload.model_dump(by_alias=True),
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
                change_reason=reason,
            )
        session.flush()
        response = _document_response(session, document)
        _store_document_mutation_receipt(
            session,
            mutation_key=mutation_key,
            mutation_type="UPDATE_STATUS",
            intent_hash=intent_hash,
            document=document,
            response=response,
            actor_id=current_user.user_id,
            trace=trace,
            reason=reason,
            before_hash=before_hash,
        )
        session.commit()
        return response
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type=_document_mutation_event_type("UPDATE_STATUS"),
            trace=trace,
            target_type="document",
            target_id=document_id,
            target_version_id=None,
            target_revision=payload.base_revision,
            reason=reason,
            error=error,
        )
        raise


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
    current_user: DocumentGovernanceUser,
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
        _claim_revision(
            session,
            document,
            payload.base_revision,
            local_request=payload.model_dump(by_alias=True),
        )
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
    request: Request,
    document_id: str,
    version_id: str,
    payload: DocumentVersionPublishRequest,
    current_user: DocumentGovernanceUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    trace = mutation_trace(current_user, request)
    raw_reason = _clean_change_reason(payload.change_reason)
    reason = sanitize_audit_text(raw_reason)
    mutation_key = _clean_idempotency_key(payload.mutation_key)
    intent_hash = _document_mutation_intent_hash(
        "PUBLISH_VERSION",
        document_id,
        {
            "baseRevision": payload.base_revision,
            "changeReason": raw_reason,
            "expectedPublishedVersionId": payload.expected_published_version_id,
            "approvalId": payload.approval_id,
            "versionId": version_id,
        },
    )
    replay = _document_mutation_replay(
        session, mutation_key, "PUBLISH_VERSION", document_id, intent_hash
    )
    if replay is not None:
        return replay
    document = _require_live_document(session, document_id)
    before_hash = _document_authority_hash(session, document)
    row = session.execute(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_id == version_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    version = row[0]
    file_object = session.get(FileObject, version.file_object_id)
    if file_object is None or not file_object.hash_sha256:
        raise _conflict(
            "FILE_HASH_MISMATCH",
            "The version has no authoritative server file hash and cannot be published.",
            document=document,
            expected_revision=payload.base_revision,
        )
    storage_root = resolve_storage_root(app_settings.storage_root)
    stored_path = (storage_root / Path(file_object.storage_key)).resolve()
    try:
        stored_path.relative_to(storage_root)
    except ValueError:
        stored_path = Path()
    if not stored_path.is_file():
        raise _conflict(
            "FILE_HASH_MISMATCH",
            "The server file for the selected version is missing.",
            document=document,
            expected_revision=payload.base_revision,
            extra={"expectedFileHash": file_object.hash_sha256},
        )
    actual_hash = _path_sha256(stored_path)
    if actual_hash != file_object.hash_sha256.lower():
        raise _conflict(
            "FILE_HASH_MISMATCH",
            "The server file SHA-256 does not match the stored version hash.",
            document=document,
            expected_revision=payload.base_revision,
            extra={"expectedFileHash": file_object.hash_sha256, "actualFileHash": actual_hash},
        )
    approval = validate_publication_approval(
        session,
        settings=app_settings,
        document=document,
        version=version,
        file_hash=actual_hash,
        approval_id=payload.approval_id,
        actor=current_user,
    )
    if (
        document.status == "PUBLISHED"
        and document.published_version_id == version.version_id
        and version.is_published
        and version.version_status == "PUBLISHED"
    ):
        response = _document_response(session, document)
        _store_document_mutation_receipt(
            session,
            mutation_key=mutation_key,
            mutation_type="PUBLISH_VERSION",
            intent_hash=intent_hash,
            document=document,
            response=response,
            actor_id=current_user.user_id,
            trace=trace,
            reason=reason,
            target_version_id=version_id,
            before_hash=before_hash,
            approval_status="APPROVED" if approval is not None else "NOT_REQUIRED",
            approved_by=approval.decided_by if approval is not None else None,
            approval_reference=approval.approval_id if approval is not None else None,
        )
        session.commit()
        return response

    if (
        payload.expected_published_version_id is not None
        and payload.expected_published_version_id != document.published_version_id
    ):
        raise _conflict(
            "PUBLISHED_VERSION_CHANGED",
            "Another administrator replaced the published version after this client loaded it.",
            document=document,
            expected_revision=payload.base_revision,
            extra={"expectedPublishedVersionId": payload.expected_published_version_id},
        )

    _claim_revision(
        session,
        document,
        payload.base_revision,
        local_request={**payload.model_dump(by_alias=True), "versionId": version_id},
    )

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
    record_publication(
        session,
        approval=approval,
        document=document,
        actor=current_user,
        reason=reason,
    )

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
        change_reason=reason,
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
            change_reason=reason,
        )

    session.flush()
    response = _document_response(session, document)
    _store_document_mutation_receipt(
        session,
        mutation_key=mutation_key,
        mutation_type="PUBLISH_VERSION",
        intent_hash=intent_hash,
        document=document,
        response=response,
        actor_id=current_user.user_id,
        trace=trace,
        reason=reason,
        target_version_id=version_id,
        before_hash=before_hash,
        approval_status="APPROVED" if approval is not None else "NOT_REQUIRED",
        approved_by=approval.decided_by if approval is not None else None,
        approval_reference=approval.approval_id if approval is not None else None,
    )
    session.commit()
    return response


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
    idempotency_key: Annotated[str | None, Form(alias="idempotencyKey")] = None,
    base_revision: Annotated[int | None, Form(alias="baseRevision", ge=1)] = None,
    base_version_id: Annotated[str | None, Form(alias="baseVersionId")] = None,
    file_hash_sha256: Annotated[str | None, Form(alias="fileHashSha256")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
    session: Annotated[Session, Depends(get_db_session)] = None,
) -> DocumentVersionResponse:
    change_reason = _validate_change_reason(change_reason)
    created_by = _validate_user_id(session, _clean_optional(created_by), "createdBy")
    idempotency_key = _clean_idempotency_key(idempotency_key)
    document = _require_live_document(session, document_id)
    actual_upload_hash = await _upload_sha256(file)
    if file_hash_sha256 and actual_upload_hash.lower() != file_hash_sha256.strip().lower():
        raise _conflict(
            "FILE_HASH_MISMATCH",
            "The uploaded file SHA-256 does not match fileHashSha256.",
            document=document,
            expected_revision=base_revision,
            extra={"expectedFileHash": file_hash_sha256, "actualFileHash": actual_upload_hash},
        )

    if idempotency_key is not None:
        existing = session.scalar(
            select(DocumentVersion).where(DocumentVersion.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.document_id != document_id:
                raise _conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "idempotencyKey is already used by another document.",
                    document=document,
                    expected_revision=base_revision,
                )
            existing_file = session.get(FileObject, existing.file_object_id)
            if existing_file is None:
                raise _conflict(
                    "IDEMPOTENT_VERSION_BROKEN",
                    "Idempotent document version has no file object.",
                    document=document,
                    expected_revision=base_revision,
                )
            if existing_file.hash_sha256 != actual_upload_hash:
                raise _conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was retried with different file content.",
                    document=document,
                    expected_revision=base_revision,
                    extra={
                        "existingFileHash": existing_file.hash_sha256,
                        "requestFileHash": actual_upload_hash,
                    },
                )
            return _version_response(existing, existing_file)

    if base_version_id is not None and base_version_id != document.latest_version_id:
        raise _conflict(
            "STALE_BASE_VERSION",
            "The server latest version changed after the local version was created.",
            document=document,
            expected_revision=base_revision,
            extra={"expectedLatestVersionId": base_version_id},
        )

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

    try:
        _claim_revision(
            session,
            document,
            base_revision,
            local_request={
                "baseRevision": base_revision,
                "baseVersionId": base_version_id,
                "fileHashSha256": actual_upload_hash,
                "changeReason": change_reason,
            },
            allowed_actions=["KEEP_SERVER", "REGISTER_NEW_VERSION"],
            conflict_kind="CONTENT_VERSION",
        )
    except HTTPException:
        _delete_stored_file(storage_root, file_object.storage_key)
        raise

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
        idempotency_key=idempotency_key,
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
        if idempotency_key is not None:
            existing = session.scalar(
                select(DocumentVersion).where(DocumentVersion.idempotency_key == idempotency_key)
            )
            if existing is not None and existing.document_id == document_id:
                existing_file = session.get(FileObject, existing.file_object_id)
                if existing_file is not None:
                    return _version_response(existing, existing_file)
        raise _conflict(
            "DOCUMENT_WRITE_CONFLICT",
            "Document version could not be saved because of a database constraint.",
            document=session.scalar(
                select(Document).where(Document.document_id == document_id)
            ),
            expected_revision=base_revision,
        ) from exc
    session.refresh(version)
    return _version_response(version, file_object)


@router.delete("/{document_id}", response_model=DocumentResponse)
def delete_document(
    request: Request,
    document_id: str,
    payload: DocumentDeleteRequest,
    current_user: DocumentGovernanceUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentResponse:
    raw_reason = _validate_change_reason(payload.change_reason)
    reason = sanitize_audit_text(raw_reason) or "[REDACTED]"
    mutation_key = _clean_idempotency_key(payload.mutation_key)
    intent_hash = _document_mutation_intent_hash(
        "DELETE_DOCUMENT",
        document_id,
        {"baseRevision": payload.base_revision, "changeReason": raw_reason},
    )
    replay = _document_mutation_replay(
        session, mutation_key, "DELETE_DOCUMENT", document_id, intent_hash
    )
    if replay is not None:
        return replay
    document = _require_live_document(session, document_id)
    before_hash = _document_authority_hash(session, document)
    before = document.status
    _claim_revision(
        session,
        document,
        payload.base_revision,
        local_request=payload.model_dump(by_alias=True),
    )
    now = datetime.now(timezone.utc)
    session.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id,
        DocumentVersion.is_published.is_(True),
    ).update(
        {"is_published": False, "published_at": None, "version_status": "ARCHIVED"},
        synchronize_session=False,
    )
    document.status = "DELETED"
    document.published_version_id = None
    document.publication_approval_id = None
    document.publication_origin = "LEGACY_PUBLICATION"
    document.deleted_at = now
    _record_activity(
        session,
        event_type="document.deleted",
        actor_id=current_user.user_id,
        target_type="document",
        target_id=document.document_id,
        target_title=document.title,
        message="Document was soft-deleted; local resend cannot restore it.",
        before_value=before,
        after_value="DELETED",
        change_reason=reason,
    )
    session.flush()
    response = _document_response(session, document)
    _store_document_mutation_receipt(
        session,
        mutation_key=mutation_key,
        mutation_type="DELETE_DOCUMENT",
        intent_hash=intent_hash,
        document=document,
        response=response,
        actor_id=current_user.user_id,
        trace=mutation_trace(current_user, request),
        reason=reason,
        before_hash=before_hash,
    )
    session.commit()
    return response
