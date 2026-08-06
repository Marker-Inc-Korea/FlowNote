from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.db.models import (
    AuditEventEnvelope,
    AuthSession,
    ChannelMessage,
    Document,
    DocumentApproval,
    DocumentVersion,
    FieldComment,
    Handover,
    HandoverReceipt,
    NotificationChannel,
    NotificationChannelMember,
    ReconciliationItem,
    Report,
    ReportSource,
    SyncMutationReceipt,
    TerminalDevice,
    WorkSequenceBoard,
    WorkSequenceItem,
    WorkSequenceNotificationCandidate,
)
from app.services.ai_readiness import database_scope, scope_readiness
from app.services.change_history_read_model import build_change_history_item
from app.services.operational_readiness_cursor import (
    decode_cursor,
    encode_cursor,
    filter_signature,
    invalid_cursor,
    parse_datetime,
)
from app.services.report_source_service import frozen_report_source_matches_current

READ_MODEL_VERSION = 1
SOURCE_AUTHORITY = "audit_event_envelopes + current_authority_tables"
CURSOR_TTL = timedelta(minutes=15)
RECENT_AUDIT_LIMIT = 200
GLOBAL_ROLES = {"admin", "system-admin"}
TERMINAL_STATUSES = {"SELECTED", "EXCLUDED", "ARCHIVED"}
SEVERITY_ORDER = {"BLOCKED": 2, "WARNING": 1, "NORMAL": 0}


@dataclass(frozen=True)
class ReadinessFilters:
    area_code: str | None = None
    severity: str | None = None
    blocker_code: str | None = None
    target_query: str | None = None


@dataclass
class AreaResult:
    area_code: str
    area_name: str
    assessed_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    failure: dict[str, Any] | None = None
    required_roles: list[str] = field(default_factory=list)


def list_operational_readiness(
    session: Session,
    current_user: AuthenticatedUser,
    filters: ReadinessFilters,
    *,
    limit: int,
    cursor: str | None,
    settings: Any,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cursor_value = decode_cursor(cursor, now, version=READ_MODEL_VERSION) if cursor else None
    signature = filter_signature(filters)
    if cursor_value is not None and cursor_value.get("filterSignature") != signature:
        raise invalid_cursor("필터와 페이지 커서가 일치하지 않습니다. 첫 페이지부터 다시 조회하세요.")
    anchor_id = (
        int(cursor_value["anchorId"])
        if cursor_value is not None
        else int(session.scalar(select(func.max(AuditEventEnvelope.id))) or 0)
    )
    as_of = (
        parse_datetime(cursor_value["asOf"])
        if cursor_value is not None
        else now
    )
    areas = [
        _run_area(builder, session, current_user, as_of, anchor_id)
        for builder in AREA_BUILDERS
    ]
    area_payloads = [_area_payload(area) for area in areas]
    all_items = [item for area in areas for item in area.items]
    all_items.sort(key=_sort_key)
    filtered_items = [item for item in all_items if _matches(item, filters)]
    start = 0
    if cursor_value is not None:
        last_item_id = cursor_value.get("lastItemId")
        index = next(
            (index for index, item in enumerate(filtered_items) if item["itemId"] == last_item_id),
            None,
        )
        if index is None:
            raise invalid_cursor(
                "snapshot의 마지막 항목이 현재 상태에서 달라졌습니다. 새로고침해 다시 조회하세요."
            )
        start = index + 1
    page = filtered_items[start : start + limit]
    next_cursor = None
    if start + limit < len(filtered_items) and page:
        next_cursor = encode_cursor(
            version=READ_MODEL_VERSION,
            anchor_id=anchor_id,
            as_of=as_of,
            last_item_id=page[-1]["itemId"],
            filter_signature_value=signature,
            expires_at=as_of + CURSOR_TTL,
        )

    latest_id = int(session.scalar(select(func.max(AuditEventEnvelope.id))) or 0)
    refresh_required = cursor_value is not None and latest_id > anchor_id
    return {
        "readModelVersion": READ_MODEL_VERSION,
        "sourceAuthority": SOURCE_AUTHORITY,
        "rebuildable": True,
        "snapshotAnchorId": anchor_id,
        "asOf": as_of,
        "cursorExpiresAt": as_of + CURSOR_TTL,
        "refreshRequired": refresh_required,
        "refreshReason": (
            "snapshot 이후 새 감사 event가 있습니다. 현재 페이지를 유지하거나 새로고침하세요."
            if refresh_required else None
        ),
        "counts": {
            **_counts(all_items),
            "normal": sum(area["normalCount"] for area in area_payloads),
        },
        "filteredTotalCount": len(filtered_items),
        "areas": area_payloads,
        "items": page,
        "nextCursor": next_cursor,
        "aiFieldReadiness": _ai_field_readiness(session, current_user, settings),
    }


def get_operational_readiness_detail(
    session: Session,
    current_user: AuthenticatedUser,
    item_id: str,
    *,
    settings: Any,
) -> dict[str, Any]:
    page = list_operational_readiness(
        session,
        current_user,
        ReadinessFilters(),
        limit=1_000_000,
        cursor=None,
        settings=settings,
    )
    item = next((value for value in page["items"] if value["itemId"] == item_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "조회할 수 있는 준비도 항목이 없습니다."},
        )
    return {
        "readModelVersion": READ_MODEL_VERSION,
        "sourceAuthority": SOURCE_AUTHORITY,
        "asOf": page["asOf"],
        "item": item,
    }


def _run_area(
    builder: Callable[[Session, AuthenticatedUser, datetime, int], AreaResult],
    session: Session,
    current_user: AuthenticatedUser,
    as_of: datetime,
    anchor_id: int,
) -> AreaResult:
    try:
        with session.begin_nested():
            return builder(session, current_user, as_of, anchor_id)
    except Exception:  # 영역별 실패는 다른 집계를 숨기지 않는다.
        area_code, area_name = AREA_METADATA[builder.__name__]
        return AreaResult(
            area_code,
            area_name,
            failure={
                "code": "AREA_AGGREGATION_FAILED",
                "message": "이 영역의 집계를 만들지 못했습니다. 원천 데이터는 변경하거나 삭제하지 않았습니다.",
                "responsibleRole": "시스템 관리자",
                "nextAction": "서버 로그와 원천 테이블 연결 상태를 확인한 뒤 다시 조회하세요.",
                "sourcePreserved": True,
            },
        )


def _documents(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("DOCUMENT_PUBLICATION", "문서 공개")
    versions = {
        row.version_id: row for row in session.scalars(
            select(DocumentVersion).where(DocumentVersion.created_at <= as_of)
        ).all()
    }
    approvals = {
        row.approval_id: row for row in session.scalars(
            select(DocumentApproval).where(DocumentApproval.created_at <= as_of)
        ).all()
    }
    for document in session.scalars(select(Document).where(
        Document.status != "DELETED", Document.created_at <= as_of
    )).all():
        if not _can_view_source(session, user, "DOCUMENT", document.document_id):
            continue
        result.assessed_count += 1
        issues: list[tuple[str, str]] = []
        published = versions.get(document.published_version_id or "")
        if document.status == "PUBLISHED" and document.published_version_id is None:
            issues.append(("DOCUMENT_PUBLISHED_VERSION_MISSING", "BLOCKED"))
        elif document.published_version_id is not None and (
            published is None
            or published.document_id != document.document_id
            or not published.is_published
            or published.version_status != "PUBLISHED"
        ):
            issues.append(("DOCUMENT_PUBLICATION_VERSION_MISMATCH", "BLOCKED"))
        if document.status != "PUBLISHED" and document.published_version_id is not None:
            issues.append(("DOCUMENT_PUBLICATION_STATUS_MISMATCH", "WARNING"))
        if document.publication_approval_id is not None:
            approval = approvals.get(document.publication_approval_id)
            if approval is None or approval.status != "PUBLISHED":
                issues.append(("DOCUMENT_PUBLICATION_APPROVAL_MISMATCH", "BLOCKED"))
        _append_item(
            result,
            issues,
            target_type="document",
            target_id=document.document_id,
            title=document.title,
            current_status=document.status,
            revision=document.revision,
            assignee=document.owner_id,
            owner="문서 관리자",
            next_action="공개본, 문서 상태와 승인 이력을 대조해 공개 작업함에서 정정하세요.",
            action_route="DOCUMENT_APPROVAL",
            oldest_at=document.updated_at,
        )
    return result


def _field_comments(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("FIELD_COMMENT", "FieldComment 검토")
    linked_ids = set(session.scalars(
        select(ReportSource.source_id).where(ReportSource.source_type == "FIELD_COMMENT")
    ).all())
    for comment in session.scalars(
        select(FieldComment).where(FieldComment.status.not_in(TERMINAL_STATUSES))
    ).all():
        if _utc(comment.created_at) > as_of:
            continue
        if not _can_view_source(session, user, "FIELD_COMMENT", comment.comment_id):
            continue
        result.assessed_count += 1
        issues: list[tuple[str, str]] = []
        if comment.review_due_at is not None and _utc(comment.review_due_at) < as_of:
            issues.append(("FIELD_COMMENT_REVIEW_OVERDUE", "BLOCKED"))
        if comment.comment_id not in linked_ids:
            issues.append(("FIELD_COMMENT_REPORT_UNLINKED", "WARNING"))
        if comment.conflict_flag:
            issues.append(("FIELD_COMMENT_SOURCE_CONFLICT", "BLOCKED"))
        if comment.assigned_to is None:
            issues.append(("FIELD_COMMENT_UNASSIGNED", "WARNING"))
        _append_item(
            result,
            issues,
            target_type="field_comment",
            target_id=comment.comment_id,
            title=f"FieldComment · {comment.category or comment.signal_level or comment.comment_type}",
            current_status=comment.status,
            revision=comment.review_revision,
            assignee=comment.assigned_to,
            owner="FieldComment 분석자·검토 책임자",
            next_action="담당자·기한·원천 연결을 확인하고 코멘트 검토 화면에서 판정하세요.",
            action_route="FIELD_COMMENT_REVIEW",
            oldest_at=comment.created_at,
        )
    return result


def _reports(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("REPORT", "보고서·정정")
    sources_by_report: dict[str, list[ReportSource]] = {}
    for source in session.scalars(
        select(ReportSource).where(ReportSource.created_at <= as_of)
    ).all():
        sources_by_report.setdefault(source.report_id, []).append(source)
    for report in session.scalars(
        select(Report).where(
            Report.superseded_by_report_id.is_(None), Report.created_at <= as_of
        )
    ).all():
        if not _can_view_source(session, user, "REPORT", report.report_id):
            continue
        if any(
            not _can_view_source(session, user, source.source_type, source.source_id)
            for source in sources_by_report.get(report.report_id, [])
        ):
            continue
        result.assessed_count += 1
        issues: list[tuple[str, str]] = []
        sources = sources_by_report.get(report.report_id, [])
        if report.replaces_report_id and report.status != "APPROVED":
            issues.append(("REPORT_CORRECTION_PENDING", "WARNING"))
        if report.status in {"REVIEWED", "APPROVED"} and not sources:
            issues.append(("REPORT_SOURCE_MISSING", "BLOCKED"))
        if any(
            not frozen_report_source_matches_current(session, source, user)
            for source in sources
        ):
            issues.append(("REPORT_SOURCE_REVISION_CONFLICT", "BLOCKED"))
        _append_item(
            result,
            issues,
            target_type="report",
            target_id=report.report_id,
            title=report.title,
            current_status=report.status,
            revision=report.report_revision,
            assignee=report.reviewed_by or report.created_by,
            owner="보고서 책임자",
            next_action="정정 계보와 고정 source revision을 보고서 화면에서 다시 대조하세요.",
            action_route="REPORT",
            oldest_at=report.created_at,
        )
    return result


def _work_sequences(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("WORK_SEQUENCE", "작업순서 전달")
    boards = {
        row.board_id: row for row in session.scalars(select(WorkSequenceBoard)).all()
    }
    for candidate in session.scalars(
        select(WorkSequenceNotificationCandidate).where(
            WorkSequenceNotificationCandidate.created_at <= as_of,
        )
    ).all():
        if not _can_view_source(session, user, "WORK_SEQUENCE_BOARD", candidate.board_id):
            continue
        result.assessed_count += 1
        if candidate.status != "CANDIDATE":
            continue
        board = boards.get(candidate.board_id)
        expired = candidate.expires_at is not None and _utc(candidate.expires_at) < as_of
        _append_item(
            result,
            [("WORK_SEQUENCE_CANDIDATE_EXPIRED" if expired else "WORK_SEQUENCE_CANDIDATE_UNSENT",
              "BLOCKED" if expired else "WARNING")],
            target_type="work_sequence_candidate",
            target_id=candidate.candidate_id,
            title=board.title if board else candidate.message,
            current_status=candidate.status,
            revision=candidate.board_revision,
            assignee=candidate.recipient_hint,
            owner="작업판 책임자",
            next_action="후보 revision과 수신 범위를 확인한 뒤 기존 전달 미리보기에서 전송하거나 제외하세요.",
            action_route="WORK_SEQUENCE",
            action_target_id=candidate.board_id,
            oldest_at=candidate.created_at,
        )
    return result


def _channels(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("CHANNEL_HANDOVER", "채널·인수인계")
    channels = {
        row.channel_id: row for row in session.scalars(
            select(NotificationChannel).where(
                NotificationChannel.status == "ACTIVE",
                NotificationChannel.created_at <= as_of,
            )
        ).all()
    }
    latest_messages: dict[str, ChannelMessage] = {}
    for message in session.scalars(
        select(ChannelMessage)
        .where(ChannelMessage.created_at <= as_of)
        .order_by(ChannelMessage.id)
    ).all():
        latest_messages[message.channel_id] = message
    members = session.scalars(
        select(NotificationChannelMember).where(
            NotificationChannelMember.status == "ACTIVE",
            NotificationChannelMember.created_at <= as_of,
        )
    ).all()
    for member in members:
        if user.role not in GLOBAL_ROLES and member.user_id != user.user_id:
            continue
        channel = channels.get(member.channel_id)
        message = latest_messages.get(member.channel_id)
        if channel is None:
            continue
        result.assessed_count += 1
        if message is None or member.last_read_message_id == message.message_id:
            continue
        _append_item(
            result,
            [("CHANNEL_MESSAGE_UNREAD", "WARNING")],
            target_type="notification_channel",
            target_id=f"{channel.channel_id}:{member.user_id}",
            title=channel.name,
            current_status="미확인",
            revision=message.id,
            assignee=member.user_id,
            owner="채널 구성원",
            next_action="채널함에서 마지막 확인 위치와 새 메시지를 확인하세요.",
            action_route="CHANNEL",
            action_target_id=channel.channel_id,
            oldest_at=message.created_at,
        )
    handovers = {
        row.handover_id: row for row in session.scalars(select(Handover)).all()
    }
    for receipt in session.scalars(
        select(HandoverReceipt).where(HandoverReceipt.created_at <= as_of)
    ).all():
        if user.role not in GLOBAL_ROLES and receipt.recipient_id != user.user_id:
            continue
        handover = handovers.get(receipt.handover_id)
        if handover is None or handover.channel_id not in channels:
            continue
        result.assessed_count += 1
        if receipt.receipt_status not in {"UNREAD", "FOLLOW_UP_REQUIRED"}:
            continue
        follow_up = receipt.receipt_status == "FOLLOW_UP_REQUIRED"
        _append_item(
            result,
            [("HANDOVER_FOLLOW_UP_REQUIRED" if follow_up else "HANDOVER_UNREAD",
              "BLOCKED" if follow_up else "WARNING")],
            target_type="handover_receipt",
            target_id=receipt.receipt_id,
            title=handover.title,
            current_status=receipt.receipt_status,
            revision=None,
            assignee=receipt.recipient_id,
            owner="인수인계 수신자·채널 관리자",
            next_action="인수인계 확인 현황에서 읽음·확인 또는 후속 조치 결과를 기록하세요.",
            action_route="HANDOVER",
            action_target_id=handover.handover_id,
            oldest_at=receipt.created_at,
        )
    return result


def _terminal_devices(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("TERMINAL_DEVICE", "승인 단말")
    if user.role not in GLOBAL_ROLES:
        result.required_roles = ["admin", "system-admin"]
        result.failure = {
            "code": "AREA_PERMISSION_REQUIRED",
            "message": "승인 단말 상태는 관리자 또는 시스템 관리자 권한이 필요합니다.",
            "responsibleRole": "시스템 관리자",
            "nextAction": "로그인 ID와 필요한 업무를 시스템 관리자에게 전달하세요.",
            "sourcePreserved": True,
        }
        return result
    devices = {
        row.device_id: row for row in session.scalars(select(TerminalDevice)).all()
    }
    for auth_session in session.scalars(
        select(AuthSession).where(
            AuthSession.status == "ACTIVE",
            AuthSession.device_id.is_not(None),
            AuthSession.created_at <= as_of,
        )
    ).all():
        device = devices.get(auth_session.device_id or "")
        if device is None:
            continue
        result.assessed_count += 1
        if device.status == "ACTIVE":
            continue
        _append_item(
            result,
            [("TERMINAL_INACTIVE_WITH_ACTIVE_SESSION", "BLOCKED")],
            target_type="terminal_device",
            target_id=device.device_id,
            title=device.device_name,
            current_status=f"{device.status} / ACTIVE_SESSION",
            revision=None,
            assignee=device.updated_by or device.registered_by,
            owner="시스템 관리자",
            next_action="승인 단말 관리에서 세션을 해지하거나 단말 상태 변경 사유를 확인하세요.",
            action_route="TERMINAL_DEVICE",
            oldest_at=auth_session.created_at,
        )
    return result


def _sync(
    session: Session, user: AuthenticatedUser, as_of: datetime, _anchor_id: int
) -> AreaResult:
    result = AreaResult("SYNC", "동기화·재결합")
    if user.role not in GLOBAL_ROLES:
        result.required_roles = ["admin", "system-admin"]
        result.failure = {
            "code": "AREA_PERMISSION_REQUIRED",
            "message": "동기화 재결합 상태는 관리자 또는 시스템 관리자 권한이 필요합니다.",
            "responsibleRole": "시스템 관리자",
            "nextAction": "로그인 ID와 필요한 업무를 시스템 관리자에게 전달하세요.",
            "sourcePreserved": True,
        }
        return result
    rows = session.scalars(
        select(ReconciliationItem).where(ReconciliationItem.created_at <= as_of)
    ).all()
    for item in rows:
        result.assessed_count += 1
        unresolved = item.resolved_at is None and item.resolution_status not in {"APPLIED", "RESOLVED"}
        if not unresolved or item.proposed_action not in {"CONFLICT", "REQUEUE"}:
            continue
        conflict = item.proposed_action == "CONFLICT"
        _append_item(
            result,
            [("SYNC_CONFLICT_UNRESOLVED" if conflict else "SYNC_REQUEUE_PENDING",
              "BLOCKED" if conflict else "WARNING")],
            target_type="reconciliation_item",
            target_id=item.item_id,
            title=f"{item.entity_type} · {item.local_id}",
            current_status=item.verdict,
            revision=item.server_revision,
            assignee=item.resolved_by,
            owner="동기화 관리자",
            next_action="보존된 로컬 요청과 서버 권위 상태를 서버 재결합 화면에서 판정하세요.",
            action_route="SYNC_RECONCILIATION",
            oldest_at=item.created_at,
        )
    return result


def _audit(
    session: Session, user: AuthenticatedUser, as_of: datetime, anchor_id: int
) -> AreaResult:
    result = AreaResult("AUDIT", "감사 완전성·최근 실패")
    rows = session.scalars(
        select(AuditEventEnvelope)
        .where(AuditEventEnvelope.id <= anchor_id)
        .order_by(AuditEventEnvelope.id.desc())
        .limit(RECENT_AUDIT_LIMIT)
    ).all()
    candidate_event_ids = _audit_candidate_event_ids(session, rows)
    visible_event_ids = (
        {row.event_id for row in rows}
        if user.role in GLOBAL_ROLES
        else _audit_visible_event_ids(session, user, rows)
    )
    for row in rows:
        if row.event_id not in visible_event_ids:
            continue
        result.assessed_count += 1
        if row.event_id not in candidate_event_ids:
            continue
        item = build_change_history_item(session, user, row)
        if item is None:
            continue
        codes = []
        for code in item["issueKinds"]:
            severity = "BLOCKED" if code in {
                "MISSING_AUDIT_FIELDS", "TARGET_MISSING", "PERMISSION_DENIED_THEN_CHANGED"
            } else "WARNING"
            codes.append((f"AUDIT_{code}", severity))
        _append_item(
            result,
            codes,
            target_type=item["targetType"],
            target_id=f"{item['targetId']}:{item['eventId']}",
            title=item["targetTitle"],
            current_status=item["currentStatus"],
            revision=item["currentRevision"],
            assignee=item["assignee"],
            owner="감사·도메인 책임자",
            next_action=item["nextAction"],
            action_route=item["actionRoute"],
            oldest_at=item["occurredAt"],
            latest_event_id=item["eventId"],
        )
    return result


def _audit_candidate_event_ids(
    session: Session,
    rows: list[AuditEventEnvelope],
) -> set[str]:
    event_ids = [row.event_id for row in rows]
    linked_event_ids = set(session.scalars(
        select(SyncMutationReceipt.event_id).where(
            SyncMutationReceipt.event_id.in_(event_ids)
        )
    ).all()) if event_ids else set()
    ids_by_type: dict[str, set[str]] = {}
    for row in rows:
        ids_by_type.setdefault(row.target_type.lower(), set()).add(row.target_id)
    existing = {
        "document": _existing_ids(session, Document.document_id, ids_by_type.get("document")),
        "document_version": _existing_ids(
            session, DocumentVersion.version_id, ids_by_type.get("document_version")
        ),
        "field_comment": _existing_ids(
            session, FieldComment.comment_id, ids_by_type.get("field_comment")
        ),
        "report": _existing_ids(session, Report.report_id, ids_by_type.get("report")),
        "work_sequence_board": _existing_ids(
            session, WorkSequenceBoard.board_id, ids_by_type.get("work_sequence_board")
        ),
        "work_sequence_item": _existing_ids(
            session, WorkSequenceItem.item_id, ids_by_type.get("work_sequence_item")
        ),
    }
    candidates: set[str] = set()
    for row in rows:
        target_type = row.target_type.lower()
        payload = _json_object(row.safe_payload_json)
        target_missing = target_type in existing and row.target_id not in existing[target_type]
        missing_revision = target_type in {
            "document", "document_version", "field_comment", "report",
            "work_sequence_board", "work_sequence_item",
        } and row.target_revision is None
        missing_version = target_type == "document_version" and row.target_version_id is None
        unlinked = bool(
            payload.get("operationKey")
            and row.event_id not in linked_event_ids
            and not payload.get("existingReceiptId")
        )
        if row.result != "SUCCESS" or target_missing or missing_revision or missing_version or unlinked:
            candidates.add(row.event_id)
    return candidates


def _audit_visible_event_ids(
    session: Session,
    user: AuthenticatedUser,
    rows: list[AuditEventEnvelope],
) -> set[str]:
    business_types = {
        "document", "document_version", "field_comment", "report",
        "work_sequence_board", "work_sequence_item",
    }
    ids_by_type: dict[str, set[str]] = {}
    for row in rows:
        ids_by_type.setdefault(row.target_type.lower(), set()).add(row.target_id)
    existing = {
        "document": _existing_ids(session, Document.document_id, ids_by_type.get("document")),
        "field_comment": _existing_ids(
            session, FieldComment.comment_id, ids_by_type.get("field_comment")
        ),
        "report": _existing_ids(session, Report.report_id, ids_by_type.get("report")),
        "work_sequence_board": _existing_ids(
            session, WorkSequenceBoard.board_id, ids_by_type.get("work_sequence_board")
        ),
        "work_sequence_item": _existing_ids(
            session, WorkSequenceItem.item_id, ids_by_type.get("work_sequence_item")
        ),
    }
    version_document_ids = dict(session.execute(
        select(DocumentVersion.version_id, DocumentVersion.document_id).where(
            DocumentVersion.version_id.in_(ids_by_type.get("document_version", set()))
        )
    ).all())
    source_by_event: dict[str, tuple[str, str]] = {}
    for row in rows:
        target_type = row.target_type.lower()
        if target_type not in business_types:
            continue
        if target_type == "document_version":
            document_id = version_document_ids.get(row.target_id)
            if document_id:
                source_by_event[row.event_id] = ("DOCUMENT", document_id)
        elif row.target_id in existing.get(target_type, set()):
            source_by_event[row.event_id] = (target_type.upper(), row.target_id)
    sources = set(source_by_event.values())
    channels_by_source: dict[tuple[str, str], set[str]] = {}
    for channel in session.scalars(
        select(NotificationChannel).where(NotificationChannel.status == "ACTIVE")
    ).all():
        key = (channel.source_type or "", channel.source_id or "")
        if key in sources:
            channels_by_source.setdefault(key, set()).add(channel.channel_id)
    member_channel_ids = set(session.scalars(
        select(NotificationChannelMember.channel_id).where(
            NotificationChannelMember.user_id == user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        )
    ).all())
    return {
        event_id
        for event_id, source in source_by_event.items()
        if source not in channels_by_source
        or bool(channels_by_source[source] & member_channel_ids)
    }


def _existing_ids(session: Session, column: Any, values: set[str] | None) -> set[str]:
    if not values:
        return set()
    return set(session.scalars(select(column).where(column.in_(values))).all())


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


AREA_BUILDERS = [
    _documents,
    _field_comments,
    _reports,
    _work_sequences,
    _channels,
    _terminal_devices,
    _sync,
    _audit,
]
AREA_METADATA = {
    "_documents": ("DOCUMENT_PUBLICATION", "문서 공개"),
    "_field_comments": ("FIELD_COMMENT", "FieldComment 검토"),
    "_reports": ("REPORT", "보고서·정정"),
    "_work_sequences": ("WORK_SEQUENCE", "작업순서 전달"),
    "_channels": ("CHANNEL_HANDOVER", "채널·인수인계"),
    "_terminal_devices": ("TERMINAL_DEVICE", "승인 단말"),
    "_sync": ("SYNC", "동기화·재결합"),
    "_audit": ("AUDIT", "감사 완전성·최근 실패"),
}


def _append_item(
    result: AreaResult,
    issues: list[tuple[str, str]],
    *,
    target_type: str,
    target_id: str,
    title: str,
    current_status: str,
    revision: int | None,
    assignee: str | None,
    owner: str,
    next_action: str,
    action_route: str,
    oldest_at: datetime,
    latest_event_id: str | None = None,
    action_target_id: str | None = None,
) -> None:
    if not issues:
        return
    severity = max((value for _, value in issues), key=SEVERITY_ORDER.__getitem__)
    stable_key = f"{result.area_code}|{target_type}|{target_id}"
    item_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:32]
    result.items.append({
        "itemId": item_id,
        "areaCode": result.area_code,
        "areaName": result.area_name,
        "severity": severity,
        "severityLabel": "차단" if severity == "BLOCKED" else "주의",
        "statusIcon": "⛔" if severity == "BLOCKED" else "⚠",
        "blockerCodes": sorted({code for code, _ in issues}),
        "targetType": target_type,
        "targetId": target_id,
        "targetTitle": title,
        "currentStatus": current_status,
        "sourceRevision": revision,
        "responsibleRole": owner,
        "assignee": assignee or "담당자 미지정",
        "nextAction": next_action,
        "actionRoute": action_route,
        "actionTargetId": action_target_id or target_id,
        "oldestAt": _utc(oldest_at),
        "latestEventId": latest_event_id,
        "auditPath": (
            f"/api/v1/change-history/{latest_event_id}" if latest_event_id else None
        ),
        "resolvedWhen": "새로고침 시 blocker 판정 조건이 더 이상 현재 상태에서 계산되지 않을 때 해결됨",
    })


def _area_payload(area: AreaResult) -> dict[str, Any]:
    counts = _counts(area.items)
    affected = len({(item["targetType"], item["targetId"]) for item in area.items})
    counts["normal"] = max(area.assessed_count - affected, 0)
    status_value = "NO_DATA" if area.failure else (
        "BLOCKED" if counts["blocked"] else "WARNING" if counts["warning"] else "NORMAL"
    )
    return {
        "areaCode": area.area_code,
        "areaName": area.area_name,
        "status": status_value,
        "statusLabel": {
            "NO_DATA": "집계 없음", "BLOCKED": "차단", "WARNING": "주의", "NORMAL": "정상"
        }[status_value],
        "statusIcon": {
            "NO_DATA": "?", "BLOCKED": "⛔", "WARNING": "⚠", "NORMAL": "✓"
        }[status_value],
        "assessedCount": area.assessed_count,
        "normalCount": counts["normal"],
        "warningCount": counts["warning"],
        "blockedCount": counts["blocked"],
        "failure": area.failure,
        "requiredRoles": area.required_roles,
    }


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "normal": 0,
        "warning": sum(item["severity"] == "WARNING" for item in items),
        "blocked": sum(item["severity"] == "BLOCKED" for item in items),
    }


def _can_view_source(
    session: Session,
    user: AuthenticatedUser,
    source_type: str,
    source_id: str,
) -> bool:
    if user.role in GLOBAL_ROLES:
        return True
    channel_ids = list(session.scalars(
        select(NotificationChannel.channel_id).where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == source_type,
            NotificationChannel.source_id == source_id,
        )
    ).all())
    if not channel_ids:
        return True
    return session.scalar(
        select(NotificationChannelMember.id).where(
            NotificationChannelMember.channel_id.in_(channel_ids),
            NotificationChannelMember.user_id == user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        ).limit(1)
    ) is not None


def _ai_field_readiness(
    session: Session, user: AuthenticatedUser, settings: Any
) -> dict[str, Any]:
    try:
        value = scope_readiness(
            session,
            customer_scope=settings.ai_customer_scope,
            site_scope=settings.ai_site_scope,
            database_scope_value=database_scope(settings.database_url),
            provider=settings.ai_provider,
            model_scope=settings.ai_model,
        )
        field_value = value["field_readiness"]
        return {
            "status": value["ai_provider_readiness_status"],
            "providerStartReady": value["provider_start_ready"],
            "acceptedDataClassification": field_value["accepted_data_classification"],
            "groundTruthCount": field_value["ground_truth_count"],
            "groundTruthGap": field_value["ground_truth_gap"],
            "latestEvaluation": field_value["latest_evaluation"],
            "readinessFailures": value["readiness_failures"],
            "syntheticIncluded": False,
            "separationNotice": "실제 익명 현장 자료만 표시하며 합성·테스트 회귀 자료는 합산하지 않습니다.",
            "failure": None,
        }
    except Exception:
        return {
            "status": "NO_DATA",
            "providerStartReady": False,
            "acceptedDataClassification": "ANONYMOUS_FIELD",
            "groundTruthCount": None,
            "groundTruthGap": None,
            "latestEvaluation": None,
            "readinessFailures": [],
            "syntheticIncluded": False,
            "separationNotice": "실제 익명 현장 자료 집계가 실패했으며 합성·테스트 자료로 대체하지 않았습니다.",
            "failure": {
                "code": "AI_FIELD_READINESS_AGGREGATION_FAILED",
                "message": "AI 실제 현장 준비도 집계를 만들지 못했습니다.",
                "responsibleRole": "AI 운영 책임자",
                "nextAction": "AI 준비도 원천과 평가 run을 확인하세요.",
                "sourcePreserved": True,
            },
        }


def _matches(item: dict[str, Any], filters: ReadinessFilters) -> bool:
    if filters.area_code and item["areaCode"] != filters.area_code:
        return False
    if filters.severity and item["severity"] != filters.severity:
        return False
    if filters.blocker_code and filters.blocker_code not in item["blockerCodes"]:
        return False
    if filters.target_query:
        needle = filters.target_query.lower()
        return any(
            needle in str(item[field]).lower()
            for field in ("targetId", "targetTitle", "actionTargetId")
        )
    return True


def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -SEVERITY_ORDER[item["severity"]],
        _utc(item["oldestAt"]),
        item["areaCode"],
        item["itemId"],
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
