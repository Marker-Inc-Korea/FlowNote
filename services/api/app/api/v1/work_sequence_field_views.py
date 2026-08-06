from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import ANDROID_DOCUMENT_VIEW_ROLES, CurrentUser
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Document,
    DocumentVersion,
    NotificationChannel,
    NotificationChannelMember,
    TerminalDevice,
    WorkSequenceBoard,
    WorkSequenceItem,
)
from app.db.session import get_db_session


router = APIRouter(
    prefix="/work-sequence-field-boards",
    tags=["work-sequence-field-boards"],
)

BOARD_STATUSES = {"ACTIVE", "ARCHIVED"}
MANAGEMENT_READ_ROLES = {
    "admin",
    "manager",
    "system-admin",
    "document-admin",
    "assistant-manager",
    "department-manager",
    "line-foreman",
    "team-lead",
}


class PublishedDocumentSummary(BaseModel):
    document_id: str
    version_id: str
    title: str
    document_revision: int


class FieldWorkSequenceItemResponse(BaseModel):
    item_id: str
    board_id: str
    title: str
    description: str | None
    work_order_no: str | None
    status: str
    hold_reason: str | None
    sort_order: int
    assigned_to: str | None
    source_type: str = "WORK_SEQUENCE_ITEM"
    source_id: str
    source_revision: int
    document_access: str
    published_document: PublishedDocumentSummary | None
    allowed_channel_ids: list[str] = Field(default_factory=list)
    updated_at: datetime


class FieldWorkSequenceBoardResponse(BaseModel):
    board_id: str
    title: str
    description: str | None
    line_code: str | None
    board_date: date | None
    status: str
    board_revision: int
    updated_at: datetime
    customer_scope: str
    site_scope: str
    user_id: str
    device_id: str
    items: list[FieldWorkSequenceItemResponse] = Field(default_factory=list)


class FieldWorkSequenceBoardListItem(BaseModel):
    board_id: str
    title: str
    line_code: str | None
    board_date: date | None
    status: str
    board_revision: int
    item_count: int
    updated_at: datetime


class FieldWorkSequenceBoardPage(BaseModel):
    items: list[FieldWorkSequenceBoardListItem]
    offset: int
    limit: int
    total: int
    has_more: bool
    refreshed_at: datetime
    customer_scope: str
    site_scope: str
    user_id: str
    device_id: str


def _approved_field_user(session: Session, current_user: CurrentUser) -> TerminalDevice:
    if current_user.role not in ANDROID_DOCUMENT_VIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERMISSION_DENIED",
                "message": "Android 작업순서 열람 역할이 필요합니다. 현장 관리자에게 권한을 요청하세요.",
            },
        )
    if current_user.device_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DEVICE_NOT_APPROVED",
                "message": "승인된 현장 단말 세션에서만 작업순서를 열람할 수 있습니다.",
            },
        )
    device = session.scalar(
        select(TerminalDevice).where(
            TerminalDevice.device_id == current_user.device_id,
            TerminalDevice.status == "ACTIVE",
        )
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DEVICE_NOT_APPROVED",
                "message": "비활성화되었거나 승인되지 않은 현장 단말입니다.",
            },
        )
    return device


def _channel_item_ids(current_user: CurrentUser):
    message_item_ids = (
        select(ChannelMessage.source_id)
        .join(NotificationChannel, NotificationChannel.channel_id == ChannelMessage.channel_id)
        .join(
            NotificationChannelMember,
            NotificationChannelMember.channel_id == ChannelMessage.channel_id,
        )
        .where(
            ChannelMessage.source_type == "WORK_SEQUENCE_ITEM",
            NotificationChannel.status == "ACTIVE",
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    )
    linked_item_ids = (
        select(NotificationChannel.source_id)
        .join(
            NotificationChannelMember,
            NotificationChannelMember.channel_id == NotificationChannel.channel_id,
        )
        .where(
            NotificationChannel.source_type == "WORK_SEQUENCE_ITEM",
            NotificationChannel.status == "ACTIVE",
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    )
    return message_item_ids.union(linked_item_ids)


def _item_access_condition(current_user: CurrentUser):
    if current_user.role in MANAGEMENT_READ_ROLES:
        return True
    return or_(
        WorkSequenceItem.assigned_to == current_user.user_id,
        WorkSequenceItem.item_id.in_(_channel_item_ids(current_user)),
    )


def _allowed_channel_ids(
    session: Session,
    current_user: CurrentUser,
    item_id: str,
) -> list[str]:
    direct = select(NotificationChannel.channel_id).join(
        NotificationChannelMember,
        NotificationChannelMember.channel_id == NotificationChannel.channel_id,
    ).where(
        NotificationChannel.source_type == "WORK_SEQUENCE_ITEM",
        NotificationChannel.source_id == item_id,
        NotificationChannel.status == "ACTIVE",
        NotificationChannelMember.user_id == current_user.user_id,
        NotificationChannelMember.status == "ACTIVE",
    )
    messaged = select(ChannelMessage.channel_id).join(
        NotificationChannel,
        NotificationChannel.channel_id == ChannelMessage.channel_id,
    ).join(
        NotificationChannelMember,
        NotificationChannelMember.channel_id == ChannelMessage.channel_id,
    ).where(
        ChannelMessage.source_type == "WORK_SEQUENCE_ITEM",
        ChannelMessage.source_id == item_id,
        NotificationChannel.status == "ACTIVE",
        NotificationChannelMember.user_id == current_user.user_id,
        NotificationChannelMember.status == "ACTIVE",
    )
    return sorted(set(session.scalars(direct.union(messaged)).all()))


def _published_document(
    session: Session,
    document_id: str | None,
) -> tuple[str, PublishedDocumentSummary | None]:
    if document_id is None:
        return "NONE", None
    document = session.scalar(
        select(Document).where(
            Document.document_id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    if (
        document is None
        or document.status != "PUBLISHED"
        or document.published_version_id is None
    ):
        return "NOT_PUBLISHED", None
    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.version_id == document.published_version_id,
            DocumentVersion.document_id == document.document_id,
            DocumentVersion.is_published.is_(True),
            DocumentVersion.version_status == "PUBLISHED",
        )
    )
    if version is None:
        return "NOT_PUBLISHED", None
    return "AVAILABLE", PublishedDocumentSummary(
        document_id=document.document_id,
        version_id=version.version_id,
        title=document.title,
        document_revision=document.revision,
    )


def _item_response(
    session: Session,
    current_user: CurrentUser,
    board: WorkSequenceBoard,
    item: WorkSequenceItem,
) -> FieldWorkSequenceItemResponse:
    document_access, document = _published_document(session, item.document_id)
    return FieldWorkSequenceItemResponse(
        item_id=item.item_id,
        board_id=item.board_id,
        title=item.title,
        description=item.description,
        work_order_no=item.work_order_no,
        status=item.status,
        hold_reason=item.hold_reason,
        sort_order=item.sort_order,
        assigned_to=item.assigned_to,
        source_id=item.item_id,
        source_revision=board.board_revision,
        document_access=document_access,
        published_document=document,
        allowed_channel_ids=_allowed_channel_ids(session, current_user, item.item_id),
        updated_at=item.updated_at,
    )


def _visible_items(
    session: Session,
    current_user: CurrentUser,
    board_id: str,
) -> list[WorkSequenceItem]:
    statement = select(WorkSequenceItem).where(WorkSequenceItem.board_id == board_id)
    condition = _item_access_condition(current_user)
    if condition is not True:
        statement = statement.where(condition)
    return list(session.scalars(statement.order_by(WorkSequenceItem.sort_order, WorkSequenceItem.id)).all())


def _audit_read(
    session: Session,
    request: Request,
    current_user: CurrentUser,
    *,
    target_type: str,
    target_id: str | None,
    revision: int | None,
    item_ids: list[str],
) -> None:
    session.add(
        ActivityHistory(
            history_id=f"hist_{uuid4().hex}",
            event_type="work_sequence.android_read",
            actor_id=current_user.user_id,
            target_type=target_type,
            target_id=target_id,
            target_title="Android 작업순서 열람",
            message="승인된 Android 단말에서 허용된 작업순서를 열람했습니다.",
            after_value=json.dumps(
                {
                    "board_revision": revision,
                    "device_id": current_user.device_id,
                    "item_ids": item_ids,
                    "request_path": request.url.path,
                    "customer_scope": current_user.customer_scope,
                    "site_scope": current_user.site_scope,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )
    session.commit()


@router.get("", response_model=FieldWorkSequenceBoardPage)
def list_field_boards(
    request: Request,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    board_date: Annotated[date | None, Query(alias="boardDate")] = None,
    line_code: Annotated[str | None, Query(alias="lineCode")] = None,
    board_status: Annotated[str, Query(alias="status")] = "ACTIVE",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> FieldWorkSequenceBoardPage:
    device = _approved_field_user(session, current_user)
    normalized_status = board_status.strip().upper()
    if normalized_status not in BOARD_STATUSES:
        raise HTTPException(status_code=422, detail="status has an unsupported value.")
    effective_date = board_date or date.today()
    statement = (
        select(WorkSequenceBoard)
        .join(WorkSequenceItem, WorkSequenceItem.board_id == WorkSequenceBoard.board_id)
        .where(
            WorkSequenceBoard.board_date == effective_date,
            WorkSequenceBoard.status == normalized_status,
        )
    )
    count_statement = (
        select(func.count(distinct(WorkSequenceBoard.id)))
        .join(WorkSequenceItem, WorkSequenceItem.board_id == WorkSequenceBoard.board_id)
        .where(
            WorkSequenceBoard.board_date == effective_date,
            WorkSequenceBoard.status == normalized_status,
        )
    )
    condition = _item_access_condition(current_user)
    if condition is not True:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    cleaned_line = line_code.strip() if line_code else None
    if cleaned_line:
        statement = statement.where(WorkSequenceBoard.line_code == cleaned_line)
        count_statement = count_statement.where(WorkSequenceBoard.line_code == cleaned_line)
    boards = list(session.scalars(
        statement.distinct().order_by(WorkSequenceBoard.updated_at.desc(), WorkSequenceBoard.id.desc())
        .offset(offset).limit(limit)
    ).all())
    total = int(session.scalar(count_statement) or 0)
    items = []
    audited_item_ids: list[str] = []
    for board in boards:
        visible = _visible_items(session, current_user, board.board_id)
        audited_item_ids.extend(item.item_id for item in visible)
        items.append(FieldWorkSequenceBoardListItem(
            board_id=board.board_id,
            title=board.title,
            line_code=board.line_code,
            board_date=board.board_date,
            status=board.status,
            board_revision=board.board_revision,
            item_count=len(visible),
            updated_at=board.updated_at,
        ))
    _audit_read(
        session,
        request,
        current_user,
        target_type="work_sequence_board_page",
        target_id=None,
        revision=None,
        item_ids=audited_item_ids,
    )
    return FieldWorkSequenceBoardPage(
        items=items,
        offset=offset,
        limit=limit,
        total=total,
        has_more=offset + len(items) < total,
        refreshed_at=datetime.now(timezone.utc),
        customer_scope=current_user.customer_scope,
        site_scope=current_user.site_scope,
        user_id=current_user.user_id,
        device_id=device.device_id,
    )


def _field_board_detail(
    request: Request,
    current_user: CurrentUser,
    session: Session,
    board: WorkSequenceBoard,
    expected_revision: int | None,
    required_item_id: str | None = None,
) -> FieldWorkSequenceBoardResponse:
    device = _approved_field_user(session, current_user)
    if expected_revision is not None and board.board_revision != expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORK_SEQUENCE_REVISION_CHANGED",
                "message": "작업순서가 바뀌었습니다. 현재 항목을 다시 확인하세요.",
                "currentRevision": board.board_revision,
            },
        )
    visible = _visible_items(session, current_user, board.board_id)
    if required_item_id is not None:
        visible = [item for item in visible if item.item_id == required_item_id]
    if not visible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WORK_SEQUENCE_NOT_VISIBLE",
                "message": "현재 역할·채널 범위에서 작업순서를 찾을 수 없습니다.",
            },
        )
    response = FieldWorkSequenceBoardResponse(
        board_id=board.board_id,
        title=board.title,
        description=board.description,
        line_code=board.line_code,
        board_date=board.board_date,
        status=board.status,
        board_revision=board.board_revision,
        updated_at=board.updated_at,
        customer_scope=current_user.customer_scope,
        site_scope=current_user.site_scope,
        user_id=current_user.user_id,
        device_id=device.device_id,
        items=[_item_response(session, current_user, board, item) for item in visible],
    )
    _audit_read(
        session,
        request,
        current_user,
        target_type="work_sequence_board",
        target_id=board.board_id,
        revision=board.board_revision,
        item_ids=[item.item_id for item in visible],
    )
    return response


@router.get("/by-item/{item_id}", response_model=FieldWorkSequenceBoardResponse)
def get_field_board_by_item(
    item_id: str,
    request: Request,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    expected_revision: Annotated[int | None, Query(alias="expectedRevision", ge=1)] = None,
) -> FieldWorkSequenceBoardResponse:
    item = session.scalar(select(WorkSequenceItem).where(WorkSequenceItem.item_id == item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Work sequence item not found.")
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == item.board_id))
    if board is None:
        raise HTTPException(status_code=404, detail="Work sequence board not found.")
    return _field_board_detail(
        request,
        current_user,
        session,
        board,
        expected_revision,
        required_item_id=item_id,
    )


@router.get("/{board_id}", response_model=FieldWorkSequenceBoardResponse)
def get_field_board(
    board_id: str,
    request: Request,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    expected_revision: Annotated[int | None, Query(alias="expectedRevision", ge=1)] = None,
) -> FieldWorkSequenceBoardResponse:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        raise HTTPException(status_code=404, detail="Work sequence board not found.")
    return _field_board_detail(request, current_user, session, board, expected_revision)
