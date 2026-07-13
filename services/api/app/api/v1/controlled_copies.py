from __future__ import annotations

import hashlib
import mimetypes
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Iterator
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.auth import CONTROLLED_COPY_DOWNLOAD_ROLES, CurrentUser
from app.core.config import Settings, get_settings
from app.core.storage import resolve_storage_root
from app.db.models import (
    ActivityHistory,
    AuthSession,
    ControlledCopyGrant,
    Document,
    DocumentAccessLog,
    DocumentVersion,
    FileObject,
)
from app.db.session import get_db_session

router = APIRouter(tags=["controlled-copies"])
_MIME_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")


class ControlledCopyGrantResponse(BaseModel):
    grant_id: str
    document_id: str
    document_version_id: str
    download_url: str
    expires_at: datetime
    filename: str
    mime_type: str
    size_bytes: int
    hash_sha256: str
    range_requests_supported: bool = False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mime_type(value: str | None, filename: str) -> str:
    if value and _MIME_TYPE_PATTERN.fullmatch(value.strip()):
        return value.strip()
    guessed = mimetypes.guess_type(filename)[0]
    return guessed or "application/octet-stream"


def _safe_storage_path(storage_root: Path, storage_key: str) -> Path:
    key_path = Path(storage_key)
    if key_path.is_absolute() or ".." in key_path.parts:
        raise ValueError("Storage key is outside the configured storage root.")
    resolved = (storage_root / key_path).resolve()
    if not resolved.is_relative_to(storage_root):
        raise ValueError("Storage key is outside the configured storage root.")
    return resolved


def _client_details(request: Request, auth_session: AuthSession | None) -> tuple[str | None, str | None, str | None]:
    return (
        auth_session.device_id if auth_session else None,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def _audit(
    session: Session,
    *,
    request: Request,
    event: str,
    actor_id: str,
    document: Document | None,
    version_id: str | None,
    reason: str,
    auth_session: AuthSession | None,
) -> None:
    device_id, client_ip, user_agent = _client_details(request, auth_session)
    activity_message = (
        f"{reason} Device: {device_id or 'unidentified'}; "
        f"client IP: {client_ip or 'unavailable'}."
    )
    if document is not None:
        session.add(
            DocumentAccessLog(
                document_id=document.document_id,
                document_version_id=version_id,
                action=event,
                actor_id=actor_id,
                device_id=device_id,
                client_ip=client_ip,
                user_agent=user_agent,
                reason=reason[:255],
            )
        )
    session.add(
        ActivityHistory(
            history_id=f"history_{uuid4().hex}",
            event_type=event,
            actor_id=actor_id,
            target_type="document_version",
            target_id=version_id or (document.document_id if document else None),
            target_title=document.title if document else None,
            message=activity_message,
            change_reason=reason,
        )
    )


def _fail(
    session: Session,
    *,
    request: Request,
    actor_id: str,
    document: Document | None,
    version_id: str | None,
    reason: str,
    auth_session: AuthSession | None,
    status_code: int,
    event: str = "controlled_copy_failed",
) -> None:
    _audit(
        session,
        request=request,
        event=event,
        actor_id=actor_id,
        document=document,
        version_id=version_id,
        reason=reason,
        auth_session=auth_session,
    )
    session.commit()
    raise HTTPException(status_code=status_code, detail=reason)


def _published_selection(document: Document, version: DocumentVersion) -> bool:
    return (
        document.status == "PUBLISHED"
        and document.deleted_at is None
        and document.published_version_id == version.version_id
        and version.document_id == document.document_id
        and version.is_published
        and version.version_status == "PUBLISHED"
    )


@router.post(
    "/documents/{document_id}/versions/{version_id}/controlled-copy",
    response_model=ControlledCopyGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_controlled_copy(
    document_id: str,
    version_id: str,
    request: Request,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ControlledCopyGrantResponse:
    document = session.scalar(select(Document).where(Document.document_id == document_id))
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.session_id == current_user.session_id)
    )
    _audit(
        session,
        request=request,
        event="controlled_copy_requested",
        actor_id=current_user.user_id,
        document=document,
        version_id=version_id,
        reason="Controlled copy requested.",
        auth_session=auth_session,
    )

    if current_user.role not in CONTROLLED_COPY_DOWNLOAD_ROLES:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Current user role is not allowed to download a controlled copy.",
            auth_session=auth_session,
            status_code=status.HTTP_403_FORBIDDEN,
            event="controlled_copy_blocked",
        )
    if document is None or document.deleted_at is not None or document.status == "DELETED":
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Document not found or unavailable.",
            auth_session=auth_session,
            status_code=status.HTTP_404_NOT_FOUND,
            event="controlled_copy_blocked",
        )

    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.version_id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    if version is None:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Document version not found.",
            auth_session=auth_session,
            status_code=status.HTTP_404_NOT_FOUND,
            event="controlled_copy_blocked",
        )
    if not _published_selection(document, version):
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Only the currently published document version can be downloaded.",
            auth_session=auth_session,
            status_code=status.HTTP_403_FORBIDDEN,
            event="controlled_copy_blocked",
        )

    file_object = session.get(FileObject, version.file_object_id)
    if file_object is None:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version file metadata is missing.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        file_path = _safe_storage_path(resolve_storage_root(settings.storage_root), file_object.storage_key)
    except ValueError:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version storage path failed the server safety check.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
            event="controlled_copy_blocked",
        )
    if not file_path.is_file():
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version storage file is missing.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
        )
    try:
        actual_size = file_path.stat().st_size
        actual_hash = _sha256(file_path)
    except OSError:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version storage file could not be read.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
        )
    if file_object.size_bytes is not None and actual_size != file_object.size_bytes:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version file size does not match its registered metadata.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
            event="controlled_copy_blocked",
        )
    if actual_size > settings.controlled_copy_max_bytes:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version file exceeds the controlled copy size limit.",
            auth_session=auth_session,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            event="controlled_copy_blocked",
        )
    if not file_object.hash_sha256 or not secrets.compare_digest(actual_hash, file_object.hash_sha256):
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=version_id,
            reason="Version file hash does not match its registered metadata.",
            auth_session=auth_session,
            status_code=status.HTTP_409_CONFLICT,
            event="controlled_copy_blocked",
        )

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=max(5, min(settings.controlled_copy_ticket_expires_seconds, 300))
    )
    grant = ControlledCopyGrant(
        grant_id=f"copy_{uuid4().hex}",
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        document_id=document_id,
        document_version_id=version_id,
        user_id=current_user.user_id,
        session_id=current_user.session_id,
        device_id=auth_session.device_id if auth_session else None,
        expected_hash_sha256=actual_hash,
        expected_size_bytes=actual_size,
        status="ISSUED",
        expires_at=expires_at,
    )
    session.add(grant)
    _audit(
        session,
        request=request,
        event="controlled_copy_allowed",
        actor_id=current_user.user_id,
        document=document,
        version_id=version_id,
        reason=f"Controlled copy grant {grant.grant_id} issued; expires at {expires_at.isoformat()}.",
        auth_session=auth_session,
    )
    session.commit()
    mime_type = _mime_type(file_object.mime_type, file_object.original_filename)
    return ControlledCopyGrantResponse(
        grant_id=grant.grant_id,
        document_id=document_id,
        document_version_id=version_id,
        download_url=f"/api/v1/controlled-copies/{raw_token}",
        expires_at=expires_at,
        filename=Path(file_object.original_filename).name,
        mime_type=mime_type,
        size_bytes=actual_size,
        hash_sha256=actual_hash,
    )


def _record_stream_result(
    request: Request,
    grant_id: str,
    *,
    event: str,
    reason: str,
) -> None:
    with request.app.state.database.session() as session:
        grant = session.scalar(select(ControlledCopyGrant).where(ControlledCopyGrant.grant_id == grant_id))
        if grant is None:
            return
        document = session.scalar(select(Document).where(Document.document_id == grant.document_id))
        auth_session = session.scalar(select(AuthSession).where(AuthSession.session_id == grant.session_id))
        if event == "controlled_copy_failed":
            grant.status = "FAILED"
            grant.failure_reason = reason[:255]
            session.add(grant)
        _audit(
            session,
            request=request,
            event=event,
            actor_id=grant.user_id,
            document=document,
            version_id=grant.document_version_id,
            reason=f"Grant {grant.grant_id}: {reason}",
            auth_session=auth_session,
        )
        session.commit()


@router.get("/controlled-copies/{token}")
def download_controlled_copy(
    token: str,
    request: Request,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> StreamingResponse:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    grant = session.scalar(select(ControlledCopyGrant).where(ControlledCopyGrant.token_hash == token_hash))
    if grant is None:
        auth_session = session.scalar(
            select(AuthSession).where(AuthSession.session_id == current_user.session_id)
        )
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=None,
            version_id=None,
            reason="Controlled copy grant not found.",
            auth_session=auth_session,
            status_code=status.HTTP_404_NOT_FOUND,
            event="controlled_copy_blocked",
        )
    document = session.scalar(select(Document).where(Document.document_id == grant.document_id))
    auth_session = session.scalar(select(AuthSession).where(AuthSession.session_id == current_user.session_id))
    if grant.status != "ISSUED":
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=grant.document_version_id,
            reason="Controlled copy grant has already been used or is no longer valid.",
            auth_session=auth_session,
            status_code=status.HTTP_410_GONE,
            event="controlled_copy_blocked",
        )
    if _as_utc(grant.expires_at) <= datetime.now(timezone.utc):
        grant.status = "EXPIRED"
        session.add(grant)
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=grant.document_version_id,
            reason="Controlled copy grant has expired.",
            auth_session=auth_session,
            status_code=status.HTTP_410_GONE,
            event="controlled_copy_blocked",
        )
    if grant.user_id != current_user.user_id or grant.session_id != current_user.session_id:
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=grant.document_version_id,
            reason="Controlled copy grant belongs to another user or login session.",
            auth_session=auth_session,
            status_code=status.HTTP_403_FORBIDDEN,
            event="controlled_copy_blocked",
        )

    consumed_at = datetime.now(timezone.utc)
    consume_result = session.execute(
        update(ControlledCopyGrant)
        .where(
            ControlledCopyGrant.id == grant.id,
            ControlledCopyGrant.status == "ISSUED",
        )
        .values(status="CONSUMED", consumed_at=consumed_at)
        .execution_options(synchronize_session=False)
    )
    if consume_result.rowcount != 1:
        session.rollback()
        _fail(
            session,
            request=request,
            actor_id=current_user.user_id,
            document=document,
            version_id=grant.document_version_id,
            reason="Controlled copy grant was consumed by another request.",
            auth_session=auth_session,
            status_code=status.HTTP_410_GONE,
            event="controlled_copy_blocked",
        )
    session.commit()
    if request.headers.get("range"):
        _record_stream_result(
            request,
            grant.grant_id,
            event="controlled_copy_failed",
            reason="Range requests are not supported for one-time controlled copies.",
        )
        raise HTTPException(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            detail="Range requests are not supported for controlled copies.",
        )

    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.version_id == grant.document_version_id,
            DocumentVersion.document_id == grant.document_id,
        )
    )
    if document is None or version is None or not _published_selection(document, version):
        _record_stream_result(
            request,
            grant.grant_id,
            event="controlled_copy_failed",
            reason="Document publication state changed after the grant was issued.",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document is no longer available.")
    file_object = session.get(FileObject, version.file_object_id)
    try:
        file_path = _safe_storage_path(resolve_storage_root(settings.storage_root), file_object.storage_key) if file_object else None
    except ValueError:
        file_path = None
    if file_object is None or file_path is None or not file_path.is_file():
        _record_stream_result(
            request,
            grant.grant_id,
            event="controlled_copy_failed",
            reason="Version storage path or file failed the download safety check.",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file is unavailable.")
    try:
        actual_size = file_path.stat().st_size
        actual_hash = _sha256(file_path)
    except OSError:
        _record_stream_result(
            request,
            grant.grant_id,
            event="controlled_copy_failed",
            reason="Version storage file could not be read during download.",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file is unavailable.")
    if (
        actual_size != grant.expected_size_bytes
        or actual_size > settings.controlled_copy_max_bytes
        or (file_object.size_bytes is not None and actual_size != file_object.size_bytes)
        or not secrets.compare_digest(actual_hash, grant.expected_hash_sha256)
        or not file_object.hash_sha256
        or not secrets.compare_digest(actual_hash, file_object.hash_sha256)
    ):
        _record_stream_result(
            request,
            grant.grant_id,
            event="controlled_copy_failed",
            reason="Version file size or hash changed after the grant was issued.",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version file integrity check failed.")

    def stream() -> Iterator[bytes]:
        try:
            with file_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    yield chunk
        except (OSError, GeneratorExit) as exc:
            _record_stream_result(
                request,
                grant.grant_id,
                event="controlled_copy_failed",
                reason=f"Controlled copy streaming failed: {type(exc).__name__}.",
            )
            raise
        else:
            _record_stream_result(
                request,
                grant.grant_id,
                event="controlled_copy_completed",
                reason="Controlled copy streaming completed with verified size and SHA-256 hash.",
            )

    filename = Path(file_object.original_filename).name.replace("\r", "_").replace("\n", "_")
    extension = Path(filename).suffix.lower()
    safe_extension = extension if 1 < len(extension) <= 11 and extension[1:].isalnum() else ""
    fallback = f"download{safe_extension}"
    disposition = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
    mime_type = _mime_type(file_object.mime_type, filename)
    return StreamingResponse(
        stream(),
        media_type=mime_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(actual_size),
            "X-Content-SHA256": actual_hash,
            "Accept-Ranges": "none",
            "Cache-Control": "no-store, private",
        },
    )
