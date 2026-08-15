from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.document_support import (
    claim_revision,
    clean_idempotency_key,
    conflict as document_conflict,
)
from app.core.auth import (
    DOCUMENT_GOVERNANCE_ROLES,
    DocumentReviewUser,
    DocumentWriteUser,
    AuthenticatedUser,
)
from app.core.config import Settings, get_settings
from app.db.models import (
    ActivityHistory,
    AndroidDocumentViewGrant,
    ControlledCopyGrant,
    ChannelMessage,
    Document,
    DocumentApproval,
    DocumentApprovalEvent,
    DocumentApprovalMutationReceipt,
    DocumentVersion,
    FileObject,
    NotificationChannel,
    UserAccount,
)
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    MutationTrace,
    canonical_hash,
    check_common_mutation_replay,
    mutation_trace,
    record_common_mutation_failure,
    record_common_mutation_result,
    sanitize_audit_text,
)

router = APIRouter(
    prefix="/document-approvals",
    tags=["document-approvals"],
)


class ApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    document_id: str = Field(alias="documentId", min_length=1)
    version_id: str = Field(alias="versionId", min_length=1)
    base_document_revision: int = Field(alias="baseDocumentRevision", ge=1)
    source_file_hash_sha256: str = Field(alias="sourceFileHashSha256", min_length=64, max_length=64)
    reviewer_user_id: str | None = Field(default=None, alias="reviewerUserId")
    reviewer_role: str | None = Field(default=None, alias="reviewerRole")
    reason: str = Field(min_length=3)
    due_at: datetime | None = Field(default=None, alias="dueAt")
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_reviewer(self) -> "ApprovalRequestCreate":
        if bool(self.reviewer_user_id) == bool(self.reviewer_role):
            raise ValueError("reviewerUserId 또는 reviewerRole 중 하나만 지정해야 합니다.")
        return self


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)


class ApprovalCancelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    reason: str = Field(min_length=3)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)


class ApprovalEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor_id: str
    actor_role: str
    reason: str | None
    document_revision: int
    source_file_hash_sha256: str
    created_at: datetime


class ApprovalResponse(BaseModel):
    approval_id: str
    document_id: str
    version_id: str
    base_document_revision: int
    source_file_hash_sha256: str
    status: str
    requester_id: str
    reviewer_user_id: str | None
    reviewer_role: str | None
    request_reason: str
    due_at: datetime | None
    decision_reason: str | None
    decided_by: str | None
    decided_at: datetime | None
    cancelled_by: str | None
    cancelled_at: datetime | None
    published_by: str | None
    published_at: datetime | None
    stale_reason: str | None
    created_at: datetime
    updated_at: datetime
    events: list[ApprovalEventResponse] = Field(default_factory=list)


def _approval_response(session: Session, approval: DocumentApproval) -> ApprovalResponse:
    events = session.scalars(
        select(DocumentApprovalEvent)
        .where(DocumentApprovalEvent.approval_id == approval.approval_id)
        .order_by(DocumentApprovalEvent.id)
    ).all()
    return ApprovalResponse(
        **{
            column: getattr(approval, column)
            for column in ApprovalResponse.model_fields
            if column != "events"
        },
        events=[
            ApprovalEventResponse(
                **{
                    column: getattr(event, column)
                    for column in ApprovalEventResponse.model_fields
                }
            )
            for event in events
        ],
    )


def _intent(mutation_type: str, target_id: str, payload: dict[str, object]) -> str:
    return canonical_hash(
        {"mutationType": mutation_type, "targetId": target_id, "payload": payload}
    )


def _replay(
    session: Session,
    *,
    mutation_key: str,
    mutation_type: str,
    target_id: str,
    intent_hash: str,
) -> ApprovalResponse | None:
    common = check_common_mutation_replay(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type=f"document.approval_{mutation_type.lower()}",
        target_type="document_approval",
        target_id=target_id,
    )
    receipt = session.scalar(
        select(DocumentApprovalMutationReceipt).where(
            DocumentApprovalMutationReceipt.mutation_key == mutation_key
        )
    )
    if receipt is None:
        if common is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMMON_RECEIPT_LINK_BROKEN", "message": "승인 receipt 연결을 확인할 수 없습니다."},
            )
        return None
    if (
        receipt.intent_hash_sha256 != intent_hash
        or receipt.mutation_type != mutation_type
        or receipt.approval_id != target_id
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "같은 mutation key를 다른 승인 결정에 사용할 수 없습니다."},
        )
    return ApprovalResponse.model_validate_json(receipt.response_json)


def _event(
    session: Session,
    approval: DocumentApproval,
    event_type: str,
    actor: AuthenticatedUser,
    reason: str | None,
    document_revision: int,
) -> DocumentApprovalEvent:
    row = DocumentApprovalEvent(
        event_id=f"apevt_{uuid4().hex}",
        approval_id=approval.approval_id,
        document_id=approval.document_id,
        version_id=approval.version_id,
        event_type=event_type,
        actor_id=actor.user_id,
        actor_role=actor.role,
        reason=sanitize_audit_text(reason),
        document_revision=document_revision,
        source_file_hash_sha256=approval.source_file_hash_sha256,
    )
    session.add(row)
    return row


def _activity(
    session: Session,
    approval: DocumentApproval,
    document: Document,
    actor_id: str,
    event_type: str,
    before: str | None,
    after: str,
    reason: str | None,
) -> None:
    session.add(
        ActivityHistory(
            history_id=f"hist_{uuid4().hex}",
            event_type=event_type,
            actor_id=actor_id,
            target_type="document_approval",
            target_id=approval.approval_id,
            target_title=document.title,
            message=f"문서 승인 상태: {before or '-'} → {after}",
            before_value=before,
            after_value=after,
            change_reason=sanitize_audit_text(reason),
        )
    )
    channel_ids = session.scalars(
        select(NotificationChannel.channel_id).where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == "DOCUMENT",
            NotificationChannel.source_id == document.document_id,
        )
    ).all()
    for channel_id in channel_ids:
        session.add(
            ChannelMessage(
                message_id=f"msg_{uuid4().hex}",
                channel_id=channel_id,
                message_type="DOCUMENT_EVENT",
                source_type="DOCUMENT",
                source_id=document.document_id,
                source_version_id=approval.version_id,
                title=f"문서 승인 상태: {after}",
                body=sanitize_audit_text(reason),
                created_by=actor_id,
            )
        )


def _store_success(
    session: Session,
    *,
    approval: DocumentApproval,
    response: ApprovalResponse,
    mutation_key: str,
    mutation_type: str,
    intent_hash: str,
    trace: MutationTrace,
    reason: str | None,
    event: DocumentApprovalEvent,
    document_revision: int,
) -> None:
    receipt = DocumentApprovalMutationReceipt(
        mutation_key=mutation_key,
        intent_hash_sha256=intent_hash,
        mutation_type=mutation_type,
        approval_id=approval.approval_id,
        document_id=approval.document_id,
        response_json=response.model_dump_json(),
    )
    session.add(receipt)
    session.flush()
    record_common_mutation_result(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type=f"document.approval_{mutation_type.lower()}",
        trace=trace,
        target_type="document_approval",
        target_id=approval.approval_id,
        target_version_id=approval.version_id,
        target_revision=document_revision,
        reason=reason,
        before_hash=None,
        after_hash=canonical_hash(response.model_dump(mode="json")),
        result="SUCCESS",
        result_code="APPLIED",
        http_status=200,
        response_detail={
            "code": "APPLIED",
            "targetId": approval.approval_id,
            "targetVersionId": approval.version_id,
            "targetRevision": document_revision,
        },
        domain_receipt_type="document_approval_mutation_receipts",
        domain_receipt_id=str(receipt.id),
        domain_audit_type="document_approval_events",
        domain_audit_id=event.event_id,
        approval_status={
            "REQUESTED": "PENDING",
            "APPROVED": "APPROVED",
            "PUBLISHED": "APPROVED",
            "REJECTED": "REJECTED",
            "CANCELLED": "REJECTED",
            "STALE": "REJECTED",
        }[approval.status],
        approved_by=approval.decided_by,
        approval_reference=approval.approval_id,
    )


def _require_approval(session: Session, approval_id: str) -> DocumentApproval:
    approval = session.scalar(
        select(DocumentApproval).where(DocumentApproval.approval_id == approval_id)
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다.")
    return approval


def _require_reviewer(approval: DocumentApproval, actor: AuthenticatedUser) -> None:
    assigned = (
        approval.reviewer_user_id == actor.user_id
        if approval.reviewer_user_id
        else approval.reviewer_role == actor.role
    )
    if not assigned:
        raise HTTPException(
            status_code=403,
            detail={"code": "REVIEWER_SCOPE_DENIED", "message": "지정된 검토자 또는 역할만 결정할 수 있습니다."},
        )


@router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
def request_approval(
    request: Request,
    payload: ApprovalRequestCreate,
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ApprovalResponse:
    mutation_key = clean_idempotency_key(payload.mutation_key) or payload.mutation_key
    approval_id = f"approval_{canonical_hash({'mutationKey': mutation_key})[:32]}"
    intent_hash = _intent("REQUEST", approval_id, payload.model_dump(mode="json", by_alias=True))
    trace = mutation_trace(current_user, request)
    reason = sanitize_audit_text(payload.reason)
    try:
        replay = _replay(
            session,
            mutation_key=mutation_key,
            mutation_type="REQUEST",
            target_id=approval_id,
            intent_hash=intent_hash,
        )
        if replay is not None:
            return replay
        document = session.scalar(
            select(Document).where(
                Document.document_id == payload.document_id,
                Document.deleted_at.is_(None),
            )
        )
        version = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == payload.document_id,
                DocumentVersion.version_id == payload.version_id,
            )
        )
        if document is None or version is None:
            raise HTTPException(status_code=404, detail="문서 또는 버전을 찾을 수 없습니다.")
        file_object = session.get(FileObject, version.file_object_id)
        if file_object is None or file_object.hash_sha256 != payload.source_file_hash_sha256.lower():
            raise HTTPException(
                status_code=409,
                detail={"code": "APPROVAL_SOURCE_HASH_MISMATCH", "message": "요청한 파일 hash가 서버 버전과 다릅니다."},
            )
        if version.version_id != document.latest_version_id:
            raise HTTPException(
                status_code=409,
                detail={"code": "APPROVAL_VERSION_NOT_LATEST", "message": "현재 최신 버전만 검토 요청할 수 있습니다."},
            )
        reviewer = None
        if payload.reviewer_user_id:
            reviewer = session.scalar(
                select(UserAccount).where(UserAccount.user_id == payload.reviewer_user_id)
            )
            if reviewer is None or not reviewer.is_active or reviewer.status != "ACTIVE":
                raise HTTPException(status_code=422, detail="활성 상태인 검토자를 지정해야 합니다.")
            if reviewer.role not in DOCUMENT_GOVERNANCE_ROLES:
                raise HTTPException(status_code=422, detail="지정한 계정에는 문서 검토 결정 권한이 없습니다.")
        reviewer_role = payload.reviewer_role.strip() if payload.reviewer_role else None
        if reviewer_role and reviewer_role not in DOCUMENT_GOVERNANCE_ROLES:
            raise HTTPException(status_code=422, detail="검토 역할에는 문서 검토 결정 권한이 필요합니다.")
        new_revision = claim_revision(session, document, payload.base_document_revision)
        document.status = "IN_REVIEW"
        version.version_status = "IN_REVIEW"
        approval = DocumentApproval(
            approval_id=approval_id,
            document_id=document.document_id,
            version_id=version.version_id,
            base_document_revision=new_revision,
            source_file_hash_sha256=file_object.hash_sha256,
            status="REQUESTED",
            requester_id=current_user.user_id,
            reviewer_user_id=reviewer.user_id if reviewer else None,
            reviewer_role=reviewer_role,
            request_reason=reason or "검토 요청",
            due_at=payload.due_at,
        )
        session.add(approval)
        event = _event(session, approval, "REQUESTED", current_user, reason, new_revision)
        _activity(session, approval, document, current_user.user_id, "document.approval_requested", None, "REQUESTED", reason)
        session.flush()
        response = _approval_response(session, approval)
        _store_success(
            session,
            approval=approval,
            response=response,
            mutation_key=mutation_key,
            mutation_type="REQUEST",
            intent_hash=intent_hash,
            trace=trace,
            reason=reason,
            event=event,
            document_revision=new_revision,
        )
        session.commit()
        return response
    except IntegrityError as error:
        session.rollback()
        concurrent_replay = _replay(
            session,
            mutation_key=mutation_key,
            mutation_type="REQUEST",
            target_id=approval_id,
            intent_hash=intent_hash,
        )
        if concurrent_replay is not None:
            return concurrent_replay
        conflict = HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_REQUEST_CONFLICT",
                "message": "같은 검토 요청이 먼저 반영되었거나 승인 저장 경합이 발생했습니다.",
            },
        )
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="document.approval_request",
            trace=trace,
            target_type="document_approval",
            target_id=approval_id,
            target_version_id=payload.version_id,
            target_revision=payload.base_document_revision,
            reason=reason,
            error=conflict,
        )
        raise conflict from error
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="document.approval_request",
            trace=trace,
            target_type="document_approval",
            target_id=approval_id,
            target_version_id=payload.version_id,
            target_revision=payload.base_document_revision,
            reason=reason,
            error=error,
        )
        raise


@router.post("/{approval_id}/decision", response_model=ApprovalResponse)
def decide_approval(
    request: Request,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    current_user: DocumentReviewUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ApprovalResponse:
    mutation_key = clean_idempotency_key(payload.mutation_key) or payload.mutation_key
    intent_hash = _intent("DECIDE", approval_id, payload.model_dump(mode="json", by_alias=True))
    replay = _replay(
        session,
        mutation_key=mutation_key,
        mutation_type="DECIDE",
        target_id=approval_id,
        intent_hash=intent_hash,
    )
    if replay is not None:
        return replay
    approval = _require_approval(session, approval_id)
    _require_reviewer(approval, current_user)
    reviewer_separation = app_settings.document_approval_requester_reviewer_separation
    if approval.requester_id == current_user.user_id and reviewer_separation is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_REVIEWER_SEPARATION_POLICY_REQUIRED",
                "message": "요청자와 검토자의 분리 정책을 현장 설정에서 먼저 정해야 합니다.",
            },
        )
    if approval.requester_id == current_user.user_id and reviewer_separation:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "APPROVAL_REVIEWER_SEPARATION_REQUIRED",
                "message": "현장 정책에 따라 요청자와 다른 검토자가 결정해야 합니다.",
            },
        )
    if approval.status != "REQUESTED":
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_NOT_PENDING", "message": "대기 중인 요청만 결정할 수 있습니다."})
    document = session.scalar(select(Document).where(Document.document_id == approval.document_id))
    version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == approval.version_id))
    if document is None or version is None:
        raise HTTPException(status_code=404, detail="승인 대상 문서를 찾을 수 없습니다.")
    if document.revision != approval.base_document_revision or document.latest_version_id != approval.version_id:
        mark_approval_stale(session, approval, document, current_user, "승인 대상 문서 revision 또는 최신 버전이 바뀌었습니다.")
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_STALE", "message": "승인 대상이 변경되어 새 검토 요청이 필요합니다."})
    before = approval.status
    approved = payload.decision == "APPROVE"
    target_status = "APPROVED" if approved else "REJECTED"
    now = datetime.now(timezone.utc)
    decision_reason = sanitize_audit_text(payload.reason)
    claimed = session.execute(
        update(DocumentApproval)
        .where(
            DocumentApproval.id == approval.id,
            DocumentApproval.status == "REQUESTED",
        )
        .values(
            status=target_status,
            decision_reason=decision_reason,
            decided_by=current_user.user_id,
            decided_at=now,
            updated_at=now,
        )
    )
    if claimed.rowcount != 1:
        session.rollback()
        concurrent_replay = _replay(
            session,
            mutation_key=mutation_key,
            mutation_type="DECIDE",
            target_id=approval_id,
            intent_hash=intent_hash,
        )
        if concurrent_replay is not None:
            return concurrent_replay
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_DECISION_CONFLICT", "message": "다른 검토 결정이 먼저 반영되었습니다."})
    approval.status = target_status
    approval.decision_reason = decision_reason
    approval.decided_by = current_user.user_id
    approval.decided_at = now
    if approved:
        version.version_status = "APPROVED"
    else:
        claim_revision(session, document, document.revision)
        document.status = "WORKING"
        version.version_status = "WORKING"
    event_type = "APPROVED" if approved else "REJECTED"
    event = _event(session, approval, event_type, current_user, payload.reason, document.revision)
    _activity(session, approval, document, current_user.user_id, f"document.approval_{event_type.lower()}", before, approval.status, payload.reason)
    session.flush()
    response = _approval_response(session, approval)
    _store_success(
        session,
        approval=approval,
        response=response,
        mutation_key=mutation_key,
        mutation_type="DECIDE",
        intent_hash=intent_hash,
        trace=mutation_trace(current_user, request),
        reason=payload.reason,
        event=event,
        document_revision=document.revision,
    )
    session.commit()
    return response


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
def cancel_approval(
    request: Request,
    approval_id: str,
    payload: ApprovalCancelRequest,
    current_user: DocumentReviewUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ApprovalResponse:
    mutation_key = clean_idempotency_key(payload.mutation_key) or payload.mutation_key
    intent_hash = _intent("CANCEL", approval_id, payload.model_dump(mode="json", by_alias=True))
    replay = _replay(session, mutation_key=mutation_key, mutation_type="CANCEL", target_id=approval_id, intent_hash=intent_hash)
    if replay is not None:
        return replay
    approval = _require_approval(session, approval_id)
    if approval.status not in {"REQUESTED", "APPROVED", "PUBLISHED"}:
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_NOT_CANCELLABLE", "message": "현재 상태의 승인은 취소할 수 없습니다."})
    document = session.scalar(select(Document).where(Document.document_id == approval.document_id))
    version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == approval.version_id))
    if document is None or version is None:
        raise HTTPException(status_code=404, detail="승인 대상 문서를 찾을 수 없습니다.")
    before = approval.status
    claim_revision(session, document, document.revision)
    claimed = session.execute(
        update(DocumentApproval)
        .where(
            DocumentApproval.id == approval.id,
            DocumentApproval.status.in_(["REQUESTED", "APPROVED", "PUBLISHED"]),
        )
        .values(
            status="CANCELLED",
            cancelled_by=current_user.user_id,
            cancelled_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if claimed.rowcount != 1:
        session.rollback()
        concurrent_replay = _replay(
            session,
            mutation_key=mutation_key,
            mutation_type="CANCEL",
            target_id=approval_id,
            intent_hash=intent_hash,
        )
        if concurrent_replay is not None:
            return concurrent_replay
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_CANCEL_CONFLICT", "message": "승인 상태가 먼저 변경되었습니다."})
    was_published = document.publication_approval_id == approval.approval_id
    approval.status = "CANCELLED"
    approval.cancelled_by = current_user.user_id
    approval.cancelled_at = datetime.now(timezone.utc)
    if was_published:
        document.status = "WORKING"
        document.published_version_id = None
        document.publication_approval_id = None
        document.publication_origin = "LEGACY_PUBLICATION"
        version.is_published = False
        version.published_at = None
        version.version_status = "WORKING"
        session.execute(
            update(AndroidDocumentViewGrant)
            .where(AndroidDocumentViewGrant.document_id == document.document_id, AndroidDocumentViewGrant.status == "ISSUED")
            .values(status="FAILED", failure_reason="문서 공개 승인이 취소되었습니다.")
        )
        session.execute(
            update(ControlledCopyGrant)
            .where(ControlledCopyGrant.document_id == document.document_id, ControlledCopyGrant.status == "ISSUED")
            .values(status="FAILED", failure_reason="문서 공개 승인이 취소되었습니다.")
        )
    elif version.version_status in {"APPROVED", "IN_REVIEW"}:
        document.status = "WORKING"
        version.version_status = "WORKING"
    event_type = "PUBLICATION_WITHDRAWN" if was_published else "CANCELLED"
    event = _event(session, approval, event_type, current_user, payload.reason, document.revision)
    _activity(session, approval, document, current_user.user_id, "document.approval_cancelled", before, "CANCELLED", payload.reason)
    session.flush()
    response = _approval_response(session, approval)
    _store_success(
        session,
        approval=approval,
        response=response,
        mutation_key=mutation_key,
        mutation_type="CANCEL",
        intent_hash=intent_hash,
        trace=mutation_trace(current_user, request),
        reason=payload.reason,
        event=event,
        document_revision=document.revision,
    )
    session.commit()
    return response


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
    document_id: Annotated[str | None, Query(alias="documentId")] = None,
    state: str | None = None,
    assigned_to_me: Annotated[bool, Query(alias="assignedToMe")] = False,
) -> list[ApprovalResponse]:
    query = select(DocumentApproval)
    if current_user.role not in DOCUMENT_GOVERNANCE_ROLES:
        query = query.where(DocumentApproval.requester_id == current_user.user_id)
    if document_id:
        query = query.where(DocumentApproval.document_id == document_id)
    if state:
        query = query.where(DocumentApproval.status == state.strip().upper())
    if assigned_to_me:
        query = query.where(
            (DocumentApproval.reviewer_user_id == current_user.user_id)
            | (
                DocumentApproval.reviewer_user_id.is_(None)
                & (DocumentApproval.reviewer_role == current_user.role)
            )
        )
    rows = session.scalars(query.order_by(desc(DocumentApproval.created_at))).all()
    return [_approval_response(session, row) for row in rows]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(
    approval_id: str,
    _current_user: DocumentWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ApprovalResponse:
    approval = _require_approval(session, approval_id)
    if (
        _current_user.role not in DOCUMENT_GOVERNANCE_ROLES
        and approval.requester_id != _current_user.user_id
    ):
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다.")
    return _approval_response(session, approval)


def mark_approval_stale(
    session: Session,
    approval: DocumentApproval,
    document: Document,
    actor: AuthenticatedUser,
    reason: str,
) -> None:
    if approval.status not in {"REQUESTED", "APPROVED"}:
        return
    before = approval.status
    approval.status = "STALE"
    approval.stale_reason = sanitize_audit_text(reason)
    _event(session, approval, "MARKED_STALE", actor, reason, document.revision)
    _activity(session, approval, document, actor.user_id, "document.approval_stale", before, "STALE", reason)


def validate_publication_approval(
    session: Session,
    *,
    settings: Settings,
    document: Document,
    version: DocumentVersion,
    file_hash: str,
    approval_id: str | None,
    actor: AuthenticatedUser,
) -> DocumentApproval | None:
    if not settings.document_approval_workflow_enforced:
        return None
    if not approval_id:
        raise document_conflict(
            "APPROVAL_REQUIRED",
            "승인된 검토 요청 ID가 있어야 공개할 수 있습니다.",
            document=document,
        )
    approval = _require_approval(session, approval_id)
    if approval.status == "STALE":
        raise document_conflict(
            "APPROVAL_STALE",
            "승인 대상이 변경되어 공개할 수 없습니다. 새 검토 요청이 필요합니다.",
            document=document,
            expected_revision=approval.base_document_revision,
        )
    if approval.status in {"REQUESTED", "REJECTED", "CANCELLED"}:
        raise document_conflict(
            "APPROVAL_NOT_APPROVED",
            "승인 완료된 정확한 버전만 공개할 수 있습니다.",
            document=document,
            expected_revision=approval.base_document_revision,
        )
    mismatch = (
        approval.document_id != document.document_id
        or approval.version_id != version.version_id
        or approval.base_document_revision != document.revision
        or approval.source_file_hash_sha256 != file_hash
        or document.latest_version_id != version.version_id
    )
    if mismatch:
        mark_approval_stale(session, approval, document, actor, "승인 뒤 version, revision 또는 file hash가 바뀌었습니다.")
        session.commit()
        raise document_conflict(
            "APPROVAL_STALE",
            "승인 대상이 변경되어 공개할 수 없습니다. 새 검토 요청이 필요합니다.",
            document=document,
            expected_revision=approval.base_document_revision,
        )
    already_published = (
        approval.status == "PUBLISHED"
        and document.publication_approval_id == approval.approval_id
        and document.published_version_id == version.version_id
        and version.version_status == "PUBLISHED"
    )
    if not already_published and (
        approval.status != "APPROVED" or version.version_status != "APPROVED"
    ):
        raise document_conflict(
            "APPROVAL_NOT_APPROVED",
            "승인 완료된 정확한 버전만 공개할 수 있습니다.",
            document=document,
            expected_revision=approval.base_document_revision,
        )
    separation = settings.document_approval_requester_publisher_separation
    if approval.requester_id == actor.user_id and separation is None:
        raise document_conflict(
            "APPROVAL_SEPARATION_POLICY_REQUIRED",
            "요청자와 공개자의 분리 정책을 현장 설정에서 먼저 정해야 합니다.",
            document=document,
            expected_revision=approval.base_document_revision,
        )
    if approval.requester_id == actor.user_id and separation:
        raise HTTPException(status_code=403, detail={"code": "APPROVAL_SEPARATION_REQUIRED", "message": "현장 정책에 따라 요청자와 다른 공개 권한자가 공개해야 합니다."})
    return approval


def record_publication(
    session: Session,
    *,
    approval: DocumentApproval | None,
    document: Document,
    actor: AuthenticatedUser,
    reason: str | None,
) -> None:
    if approval is None:
        document.publication_origin = "LEGACY_PUBLICATION"
        document.publication_approval_id = None
        return
    approval.status = "PUBLISHED"
    approval.published_by = actor.user_id
    approval.published_at = datetime.now(timezone.utc)
    document.publication_origin = "APPROVAL_WORKFLOW"
    document.publication_approval_id = approval.approval_id
    _event(session, approval, "PUBLISHED", actor, reason, document.revision)
