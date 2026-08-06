from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.handover_contracts import HandoverReceiptResponse, HandoverResponse
from app.api.v1.work_sequence_field_views import (
    _approved_field_user,
    _published_document,
    _visible_items,
)
from app.core.auth import CurrentUser
from app.db.models import (
    ChannelMessage,
    Document,
    FieldComment,
    Handover,
    HandoverReceipt,
    Report,
    WorkRecord,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)


def handover_response(session: Session, handover: Handover) -> HandoverResponse:
    receipts = session.scalars(
        select(HandoverReceipt)
        .where(HandoverReceipt.handover_id == handover.handover_id)
        .order_by(HandoverReceipt.id)
    ).all()
    return HandoverResponse(
        handover_id=handover.handover_id,
        idempotency_key=handover.idempotency_key,
        channel_id=handover.channel_id,
        title=handover.title,
        body=handover.body,
        source_type=handover.source_type,
        source_id=handover.source_id,
        source_version_id=handover.source_version_id,
        source_revision=handover.source_revision,
        server_scope=handover.server_scope,
        intent_hash_sha256=handover.intent_hash_sha256,
        related_document_id=handover.related_document_id,
        related_document_version_id=handover.related_document_version_id,
        status=handover.status,
        created_by=handover.created_by,
        entry_source=handover.entry_source,
        device_id=handover.device_id,
        sent_at=handover.sent_at,
        created_at=handover.created_at,
        updated_at=handover.updated_at,
        receipts=[
            HandoverReceiptResponse(
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
            for receipt in receipts
        ],
    )


def ensure_android_handover_source(
    session: Session,
    current_user: CurrentUser,
    channel_id: str,
    source_type: str | None,
    source_id: str | None,
    source_version_id: str | None,
    source_revision: int | None,
    related_document_id: str | None,
    related_document_version_id: str | None,
) -> tuple[str | None, str | None]:
    if source_type is None or source_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "SOURCE_REQUIRED",
                "message": "Android 인수인계는 원천 연결이 필요합니다.",
            },
        )
    visible = False
    if source_type == "DOCUMENT":
        document = session.scalar(select(Document).where(Document.document_id == source_id))
        visible = (
            document is not None
            and document.status == "PUBLISHED"
            and (
                source_version_id is None
                or source_version_id == document.published_version_id
            )
        )
    elif source_type == "FIELD_COMMENT":
        visible = session.scalar(
            select(FieldComment.id).where(
                FieldComment.comment_id == source_id,
                FieldComment.status != "ARCHIVED",
            )
        ) is not None
    elif source_type == "WORK_SEQUENCE_ITEM":
        _approved_field_user(session, current_user)
        item = session.scalar(select(WorkSequenceItem).where(WorkSequenceItem.item_id == source_id))
        board = session.scalar(
            select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == item.board_id)
        ) if item is not None else None
        if board is None or source_revision != board.board_revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "WORK_SEQUENCE_REVISION_CHANGED",
                    "message": "인수인계를 시작한 뒤 작업순서가 바뀌었습니다. 현재 항목을 다시 확인하세요.",
                    "currentRevision": board.board_revision if board is not None else None,
                },
            )
        visible = any(
            row.item_id == source_id
            for row in _visible_items(session, current_user, board.board_id)
        )
        document_access, published = _published_document(session, item.document_id)
        expected_document_id = published.document_id if published is not None else None
        expected_version_id = published.version_id if published is not None else None
        if (
            document_access == "AVAILABLE"
            and (
                related_document_id != expected_document_id
                or related_document_version_id != expected_version_id
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SOURCE_DOCUMENT_CHANGED",
                    "message": "작업순서에 연결된 공개 문서가 바뀌었습니다. 현재 문서를 다시 확인하세요.",
                },
            )
        if document_access != "AVAILABLE" and (
            related_document_id is not None or related_document_version_id is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SOURCE_DOCUMENT_NOT_PUBLISHED",
                    "message": "연결 문서가 더 이상 공개 상태가 아닙니다. 입력은 단말에 보존됩니다.",
                },
            )
        related_document_id = expected_document_id
        related_document_version_id = expected_version_id
    elif source_type == "WORK_SEQUENCE_HISTORY":
        visible = session.scalar(
            select(WorkSequenceChangeHistory.id).where(
                WorkSequenceChangeHistory.change_id == source_id
            )
        ) is not None
    elif source_type == "WORK_RECORD":
        visible = session.scalar(
            select(WorkRecord.id).where(
                WorkRecord.work_record_id == source_id,
                WorkRecord.status != "ARCHIVED",
            )
        ) is not None
    elif source_type == "REPORT":
        visible = session.scalar(
            select(Report.id).where(
                Report.report_id == source_id,
                Report.status == "APPROVED",
                Report.superseded_by_report_id.is_(None),
            )
        ) is not None
    elif source_type == "CHANNEL_MESSAGE":
        visible = session.scalar(
            select(ChannelMessage.id).where(
                ChannelMessage.message_id == source_id,
                ChannelMessage.channel_id == channel_id,
            )
        ) is not None
    if not visible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SOURCE_NOT_VISIBLE",
                "message": "원천을 찾을 수 없거나 현장 역할에 공개되지 않았습니다.",
            },
        )
    return related_document_id, related_document_version_id


def handover_matches_request(
    session: Session,
    handover: Handover,
    *,
    channel_id: str,
    title: str,
    body: str,
    source_type: str | None,
    source_id: str | None,
    source_version_id: str | None,
    source_revision: int | None,
    related_document_id: str | None,
    related_document_version_id: str | None,
    server_scope: str | None,
    intent_hash_sha256: str | None,
    recipient_ids: list[str],
    entry_source: str,
    device_id: str | None,
    created_by: str,
) -> bool:
    saved_recipients = session.scalars(
        select(HandoverReceipt.recipient_id).where(
            HandoverReceipt.handover_id == handover.handover_id
        )
    ).all()
    return (
        handover.channel_id == channel_id
        and handover.title == title
        and handover.body == body
        and handover.source_type == source_type
        and handover.source_id == source_id
        and handover.source_version_id == source_version_id
        and handover.source_revision == source_revision
        and handover.related_document_id == related_document_id
        and handover.related_document_version_id == related_document_version_id
        and handover.server_scope == server_scope
        and handover.intent_hash_sha256 == intent_hash_sha256
        and sorted(saved_recipients) == sorted(recipient_ids)
        and handover.entry_source == entry_source
        and handover.device_id == device_id
        and handover.created_by == created_by
    )
