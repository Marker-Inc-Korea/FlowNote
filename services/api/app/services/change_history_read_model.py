from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.db.models import (
    AuditEventEnvelope,
    Document,
    DocumentVersion,
    FieldComment,
    NotificationChannel,
    NotificationChannelMember,
    Report,
    SyncMutationReceipt,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceItem,
)

READ_MODEL_VERSION = 1
SOURCE_AUTHORITY = "audit_event_envelopes"
GLOBAL_AUDIT_ROLES = {"admin", "system-admin"}
BUSINESS_TARGET_TYPES = {
    "document",
    "document_version",
    "field_comment",
    "report",
    "work_sequence_board",
    "work_sequence_item",
}


@dataclass(frozen=True)
class ChangeHistoryFilters:
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    device_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    target_query: str | None = None
    target_version_id: str | None = None
    target_revision: int | None = None
    result: str | None = None
    risk_level: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    action_required: bool | None = None


@dataclass(frozen=True)
class TargetState:
    target_type: str
    target_id: str
    title: str
    status: str
    revision: int | None
    assignee: str | None
    channel_source_type: str
    channel_source_id: str
    action_route: str
    exists: bool = True


def list_change_history(
    session: Session,
    current_user: AuthenticatedUser,
    filters: ChangeHistoryFilters,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    cursor_value = _decode_cursor(cursor) if cursor else None
    filter_signature = _filter_signature(filters)
    if cursor_value is not None and cursor_value.get("filterSignature") != filter_signature:
        raise _invalid_cursor("필터와 페이지 커서가 일치하지 않습니다. 첫 페이지부터 다시 조회하세요.")
    anchor_id = (
        int(cursor_value["anchorId"])
        if cursor_value is not None
        else int(session.scalar(select(func.max(AuditEventEnvelope.id))) or 0)
    )
    rows = session.scalars(
        select(AuditEventEnvelope).where(AuditEventEnvelope.id <= anchor_id)
    ).all()
    items = []
    for row in rows:
        item = build_change_history_item(session, current_user, row)
        if item is not None and _matches(item, row, filters):
            items.append(item)
    items.sort(key=_sort_key)

    start = 0
    if cursor_value is not None:
        last_event_id = cursor_value.get("lastEventId")
        index = next(
            (index for index, item in enumerate(items) if item["eventId"] == last_event_id),
            None,
        )
        if index is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "CHANGE_HISTORY_CURSOR_INVALID",
                    "message": "필터와 페이지 커서가 일치하지 않습니다. 첫 페이지부터 다시 조회하세요.",
                },
            )
        start = index + 1

    page = items[start : start + limit]
    next_cursor = None
    if start + limit < len(items) and page:
        next_cursor = _encode_cursor(anchor_id, page[-1]["eventId"], filter_signature)
    return {
        "readModelVersion": READ_MODEL_VERSION,
        "sourceAuthority": SOURCE_AUTHORITY,
        "rebuildable": True,
        "snapshotAnchorId": anchor_id,
        "totalCount": len(items),
        "actionRequiredCount": sum(1 for item in items if item["actionRequired"]),
        "totalsByResult": _totals(items, "result"),
        "totalsByRisk": _totals(items, "riskLevel"),
        "items": page,
        "nextCursor": next_cursor,
    }


def get_change_history_detail(
    session: Session,
    current_user: AuthenticatedUser,
    event_id: str,
) -> dict[str, Any]:
    row = session.scalar(
        select(AuditEventEnvelope).where(AuditEventEnvelope.event_id == event_id)
    )
    if row is None:
        raise _not_found()
    item = build_change_history_item(session, current_user, row)
    if item is None:
        raise _not_found()
    return {
        "readModelVersion": READ_MODEL_VERSION,
        "sourceAuthority": SOURCE_AUTHORITY,
        "rebuildable": True,
        "item": item,
        "auditEnvelope": {
            "eventId": row.event_id,
            "schemaVersion": row.schema_version,
            "eventType": row.event_type,
            "actorId": row.actor_id,
            "actorRole": row.actor_role,
            "sessionId": row.session_id,
            "deviceId": row.device_id,
            "targetType": row.target_type,
            "targetId": row.target_id,
            "targetVersionId": row.target_version_id,
            "targetRevision": row.target_revision,
            "reason": row.reason,
            "approvalStatus": row.approval_status,
            "approvedBy": row.approved_by,
            "approvalReference": row.approval_reference,
            "beforeHashSha256": row.before_hash_sha256,
            "afterHashSha256": row.after_hash_sha256,
            "result": row.result,
            "resultCode": row.result_code,
            "httpStatus": row.http_status,
            "runId": row.run_id,
            "correlationId": row.correlation_id,
            "domainAuditType": row.domain_audit_type,
            "domainAuditId": row.domain_audit_id,
            "safePayload": _safe_payload(row.safe_payload_json),
            "serverTime": _utc_datetime(row.server_time),
        },
    }


def build_change_history_item(
    session: Session,
    current_user: AuthenticatedUser,
    row: AuditEventEnvelope,
) -> dict[str, Any] | None:
    target = _target_state(session, row)
    if not _can_view_target(session, current_user, row, target):
        return None
    payload = _safe_payload(row.safe_payload_json)
    receipt = session.scalar(
        select(SyncMutationReceipt).where(SyncMutationReceipt.event_id == row.event_id)
    )
    missing_fields = _missing_fields(row, payload, receipt)
    linked_mutation = receipt is not None or bool(payload.get("existingReceiptId"))
    issue_kinds: list[str] = []
    if not target.exists:
        issue_kinds.append("TARGET_MISSING")
    if row.result == "CONFLICT":
        issue_kinds.append("CONFLICT")
    if row.result == "REJECTED" or "FAIL" in row.result_code or "ERROR" in row.result_code:
        issue_kinds.append("FAILURE")
    if payload.get("operationKey") and not linked_mutation:
        issue_kinds.append("UNLINKED_MUTATION")
    if missing_fields:
        issue_kinds.append("MISSING_AUDIT_FIELDS")
    permission_denied_changed = bool(
        row.result == "REJECTED"
        and row.http_status == status.HTTP_403_FORBIDDEN
        and target.revision is not None
        and row.target_revision is not None
        and target.revision != row.target_revision
    )
    if row.result == "REJECTED" and row.http_status == status.HTTP_403_FORBIDDEN:
        issue_kinds.append(
            "PERMISSION_DENIED_THEN_CHANGED"
            if permission_denied_changed
            else "PERMISSION_DENIED"
        )

    risk_level = _risk_level(issue_kinds)
    action_required = bool(issue_kinds)
    impact, next_action = _guidance(issue_kinds, target)
    actor = session.scalar(select(UserAccount).where(UserAccount.user_id == row.actor_id))
    return {
        "eventId": row.event_id,
        "occurredAt": _utc_datetime(row.server_time),
        "eventType": row.event_type,
        "actorId": row.actor_id,
        "actorDisplayName": actor.display_name if actor is not None else row.actor_id,
        "actorRole": row.actor_role,
        "deviceId": row.device_id,
        "targetType": row.target_type,
        "targetId": row.target_id,
        "targetTitle": target.title,
        "targetVersionId": row.target_version_id,
        "targetRevision": row.target_revision,
        "result": row.result,
        "resultCode": row.result_code,
        "httpStatus": row.http_status,
        "riskLevel": risk_level,
        "actionRequired": action_required,
        "issueKinds": issue_kinds,
        "impact": impact,
        "currentStatus": target.status,
        "currentRevision": target.revision,
        "assignee": target.assignee or "담당자 미지정",
        "nextAction": next_action,
        "actionRoute": target.action_route if action_required else "AUDIT_DETAIL",
        "runId": row.run_id,
        "correlationId": row.correlation_id,
        "linkedMutation": linked_mutation,
        "permissionDeniedChangeDetected": permission_denied_changed,
        "missingAuditFields": missing_fields,
        "rawAuditPath": f"/api/v1/change-history/{row.event_id}",
    }


def _target_state(session: Session, row: AuditEventEnvelope) -> TargetState:
    target_type = row.target_type.lower()
    if target_type == "document":
        document = session.scalar(select(Document).where(Document.document_id == row.target_id))
        if document is None:
            return _missing_target(row)
        return TargetState(
            target_type, row.target_id, document.title, document.status, document.revision,
            document.owner_id, "DOCUMENT", document.document_id, "DOCUMENT_CONFLICT",
        )
    if target_type == "document_version":
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.version_id == row.target_id)
        )
        document = session.scalar(
            select(Document).where(Document.document_id == version.document_id)
        ) if version is not None else None
        if version is None or document is None:
            return _missing_target(row)
        return TargetState(
            target_type, row.target_id, f"{document.title} · v{version.version_no}",
            version.version_status, document.revision, document.owner_id,
            "DOCUMENT", document.document_id, "DOCUMENT_CONFLICT",
        )
    if target_type == "field_comment":
        comment = session.scalar(
            select(FieldComment).where(FieldComment.comment_id == row.target_id)
        )
        if comment is None:
            return _missing_target(row)
        title = f"FieldComment · {comment.category or comment.signal_level or comment.comment_type}"
        return TargetState(
            target_type, row.target_id, title, comment.status, comment.review_revision,
            comment.assigned_to, "FIELD_COMMENT", comment.comment_id, "FIELD_COMMENT_REVIEW",
        )
    if target_type == "report":
        report = session.scalar(select(Report).where(Report.report_id == row.target_id))
        if report is None:
            return _missing_target(row)
        return TargetState(
            target_type, row.target_id, report.title, report.status, report.report_revision,
            report.reviewed_by or report.created_by, "REPORT", report.report_id, "REPORT",
        )
    if target_type == "work_sequence_board":
        board = session.scalar(
            select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == row.target_id)
        )
        if board is None:
            return _missing_target(row)
        return TargetState(
            target_type, row.target_id, board.title, board.status, board.board_revision,
            board.created_by, "WORK_SEQUENCE_BOARD", board.board_id, "WORK_SEQUENCE",
        )
    if target_type == "work_sequence_item":
        item = session.scalar(
            select(WorkSequenceItem).where(WorkSequenceItem.item_id == row.target_id)
        )
        board = session.scalar(
            select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == item.board_id)
        ) if item is not None else None
        if item is None or board is None:
            return _missing_target(row)
        return TargetState(
            target_type, row.target_id, item.title, item.status, board.board_revision,
            item.assigned_to, "WORK_SEQUENCE_ITEM", item.item_id, "WORK_SEQUENCE",
        )
    return TargetState(
        target_type, row.target_id, row.target_id, "원본 감사 확인 필요",
        row.target_revision, None, row.target_type.upper(), row.target_id, "AUDIT_DETAIL",
    )


def _missing_target(row: AuditEventEnvelope) -> TargetState:
    return TargetState(
        row.target_type.lower(), row.target_id, row.target_id, "대상 없음",
        None, None, row.target_type.upper(), row.target_id, "AUDIT_DETAIL", exists=False,
    )


def _can_view_target(
    session: Session,
    current_user: AuthenticatedUser,
    row: AuditEventEnvelope,
    target: TargetState,
) -> bool:
    if current_user.role in GLOBAL_AUDIT_ROLES:
        return True
    if not target.exists:
        return False
    if row.target_type.lower() not in BUSINESS_TARGET_TYPES:
        return False
    channel_ids = list(session.scalars(
        select(NotificationChannel.channel_id).where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == target.channel_source_type,
            NotificationChannel.source_id == target.channel_source_id,
        )
    ).all())
    if not channel_ids:
        return True
    return session.scalar(
        select(NotificationChannelMember.id).where(
            NotificationChannelMember.channel_id.in_(channel_ids),
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        ).limit(1)
    ) is not None


def _missing_fields(
    row: AuditEventEnvelope,
    payload: dict[str, Any],
    receipt: SyncMutationReceipt | None,
) -> list[str]:
    required = {
        "eventType": row.event_type,
        "actorId": row.actor_id,
        "actorRole": row.actor_role,
        "sessionId": row.session_id,
        "targetType": row.target_type,
        "targetId": row.target_id,
        "result": row.result,
        "resultCode": row.result_code,
        "httpStatus": row.http_status,
        "correlationId": row.correlation_id,
        "serverTime": row.server_time,
    }
    missing = [name for name, value in required.items() if value is None or value == ""]
    if row.target_type.lower() in BUSINESS_TARGET_TYPES and row.target_revision is None:
        missing.append("targetRevision")
    if row.target_type.lower() == "document_version" and row.target_version_id is None:
        missing.append("targetVersionId")
    if payload.get("operationKey") and receipt is None and not payload.get("existingReceiptId"):
        missing.append("syncMutationReceipt")
    return missing


def _risk_level(issue_kinds: list[str]) -> str:
    if (
        "PERMISSION_DENIED_THEN_CHANGED" in issue_kinds
        or "MISSING_AUDIT_FIELDS" in issue_kinds
        or "TARGET_MISSING" in issue_kinds
    ):
        return "CRITICAL"
    if "CONFLICT" in issue_kinds or "UNLINKED_MUTATION" in issue_kinds:
        return "HIGH"
    if "FAILURE" in issue_kinds or "PERMISSION_DENIED" in issue_kinds:
        return "MEDIUM"
    return "LOW"


def _guidance(issue_kinds: list[str], target: TargetState) -> tuple[str, str]:
    if "TARGET_MISSING" in issue_kinds:
        return (
            "원본 감사의 업무 대상을 현재 권위 테이블에서 찾을 수 없습니다.",
            "원본 event와 삭제·복구 이력을 대조해 고아 참조 여부를 확인하세요.",
        )
    if "PERMISSION_DENIED_THEN_CHANGED" in issue_kinds:
        return (
            "권한 거부 뒤 대상 revision이 달라져 승인되지 않은 변경 여부를 확인해야 합니다.",
            "원본 감사와 현재 대상을 대조하고 권한 담당자가 변경 경로를 확인하세요.",
        )
    if "MISSING_AUDIT_FIELDS" in issue_kinds:
        return (
            "필수 감사 필드가 없어 행위와 업무 변경의 완전한 역추적이 어렵습니다.",
            "원본 감사와 공통 mutation receipt를 대조해 누락 원인을 보완하세요.",
        )
    if "UNLINKED_MUTATION" in issue_kinds:
        return (
            "operation key가 공통 mutation receipt와 연결되지 않았습니다.",
            "동일 operation key의 도메인 receipt와 업무 revision을 확인하세요.",
        )
    if "CONFLICT" in issue_kinds:
        return (
            f"{target.title} 변경이 서버 권위 상태와 충돌해 자동 반영되지 않았습니다.",
            "서버 현재 상태와 보존된 요청을 비교한 뒤 적용할 값을 결정하세요.",
        )
    if "FAILURE" in issue_kinds or "PERMISSION_DENIED" in issue_kinds:
        return (
            f"{target.title} 변경 요청이 반영되지 않았습니다.",
            "결과 코드와 현재 상태를 확인하고 담당 권한으로 다시 조치하세요.",
        )
    return "업무 변경이 정상 기록되었습니다.", "원본 감사 상세에서 변경 근거를 확인할 수 있습니다."


def _matches(
    item: dict[str, Any],
    row: AuditEventEnvelope,
    filters: ChangeHistoryFilters,
) -> bool:
    pairs = (
        (filters.actor_id, row.actor_id),
        (filters.actor_role, row.actor_role),
        (filters.device_id, row.device_id),
        (filters.target_type, row.target_type),
        (filters.target_id, row.target_id),
        (filters.target_version_id, row.target_version_id),
        (filters.result, row.result),
        (filters.risk_level, item["riskLevel"]),
        (filters.run_id, row.run_id),
        (filters.correlation_id, row.correlation_id),
    )
    if any(expected is not None and str(actual).lower() != expected.lower() for expected, actual in pairs):
        return False
    row_time = _utc_datetime(row.server_time)
    if filters.occurred_from is not None and row_time < _utc_datetime(filters.occurred_from):
        return False
    if filters.occurred_to is not None and row_time > _utc_datetime(filters.occurred_to):
        return False
    if filters.target_revision is not None and row.target_revision != filters.target_revision:
        return False
    if filters.action_required is not None and item["actionRequired"] != filters.action_required:
        return False
    if filters.target_query is not None:
        needle = filters.target_query.lower()
        if needle not in row.target_id.lower() and needle not in item["targetTitle"].lower():
            return False
    return True


def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    occurred_at = item["occurredAt"]
    timestamp = _utc_datetime(occurred_at).timestamp() if occurred_at is not None else 0
    return (
        -int(item["actionRequired"]),
        -_issue_sort_priority(item["issueKinds"]),
        -timestamp,
        item["eventId"],
    )


def _issue_sort_priority(issue_kinds: list[str]) -> int:
    issues = set(issue_kinds)
    if issues & {"MISSING_AUDIT_FIELDS", "TARGET_MISSING"}:
        return 5
    if issues & {"PERMISSION_DENIED", "PERMISSION_DENIED_THEN_CHANGED"}:
        return 4
    if issues & {"CONFLICT", "UNLINKED_MUTATION"}:
        return 3
    if "FAILURE" in issues:
        return 2
    return 1


def _totals(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        key = str(item[field])
        result[key] = result.get(key, 0) + 1
    return result


def _safe_payload(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _filter_signature(filters: ChangeHistoryFilters) -> str:
    canonical = json.dumps(
        {
            key: _utc_datetime(value).isoformat() if isinstance(value, datetime) else value
            for key, value in filters.__dict__.items()
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _encode_cursor(anchor_id: int, last_event_id: str, filter_signature: str) -> str:
    value = json.dumps(
        {
            "anchorId": anchor_id,
            "lastEventId": last_event_id,
            "filterSignature": filter_signature,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(value) % 4)
        parsed = json.loads(base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8"))
        if not isinstance(parsed, dict) or int(parsed["anchorId"]) < 0 or not parsed["lastEventId"]:
            raise ValueError
        return parsed
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise _invalid_cursor(
            "페이지 커서를 해석할 수 없습니다. 첫 페이지부터 다시 조회하세요."
        ) from None


def _invalid_cursor(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "CHANGE_HISTORY_CURSOR_INVALID",
            "message": message,
        },
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "RESOURCE_NOT_FOUND",
            "message": "요청한 변경 이력을 찾을 수 없습니다.",
        },
    )
