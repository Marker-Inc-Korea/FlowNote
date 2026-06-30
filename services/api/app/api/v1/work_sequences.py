from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DocumentWriteUser, get_current_user
from app.db.models import (
    ActivityHistory,
    Document,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
    WorkSequenceNotificationCandidate,
)
from app.db.session import get_db_session

router = APIRouter(
    prefix="/work-sequence-boards",
    tags=["work-sequence-boards"],
    dependencies=[Depends(get_current_user)],
)

BOARD_STATUSES = {"ACTIVE", "ARCHIVED"}
ITEM_STATUSES = {"WAITING", "IN_PROGRESS", "HOLD", "COMPLETED"}


class WorkSequenceBoardCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1)
    description: str | None = None
    line_code: str | None = Field(default=None, alias="lineCode")
    board_date: date | None = Field(default=None, alias="boardDate")
    created_by: str | None = Field(default=None, alias="createdBy")


class WorkSequenceItemCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1)
    description: str | None = None
    work_order_no: str | None = Field(default=None, alias="workOrderNo")
    document_id: str | None = Field(default=None, alias="documentId")
    assigned_to: str | None = Field(default=None, alias="assignedTo")
    created_by: str | None = Field(default=None, alias="createdBy")


class WorkSequenceItemStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1)
    actor_id: str | None = Field(default=None, alias="actorId")
    change_reason: str | None = Field(default=None, alias="changeReason")
    hold_reason: str | None = Field(default=None, alias="holdReason")


class WorkSequenceReorderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item_ids: list[str] = Field(alias="itemIds", min_length=1)
    actor_id: str | None = Field(default=None, alias="actorId")
    change_reason: str | None = Field(default=None, alias="changeReason")


class WorkSequenceItemResponse(BaseModel):
    item_id: str
    board_id: str
    title: str
    description: str | None
    work_order_no: str | None
    document_id: str | None
    status: str
    hold_reason: str | None
    sort_order: int
    assigned_to: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class WorkSequenceBoardResponse(BaseModel):
    board_id: str
    title: str
    description: str | None
    line_code: str | None
    board_date: date | None
    status: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    items: list[WorkSequenceItemResponse] = Field(default_factory=list)


class WorkSequenceBoardListItem(BaseModel):
    board_id: str
    title: str
    line_code: str | None
    board_date: date | None
    status: str
    item_count: int
    updated_at: datetime


class WorkSequenceHistoryResponse(BaseModel):
    change_id: str
    board_id: str
    item_id: str | None
    change_type: str
    actor_id: str | None
    before_value: str | None
    after_value: str | None
    change_reason: str | None
    created_at: datetime


class WorkSequenceNotificationCandidateResponse(BaseModel):
    candidate_id: str
    board_id: str
    item_id: str | None
    event_type: str
    actor_id: str | None
    recipient_hint: str | None
    message: str
    status: str
    created_at: datetime


class WorkSequenceNotificationCandidateStatusRequest(BaseModel):
    status: str = Field(min_length=1)


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_choice(value: str, allowed: set[str], field_name: str) -> str:
    cleaned = value.strip().upper()
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return cleaned


def _validate_user_id(session: Session, user_id: str | None, field_name: str) -> str | None:
    if user_id is None:
        return None
    exists = session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} must reference an existing user_id.",
        )
    return user_id


def _validate_document_id(session: Session, document_id: str | None) -> str | None:
    if document_id is None:
        return None
    exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="documentId is unknown.")
    return document_id


def _item_response(item: WorkSequenceItem) -> WorkSequenceItemResponse:
    return WorkSequenceItemResponse(
        item_id=item.item_id,
        board_id=item.board_id,
        title=item.title,
        description=item.description,
        work_order_no=item.work_order_no,
        document_id=item.document_id,
        status=item.status,
        hold_reason=item.hold_reason,
        sort_order=item.sort_order,
        assigned_to=item.assigned_to,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _board_response(session: Session, board: WorkSequenceBoard) -> WorkSequenceBoardResponse:
    items = session.scalars(
        select(WorkSequenceItem)
        .where(WorkSequenceItem.board_id == board.board_id)
        .order_by(WorkSequenceItem.sort_order, WorkSequenceItem.id)
    ).all()
    return WorkSequenceBoardResponse(
        board_id=board.board_id,
        title=board.title,
        description=board.description,
        line_code=board.line_code,
        board_date=board.board_date,
        status=board.status,
        created_by=board.created_by,
        created_at=board.created_at,
        updated_at=board.updated_at,
        items=[_item_response(item) for item in items],
    )


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
) -> None:
    session.add(
        WorkSequenceChangeHistory(
            change_id=_new_public_id("wseqhist"),
            board_id=board_id,
            item_id=item_id,
            change_type=change_type,
            actor_id=actor_id,
            before_value=before_value,
            after_value=after_value,
            change_reason=_clean_optional(change_reason),
        )
    )


def _record_notification_candidate(
    session: Session,
    *,
    board_id: str,
    item_id: str | None,
    event_type: str,
    actor_id: str | None,
    message: str,
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


@router.post("", response_model=WorkSequenceBoardResponse, status_code=status.HTTP_201_CREATED)
def create_board(
    request: WorkSequenceBoardCreateRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceBoardResponse:
    created_by = _validate_user_id(
        session,
        _clean_optional(request.created_by) or current_user.user_id,
        "createdBy",
    )
    board = WorkSequenceBoard(
        board_id=_new_public_id("wseqboard"),
        title=request.title.strip(),
        description=_clean_optional(request.description),
        line_code=_clean_optional(request.line_code),
        board_date=request.board_date,
        status="ACTIVE",
        created_by=created_by,
    )
    session.add(board)
    session.flush()
    _record_history(
        session,
        board_id=board.board_id,
        item_id=None,
        change_type="BOARD_CREATED",
        actor_id=created_by,
        before_value=None,
        after_value=board.title,
        change_reason="Initial board creation.",
    )
    session.commit()
    session.refresh(board)
    return _board_response(session, board)


@router.get("", response_model=list[WorkSequenceBoardListItem])
def list_boards(
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    line_code: Annotated[str | None, Query(alias="lineCode")] = None,
    board_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[WorkSequenceBoardListItem]:
    statement = (
        select(WorkSequenceBoard, func.count(WorkSequenceItem.id))
        .outerjoin(WorkSequenceItem, WorkSequenceItem.board_id == WorkSequenceBoard.board_id)
        .group_by(WorkSequenceBoard.id)
        .order_by(desc(WorkSequenceBoard.updated_at), desc(WorkSequenceBoard.id))
    )
    if line_code is not None:
        statement = statement.where(WorkSequenceBoard.line_code == line_code)
    if board_status is not None:
        statement = statement.where(
            WorkSequenceBoard.status == _validate_choice(board_status, BOARD_STATUSES, "status")
        )

    rows = session.execute(statement).all()
    return [
        WorkSequenceBoardListItem(
            board_id=board.board_id,
            title=board.title,
            line_code=board.line_code,
            board_date=board.board_date,
            status=board.status,
            item_count=item_count,
            updated_at=board.updated_at,
        )
        for board, item_count in rows
    ]


@router.get("/{board_id}", response_model=WorkSequenceBoardResponse)
def get_board(
    board_id: str,
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceBoardResponse:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")
    return _board_response(session, board)


@router.post("/{board_id}/items", response_model=WorkSequenceBoardResponse, status_code=status.HTTP_201_CREATED)
def add_item(
    board_id: str,
    request: WorkSequenceItemCreateRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceBoardResponse:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")

    created_by = _validate_user_id(
        session,
        _clean_optional(request.created_by) or current_user.user_id,
        "createdBy",
    )
    document_id = _validate_document_id(session, _clean_optional(request.document_id))
    next_order = (
        session.scalar(select(func.max(WorkSequenceItem.sort_order)).where(WorkSequenceItem.board_id == board_id))
        or 0
    ) + 1
    item = WorkSequenceItem(
        item_id=_new_public_id("wseqitem"),
        board_id=board_id,
        title=request.title.strip(),
        description=_clean_optional(request.description),
        work_order_no=_clean_optional(request.work_order_no),
        document_id=document_id,
        status="WAITING",
        sort_order=next_order,
        assigned_to=_clean_optional(request.assigned_to),
        created_by=created_by,
    )
    session.add(item)
    session.flush()
    _record_history(
        session,
        board_id=board_id,
        item_id=item.item_id,
        change_type="ITEM_ADDED",
        actor_id=created_by,
        before_value=None,
        after_value=item.title,
        change_reason="Initial item creation.",
    )
    board.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(board)
    return _board_response(session, board)


@router.put("/{board_id}/items/order", response_model=WorkSequenceBoardResponse)
def reorder_items(
    board_id: str,
    request: WorkSequenceReorderRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceBoardResponse:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")

    items = session.scalars(
        select(WorkSequenceItem)
        .where(WorkSequenceItem.board_id == board_id)
        .order_by(WorkSequenceItem.sort_order, WorkSequenceItem.id)
    ).all()
    existing_ids = [item.item_id for item in items]
    if sorted(existing_ids) != sorted(request.item_ids) or len(set(request.item_ids)) != len(request.item_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="itemIds must contain every item on the board exactly once.",
        )

    actor_id = _validate_user_id(session, _clean_optional(request.actor_id) or current_user.user_id, "actorId")
    before = existing_ids
    item_by_id = {item.item_id: item for item in items}
    for index, item in enumerate(items, start=1):
        item.sort_order = -index
    session.flush()
    for index, item_id in enumerate(request.item_ids, start=1):
        item_by_id[item_id].sort_order = index

    _record_history(
        session,
        board_id=board_id,
        item_id=None,
        change_type="ITEM_REORDERED",
        actor_id=actor_id,
        before_value=json.dumps(before, ensure_ascii=False),
        after_value=json.dumps(request.item_ids, ensure_ascii=False),
        change_reason=request.change_reason,
    )
    _record_notification_candidate(
        session,
        board_id=board_id,
        item_id=None,
        event_type="work_sequence.reordered",
        actor_id=actor_id,
        recipient_hint=board.line_code,
        message=f"Work sequence board order changed: {board.title}.",
    )
    board.updated_at = datetime.now(timezone.utc)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Work sequence order could not be saved.",
        ) from exc
    session.refresh(board)
    return _board_response(session, board)


@router.patch("/{board_id}/items/{item_id}/status", response_model=WorkSequenceBoardResponse)
def update_item_status(
    board_id: str,
    item_id: str,
    request: WorkSequenceItemStatusUpdateRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceBoardResponse:
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")
    item = session.scalar(
        select(WorkSequenceItem).where(
            WorkSequenceItem.board_id == board_id,
            WorkSequenceItem.item_id == item_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence item not found.")

    target_status = _validate_choice(request.status, ITEM_STATUSES, "status")
    actor_id = _validate_user_id(session, _clean_optional(request.actor_id) or current_user.user_id, "actorId")
    before = item.status
    target_hold_reason = _clean_optional(request.hold_reason or request.change_reason) if target_status == "HOLD" else None
    hold_reason_before = item.hold_reason
    status_changed = before != target_status
    hold_reason_changed = _clean_optional(hold_reason_before) != target_hold_reason
    if status_changed or hold_reason_changed:
        item.status = target_status
        item.hold_reason = target_hold_reason
        if status_changed:
            _record_history(
                session,
                board_id=board_id,
                item_id=item_id,
                change_type="STATUS_CHANGED",
                actor_id=actor_id,
                before_value=before,
                after_value=target_status,
                change_reason=request.change_reason,
            )
            _record_notification_candidate(
                session,
                board_id=board_id,
                item_id=item_id,
                event_type="work_sequence.status_changed",
                actor_id=actor_id,
                recipient_hint=item.assigned_to or board.line_code,
                message=f"Work sequence item status changed: {item.title} {before} -> {target_status}.",
            )
        if hold_reason_changed:
            _record_history(
                session,
                board_id=board_id,
                item_id=item_id,
                change_type="HOLD_REASON_CHANGED",
                actor_id=actor_id,
                before_value=hold_reason_before,
                after_value=target_hold_reason,
                change_reason=request.change_reason,
            )
            _record_notification_candidate(
                session,
                board_id=board_id,
                item_id=item_id,
                event_type="work_sequence.hold_reason_changed",
                actor_id=actor_id,
                recipient_hint=item.assigned_to or board.line_code,
                message=f"Work sequence hold reason changed: {item.title}.",
            )
        board.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(board)
    return _board_response(session, board)


@router.get("/{board_id}/history", response_model=list[WorkSequenceHistoryResponse])
def list_history(
    board_id: str,
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[WorkSequenceHistoryResponse]:
    board_exists = session.scalar(select(WorkSequenceBoard.id).where(WorkSequenceBoard.board_id == board_id))
    if board_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")

    rows = session.scalars(
        select(WorkSequenceChangeHistory)
        .where(WorkSequenceChangeHistory.board_id == board_id)
        .order_by(desc(WorkSequenceChangeHistory.created_at), desc(WorkSequenceChangeHistory.id))
        .limit(limit)
    ).all()
    return [
        WorkSequenceHistoryResponse(
            change_id=row.change_id,
            board_id=row.board_id,
            item_id=row.item_id,
            change_type=row.change_type,
            actor_id=row.actor_id,
            before_value=row.before_value,
            after_value=row.after_value,
            change_reason=row.change_reason,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get(
    "/{board_id}/notification-candidates",
    response_model=list[WorkSequenceNotificationCandidateResponse],
)
def list_notification_candidates(
    board_id: str,
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    candidate_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[WorkSequenceNotificationCandidateResponse]:
    board_exists = session.scalar(select(WorkSequenceBoard.id).where(WorkSequenceBoard.board_id == board_id))
    if board_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work sequence board not found.")

    statement = (
        select(WorkSequenceNotificationCandidate)
        .where(WorkSequenceNotificationCandidate.board_id == board_id)
        .order_by(desc(WorkSequenceNotificationCandidate.created_at), desc(WorkSequenceNotificationCandidate.id))
        .limit(limit)
    )
    if candidate_status is not None:
        statement = statement.where(
            WorkSequenceNotificationCandidate.status
            == _validate_choice(candidate_status, {"CANDIDATE", "SENT", "DISMISSED"}, "status")
        )
    rows = session.scalars(statement).all()
    return [
        WorkSequenceNotificationCandidateResponse(
            candidate_id=row.candidate_id,
            board_id=row.board_id,
            item_id=row.item_id,
            event_type=row.event_type,
            actor_id=row.actor_id,
            recipient_hint=row.recipient_hint,
            message=row.message,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.patch(
    "/{board_id}/notification-candidates/{candidate_id}",
    response_model=WorkSequenceNotificationCandidateResponse,
)
def update_notification_candidate_status(
    board_id: str,
    candidate_id: str,
    request: WorkSequenceNotificationCandidateStatusRequest,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkSequenceNotificationCandidateResponse:
    candidate = session.scalar(
        select(WorkSequenceNotificationCandidate).where(
            WorkSequenceNotificationCandidate.board_id == board_id,
            WorkSequenceNotificationCandidate.candidate_id == candidate_id,
        )
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work sequence notification candidate not found.",
        )

    target_status = _validate_choice(request.status, {"CANDIDATE", "SENT", "DISMISSED"}, "status")
    before = candidate.status
    if before != target_status:
        candidate.status = target_status
        session.add(
            ActivityHistory(
                history_id=_new_public_id("hist"),
                event_type="work_sequence.notification_candidate_status_changed",
                actor_id=current_user.user_id,
                target_type="work_sequence_notification_candidate",
                target_id=candidate.candidate_id,
                target_title=None,
                message=f"Work sequence notification candidate status changed: {before} -> {target_status}.",
                before_value=before,
                after_value=target_status,
            )
        )
        session.commit()
        session.refresh(candidate)

    return WorkSequenceNotificationCandidateResponse(
        candidate_id=candidate.candidate_id,
        board_id=candidate.board_id,
        item_id=candidate.item_id,
        event_type=candidate.event_type,
        actor_id=candidate.actor_id,
        recipient_hint=candidate.recipient_hint,
        message=candidate.message,
        status=candidate.status,
        created_at=candidate.created_at,
    )
