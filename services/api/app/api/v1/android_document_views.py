from __future__ import annotations

import hashlib
import mimetypes
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.controlled_copies import _as_utc, _audit, _safe_storage_path, _sha256
from app.core.auth import ANDROID_DOCUMENT_VIEW_ROLES, CurrentUser
from app.core.config import Settings, get_settings
from app.core.storage import resolve_storage_root
from app.db.models import (
    AndroidDocumentViewGrant,
    AuthSession,
    Document,
    DocumentVersion,
    FileObject,
    TerminalDevice,
    UserAccount,
)
from app.db.session import get_db_session

router = APIRouter(tags=["android-document-views"])

_ALLOWED_MEDIA = {
    ".pdf": ("PDF", "application/pdf"),
    ".png": ("IMAGE", "image/png"),
    ".jpg": ("IMAGE", "image/jpeg"),
    ".jpeg": ("IMAGE", "image/jpeg"),
    ".webp": ("IMAGE", "image/webp"),
    ".txt": ("TEXT", "text/plain"),
}


class AndroidViewGrantResponse(BaseModel):
    grant_id: str
    document_id: str
    document_version_id: str
    stream_url: str
    expires_at: datetime
    media_kind: str
    mime_type: str
    size_bytes: int
    hash_sha256: str
    max_pdf_pages: int
    max_text_bytes: int
    auto_close_seconds: int


def _published(document: Document, version: DocumentVersion) -> bool:
    return (
        document.status == "PUBLISHED"
        and document.deleted_at is None
        and document.published_version_id == version.version_id
        and version.document_id == document.document_id
        and version.is_published
        and version.version_status == "PUBLISHED"
    )


def _session_and_device(
    session: Session, current_user: CurrentUser
) -> tuple[AuthSession | None, TerminalDevice | None]:
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.session_id == current_user.session_id)
    )
    device = None
    if auth_session is not None and auth_session.device_id:
        device = session.scalar(
            select(TerminalDevice).where(TerminalDevice.device_id == auth_session.device_id)
        )
    return auth_session, device


def _fail(
    session: Session,
    *,
    request: Request,
    current_user: CurrentUser,
    document: Document | None,
    version_id: str | None,
    auth_session: AuthSession | None,
    detail: str,
    status_code: int,
    grant: AndroidDocumentViewGrant | None = None,
    event: str = "android_view_blocked",
) -> None:
    if grant is not None and grant.status == "ISSUED":
        grant.status = "EXPIRED" if status_code == status.HTTP_410_GONE else "FAILED"
        grant.failure_reason = detail[:255]
        session.add(grant)
    _audit(
        session,
        request=request,
        event=event,
        actor_id=current_user.user_id,
        document=document,
        version_id=version_id,
        reason=detail,
        auth_session=auth_session,
    )
    session.commit()
    raise HTTPException(status_code=status_code, detail=detail)


def _file_contract(file_object: FileObject) -> tuple[str, str]:
    extension = Path(file_object.original_filename).suffix.lower()
    contract = _ALLOWED_MEDIA.get(extension)
    if contract is None:
        raise ValueError("This file format is not supported by the Android secure viewer.")
    media_kind, canonical_mime = contract
    supplied = (file_object.mime_type or "").lower().split(";", 1)[0].strip()
    guessed = mimetypes.guess_type(file_object.original_filename)[0]
    compatible = {canonical_mime}
    if extension in {".jpg", ".jpeg"}:
        compatible.add("image/jpg")
    if supplied and supplied not in compatible:
        raise ValueError("The file extension and registered media type do not match.")
    if guessed and media_kind != "TEXT" and guessed not in compatible:
        raise ValueError("The file extension and media type do not match.")
    return media_kind, canonical_mime


def _validate_basic_content(path: Path, media_kind: str, mime_type: str, max_pdf_pages: int) -> None:
    with path.open("rb") as source:
        prefix = source.read(min(path.stat().st_size, 1024 * 1024))
    if media_kind == "PDF":
        if not prefix.startswith(b"%PDF-") or b"%%EOF" not in path.read_bytes()[-4096:]:
            raise ValueError("The PDF file is damaged or incomplete.")
        page_count = len(re.findall(rb"/Type\s*/Page\b", path.read_bytes()))
        if page_count > max_pdf_pages:
            raise OverflowError("The PDF exceeds the secure viewer page limit.")
    elif media_kind == "IMAGE":
        signatures = {
            "image/png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": prefix.startswith(b"\xff\xd8\xff"),
            "image/webp": prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP",
        }
        if not signatures[mime_type]:
            raise ValueError("The image file is damaged or its format does not match.")
    else:
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT files must be valid UTF-8 text.") from exc


def _resolve_verified_file(
    settings: Settings,
    file_object: FileObject | None,
    grant: AndroidDocumentViewGrant | None = None,
) -> tuple[FileObject, Path, int, str, str, str]:
    if file_object is None:
        raise RuntimeError("File metadata was not loaded.")
    media_kind, mime_type = _file_contract(file_object)
    path = _safe_storage_path(resolve_storage_root(settings.storage_root), file_object.storage_key)
    if not path.is_file():
        raise ValueError("The document file is unavailable.")
    size = path.stat().st_size
    if size > settings.android_view_max_bytes:
        raise OverflowError("The document exceeds the Android secure viewer size limit.")
    if media_kind == "TEXT" and size > settings.android_view_max_text_bytes:
        raise OverflowError("The TXT document exceeds the Android secure viewer text limit.")
    digest = _sha256(path)
    if file_object.size_bytes is not None and size != file_object.size_bytes:
        raise ValueError("The document size does not match its registered metadata.")
    if not file_object.hash_sha256 or not secrets.compare_digest(digest, file_object.hash_sha256):
        raise ValueError("The document SHA-256 does not match its registered metadata.")
    if grant is not None and (
        size != grant.expected_size_bytes
        or not secrets.compare_digest(digest, grant.expected_hash_sha256)
        or media_kind != grant.media_kind
        or mime_type != grant.mime_type
    ):
        raise ValueError("The document changed after the Android view grant was issued.")
    _validate_basic_content(path, media_kind, mime_type, settings.android_view_max_pdf_pages)
    return file_object, path, size, digest, media_kind, mime_type


def _record_stream_result(request: Request, grant_id: str, *, event: str, reason: str) -> None:
    with request.app.state.database.session() as session:
        grant = session.scalar(select(AndroidDocumentViewGrant).where(
            AndroidDocumentViewGrant.grant_id == grant_id))
        if grant is None:
            return
        if event == "android_view_failed":
            grant.status = "FAILED"
            grant.failure_reason = reason[:255]
            session.add(grant)
        document = session.scalar(select(Document).where(Document.document_id == grant.document_id))
        auth_session = session.scalar(select(AuthSession).where(
            AuthSession.session_id == grant.session_id))
        _audit(session, request=request, event=event, actor_id=grant.user_id,
               document=document, version_id=grant.document_version_id,
               reason=f"Grant {grant.grant_id}: {reason}", auth_session=auth_session)
        session.commit()


@router.post(
    "/documents/{document_id}/versions/{version_id}/android-view-grants",
    response_model=AndroidViewGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_android_view_grant(
    document_id: str,
    version_id: str,
    request: Request,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AndroidViewGrantResponse:
    document = session.scalar(select(Document).where(Document.document_id == document_id))
    auth_session, device = _session_and_device(session, current_user)
    if current_user.role not in ANDROID_DOCUMENT_VIEW_ROLES:
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session,
              detail="Current user role is not allowed to use the Android secure viewer.",
              status_code=status.HTTP_403_FORBIDDEN)
    if auth_session is None or device is None or device.status != "ACTIVE":
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session,
              detail="An approved active terminal device is required.",
              status_code=status.HTTP_403_FORBIDDEN)
    version = session.scalar(select(DocumentVersion).where(
        DocumentVersion.version_id == version_id, DocumentVersion.document_id == document_id))
    if document is None or version is None or not _published(document, version):
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session,
              detail="Only the currently published document version can be viewed.",
              status_code=status.HTTP_403_FORBIDDEN)
    file_object = session.get(FileObject, version.file_object_id)
    try:
        _, _, size, digest, media_kind, mime_type = _resolve_verified_file(
            settings, file_object)
    except OverflowError as exc:
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, detail=str(exc),
              status_code=status.HTTP_413_CONTENT_TOO_LARGE, event="android_view_failed")
    except (OSError, RuntimeError, ValueError) as exc:
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, detail=str(exc),
              status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, event="android_view_failed")
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=max(5, min(settings.android_view_grant_expires_seconds, 300)))
    grant = AndroidDocumentViewGrant(
        grant_id=f"aview_{uuid4().hex}", token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        document_id=document_id, document_version_id=version_id,
        user_id=current_user.user_id, session_id=current_user.session_id,
        device_id=device.device_id, media_kind=media_kind, mime_type=mime_type,
        expected_hash_sha256=digest, expected_size_bytes=size,
        status="ISSUED", expires_at=expires_at)
    session.add(grant)
    _audit(session, request=request, event="android_view_granted", actor_id=current_user.user_id,
           document=document, version_id=version_id,
           reason=f"Android view grant {grant.grant_id} issued.", auth_session=auth_session)
    session.commit()
    return AndroidViewGrantResponse(
        grant_id=grant.grant_id, document_id=document_id, document_version_id=version_id,
        stream_url=f"/api/v1/android-document-views/{raw_token}/stream", expires_at=expires_at,
        media_kind=media_kind, mime_type=mime_type, size_bytes=size, hash_sha256=digest,
        max_pdf_pages=settings.android_view_max_pdf_pages,
        max_text_bytes=settings.android_view_max_text_bytes,
        auto_close_seconds=settings.android_view_auto_close_seconds)


@router.get("/android-document-views/{token}/stream")
def stream_android_document(
    token: str, request: Request, current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> StreamingResponse:
    grant = session.scalar(select(AndroidDocumentViewGrant).where(
        AndroidDocumentViewGrant.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    auth_session, device = _session_and_device(session, current_user)
    document = session.scalar(select(Document).where(Document.document_id == grant.document_id)) if grant else None
    version_id = grant.document_version_id if grant else None
    if grant is None:
        _fail(session, request=request, current_user=current_user, document=None, version_id=None,
              auth_session=auth_session, detail="Android view grant was not found.",
              status_code=status.HTTP_404_NOT_FOUND)
    if grant.status != "ISSUED" or _as_utc(grant.expires_at) <= datetime.now(timezone.utc):
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, grant=grant,
              detail="Android view grant has expired or was already used.",
              status_code=status.HTTP_410_GONE, event="android_view_expired")
    account = session.scalar(select(UserAccount).where(UserAccount.user_id == grant.user_id))
    if (grant.user_id != current_user.user_id or grant.session_id != current_user.session_id
            or auth_session is None or auth_session.status != "ACTIVE"
            or device is None or device.device_id != grant.device_id or device.status != "ACTIVE"
            or account is None or not account.is_active or account.status != "ACTIVE"
            or current_user.role not in ANDROID_DOCUMENT_VIEW_ROLES):
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, grant=grant,
              detail="User, session, role, or approved terminal is no longer eligible.",
              status_code=status.HTTP_403_FORBIDDEN)
    version = session.scalar(select(DocumentVersion).where(
        DocumentVersion.version_id == grant.document_version_id,
        DocumentVersion.document_id == grant.document_id))
    if document is None or version is None or not _published(document, version):
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, grant=grant,
              detail="The published document selection changed after grant issuance.",
              status_code=status.HTTP_409_CONFLICT)
    file_object = session.get(FileObject, version.file_object_id)
    try:
        _, path, size, digest, _, mime_type = _resolve_verified_file(
            settings, file_object, grant)
    except (OSError, OverflowError, RuntimeError, ValueError) as exc:
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, grant=grant,
              detail=str(exc), status_code=status.HTTP_409_CONFLICT, event="android_view_failed")
    result = session.execute(update(AndroidDocumentViewGrant).where(
        AndroidDocumentViewGrant.id == grant.id, AndroidDocumentViewGrant.status == "ISSUED"
    ).values(status="CONSUMED", consumed_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        session.rollback()
        _fail(session, request=request, current_user=current_user, document=document,
              version_id=version_id, auth_session=auth_session, grant=grant,
              detail="Android view grant was consumed by another request.",
              status_code=status.HTTP_410_GONE)
    _audit(session, request=request, event="android_view_stream_started", actor_id=current_user.user_id,
           document=document, version_id=version_id,
           reason=f"Android view grant {grant.grant_id} stream started.", auth_session=auth_session)
    session.commit()

    def stream() -> Iterator[bytes]:
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(256 * 1024), b""):
                    yield chunk
        except (OSError, GeneratorExit) as exc:
            _record_stream_result(
                request, grant.grant_id, event="android_view_failed",
                reason=f"Android stream interrupted: {type(exc).__name__}.")
            raise
        else:
            _record_stream_result(
                request, grant.grant_id, event="android_view_completed",
                reason="Android stream completed with verified size and SHA-256.")

    return StreamingResponse(stream(), media_type=mime_type, headers={
        "Content-Disposition": "inline",
        "Content-Length": str(size),
        "X-Content-SHA256": digest,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store, private, max-age=0",
        "Pragma": "no-cache",
        "Accept-Ranges": "none",
    })
