from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    ActivityHistory,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceMutationReceipt,
    WorkSequenceNotificationCandidate,
)
from app.services.mutation_receipts import (
    MutationTrace,
    canonical_hash,
    record_common_mutation_result,
)


class MutationResponse(Protocol):
    def model_dump_json(self) -> str: ...

    def model_dump(self, *, mode: str) -> dict: ...


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _record_history(
    session: Session,
    *,
    board_id: str,
    item_id: str | None,
    change_type: str,
    actor_id: str | None,
    before_value: str | None,
    after_value: str | None,
    change_reason: str | None,
    mutation_key: str,
    board_revision: int,
) -> str:
    change_id = _new_public_id("wseqhist")
    session.add(
        WorkSequenceChangeHistory(
            change_id=change_id,
            mutation_key=mutation_key,
            board_revision=board_revision,
            board_id=board_id,
            item_id=item_id,
            change_type=change_type,
            actor_id=actor_id,
            before_value=before_value,
            after_value=after_value,
            change_reason=_clean_optional(change_reason),
        )
    )
    return change_id


def _claim_board_revision(
    session: Session,
    board: WorkSequenceBoard,
    base_revision: int,
) -> int:
    next_revision = base_revision + 1
    result = session.execute(
        update(WorkSequenceBoard)
        .where(
            WorkSequenceBoard.board_id == board.board_id,
            WorkSequenceBoard.board_revision == base_revision,
        )
        .values(board_revision=next_revision, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        session.rollback()
        current_revision = session.scalar(
            select(WorkSequenceBoard.board_revision).where(
                WorkSequenceBoard.board_id == board.board_id
            )
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORK_SEQUENCE_STALE_REVISION",
                "message": "다른 사용자가 작업순서를 먼저 변경했습니다. 새로고침한 뒤 다시 시도하세요.",
                "expectedRevision": base_revision,
                "currentRevision": current_revision,
            },
        )
    board.board_revision = next_revision
    return next_revision


def _save_receipt(
    session: Session,
    *,
    mutation_key: str,
    mutation_type: str,
    intent_hash: str,
    board: WorkSequenceBoard,
    change_id: str,
    trace: MutationTrace,
    reason: str | None,
    before_hash: str | None,
    http_status: int,
    response_factory: Callable[[Session, WorkSequenceBoard], MutationResponse],
) -> MutationResponse:
    session.flush()
    response = response_factory(session, board)
    receipt = WorkSequenceMutationReceipt(
        mutation_key=mutation_key,
        mutation_type=mutation_type,
        intent_hash_sha256=intent_hash,
        board_id=board.board_id,
        board_revision=board.board_revision,
        change_id=change_id,
        response_json=response.model_dump_json(),
    )
    session.add(receipt)
    session.flush()
    record_common_mutation_result(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type=_mutation_event_type(mutation_type),
        trace=trace,
        target_type="work_sequence_board",
        target_id=board.board_id,
        target_version_id=None,
        target_revision=board.board_revision,
        reason=reason,
        before_hash=before_hash,
        after_hash=canonical_hash(response.model_dump(mode="json")),
        result="SUCCESS",
        result_code="APPLIED",
        http_status=http_status,
        response_detail={
            "code": "APPLIED",
            "targetId": board.board_id,
            "targetRevision": board.board_revision,
        },
        domain_receipt_type="work_sequence_mutation_receipts",
        domain_receipt_id=str(receipt.id),
        domain_audit_type="work_sequence_change_history",
        domain_audit_id=change_id,
    )
    session.commit()
    return response


def _mutation_event_type(mutation_type: str) -> str:
    return {
        "BOARD_CREATED": "work_sequence.board_created",
        "ITEM_ADDED": "work_sequence.item_added",
        "ITEM_REORDERED": "work_sequence.reordered",
        "ITEM_STATUS_CHANGED": "work_sequence.status_changed",
    }.get(mutation_type, f"work_sequence.{mutation_type.lower()}")


def _record_notification_candidate(
    session: Session,
    *,
    board_id: str,
    item_id: str | None,
    event_type: str,
    actor_id: str | None,
    message: str,
    board_revision: int,
    change_id: str,
    recipient_hint: str | None = None,
) -> None:
    session.add(
        WorkSequenceNotificationCandidate(
            candidate_id=_new_public_id("wseqnotify"),
            board_id=board_id,
            item_id=item_id,
            event_type=event_type,
            actor_id=actor_id,
            recipient_hint=recipient_hint,
            message=message,
            board_revision=board_revision,
            change_id=change_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    )
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="work_sequence.notification_candidate",
            actor_id=actor_id,
            target_type="work_sequence_item" if item_id else "work_sequence_board",
            target_id=item_id or board_id,
            target_title=None,
            message=message,
        )
    )
