from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import DOCUMENT_WRITE_ROLES, CurrentUser, get_current_user
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Document,
    DocumentVersion,
    Handover,
    HandoverReceipt,
    NotificationChannel,
    NotificationChannelMember,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceCandidateDelivery,
    WorkSequenceChangeHistory,
    WorkSequenceDeliveryRecipient,
    WorkSequenceDeliveryTemplate,
    WorkSequenceItem,
    WorkSequenceNotificationCandidate,
)
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    canonical_hash,
    check_common_mutation_replay,
    mutation_trace,
    record_common_mutation_result,
    sanitize_audit_text,
)

router = APIRouter(
    prefix="/work-sequence-boards",
    tags=["work-sequence-candidate-deliveries"],
    dependencies=[Depends(get_current_user)],
)
template_router = APIRouter(
    prefix="/work-sequence-delivery-templates",
    tags=["work-sequence-candidate-deliveries"],
    dependencies=[Depends(get_current_user)],
)

DELIVERY_MODES = {"CHANNEL", "HANDOVER"}
CHANNEL_MANAGER_ROLES = {"OWNER", "MANAGER"}
GLOBAL_CHANNEL_ADMIN_ROLES = {"admin", "system-admin"}


class DeliveryRecipientPreview(BaseModel):
    user_id: str
    display_name: str
    member_role: str


class DeliverySourcePreview(BaseModel):
    source_type: str
    source_id: str
    change_id: str
    item_title: str | None
    published_document_id: str | None
    published_document_version_id: str | None
    published_document_title: str | None


class WorkSequenceDeliveryPreviewResponse(BaseModel):
    candidate_id: str
    candidate_status: str
    candidate_board_revision: int
    current_board_revision: int
    expires_at: datetime | None
    channel_id: str
    channel_name: str
    channel_type: str
    channel_source_type: str | None
    channel_source_id: str | None
    required_member_role: str
    can_deliver: bool
    recipients: list[DeliveryRecipientPreview]
    recipient_count: int
    title: str
    body: str
    source: DeliverySourcePreview


class WorkSequenceDeliveryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel_id: str = Field(alias="channelId", min_length=1, max_length=64)
    delivery_mode: str = Field(alias="deliveryMode", min_length=1)
    recipient_ids: list[str] = Field(alias="recipientIds", min_length=1)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=1000)
    base_board_revision: int = Field(alias="baseBoardRevision", ge=1)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1, max_length=160)
    intent_hash_sha256: str | None = Field(default=None, alias="intentHashSha256", min_length=64, max_length=64)


class DeliveryRecipientResult(BaseModel):
    recipient_id: str
    delivery_status: str
    handover_receipt_id: str | None
    error_code: str | None
    error_message: str | None
    attempt_count: int


class WorkSequenceDeliveryResponse(BaseModel):
    delivery_id: str
    candidate_id: str
    candidate_status: str
    board_id: str
    board_revision: int
    change_id: str
    channel_id: str
    delivery_mode: str
    intent_hash_sha256: str
    message_id: str | None
    handover_id: str | None
    source_type: str
    source_id: str
    source_version_id: str | None
    related_document_id: str | None
    related_document_version_id: str | None
    status: str
    success_count: int
    failure_count: int
    recipients: list[DeliveryRecipientResult]
    created_at: datetime
    updated_at: datetime


class DeliveryTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class DeliveryTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=4000)
    status: str | None = None


class DeliveryTemplateResponse(BaseModel):
    template_id: str
    site_scope: str
    name: str
    title: str
    body: str
    status: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _conflict(code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message, **extra},
    )


def _require_writer(current_user: CurrentUser) -> None:
    if current_user.role not in DOCUMENT_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WORK_SEQUENCE_DELIVERY_ROLE_REQUIRED",
                "message": "작업순서 전달은 작업순서 변경 권한이 필요합니다. 현장 관리자에게 권한을 요청하세요.",
            },
        )


def _candidate_context(
    session: Session,
    *,
    board_id: str,
    candidate_id: str,
    channel_id: str,
    current_user: CurrentUser,
    recipient_ids: list[str] | None = None,
    base_board_revision: int | None = None,
) -> tuple[
    WorkSequenceBoard,
    WorkSequenceNotificationCandidate,
    WorkSequenceChangeHistory,
    NotificationChannel,
    NotificationChannelMember,
    list[tuple[NotificationChannelMember, UserAccount]],
    WorkSequenceItem | None,
    Document | None,
]:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    candidate = session.scalar(
        select(WorkSequenceNotificationCandidate).where(
            WorkSequenceNotificationCandidate.board_id == board_id,
            WorkSequenceNotificationCandidate.candidate_id == candidate_id,
        )
    )
    if board is None or candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="작업순서 알림 후보를 찾을 수 없습니다.")
    if candidate.status == "DISMISSED":
        raise _conflict("CANDIDATE_DISMISSED", "제외한 알림 후보는 전달할 수 없습니다.")
    if _aware(candidate.expires_at) is not None and _aware(candidate.expires_at) <= datetime.now(timezone.utc):
        raise _conflict(
            "CANDIDATE_EXPIRED",
            "알림 후보가 생성 후 24시간을 지나 만료되었습니다. 현재 작업순서에서 새 후보를 만드세요.",
        )
    if candidate.board_revision != board.board_revision or (
        base_board_revision is not None and base_board_revision != board.board_revision
    ):
        raise _conflict(
            "WORK_SEQUENCE_DELIVERY_STALE_REVISION",
            "후보 생성 뒤 작업순서가 바뀌었습니다. 새로고침한 뒤 현재 변경 후보를 선택하세요.",
            candidateRevision=candidate.board_revision,
            expectedRevision=base_board_revision,
            currentRevision=board.board_revision,
        )
    history = session.scalar(
        select(WorkSequenceChangeHistory).where(
            WorkSequenceChangeHistory.change_id == candidate.change_id,
            WorkSequenceChangeHistory.board_id == board_id,
            WorkSequenceChangeHistory.board_revision == candidate.board_revision,
        )
    )
    if history is None:
        raise _conflict(
            "CANDIDATE_SOURCE_CHANGED",
            "후보가 가리키는 작업순서 변경 이력을 다시 확인할 수 없습니다.",
        )

    channel = session.scalar(
        select(NotificationChannel).where(
            NotificationChannel.channel_id == channel_id,
            NotificationChannel.status == "ACTIVE",
        )
    )
    actor_member = session.scalar(
        select(NotificationChannelMember).where(
            NotificationChannelMember.channel_id == channel_id,
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    )
    if channel is None or actor_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CHANNEL_NOT_VISIBLE",
                "message": "이 채널은 표시하거나 전달할 수 없습니다. 채널 관리자에게 멤버 등록을 요청하세요.",
            },
        )

    rows = session.execute(
        select(NotificationChannelMember, UserAccount)
        .join(UserAccount, UserAccount.user_id == NotificationChannelMember.user_id)
        .where(
            NotificationChannelMember.channel_id == channel_id,
            NotificationChannelMember.status == "ACTIVE",
            UserAccount.is_active.is_(True),
            UserAccount.status == "ACTIVE",
        )
        .order_by(NotificationChannelMember.id)
    ).all()
    if recipient_ids is not None:
        cleaned = [value.strip() for value in recipient_ids]
        if any(not value for value in cleaned) or len(cleaned) != len(set(cleaned)):
            raise HTTPException(status_code=422, detail="recipientIds는 비어 있거나 중복될 수 없습니다.")
        by_id = {account.user_id: (member, account) for member, account in rows}
        missing = [value for value in cleaned if value not in by_id]
        if missing:
            raise _conflict(
                "CHANNEL_MEMBERSHIP_CHANGED",
                "미리보기 뒤 채널 수신자 멤버십이 바뀌었습니다. 다시 미리보기 하세요.",
                recipientIds=missing,
            )
        rows = [by_id[value] for value in cleaned]

    item = None
    document = None
    if candidate.item_id is not None:
        item = session.scalar(
            select(WorkSequenceItem).where(
                WorkSequenceItem.item_id == candidate.item_id,
                WorkSequenceItem.board_id == board_id,
            )
        )
        if item is None:
            raise _conflict("CANDIDATE_SOURCE_CHANGED", "후보의 작업순서 항목을 다시 확인할 수 없습니다.")
        if item.document_id is not None:
            document = session.scalar(
                select(Document).where(
                    Document.document_id == item.document_id,
                    Document.status == "PUBLISHED",
                    Document.deleted_at.is_(None),
                    Document.published_version_id.is_not(None),
                )
            )
            if document is not None:
                published = session.scalar(
                    select(DocumentVersion.id).where(
                        DocumentVersion.document_id == document.document_id,
                        DocumentVersion.version_id == document.published_version_id,
                        DocumentVersion.version_status == "PUBLISHED",
                        DocumentVersion.is_published.is_(True),
                    )
                )
                if published is None:
                    document = None
    return board, candidate, history, channel, actor_member, rows, item, document


def _source_preview(
    candidate: WorkSequenceNotificationCandidate,
    history: WorkSequenceChangeHistory,
    item: WorkSequenceItem | None,
    document: Document | None,
) -> DeliverySourcePreview:
    return DeliverySourcePreview(
        source_type="WORK_SEQUENCE_ITEM" if item is not None else "WORK_SEQUENCE_HISTORY",
        source_id=item.item_id if item is not None else history.change_id,
        change_id=history.change_id,
        item_title=item.title if item is not None else None,
        published_document_id=document.document_id if document is not None else None,
        published_document_version_id=document.published_version_id if document is not None else None,
        published_document_title=document.title if document is not None else None,
    )


@router.get(
    "/{board_id}/notification-candidates/{candidate_id}/delivery-preview",
    response_model=WorkSequenceDeliveryPreviewResponse,
)
def preview_delivery(
    board_id: str,
    candidate_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    channel_id: Annotated[str, Query(alias="channelId", min_length=1)],
) -> WorkSequenceDeliveryPreviewResponse:
    board, candidate, history, channel, actor_member, rows, item, document = _candidate_context(
        session,
        board_id=board_id,
        candidate_id=candidate_id,
        channel_id=channel_id,
        current_user=current_user,
    )
    recipients = [
        DeliveryRecipientPreview(
            user_id=account.user_id,
            display_name=account.display_name,
            member_role=member.member_role,
        )
        for member, account in rows
    ]
    return WorkSequenceDeliveryPreviewResponse(
        candidate_id=candidate.candidate_id,
        candidate_status=candidate.status,
        candidate_board_revision=candidate.board_revision,
        current_board_revision=board.board_revision,
        expires_at=candidate.expires_at,
        channel_id=channel.channel_id,
        channel_name=channel.name,
        channel_type=channel.channel_type,
        channel_source_type=channel.source_type,
        channel_source_id=channel.source_id,
        required_member_role="OWNER_OR_MANAGER",
        can_deliver=(
            actor_member.member_role in CHANNEL_MANAGER_ROLES
            and current_user.role in DOCUMENT_WRITE_ROLES
        ),
        recipients=recipients,
        recipient_count=len(recipients),
        title=f"작업순서 변경: {item.title if item is not None else board.title}",
        body=candidate.message,
        source=_source_preview(candidate, history, item, document),
    )


def _delivery_response(
    session: Session,
    delivery: WorkSequenceCandidateDelivery,
    candidate: WorkSequenceNotificationCandidate | None = None,
) -> WorkSequenceDeliveryResponse:
    candidate = candidate or session.scalar(
        select(WorkSequenceNotificationCandidate).where(
            WorkSequenceNotificationCandidate.candidate_id == delivery.candidate_id
        )
    )
    rows = session.scalars(
        select(WorkSequenceDeliveryRecipient)
        .where(WorkSequenceDeliveryRecipient.delivery_id == delivery.delivery_id)
        .order_by(WorkSequenceDeliveryRecipient.id)
    ).all()
    success_count = sum(row.delivery_status == "DELIVERED" for row in rows)
    return WorkSequenceDeliveryResponse(
        delivery_id=delivery.delivery_id,
        candidate_id=delivery.candidate_id,
        candidate_status=candidate.status if candidate is not None else "CANDIDATE",
        board_id=delivery.board_id,
        board_revision=delivery.board_revision,
        change_id=delivery.change_id,
        channel_id=delivery.channel_id,
        delivery_mode=delivery.delivery_mode,
        intent_hash_sha256=delivery.intent_hash_sha256,
        message_id=delivery.message_id,
        handover_id=delivery.handover_id,
        source_type=delivery.source_type,
        source_id=delivery.source_id,
        source_version_id=delivery.source_version_id,
        related_document_id=delivery.related_document_id,
        related_document_version_id=delivery.related_document_version_id,
        status=delivery.status,
        success_count=success_count,
        failure_count=len(rows) - success_count,
        recipients=[
            DeliveryRecipientResult(
                recipient_id=row.recipient_id,
                delivery_status=row.delivery_status,
                handover_receipt_id=row.handover_receipt_id,
                error_code=row.error_code,
                error_message=row.error_message,
                attempt_count=row.attempt_count,
            )
            for row in rows
        ],
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


def _retry_partial_delivery(
    session: Session,
    *,
    delivery: WorkSequenceCandidateDelivery,
    candidate: WorkSequenceNotificationCandidate,
    history: WorkSequenceChangeHistory,
    current_user: CurrentUser,
    http_request: Request,
) -> WorkSequenceDeliveryResponse:
    failed = session.scalars(
        select(WorkSequenceDeliveryRecipient).where(
            WorkSequenceDeliveryRecipient.delivery_id == delivery.delivery_id,
            WorkSequenceDeliveryRecipient.delivery_status == "FAILED",
        )
    ).all()
    handover = session.scalar(
        select(Handover).where(Handover.handover_id == delivery.handover_id)
    ) if delivery.handover_id is not None else None
    for row in failed:
        row.attempt_count += 1
        try:
            with session.begin_nested():
                if handover is not None:
                    receipt_id = _new_public_id("hreceipt")
                    session.add(
                        HandoverReceipt(
                            receipt_id=receipt_id,
                            handover_id=handover.handover_id,
                            recipient_id=row.recipient_id,
                            receipt_status="UNREAD",
                        )
                    )
                    row.handover_receipt_id = receipt_id
                row.delivery_status = "DELIVERED"
                row.error_code = None
                row.error_message = None
                session.flush()
        except IntegrityError:
            row.delivery_status = "FAILED"
            row.error_code = "RECEIPT_WRITE_FAILED"
            row.error_message = "재시도한 수신 확인을 저장하지 못했습니다. 기존 성공 receipt는 유지됩니다."

    session.flush()
    remaining = session.scalar(
        select(WorkSequenceDeliveryRecipient.id).where(
            WorkSequenceDeliveryRecipient.delivery_id == delivery.delivery_id,
            WorkSequenceDeliveryRecipient.delivery_status == "FAILED",
        ).limit(1)
    )
    if remaining is None:
        delivery.status = "COMPLETED"
        candidate.status = "SENT"
        if handover is not None:
            handover.status = "SENT"
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="work_sequence.candidate_delivery_retried",
            actor_id=current_user.user_id,
            target_type="work_sequence_candidate_delivery",
            target_id=delivery.delivery_id,
            target_title=delivery.title,
            message="작업순서 후보 전달의 실패 수신자만 다시 시도했습니다.",
            after_value=json.dumps(
                {"retried_recipient_ids": [row.recipient_id for row in failed]},
                ensure_ascii=False,
                sort_keys=True,
            ),
            change_reason=delivery.reason,
        )
    )
    session.flush()
    response = _delivery_response(session, delivery, candidate)
    if delivery.status == "COMPLETED":
        record_common_mutation_result(
            session,
            operation_key=delivery.idempotency_key,
            intent_hash=delivery.intent_hash_sha256,
            event_type="work_sequence.candidate_delivered",
            trace=mutation_trace(current_user, http_request),
            target_type="work_sequence_notification_candidate",
            target_id=candidate.candidate_id,
            target_version_id=None,
            target_revision=delivery.board_revision,
            reason=delivery.reason,
            before_hash=canonical_hash({"deliveryStatus": "PARTIAL"}),
            after_hash=canonical_hash(response.model_dump(mode="json")),
            result="SUCCESS",
            result_code="RETRY_APPLIED",
            http_status=status.HTTP_201_CREATED,
            response_detail=response.model_dump(mode="json"),
            domain_receipt_type="work_sequence_candidate_deliveries",
            domain_receipt_id=str(delivery.id),
            related_target_type="work_sequence_change_history",
            related_target_id=history.change_id,
            related_target_revision=history.board_revision,
        )
    session.commit()
    session.refresh(delivery)
    return _delivery_response(session, delivery, candidate)


@router.post(
    "/{board_id}/notification-candidates/{candidate_id}/deliveries",
    response_model=WorkSequenceDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def deliver_candidate(
    http_request: Request,
    board_id: str,
    candidate_id: str,
    request: WorkSequenceDeliveryRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceDeliveryResponse:
    _require_writer(current_user)
    delivery_mode = request.delivery_mode.strip().upper()
    if delivery_mode not in DELIVERY_MODES:
        raise HTTPException(status_code=422, detail="deliveryMode는 CHANNEL 또는 HANDOVER여야 합니다.")
    recipient_ids = [value.strip() for value in request.recipient_ids]
    title = request.title.strip()
    body = request.body.strip()
    reason = sanitize_audit_text(request.reason) or ""
    intent = {
        "boardId": board_id,
        "candidateId": candidate_id,
        "channelId": request.channel_id.strip(),
        "deliveryMode": delivery_mode,
        "recipientIds": sorted(recipient_ids),
        "title": title,
        "body": body,
        "reason": reason,
        "baseBoardRevision": request.base_board_revision,
    }
    intent_hash = canonical_hash(intent)
    if request.intent_hash_sha256 is not None and request.intent_hash_sha256.lower() != intent_hash:
        raise _conflict("INTENT_HASH_MISMATCH", "클라이언트와 서버의 전달 intent hash가 다릅니다.")

    existing_by_key = session.scalar(
        select(WorkSequenceCandidateDelivery).where(
            WorkSequenceCandidateDelivery.idempotency_key == request.idempotency_key.strip()
        )
    )
    if existing_by_key is not None:
        if existing_by_key.intent_hash_sha256 != intent_hash:
            raise _conflict("IDEMPOTENCY_KEY_REUSED", "같은 멱등키를 다른 채널이나 문구에 사용할 수 없습니다.")
        if existing_by_key.status == "COMPLETED":
            return _delivery_response(session, existing_by_key)
    check_common_mutation_replay(
        session,
        operation_key=request.idempotency_key.strip(),
        intent_hash=intent_hash,
        event_type="work_sequence.candidate_delivered",
        target_type="work_sequence_notification_candidate",
        target_id=candidate_id,
    )

    board, candidate, history, channel, actor_member, rows, item, document = _candidate_context(
        session,
        board_id=board_id,
        candidate_id=candidate_id,
        channel_id=request.channel_id.strip(),
        current_user=current_user,
        recipient_ids=recipient_ids,
        base_board_revision=request.base_board_revision,
    )
    if actor_member.member_role not in CHANNEL_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CHANNEL_MANAGER_ROLE_REQUIRED",
                "message": "채널 전달에는 채널 소유자 또는 관리자 역할이 필요합니다. 채널 관리자에게 역할 변경을 요청하세요.",
            },
        )
    if existing_by_key is not None:
        return _retry_partial_delivery(
            session,
            delivery=existing_by_key,
            candidate=candidate,
            history=history,
            current_user=current_user,
            http_request=http_request,
        )
    existing_channel = session.scalar(
        select(WorkSequenceCandidateDelivery).where(
            WorkSequenceCandidateDelivery.candidate_id == candidate_id,
            WorkSequenceCandidateDelivery.channel_id == channel.channel_id,
        )
    )
    if existing_channel is not None:
        if existing_channel.intent_hash_sha256 == intent_hash:
            return _delivery_response(session, existing_channel, candidate)
        raise _conflict(
            "CANDIDATE_CHANNEL_ALREADY_DELIVERED",
            "이 후보는 해당 채널에 이미 다른 내용으로 확정되었습니다. 기존 전달 내역을 확인하세요.",
            deliveryId=existing_channel.delivery_id,
        )

    source = _source_preview(candidate, history, item, document)
    delivery = WorkSequenceCandidateDelivery(
        delivery_id=_new_public_id("wseqdelivery"),
        idempotency_key=request.idempotency_key.strip(),
        intent_hash_sha256=intent_hash,
        candidate_id=candidate_id,
        board_id=board_id,
        board_revision=board.board_revision,
        change_id=history.change_id,
        channel_id=channel.channel_id,
        delivery_mode=delivery_mode,
        title=title,
        body=body,
        reason=reason,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version_id=history.change_id,
        related_document_id=source.published_document_id,
        related_document_version_id=source.published_document_version_id,
        requested_recipient_ids_json=json.dumps(recipient_ids, ensure_ascii=False),
        status="PARTIAL",
        created_by=current_user.user_id,
    )
    session.add(delivery)
    session.flush()

    handover = None
    if delivery_mode == "HANDOVER":
        handover = Handover(
            handover_id=_new_public_id("handover"),
            idempotency_key=f"wseq:{intent_hash}",
            channel_id=channel.channel_id,
            title=title,
            body=body,
            source_type=source.source_type,
            source_id=source.source_id,
            source_version_id=history.change_id,
            related_document_id=source.published_document_id,
            related_document_version_id=source.published_document_version_id,
            status="SENT",
            created_by=current_user.user_id,
            entry_source="windows_client",
            sent_at=datetime.now(timezone.utc),
        )
        session.add(handover)
        session.flush()
        delivery.handover_id = handover.handover_id

    message = ChannelMessage(
        message_id=_new_public_id("chmsg"),
        channel_id=channel.channel_id,
        message_type="HANDOVER" if handover is not None else "WORK_SEQUENCE_EVENT",
        source_type="HANDOVER" if handover is not None else source.source_type,
        source_id=handover.handover_id if handover is not None else source.source_id,
        source_version_id=history.change_id,
        related_document_id=source.published_document_id,
        related_document_version_id=source.published_document_version_id,
        title=title,
        body=body,
        created_by=current_user.user_id,
    )
    session.add(message)
    session.flush()
    delivery.message_id = message.message_id

    success_count = 0
    for _, account in rows:
        receipt_id = None
        try:
            with session.begin_nested():
                if handover is not None:
                    receipt_id = _new_public_id("hreceipt")
                    session.add(
                        HandoverReceipt(
                            receipt_id=receipt_id,
                            handover_id=handover.handover_id,
                            recipient_id=account.user_id,
                            receipt_status="UNREAD",
                        )
                    )
                session.add(
                    WorkSequenceDeliveryRecipient(
                        delivery_recipient_id=_new_public_id("wseqrecipient"),
                        delivery_id=delivery.delivery_id,
                        recipient_id=account.user_id,
                        delivery_status="DELIVERED",
                        handover_receipt_id=receipt_id,
                        attempt_count=1,
                    )
                )
                session.flush()
            success_count += 1
        except IntegrityError:
            session.add(
                WorkSequenceDeliveryRecipient(
                    delivery_recipient_id=_new_public_id("wseqrecipient"),
                    delivery_id=delivery.delivery_id,
                    recipient_id=account.user_id,
                    delivery_status="FAILED",
                    error_code="RECEIPT_WRITE_FAILED",
                    error_message="수신 확인 저장에 실패했습니다. 원천과 기존 성공 수신자는 유지됩니다.",
                    attempt_count=1,
                )
            )

    delivery.status = "COMPLETED" if success_count == len(rows) else "PARTIAL"
    if delivery.status == "COMPLETED":
        candidate.status = "SENT"
    elif handover is not None:
        handover.status = "FOLLOW_UP_REQUIRED"
    audit = ActivityHistory(
        history_id=_new_public_id("hist"),
        event_type="work_sequence.candidate_delivered",
        actor_id=current_user.user_id,
        target_type="work_sequence_notification_candidate",
        target_id=candidate_id,
        target_title=title,
        message=f"작업순서 알림 후보를 {channel.name} 채널에 전달했습니다.",
        before_value="CANDIDATE",
        after_value=json.dumps(
            {
                "delivery_id": delivery.delivery_id,
                "channel_id": channel.channel_id,
                "delivery_mode": delivery_mode,
                "message_id": message.message_id,
                "handover_id": delivery.handover_id,
                "success_count": success_count,
                "failure_count": len(rows) - success_count,
                "change_id": history.change_id,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        change_reason=reason,
    )
    session.add(audit)
    session.flush()
    response = _delivery_response(session, delivery, candidate)
    if delivery.status == "COMPLETED":
        record_common_mutation_result(
            session,
            operation_key=request.idempotency_key.strip(),
            intent_hash=intent_hash,
            event_type="work_sequence.candidate_delivered",
            trace=mutation_trace(current_user, http_request),
            target_type="work_sequence_notification_candidate",
            target_id=candidate_id,
            target_version_id=None,
            target_revision=board.board_revision,
            reason=reason,
            before_hash=canonical_hash({"candidateStatus": "CANDIDATE"}),
            after_hash=canonical_hash(response.model_dump(mode="json")),
            result="SUCCESS",
            result_code="APPLIED",
            http_status=status.HTTP_201_CREATED,
            response_detail=response.model_dump(mode="json"),
            domain_receipt_type="work_sequence_candidate_deliveries",
            domain_receipt_id=str(delivery.id),
            domain_audit_type="activity_history",
            domain_audit_id=audit.history_id,
            related_target_type="work_sequence_change_history",
            related_target_id=history.change_id,
            related_target_revision=history.board_revision,
        )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(WorkSequenceCandidateDelivery).where(
                (WorkSequenceCandidateDelivery.idempotency_key == request.idempotency_key.strip())
                | (
                    (WorkSequenceCandidateDelivery.candidate_id == candidate_id)
                    & (WorkSequenceCandidateDelivery.channel_id == request.channel_id.strip())
                )
            )
        )
        if existing is not None and existing.intent_hash_sha256 == intent_hash:
            return _delivery_response(session, existing)
        raise _conflict("DELIVERY_RACE", "다른 요청이 먼저 후보 전달을 확정했습니다.") from exc
    session.refresh(delivery)
    return _delivery_response(session, delivery, candidate)


def _template_response(row: WorkSequenceDeliveryTemplate) -> DeliveryTemplateResponse:
    return DeliveryTemplateResponse(
        template_id=row.template_id,
        site_scope=row.site_scope,
        name=row.name,
        title=row.title,
        body=row.body,
        status=row.status,
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@template_router.get("", response_model=list[DeliveryTemplateResponse])
def list_delivery_templates(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[DeliveryTemplateResponse]:
    rows = session.scalars(
        select(WorkSequenceDeliveryTemplate)
        .where(
            WorkSequenceDeliveryTemplate.site_scope == current_user.site_scope,
            WorkSequenceDeliveryTemplate.status == "ACTIVE",
        )
        .order_by(WorkSequenceDeliveryTemplate.name)
    ).all()
    return [_template_response(row) for row in rows]


@template_router.post("", response_model=DeliveryTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_delivery_template(
    request: DeliveryTemplateCreateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DeliveryTemplateResponse:
    _require_writer(current_user)
    row = WorkSequenceDeliveryTemplate(
        template_id=_new_public_id("wseqtemplate"),
        site_scope=current_user.site_scope,
        name=request.name.strip(),
        title=request.title.strip(),
        body=request.body.strip(),
        status="ACTIVE",
        created_by=current_user.user_id,
        updated_by=current_user.user_id,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _conflict("TEMPLATE_NAME_ALREADY_EXISTS", "이 현장에 같은 이름의 문구 템플릿이 있습니다.") from exc
    session.refresh(row)
    return _template_response(row)


@template_router.patch("/{template_id}", response_model=DeliveryTemplateResponse)
def update_delivery_template(
    template_id: str,
    request: DeliveryTemplateUpdateRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> DeliveryTemplateResponse:
    _require_writer(current_user)
    row = session.scalar(
        select(WorkSequenceDeliveryTemplate).where(
            WorkSequenceDeliveryTemplate.template_id == template_id,
            WorkSequenceDeliveryTemplate.site_scope == current_user.site_scope,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="문구 템플릿을 찾을 수 없습니다.")
    if row.created_by != current_user.user_id and current_user.role not in GLOBAL_CHANNEL_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="템플릿 작성자 또는 시스템 관리자만 수정할 수 있습니다.")
    if request.name is not None:
        row.name = request.name.strip()
    if request.title is not None:
        row.title = request.title.strip()
    if request.body is not None:
        row.body = request.body.strip()
    if request.status is not None:
        template_status = request.status.strip().upper()
        if template_status not in {"ACTIVE", "ARCHIVED"}:
            raise HTTPException(status_code=422, detail="status는 ACTIVE 또는 ARCHIVED여야 합니다.")
        row.status = template_status
    row.updated_by = current_user.user_id
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _conflict("TEMPLATE_NAME_ALREADY_EXISTS", "이 현장에 같은 이름의 문구 템플릿이 있습니다.") from exc
    session.refresh(row)
    return _template_response(row)
