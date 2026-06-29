from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import Document, DocumentAccessLog, DocumentVersion, UserAccount
from app.db.session import get_db_session

router = APIRouter(
    prefix="/documents",
    tags=["document-access-logs"],
    dependencies=[Depends(get_current_user)],
)

ACTIONS = {"view_started", "view_closed", "download_blocked", "auto_closed"}


class DocumentAccessLogCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_version_id: str | None = Field(default=None, alias="documentVersionId")
    action: str = Field(min_length=1)
    actor_id: str | None = Field(default=None, alias="actorId")
    device_id: str | None = Field(default=None, alias="deviceId")
    client_ip: str | None = Field(default=None, alias="clientIp")
    user_agent: str | None = Field(default=None, alias="userAgent")


class DocumentAccessLogResponse(BaseModel):
    log_id: int
    document_id: str
    document_version_id: str | None
    action: str
    actor_id: str | None
    device_id: str | None
    client_ip: str | None
    user_agent: str | None
    created_at: datetime


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_action(action: str) -> str:
    cleaned = action.strip()
    if cleaned not in ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="action has an unsupported value.",
        )
    return cleaned


def _validate_document(session: Session, document_id: str) -> None:
    exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")


def _validate_version(session: Session, document_id: str, version_id: str | None) -> str | None:
    version_id = _clean_optional(version_id)
    if version_id is None:
        return None

    version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == version_id))
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="documentVersionId must reference an existing version_id.",
        )
    if version.document_id != document_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="documentVersionId must belong to documentId.",
        )
    return version_id


def _validate_actor(session: Session, actor_id: str | None) -> str | None:
    actor_id = _clean_optional(actor_id)
    if actor_id is None:
        return None

    exists = session.scalar(select(UserAccount.id).where(UserAccount.user_id == actor_id))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="actorId must reference an existing user_id.",
        )
    return actor_id


def _response(log: DocumentAccessLog) -> DocumentAccessLogResponse:
    return DocumentAccessLogResponse(
        log_id=log.id,
        document_id=log.document_id,
        document_version_id=log.document_version_id,
        action=log.action,
        actor_id=log.actor_id,
        device_id=log.device_id,
        client_ip=log.client_ip,
        user_agent=log.user_agent,
        created_at=log.created_at,
    )


@router.post(
    "/{document_id}/access-logs",
    response_model=DocumentAccessLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document_access_log(
    document_id: str,
    payload: DocumentAccessLogCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentAccessLogResponse:
    _validate_document(session, document_id)
    version_id = _validate_version(session, document_id, payload.document_version_id)
    actor_id = _validate_actor(session, payload.actor_id)
    action = _validate_action(payload.action)

    log = DocumentAccessLog(
        document_id=document_id,
        document_version_id=version_id,
        action=action,
        actor_id=actor_id,
        device_id=_clean_optional(payload.device_id),
        client_ip=_clean_optional(payload.client_ip)
        or (request.client.host if request.client else None),
        user_agent=_clean_optional(payload.user_agent) or request.headers.get("user-agent"),
    )
    session.add(log)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document access log could not be saved because of a database constraint.",
        ) from exc
    session.refresh(log)
    return _response(log)


@router.get("/{document_id}/access-logs", response_model=list[DocumentAccessLogResponse])
def list_document_access_logs(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DocumentAccessLogResponse]:
    _validate_document(session, document_id)
    logs = session.scalars(
        select(DocumentAccessLog)
        .where(DocumentAccessLog.document_id == document_id)
        .order_by(desc(DocumentAccessLog.created_at), desc(DocumentAccessLog.id))
        .limit(limit)
    ).all()
    return [_response(log) for log in logs]
