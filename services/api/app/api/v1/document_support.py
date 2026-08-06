from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, object_session

from app.core.config import Settings
from app.core.storage import resolve_storage_root, store_upload_file
from app.db.models import (
    ActivityHistory,
    Document,
    DocumentMutationReceipt,
    DocumentTag,
    DocumentTagRevision,
    DocumentVersion,
    FileObject,
    TagDefinition,
    UserAccount,
)
from app.services.mutation_receipts import (
    MutationTrace,
    canonical_hash,
    check_common_mutation_replay,
    record_common_mutation_result,
)

DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}
CREATABLE_DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "ARCHIVED"}
VERSION_STATUSES = {"WORKING", "IN_REVIEW", "APPROVED", "PUBLISHED", "ARCHIVED"}
DOCUMENT_STATUS_TRANSITIONS = {
    "WORKING": {"IN_REVIEW", "ARCHIVED"},
    "IN_REVIEW": {"WORKING", "ARCHIVED"},
    "PUBLISHED": {"IN_REVIEW", "ARCHIVED"},
    "ARCHIVED": {"WORKING", "IN_REVIEW"},
}


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


class DocumentAuthoritySnapshot(BaseModel):
    revision: int
    status: str
    deleted: bool
    latest_version_id: str | None
    latest_version_hash_sha256: str | None
    published_version_id: str | None
    published_version_hash_sha256: str | None
    tags: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    description: str | None
    document_type: str
    owner_id: str | None
    category_id: str | None
    status: str
    revision: int
    latest_version_id: str | None
    published_version_id: str | None
    latest_version_hash_sha256: str | None = None
    published_version_hash_sha256: str | None = None
    deleted: bool = False
    server_tag_snapshot: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    publication_approval_id: str | None = None
    publication_origin: str = "LEGACY_PUBLICATION"
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    latest_version: DocumentVersionResponse | None = None
    published_version: DocumentVersionResponse | None = None
    authoritative_snapshot: DocumentAuthoritySnapshot | None = None


class DocumentListItem(BaseModel):
    document_id: str
    title: str
    document_type: str
    status: str
    revision: int
    latest_version_id: str | None
    latest_version_no: int | None = None
    latest_filename: str | None = None
    published_version_id: str | None = None
    publication_approval_id: str | None = None
    publication_origin: str = "LEGACY_PUBLICATION"
    published_version_no: int | None = None
    published_filename: str | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime


class DocumentStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1)
    change_reason: str | None = Field(default=None, alias="changeReason")
    base_revision: int | None = Field(default=None, alias="baseRevision", ge=1)
    mutation_key: str | None = Field(default=None, alias="mutationKey")


class DocumentVersionStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1)
    change_reason: str | None = Field(default=None, alias="changeReason")
    base_revision: int = Field(alias="baseRevision", ge=1)


class DocumentVersionPublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_reason: str | None = Field(default=None, alias="changeReason")
    base_revision: int | None = Field(default=None, alias="baseRevision", ge=1)
    expected_published_version_id: str | None = Field(
        default=None, alias="expectedPublishedVersionId"
    )
    mutation_key: str | None = Field(default=None, alias="mutationKey")
    approval_id: str | None = Field(default=None, alias="approvalId")


class DocumentDeleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_reason: str = Field(alias="changeReason", min_length=1)
    base_revision: int = Field(alias="baseRevision", ge=1)
    mutation_key: str | None = Field(default=None, alias="mutationKey")


class DocumentTagMutationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_revision: int = Field(alias="baseRevision", ge=1)
    added_tags: list[str] = Field(default_factory=list, alias="addedTags")
    removed_tags: list[str] = Field(default_factory=list, alias="removedTags")
    intent_hash: str = Field(alias="intentHash", min_length=64, max_length=64)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)


def new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def validate_change_reason(change_reason: str) -> str:
    cleaned = change_reason.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="changeReason is required.",
        )
    return cleaned


def clean_change_reason(change_reason: str | None) -> str | None:
    if change_reason is None:
        return None
    cleaned = change_reason.strip()
    return cleaned or None


def validate_status(value: str, allowed: set[str], field_name: str = "status") -> str:
    cleaned = value.strip().upper()
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return cleaned


def validate_document_status_transition(before: str, after: str) -> None:
    if before == after:
        return
    if after == "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document cannot be set to PUBLISHED without a published version.",
        )
    if after not in DOCUMENT_STATUS_TRANSITIONS.get(before, set()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Document status transition {before} -> {after} is not allowed.",
        )


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def clean_idempotency_key(value: str | None) -> str | None:
    cleaned = clean_optional(value)
    if cleaned is None:
        return None
    if len(cleaned) > 160:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="idempotencyKey is too long.",
        )
    return cleaned


def document_mutation_intent_hash(
    mutation_type: str,
    document_id: str,
    payload: dict[str, object | None],
) -> str:
    canonical = json.dumps(
        {
            "mutationType": mutation_type,
            "documentId": document_id,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def document_tag_intent_hash(
    document_id: str,
    base_revision: int,
    added_tags: list[str],
    removed_tags: list[str],
) -> str:
    added_codes = sorted({_normalize_tag_code(tag) for tag in added_tags})
    removed_codes = sorted({_normalize_tag_code(tag) for tag in removed_tags})
    canonical = "\n".join(
        [
            "document-tags-v1",
            document_id,
            str(base_revision),
            "add:" + ",".join(added_codes),
            "remove:" + ",".join(removed_codes),
        ]
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def document_mutation_replay(
    session: Session,
    mutation_key: str | None,
    mutation_type: str,
    document_id: str,
    intent_hash: str,
) -> DocumentResponse | None:
    if mutation_key is None:
        return None
    event_type = document_mutation_event_type(mutation_type)
    receipt = session.scalar(
        select(DocumentMutationReceipt).where(
            DocumentMutationReceipt.mutation_key == mutation_key
        )
    )
    if receipt is not None and (
        receipt.mutation_type != mutation_type
        or receipt.document_id != document_id
        or receipt.intent_hash_sha256 != intent_hash
    ):
        raise conflict(
            "IDEMPOTENCY_KEY_REUSED",
            "The mutation key was retried with a different document mutation intent.",
            document=session.scalar(
                select(Document).where(Document.document_id == document_id)
            ),
        )
    try:
        common_receipt = check_common_mutation_replay(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type=event_type,
            target_type="document",
            target_id=document_id,
        )
    except HTTPException as error:
        if (
            error.status_code == status.HTTP_409_CONFLICT
            and isinstance(error.detail, dict)
            and error.detail.get("code") == "IDEMPOTENCY_KEY_REUSED"
        ):
            raise conflict(
                "IDEMPOTENCY_KEY_REUSED",
                "The mutation key was retried with a different document mutation intent.",
                document=session.scalar(
                    select(Document).where(Document.document_id == document_id)
                ),
            ) from error
        raise
    if receipt is None:
        if common_receipt is not None:
            raise conflict(
                "COMMON_RECEIPT_LINK_BROKEN",
                "The common receipt has no matching document receipt.",
                document=session.scalar(
                    select(Document).where(Document.document_id == document_id)
                ),
            )
        return None
    return DocumentResponse.model_validate_json(receipt.response_json)


def store_document_mutation_receipt(
    session: Session,
    *,
    mutation_key: str | None,
    mutation_type: str,
    intent_hash: str,
    document: Document,
    response: DocumentResponse,
    actor_id: str,
    trace: MutationTrace | None = None,
    reason: str | None = None,
    target_version_id: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    approval_status: str = "NOT_REQUIRED",
    approved_by: str | None = None,
    approval_reference: str | None = None,
) -> None:
    if mutation_key is None:
        return
    receipt = DocumentMutationReceipt(
            mutation_key=mutation_key,
            mutation_type=mutation_type,
            intent_hash_sha256=intent_hash,
            document_id=document.document_id,
            applied_revision=document.revision,
            response_json=response.model_dump_json(),
            created_by=actor_id,
        )
    session.add(receipt)
    if trace is not None:
        session.flush()
        record_common_mutation_result(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type=document_mutation_event_type(mutation_type),
            trace=trace,
            target_type="document",
            target_id=document.document_id,
            target_version_id=target_version_id,
            target_revision=document.revision,
            reason=reason,
            before_hash=before_hash,
            after_hash=after_hash or document_authority_hash(session, document),
            result="SUCCESS",
            result_code="APPLIED",
            http_status=status.HTTP_200_OK,
            response_detail={
                "code": "APPLIED",
                "targetId": document.document_id,
                "targetVersionId": target_version_id,
                "targetRevision": document.revision,
            },
            domain_receipt_type="document_mutation_receipts",
            domain_receipt_id=str(receipt.id),
            approval_status=approval_status,
            approved_by=approved_by,
            approval_reference=approval_reference,
        )


def document_mutation_event_type(mutation_type: str) -> str:
    return {
        "UPDATE_STATUS": "document.status_changed",
        "PUBLISH_VERSION": "document.version_published",
        "DELETE_DOCUMENT": "document.deleted",
        "MERGE_TAGS": "document.tags_merged",
        "REPLACE_TAGS": "document.tags_changed",
    }.get(mutation_type, f"document.{mutation_type.lower()}")


def document_authority_hash(session: Session, document: Document) -> str:
    latest = latest_version_for_document(session, document.document_id)
    latest_hash = latest[1].hash_sha256 if latest is not None else None
    return canonical_hash(
        {
            "documentId": document.document_id,
            "revision": document.revision,
            "status": document.status,
            "latestVersionId": document.latest_version_id,
            "publishedVersionId": document.published_version_id,
            "latestVersionHash": latest_hash,
            "tags": tag_response(session, document.document_id),
        }
    )


def conflict(
    code: str,
    message: str,
    *,
    document: Document | None = None,
    expected_revision: int | None = None,
    extra: dict[str, object | None] | None = None,
) -> HTTPException:
    conflict_kind, allowed_actions = document_conflict_policy(code)
    snapshot = _conflict_authoritative_snapshot(document, allowed_actions)
    server_value = {
        "revision": snapshot.get("revision"),
        "status": snapshot.get("status"),
        "latestVersionId": snapshot.get("latestVersionId"),
        "latestVersionHashSha256": snapshot.get("latestVersionHashSha256"),
        "publishedVersionId": snapshot.get("publishedVersionId"),
        "publishedVersionHashSha256": snapshot.get("publishedVersionHashSha256"),
        "deleted": snapshot.get("deleted"),
        "tags": snapshot.get("tags"),
    }
    detail: dict[str, object | None] = {
        "schemaVersion": "document-conflict-v1",
        "code": code,
        "conflictKind": conflict_kind,
        "message": message,
        "documentId": document.document_id if document is not None else None,
        "expectedRevision": expected_revision,
        "currentRevision": document.revision if document is not None else None,
        "currentStatus": document.status if document is not None else None,
        "currentLatestVersionId": document.latest_version_id if document is not None else None,
        "currentPublishedVersionId": (
            document.published_version_id if document is not None else None
        ),
        "serverValue": server_value,
        "authoritativeSnapshot": snapshot,
        "localRequest": {"baseRevision": expected_revision},
        "baseSnapshotHash": None,
        "allowedActions": allowed_actions,
        "autoMergeAllowed": False,
        "sourcePreserved": True,
        "retryPolicy": {
            "automatic": False,
            "retryNotBeforeSeconds": 300 if code == "DOCUMENT_READ_BACK_MISMATCH" else 0,
        },
    }
    if extra:
        merged_extra = dict(extra)
        extra_server_value = merged_extra.pop("serverValue", None)
        if isinstance(extra_server_value, dict):
            server_value.update(extra_server_value)
        extra_allowed_actions = merged_extra.get("allowedActions")
        if isinstance(extra_allowed_actions, list):
            snapshot["allowedActions"] = extra_allowed_actions
        detail.update(merged_extra)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def document_conflict_policy(code: str) -> tuple[str, list[str]]:
    if code.startswith("TAG_"):
        return "TAG_SET", ["KEEP_SERVER", "RETRY_WITH_LATEST", "REAPPLY_TAG_DELTA"]
    if code.startswith("APPROVAL_"):
        return "PUBLICATION_APPROVAL", ["KEEP_SERVER"]
    if code in {"STALE_BASE_VERSION", "FILE_HASH_MISMATCH"}:
        return "CONTENT_VERSION", ["KEEP_SERVER", "REGISTER_NEW_VERSION"]
    if code == "PUBLISHED_VERSION_CHANGED":
        return "PUBLISHED_VERSION", ["KEEP_SERVER", "RETRY_WITH_LATEST"]
    if code == "DOCUMENT_DELETED":
        return "SOFT_DELETE", ["KEEP_SERVER"]
    if code in {
        "IDEMPOTENCY_KEY_REUSED",
        "COMMON_RECEIPT_LINK_BROKEN",
        "IDEMPOTENT_VERSION_BROKEN",
        "DOCUMENT_WRITE_CONFLICT",
    }:
        return "MUTATION_IDENTITY", ["KEEP_SERVER"]
    return "DOCUMENT_STATE", ["KEEP_SERVER", "RETRY_WITH_LATEST"]


def _conflict_authoritative_snapshot(
    document: Document | None,
    allowed_actions: list[str],
) -> dict[str, object | None]:
    if document is None:
        return {
            "revision": None,
            "status": None,
            "deleted": False,
            "latestVersionId": None,
            "latestVersionHashSha256": None,
            "publishedVersionId": None,
            "publishedVersionHashSha256": None,
            "tags": [],
            "allowedActions": allowed_actions,
        }
    session = object_session(document)
    latest = latest_version_for_document(session, document.document_id) if session else None
    published = (
        published_version_for_document(session, document.document_id) if session else None
    )
    tags = tag_response(session, document.document_id) if session else []
    return {
        "revision": document.revision,
        "status": document.status,
        "deleted": document.deleted_at is not None or document.status == "DELETED",
        "latestVersionId": document.latest_version_id,
        "latestVersionHashSha256": latest[1].hash_sha256 if latest else None,
        "publishedVersionId": document.published_version_id,
        "publishedVersionHashSha256": published[1].hash_sha256 if published else None,
        "tags": tags,
        "allowedActions": allowed_actions,
    }


def require_live_document(session: Session, document_id: str) -> Document:
    document = session.scalar(select(Document).where(Document.document_id == document_id))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.deleted_at is not None or document.status == "DELETED":
        raise conflict(
            "DOCUMENT_DELETED",
            "The server document was deleted; a local resend cannot restore it implicitly.",
            document=document,
        )
    return document


def claim_revision(
    session: Session,
    document: Document,
    expected_revision: int | None,
    *,
    local_request: dict[str, object | None] | None = None,
    allowed_actions: list[str] | None = None,
    conflict_kind: str | None = None,
) -> int:
    base_revision = document.revision if expected_revision is None else expected_revision
    claimed = session.execute(
        update(Document)
        .where(
            Document.id == document.id,
            Document.deleted_at.is_(None),
            Document.revision == base_revision,
        )
        .values(revision=Document.revision + 1)
    )
    if claimed.rowcount != 1:
        session.rollback()
        current = session.scalar(select(Document).where(Document.id == document.id))
        extra: dict[str, object | None] = {}
        if local_request is not None:
            extra["localRequest"] = local_request
        if allowed_actions is not None:
            extra["allowedActions"] = allowed_actions
        if conflict_kind is not None:
            extra["conflictKind"] = conflict_kind
        raise conflict(
            "STALE_REVISION",
            "The document changed after the client base revision. Administrator resolution is required.",
            document=current,
            expected_revision=base_revision,
            extra=extra or None,
        )
    document.revision = base_revision + 1
    return document.revision


async def upload_sha256(upload: UploadFile) -> str:
    digest = sha256()
    await upload.seek(0)
    while chunk := await upload.read(1024 * 1024):
        digest.update(chunk)
    await upload.seek(0)
    return digest.hexdigest()


def path_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_tag_code(value: str) -> str:
    return "-".join(value.strip().lower().split())


def clean_tags(values: list[str] | None) -> list[str]:
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


def tag_response(session: Session, document_id: str) -> list[str]:
    rows = session.execute(
        select(TagDefinition.name)
        .join(DocumentTag, DocumentTag.tag_id == TagDefinition.tag_id)
        .where(DocumentTag.document_id == document_id, TagDefinition.is_active.is_(True))
        .order_by(TagDefinition.name)
    ).all()
    return [row[0] for row in rows]


def record_document_tag_revision(
    session: Session,
    document_id: str,
    document_revision: int,
    tags: list[str],
    mutation_key: str | None = None,
) -> None:
    normalized = sorted(clean_tags(tags), key=_normalize_tag_code)
    session.add(
        DocumentTagRevision(
            document_id=document_id,
            document_revision=document_revision,
            tags_json=json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
            mutation_key=mutation_key,
        )
    )


def document_tags_at_revision(
    session: Session,
    document_id: str,
    document_revision: int,
) -> list[str] | None:
    snapshot = session.scalar(
        select(DocumentTagRevision)
        .where(
            DocumentTagRevision.document_id == document_id,
            DocumentTagRevision.document_revision <= document_revision,
        )
        .order_by(DocumentTagRevision.document_revision.desc())
        .limit(1)
    )
    if snapshot is None:
        return None
    value = json.loads(snapshot.tags_json)
    return [str(tag) for tag in value] if isinstance(value, list) else None


def document_revisions_since_are_tag_only(
    session: Session,
    document_id: str,
    base_revision: int,
    current_revision: int,
) -> bool:
    if base_revision >= current_revision:
        return True
    tag_revisions = set(
        session.scalars(
            select(DocumentTagRevision.document_revision).where(
                DocumentTagRevision.document_id == document_id,
                DocumentTagRevision.document_revision > base_revision,
                DocumentTagRevision.document_revision <= current_revision,
            )
        ).all()
    )
    return tag_revisions == set(range(base_revision + 1, current_revision + 1))


def _ensure_tag(session: Session, name: str, *, tag_type: str = "custom") -> TagDefinition:
    code = _normalize_tag_code(name)
    existing = session.scalar(
        select(TagDefinition).where(
            TagDefinition.tag_type == tag_type,
            TagDefinition.code == code,
        )
    )
    if existing is not None:
        if existing.name != name:
            existing.name = name
        if not existing.is_active:
            existing.is_active = True
        return existing

    tag = TagDefinition(
        tag_id=new_public_id("tag"),
        tag_type=tag_type,
        code=code,
        name=name,
    )
    session.add(tag)
    session.flush()
    return tag


def replace_document_tags(session: Session, document_id: str, tags: list[str]) -> None:
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    for name in tags:
        tag = _ensure_tag(session, name)
        session.add(DocumentTag(document_id=document_id, tag_id=tag.tag_id))


def validate_user_id(session: Session, user_id: str | None, field_name: str) -> str | None:
    if user_id is None:
        return None
    exists = session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must reference an existing user_id.",
        )
    return user_id


def record_activity(
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
            history_id=new_public_id("hist"),
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


def delete_stored_file(storage_root: Path, storage_key: str) -> None:
    target_path = (storage_root / Path(storage_key)).resolve()
    try:
        target_path.relative_to(storage_root)
    except ValueError:
        return
    if target_path.exists() and target_path.is_file():
        target_path.unlink()


def file_response(file_object: FileObject) -> FileObjectResponse:
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


def version_response(
    version: DocumentVersion,
    file_object: FileObject,
) -> DocumentVersionResponse:
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
        file=file_response(file_object),
    )


def latest_version_for_document(
    session: Session,
    document_id: str,
) -> tuple[DocumentVersion, FileObject] | None:
    row = session.execute(
        select(DocumentVersion, FileObject)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_latest.is_(True),
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def published_version_for_document(
    session: Session,
    document_id: str,
) -> tuple[DocumentVersion, FileObject] | None:
    row = session.execute(
        select(DocumentVersion, FileObject)
        .join(FileObject, DocumentVersion.file_object_id == FileObject.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_id
            == select(Document.published_version_id)
            .where(Document.document_id == document_id)
            .scalar_subquery(),
            DocumentVersion.is_published.is_(True),
            DocumentVersion.version_status == "PUBLISHED",
        )
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def document_response(session: Session, document: Document) -> DocumentResponse:
    latest = latest_version_for_document(session, document.document_id)
    latest_response = version_response(*latest) if latest is not None else None
    published = published_version_for_document(session, document.document_id)
    published_response = version_response(*published) if published is not None else None
    tags = tag_response(session, document.document_id)
    return DocumentResponse(
        document_id=document.document_id,
        title=document.title,
        description=document.description,
        document_type=document.document_type,
        owner_id=document.owner_id,
        category_id=document.category_id,
        status=document.status,
        revision=document.revision,
        latest_version_id=document.latest_version_id,
        published_version_id=document.published_version_id,
        latest_version_hash_sha256=latest[1].hash_sha256 if latest else None,
        published_version_hash_sha256=published[1].hash_sha256 if published else None,
        deleted=document.deleted_at is not None or document.status == "DELETED",
        server_tag_snapshot=tags,
        allowed_actions=[],
        publication_approval_id=document.publication_approval_id,
        publication_origin=document.publication_origin,
        created_at=document.created_at,
        updated_at=document.updated_at,
        tags=tags,
        latest_version=latest_response,
        published_version=published_response,
        authoritative_snapshot=DocumentAuthoritySnapshot(
            revision=document.revision,
            status=document.status,
            deleted=document.deleted_at is not None or document.status == "DELETED",
            latest_version_id=document.latest_version_id,
            latest_version_hash_sha256=latest[1].hash_sha256 if latest else None,
            published_version_id=document.published_version_id,
            published_version_hash_sha256=published[1].hash_sha256 if published else None,
            tags=tags,
            allowed_actions=[],
        ),
    )


async def save_file_object(
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
