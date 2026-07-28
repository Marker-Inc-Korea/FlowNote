from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DOCUMENT_WRITE_ROLES, get_current_user
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Handover,
    HandoverReceipt,
    NotificationChannel,
    NotificationChannelMember,
    UserAccount,
)
from app.db.session import get_db_session

router = APIRouter(tags=["notification-channels"], dependencies=[Depends(get_current_user)])

CHANNEL_TYPES = {"LINE", "EQUIPMENT", "PROCESS", "WORK_GROUP", "HANDOVER", "WORK_RECORD", "CUSTOM"}
CHANNEL_STATUSES = {"ACTIVE", "ARCHIVED"}
MEMBER_ROLES = {"OWNER", "MANAGER", "MEMBER"}
MEMBER_STATUSES = {"ACTIVE", "REMOVED"}
MESSAGE_TYPES = {"NOTICE", "DOCUMENT_EVENT", "FIELD_COMMENT_EVENT", "WORK_SEQUENCE_EVENT", "HANDOVER", "SYSTEM"}
MESSAGE_SOURCE_TYPES = {
    "DOCUMENT",
    "FIELD_COMMENT",
    "WORK_SEQUENCE_ITEM",
    "WORK_SEQUENCE_HISTORY",
    "WORK_RECORD",
    "REPORT",
    "HANDOVER",
    "SYSTEM",
}
HANDOVER_STATUSES = {"DRAFT", "SENT", "ACKNOWLEDGED", "FOLLOW_UP_REQUIRED", "ARCHIVED"}
HANDOVER_SOURCE_TYPES = {
    "DOCUMENT",
    "FIELD_COMMENT",
    "WORK_SEQUENCE_ITEM",
    "WORK_SEQUENCE_HISTORY",
    "WORK_RECORD",
    "REPORT",
    "CHANNEL_MESSAGE",
}
RECEIPT_STATUSES = {"UNREAD", "READ", "ACKNOWLEDGED", "FOLLOW_UP_REQUIRED"}
CHANNEL_ADMIN_ROLES = {"admin", "system-admin"}


class NotificationChannelCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1)
    description: str | None = None
    channel_type: str = Field(alias="channelType", min_length=1)
    source_type: str | None = Field(default=None, alias="sourceType")
    source_id: str | None = Field(default=None, alias="sourceId")
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")


class NotificationChannelResponse(BaseModel):
    channel_id: str
    name: str
    description: str | None
    channel_type: str
    source_type: str | None
    source_id: str | None
    source_version_id: str | None
    status: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ChannelMemberUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId", min_length=1)
    member_role: str = Field(default="MEMBER", alias="memberRole")


class ChannelMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    member_role: str | None = Field(default=None, alias="memberRole")
    status: str | None = None


class ChannelMemberResponse(BaseModel):
    member_id: str
    channel_id: str
    user_id: str
    member_role: str
    status: str
    last_read_message_id: str | None
    last_read_at: datetime | None
    added_by: str | None
    created_at: datetime
    updated_at: datetime


class ChannelMessageCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_type: str = Field(alias="messageType", min_length=1)
    source_type: str = Field(alias="sourceType", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1)
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    title: str = Field(min_length=1)
    body: str | None = None


class ChannelMessageResponse(BaseModel):
    message_id: str
    channel_id: str
    message_type: str
    source_type: str
    source_id: str
    source_version_id: str | None
    title: str
    body: str | None
    created_by: str | None
    created_at: datetime


class UserNotificationResponse(ChannelMessageResponse):
    cursor: int
    channel_name: str
    read: bool
    read_at: datetime | None


class HandoverCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel_id: str = Field(alias="channelId", min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source_type: str | None = Field(default=None, alias="sourceType")
    source_id: str | None = Field(default=None, alias="sourceId")
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    recipient_ids: list[str] = Field(alias="recipientIds", min_length=1)


class HandoverReceiptUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipt_status: str = Field(alias="receiptStatus", min_length=1)
    note: str | None = None
    delivery_run_id: str | None = Field(default=None, alias="deliveryRunId", max_length=120)
    displayed_at: datetime | None = Field(default=None, alias="displayedAt")


class NotificationReadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    delivery_run_id: str | None = Field(default=None, alias="deliveryRunId", max_length=120)
    displayed_at: datetime | None = Field(default=None, alias="displayedAt")


class HandoverReceiptResponse(BaseModel):
    receipt_id: str
    handover_id: str
    recipient_id: str
    receipt_status: str
    note: str | None
    read_at: datetime | None
    acknowledged_at: datetime | None
    follow_up_required_at: datetime | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class HandoverResponse(BaseModel):
    handover_id: str
    channel_id: str
    title: str
    body: str
    source_type: str | None
    source_id: str | None
    source_version_id: str | None
    status: str
    created_by: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    receipts: list[HandoverReceiptResponse]


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
    cleaned = value.strip().upper()
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return cleaned


def _require_channel_write_role(current_user: CurrentUser) -> None:
    if current_user.role not in DOCUMENT_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user role is not allowed to perform this action.",
        )


def _validate_user_id(session: Session, user_id: str, field_name: str = "userId") -> str:
    cleaned = user_id.strip()
    exists = session.scalar(select(UserAccount.id).where(UserAccount.user_id == cleaned))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must reference an existing user_id.",
        )
    return cleaned


def _get_channel(session: Session, channel_id: str) -> NotificationChannel:
    channel = session.scalar(select(NotificationChannel).where(NotificationChannel.channel_id == channel_id))
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")
    return channel


def _get_active_member(
    session: Session,
    channel_id: str,
    user_id: str,
) -> NotificationChannelMember | None:
    return session.scalar(
        select(NotificationChannelMember).where(
            NotificationChannelMember.channel_id == channel_id,
            NotificationChannelMember.user_id == user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    )


def _can_manage_channel(
    session: Session,
    channel_id: str,
    user_id: str,
    user_role: str,
) -> bool:
    if user_role in CHANNEL_ADMIN_ROLES:
        return True
    member = _get_active_member(session, channel_id, user_id)
    return member is not None and member.member_role in {"OWNER", "MANAGER"}


def _ensure_channel_member(session: Session, channel_id: str, current_user: CurrentUser) -> NotificationChannelMember:
    member = _get_active_member(session, channel_id, current_user.user_id)
    if member is None and current_user.role not in CHANNEL_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user is not a member of this channel.",
        )
    if member is None:
        return NotificationChannelMember(
            member_id="",
            channel_id=channel_id,
            user_id=current_user.user_id,
            member_role="OWNER",
            status="ACTIVE",
        )
    return member


def _ensure_channel_manager(session: Session, channel_id: str, current_user: CurrentUser) -> None:
    if not _can_manage_channel(session, channel_id, current_user.user_id, current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user cannot manage this channel.",
        )


def _channel_response(channel: NotificationChannel) -> NotificationChannelResponse:
    return NotificationChannelResponse(
        channel_id=channel.channel_id,
        name=channel.name,
        description=channel.description,
        channel_type=channel.channel_type,
        source_type=channel.source_type,
        source_id=channel.source_id,
        source_version_id=channel.source_version_id,
        status=channel.status,
        created_by=channel.created_by,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _member_response(member: NotificationChannelMember) -> ChannelMemberResponse:
    return ChannelMemberResponse(
        member_id=member.member_id,
        channel_id=member.channel_id,
        user_id=member.user_id,
        member_role=member.member_role,
        status=member.status,
        last_read_message_id=member.last_read_message_id,
        last_read_at=member.last_read_at,
        added_by=member.added_by,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def _message_response(message: ChannelMessage) -> ChannelMessageResponse:
    return ChannelMessageResponse(
        message_id=message.message_id,
        channel_id=message.channel_id,
        message_type=message.message_type,
        source_type=message.source_type,
        source_id=message.source_id,
        source_version_id=message.source_version_id,
        title=message.title,
        body=message.body,
        created_by=message.created_by,
        created_at=message.created_at,
    )


def _receipt_response(receipt: HandoverReceipt) -> HandoverReceiptResponse:
    return HandoverReceiptResponse(
        receipt_id=receipt.receipt_id,
        handover_id=receipt.handover_id,
        recipient_id=receipt.recipient_id,
        receipt_status=receipt.receipt_status,
        note=receipt.note,
        read_at=receipt.read_at,
        acknowledged_at=receipt.acknowledged_at,
        follow_up_required_at=receipt.follow_up_required_at,
        updated_by=receipt.updated_by,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
    )


def _handover_response(session: Session, handover: Handover) -> HandoverResponse:
    receipts = session.scalars(
        select(HandoverReceipt)
        .where(HandoverReceipt.handover_id == handover.handover_id)
        .order_by(HandoverReceipt.id)
    ).all()
    return HandoverResponse(
        handover_id=handover.handover_id,
        channel_id=handover.channel_id,
        title=handover.title,
        body=handover.body,
        source_type=handover.source_type,
        source_id=handover.source_id,
        source_version_id=handover.source_version_id,
        status=handover.status,
        created_by=handover.created_by,
        sent_at=handover.sent_at,
        created_at=handover.created_at,
        updated_at=handover.updated_at,
        receipts=[_receipt_response(receipt) for receipt in receipts],
    )


def _sync_handover_status(session: Session, handover: Handover) -> None:
    statuses = session.scalars(
        select(HandoverReceipt.receipt_status).where(HandoverReceipt.handover_id == handover.handover_id)
    ).all()
    if any(item == "FOLLOW_UP_REQUIRED" for item in statuses):
        handover.status = "FOLLOW_UP_REQUIRED"
    elif statuses and all(item == "ACKNOWLEDGED" for item in statuses):
        handover.status = "ACKNOWLEDGED"
    elif handover.status == "DRAFT":
        handover.status = "SENT"


@router.post(
    "/notification-channels",
    response_model=NotificationChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_channel(
    request: NotificationChannelCreateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> NotificationChannelResponse:
    _require_channel_write_role(current_user)
    channel_type = _normalize_choice(request.channel_type, CHANNEL_TYPES, "channelType")
    source_type = None
    if request.source_type is not None:
        source_type = _normalize_choice(request.source_type, MESSAGE_SOURCE_TYPES, "sourceType")
    channel = NotificationChannel(
        channel_id=_new_public_id("channel"),
        name=request.name.strip(),
        description=_clean_optional(request.description),
        channel_type=channel_type,
        source_type=source_type,
        source_id=_clean_optional(request.source_id),
        source_version_id=_clean_optional(request.source_version_id),
        status="ACTIVE",
        created_by=current_user.user_id,
    )
    session.add(channel)
    session.flush()
    session.add(
        NotificationChannelMember(
            member_id=_new_public_id("chmember"),
            channel_id=channel.channel_id,
            user_id=current_user.user_id,
            member_role="OWNER",
            status="ACTIVE",
            added_by=current_user.user_id,
        )
    )
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="notification_channel.created",
            actor_id=current_user.user_id,
            target_type="notification_channel",
            target_id=channel.channel_id,
            target_title=channel.name,
            message=f"Notification channel created: {channel.name}.",
        )
    )
    session.commit()
    session.refresh(channel)
    return _channel_response(channel)


@router.get("/notification-channels", response_model=list[NotificationChannelResponse])
def list_channels(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    channel_type: Annotated[str | None, Query(alias="channelType")] = None,
    channel_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[NotificationChannelResponse]:
    statement = select(NotificationChannel).order_by(desc(NotificationChannel.updated_at), desc(NotificationChannel.id))
    if current_user.role not in CHANNEL_ADMIN_ROLES:
        statement = statement.join(
            NotificationChannelMember,
            NotificationChannelMember.channel_id == NotificationChannel.channel_id,
        ).where(
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    if channel_type is not None:
        statement = statement.where(
            NotificationChannel.channel_type == _normalize_choice(channel_type, CHANNEL_TYPES, "channelType")
        )
    if channel_status is not None:
        statement = statement.where(
            NotificationChannel.status == _normalize_choice(channel_status, CHANNEL_STATUSES, "status")
        )
    return [_channel_response(channel) for channel in session.scalars(statement).all()]


@router.get("/notification-channels/{channel_id}", response_model=NotificationChannelResponse)
def get_channel(
    channel_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> NotificationChannelResponse:
    channel = _get_channel(session, channel_id)
    _ensure_channel_member(session, channel_id, current_user)
    return _channel_response(channel)


@router.post(
    "/notification-channels/{channel_id}/members",
    response_model=ChannelMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def upsert_channel_member(
    channel_id: str,
    request: ChannelMemberUpsertRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ChannelMemberResponse:
    _get_channel(session, channel_id)
    _ensure_channel_manager(session, channel_id, current_user)
    user_id = _validate_user_id(session, request.user_id)
    member_role = _normalize_choice(request.member_role, MEMBER_ROLES, "memberRole")
    member = session.scalar(
        select(NotificationChannelMember).where(
            NotificationChannelMember.channel_id == channel_id,
            NotificationChannelMember.user_id == user_id,
        )
    )
    if member is None:
        member = NotificationChannelMember(
            member_id=_new_public_id("chmember"),
            channel_id=channel_id,
            user_id=user_id,
            member_role=member_role,
            status="ACTIVE",
            added_by=current_user.user_id,
        )
        session.add(member)
    else:
        member.member_role = member_role
        member.status = "ACTIVE"
        member.added_by = current_user.user_id
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Channel member could not be saved.") from exc
    session.refresh(member)
    return _member_response(member)


@router.get("/notification-channels/{channel_id}/members", response_model=list[ChannelMemberResponse])
def list_channel_members(
    channel_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ChannelMemberResponse]:
    _get_channel(session, channel_id)
    _ensure_channel_member(session, channel_id, current_user)
    members = session.scalars(
        select(NotificationChannelMember)
        .where(NotificationChannelMember.channel_id == channel_id)
        .order_by(NotificationChannelMember.id)
    ).all()
    return [_member_response(member) for member in members]


@router.patch("/notification-channels/{channel_id}/members/{member_id}", response_model=ChannelMemberResponse)
def update_channel_member(
    channel_id: str,
    member_id: str,
    request: ChannelMemberUpdateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ChannelMemberResponse:
    _get_channel(session, channel_id)
    _ensure_channel_manager(session, channel_id, current_user)
    member = session.scalar(
        select(NotificationChannelMember).where(
            NotificationChannelMember.channel_id == channel_id,
            NotificationChannelMember.member_id == member_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel member not found.")
    if request.member_role is not None:
        member.member_role = _normalize_choice(request.member_role, MEMBER_ROLES, "memberRole")
    if request.status is not None:
        member.status = _normalize_choice(request.status, MEMBER_STATUSES, "status")
    session.commit()
    session.refresh(member)
    return _member_response(member)


@router.post(
    "/notification-channels/{channel_id}/messages",
    response_model=ChannelMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_channel_message(
    channel_id: str,
    request: ChannelMessageCreateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ChannelMessageResponse:
    channel = _get_channel(session, channel_id)
    if channel.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Notification channel is not active.")
    _ensure_channel_member(session, channel_id, current_user)
    message_type = _normalize_choice(request.message_type, MESSAGE_TYPES, "messageType")
    source_type = _normalize_choice(request.source_type, MESSAGE_SOURCE_TYPES, "sourceType")
    source_id = request.source_id.strip()
    if message_type == "FIELD_COMMENT_EVENT" and source_type == "FIELD_COMMENT":
        existing = session.scalar(
            select(ChannelMessage)
            .where(
                ChannelMessage.channel_id == channel_id,
                ChannelMessage.message_type == message_type,
                ChannelMessage.source_type == source_type,
                ChannelMessage.source_id == source_id,
            )
            .order_by(ChannelMessage.id)
        )
        if existing is not None:
            return _message_response(existing)

    message = ChannelMessage(
        message_id=_new_public_id("chmsg"),
        channel_id=channel_id,
        message_type=message_type,
        source_type=source_type,
        source_id=source_id,
        source_version_id=_clean_optional(request.source_version_id),
        title=request.title.strip(),
        body=_clean_optional(request.body),
        created_by=current_user.user_id,
    )
    session.add(message)
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="channel_message.created",
            actor_id=current_user.user_id,
            target_type="channel_message",
            target_id=message.message_id,
            target_title=message.title,
            message=f"Channel message created: {message.title}.",
        )
    )
    session.commit()
    session.refresh(message)
    return _message_response(message)


@router.get("/notification-channels/{channel_id}/messages", response_model=list[ChannelMessageResponse])
def list_channel_messages(
    channel_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ChannelMessageResponse]:
    _get_channel(session, channel_id)
    _ensure_channel_member(session, channel_id, current_user)
    messages = session.scalars(
        select(ChannelMessage)
        .where(ChannelMessage.channel_id == channel_id)
        .order_by(desc(ChannelMessage.created_at), desc(ChannelMessage.id))
        .limit(limit)
    ).all()
    return [_message_response(message) for message in messages]


@router.get("/notifications", response_model=list[UserNotificationResponse])
def list_my_notifications(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    response: Response,
    unread_only: Annotated[bool, Query(alias="unreadOnly")] = False,
    after_id: Annotated[int | None, Query(alias="afterId", ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[UserNotificationResponse]:
    current_cursor = session.scalar(select(ChannelMessage.id).order_by(desc(ChannelMessage.id)).limit(1))
    response.headers["X-FlowNote-Notification-Cursor"] = str(current_cursor or 0)
    statement = (
        select(ChannelMessage, NotificationChannel, NotificationChannelMember)
        .join(NotificationChannel, NotificationChannel.channel_id == ChannelMessage.channel_id)
        .join(
            NotificationChannelMember,
            NotificationChannelMember.channel_id == ChannelMessage.channel_id,
        )
        .where(
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    )
    if after_id is not None:
        statement = statement.where(ChannelMessage.id > after_id).order_by(ChannelMessage.id)
    else:
        statement = statement.order_by(desc(ChannelMessage.id))
    # unreadOnly is derived from the channel member read watermark, so apply the
    # limit after filtering to avoid returning a short or empty page incorrectly.
    rows = session.execute(statement).all()
    notifications: list[UserNotificationResponse] = []
    for message, channel, member in rows:
        read = member.last_read_at is not None and (
            member.last_read_message_id == message.message_id or message.created_at <= member.last_read_at
        )
        if unread_only and read:
            continue
        notifications.append(
            UserNotificationResponse(
                **_message_response(message).model_dump(),
                cursor=message.id,
                channel_name=channel.name,
                read=read,
                read_at=member.last_read_at if read else None,
            )
        )
        if len(notifications) >= limit:
            break
    next_cursor = notifications[-1].cursor if notifications else (after_id or 0)
    response.headers["X-FlowNote-Next-Cursor"] = str(next_cursor)
    response.headers["X-FlowNote-Has-More"] = str(len(notifications) == limit).lower()
    return notifications


@router.patch("/notifications/{message_id}/read", response_model=UserNotificationResponse)
def mark_notification_read(
    message_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    request: NotificationReadRequest | None = None,
) -> UserNotificationResponse:
    row = session.execute(
        select(ChannelMessage, NotificationChannel, NotificationChannelMember)
        .join(NotificationChannel, NotificationChannel.channel_id == ChannelMessage.channel_id)
        .join(
            NotificationChannelMember,
            NotificationChannelMember.channel_id == ChannelMessage.channel_id,
        )
        .where(
            ChannelMessage.message_id == message_id,
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification message not found.")
    message, channel, member = row
    if member.last_read_message_id == message.message_id:
        return UserNotificationResponse(
            **_message_response(message).model_dump(),
            cursor=message.id,
            channel_name=channel.name,
            read=True,
            read_at=member.last_read_at,
        )
    member.last_read_message_id = message.message_id
    member.last_read_at = datetime.now(timezone.utc)
    delivery_evidence = None
    if request is not None and request.delivery_run_id:
        delivery_evidence = json.dumps(
            {
                "delivery_run_id": request.delivery_run_id,
                "displayed_at": request.displayed_at.isoformat() if request.displayed_at else None,
                "read_at": member.last_read_at.isoformat(),
            },
            sort_keys=True,
        )
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="channel_message.read",
            actor_id=current_user.user_id,
            target_type="channel_message",
            target_id=message.message_id,
            target_title=message.title,
            message=f"Channel message read: {message.title}.",
            after_value=delivery_evidence,
        )
    )
    session.commit()
    session.refresh(member)
    return UserNotificationResponse(
        **_message_response(message).model_dump(),
        cursor=message.id,
        channel_name=channel.name,
        read=True,
        read_at=member.last_read_at,
    )


@router.post("/handovers", response_model=HandoverResponse, status_code=status.HTTP_201_CREATED)
def create_handover(
    request: HandoverCreateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponse:
    channel = _get_channel(session, request.channel_id)
    if channel.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Notification channel is not active.")
    _ensure_channel_member(session, channel.channel_id, current_user)
    source_type = None
    if request.source_type is not None:
        source_type = _normalize_choice(request.source_type, HANDOVER_SOURCE_TYPES, "sourceType")
    recipient_ids = []
    for recipient_id in request.recipient_ids:
        user_id = _validate_user_id(session, recipient_id, "recipientIds")
        if user_id in recipient_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="recipientIds must not contain duplicate values.",
            )
        if _get_active_member(session, channel.channel_id, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="recipientIds must reference active channel members.",
            )
        recipient_ids.append(user_id)

    handover = Handover(
        handover_id=_new_public_id("handover"),
        channel_id=channel.channel_id,
        title=request.title.strip(),
        body=request.body.strip(),
        source_type=source_type,
        source_id=_clean_optional(request.source_id),
        source_version_id=_clean_optional(request.source_version_id),
        status="SENT",
        created_by=current_user.user_id,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(handover)
    session.flush()
    for recipient_id in recipient_ids:
        session.add(
            HandoverReceipt(
                receipt_id=_new_public_id("hreceipt"),
                handover_id=handover.handover_id,
                recipient_id=recipient_id,
                receipt_status="UNREAD",
            )
        )
    session.add(
        ChannelMessage(
            message_id=_new_public_id("chmsg"),
            channel_id=channel.channel_id,
            message_type="HANDOVER",
            source_type="HANDOVER",
            source_id=handover.handover_id,
            source_version_id=None,
            title=handover.title,
            body=handover.body,
            created_by=current_user.user_id,
        )
    )
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="handover.created",
            actor_id=current_user.user_id,
            target_type="handover",
            target_id=handover.handover_id,
            target_title=handover.title,
            message=f"Handover created: {handover.title}.",
        )
    )
    session.commit()
    session.refresh(handover)
    return _handover_response(session, handover)


@router.get("/handovers", response_model=list[HandoverResponse])
def list_handovers(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[HandoverResponse]:
    statement = (
        select(Handover)
        .join(NotificationChannelMember, NotificationChannelMember.channel_id == Handover.channel_id)
        .where(
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
        .order_by(desc(Handover.created_at), desc(Handover.id))
        .limit(limit)
    )
    handovers = session.scalars(statement).all()
    return [_handover_response(session, handover) for handover in handovers]


@router.get("/handovers/{handover_id}", response_model=HandoverResponse)
def get_handover(
    handover_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponse:
    handover = session.scalar(select(Handover).where(Handover.handover_id == handover_id))
    if handover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handover not found.")
    _ensure_channel_member(session, handover.channel_id, current_user)
    return _handover_response(session, handover)


@router.patch("/handovers/{handover_id}/receipts/{receipt_id}", response_model=HandoverResponse)
def update_handover_receipt(
    handover_id: str,
    receipt_id: str,
    request: HandoverReceiptUpdateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponse:
    handover = session.scalar(select(Handover).where(Handover.handover_id == handover_id))
    if handover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handover not found.")
    receipt = session.scalar(
        select(HandoverReceipt).where(
            HandoverReceipt.handover_id == handover_id,
            HandoverReceipt.receipt_id == receipt_id,
        )
    )
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handover receipt not found.")
    if receipt.recipient_id != current_user.user_id and current_user.role not in CHANNEL_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user cannot update this handover receipt.",
        )

    target_status = _normalize_choice(request.receipt_status, RECEIPT_STATUSES, "receiptStatus")
    target_note = _clean_optional(request.note)
    if receipt.receipt_status == target_status and receipt.note == target_note:
        return _handover_response(session, handover)
    now = datetime.now(timezone.utc)
    receipt.receipt_status = target_status
    receipt.note = target_note
    receipt.updated_by = current_user.user_id
    if target_status in {"READ", "ACKNOWLEDGED", "FOLLOW_UP_REQUIRED"} and receipt.read_at is None:
        receipt.read_at = now
    if target_status == "ACKNOWLEDGED":
        receipt.acknowledged_at = now
    if target_status == "FOLLOW_UP_REQUIRED":
        receipt.follow_up_required_at = now
    session.flush()
    _sync_handover_status(session, handover)
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="handover.receipt_status_changed",
            actor_id=current_user.user_id,
            target_type="handover_receipt",
            target_id=receipt.receipt_id,
            target_title=handover.title,
            message=f"Handover receipt status changed: {target_status}.",
            after_value=(
                json.dumps(
                    {
                        "receipt_status": target_status,
                        "delivery_run_id": request.delivery_run_id,
                        "displayed_at": (
                            request.displayed_at.isoformat() if request.displayed_at else None
                        ),
                        "receipt_at": now.isoformat(),
                    },
                    sort_keys=True,
                )
                if request.delivery_run_id
                else target_status
            ),
            change_reason=receipt.note,
        )
    )
    session.commit()
    session.refresh(handover)
    return _handover_response(session, handover)
