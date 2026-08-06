from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.db.models import (
    Document,
    DocumentVersion,
    FieldComment,
    FileObject,
    NotificationChannel,
    NotificationChannelMember,
    ReportSource,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)

REPORT_SOURCE_TYPES = {
    "FIELD_COMMENT",
    "DOCUMENT",
    "WORK_SEQUENCE_ITEM",
    "WORK_SEQUENCE_HISTORY",
    "WORK_RECORD",
    "WORK_RECORD_VERSION",
}
FIELD_COMMENT_REPORT_SOURCE_STATUS = "SELECTED"
REPORT_STATUS_TRANSITIONS = {
    "DRAFT": {"REVIEWED", "APPROVED"},
    "AI_DRAFTED": {"REVIEWED", "APPROVED"},
    "REVIEWED": {"DRAFT", "APPROVED"},
    "APPROVED": {"ARCHIVED"},
    "ARCHIVED": set(),
}
SOURCE_NOT_VISIBLE_DETAIL = {
    "code": "SOURCE_NOT_VISIBLE",
    "message": "요청한 원천을 찾을 수 없거나 현재 공개 범위에서 열람할 수 없습니다.",
}


class ReportSourceInput(Protocol):
    source_type: str
    source_id: str
    source_version_id: str | None
    relation_type: str | None
    source_revision: int | None
    source_hash_sha256: str | None


@dataclass(frozen=True)
class FrozenReportSourceInput:
    source_type: str
    source_id: str
    source_version_id: str | None = None
    relation_type: str | None = None
    source_revision: int | None = None
    source_hash_sha256: str | None = None


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"

def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required(value: str | None, field_name: str) -> str:
    cleaned = _clean_optional(value)
    if cleaned is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} is required.",
        )
    return cleaned


def _clean_idempotency_key(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    if cleaned is not None and len(cleaned) > 160:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="idempotencyKey is too long.",
        )
    return cleaned


def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
    cleaned = value.strip().upper()
    if cleaned not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field_name} has an unsupported value.",
        )
    return cleaned


def _normalize_source_type(value: str) -> str:
    return _normalize_choice(value, REPORT_SOURCE_TYPES, "sourceType")


def _validate_work_record(session: Session, work_record_id: str | None) -> str | None:
    cleaned = _clean_optional(work_record_id)
    if cleaned is None:
        return None
    exists = session.scalar(select(WorkRecord.id).where(WorkRecord.work_record_id == cleaned))
    if exists is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="workRecordId is unknown.")
    return cleaned


def _ensure_source_channel_access(
    session: Session,
    current_user: CurrentUser,
    source_type: str,
    source_id: str,
) -> None:
    if current_user.role in {"admin", "system-admin"}:
        return
    channel_ids = list(session.scalars(
        select(NotificationChannel.channel_id).where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == source_type,
            NotificationChannel.source_id == source_id,
        )
    ).all())
    if not channel_ids:
        return
    membership = session.scalar(
        select(NotificationChannelMember.id).where(
            NotificationChannelMember.channel_id.in_(channel_ids),
            NotificationChannelMember.user_id == current_user.user_id,
            NotificationChannelMember.status == "ACTIVE",
        ).limit(1)
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SOURCE_NOT_VISIBLE_DETAIL,
        )


def _validate_source(
    session: Session,
    source: ReportSourceInput,
    current_user: CurrentUser,
) -> tuple[str, str, str, int | None, str | None, str]:
    source_type = _normalize_source_type(source.source_type)
    source_id = source.source_id.strip()
    source_version_id = _clean_optional(source.source_version_id)
    relation_type = _clean_optional(source.relation_type)
    source_revision: int | None = None

    if source_type == "FIELD_COMMENT":
        field_comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == source_id))
        if field_comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SOURCE_NOT_VISIBLE_DETAIL)
        if field_comment.status != FIELD_COMMENT_REPORT_SOURCE_STATUS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        source_version_id = field_comment.document_version_id
        source_hash = _field_comment_source_hash(field_comment)
        source_revision = field_comment.review_revision
    elif source_type == "DOCUMENT":
        document = session.scalar(
            select(Document).where(Document.document_id == source_id, Document.deleted_at.is_(None))
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SOURCE_NOT_VISIBLE_DETAIL)
        if document.status != "PUBLISHED" or document.published_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        source_version_id = source_version_id or document.published_version_id
        version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == source_version_id))
        if version is None or version.document_id != document.document_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        if source_version_id != document.published_version_id or not version.is_published:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        file_object = session.scalar(select(FileObject).where(FileObject.id == version.file_object_id))
        source_hash = file_object.hash_sha256 if file_object is not None else None
    elif source_type == "WORK_SEQUENCE_ITEM":
        item = session.scalar(select(WorkSequenceItem).where(WorkSequenceItem.item_id == source_id))
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        latest_change = session.scalar(
            select(WorkSequenceChangeHistory)
            .where(WorkSequenceChangeHistory.item_id == source_id)
            .order_by(desc(WorkSequenceChangeHistory.created_at), desc(WorkSequenceChangeHistory.id))
            .limit(1)
        )
        source_version_id = latest_change.change_id if latest_change is not None else item.item_id
        source_hash = _hash_payload(_work_sequence_item_snapshot(item))
    elif source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(
            select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == source_id)
        )
        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        source_version_id = history.change_id
        source_hash = _hash_payload(_work_sequence_history_snapshot(history))
    elif source_type == "WORK_RECORD":
        work_record = session.scalar(select(WorkRecord).where(WorkRecord.work_record_id == source_id))
        if work_record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SOURCE_NOT_VISIBLE_DETAIL)
        if work_record.latest_version_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SOURCE_NOT_VISIBLE_DETAIL)
        version = session.scalar(
            select(WorkRecordVersion).where(WorkRecordVersion.version_id == work_record.latest_version_id)
        )
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SOURCE_NOT_VISIBLE_DETAIL)
        source_version_id = version.version_id
        source_hash = _hash_payload(_work_record_version_snapshot(version))
    elif source_type == "WORK_RECORD_VERSION":
        version = session.scalar(select(WorkRecordVersion).where(WorkRecordVersion.version_id == source_id))
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SOURCE_NOT_VISIBLE_DETAIL,
            )
        source_version_id = version.version_id
        source_hash = _hash_payload(_work_record_version_snapshot(version))

    _ensure_source_channel_access(session, current_user, source_type, source_id)
    if not source_version_id:
        raise HTTPException(status_code=422, detail=f"{source_type} source requires a fixed source version.")
    if not source_hash:
        raise HTTPException(status_code=422, detail=f"{source_type} source requires a verifiable source hash.")
    if source.source_revision is not None and source.source_revision != source_revision:
        raise HTTPException(status_code=409, detail="Report source revision changed before it could be frozen.")
    if source.source_hash_sha256 is not None and source.source_hash_sha256.lower() != source_hash.lower():
        raise HTTPException(status_code=409, detail="Report source hash changed before it could be frozen.")
    return source_type, source_id, source_version_id, source_revision, relation_type, source_hash


def _hash_payload(payload: dict) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _report_event_type(report_status: str) -> str:
    return {
        "DRAFT": "report.review_invalidated",
        "REVIEWED": "report.reviewed",
        "APPROVED": "report.approved",
        "ARCHIVED": "report.archived",
    }[report_status]


def _validate_report_transition(current_status: str, target_status: str) -> None:
    if target_status not in REPORT_STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REPORT_STATUS_TRANSITION_NOT_ALLOWED",
                "message": f"보고서 상태를 {current_status}에서 {target_status}(으)로 변경할 수 없습니다.",
                "currentStatus": current_status,
                "targetStatus": target_status,
            },
        )


def _field_comment_source_hash(note: FieldComment) -> str:
    return _hash_payload({
        "comment_id": note.comment_id,
        "document_id": note.document_id,
        "document_version_id": note.document_version_id,
        "structure_item_id": note.structure_item_id,
        "work_record_id": note.work_record_id,
        "comment_type": note.comment_type,
        "input_mode": note.input_mode,
        "signal_level": note.signal_level,
        "template_id": note.template_id,
        "raw_content": note.raw_content,
        "author_id": note.author_id,
        "reported_by": note.reported_by,
        "operator_id": note.operator_id,
        "entry_source": note.entry_source,
        "device_id": note.device_id,
        "location_code": note.location_code,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    })


def _work_sequence_item_snapshot(item: WorkSequenceItem) -> dict:
    return {
        "item_id": item.item_id,
        "board_id": item.board_id,
        "title": item.title,
        "description": item.description,
        "work_order_no": item.work_order_no,
        "document_id": item.document_id,
        "status": item.status,
        "hold_reason": item.hold_reason,
        "sort_order": item.sort_order,
        "assigned_to": item.assigned_to,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _work_sequence_history_snapshot(history: WorkSequenceChangeHistory) -> dict:
    return {
        "change_id": history.change_id,
        "board_id": history.board_id,
        "item_id": history.item_id,
        "change_type": history.change_type,
        "actor_id": history.actor_id,
        "before_value": history.before_value,
        "after_value": history.after_value,
        "change_reason": history.change_reason,
        "created_at": history.created_at.isoformat() if history.created_at else None,
    }


def _work_record_version_snapshot(version: WorkRecordVersion) -> dict:
    return {
        "version_id": version.version_id,
        "work_record_id": version.work_record_id,
        "version_no": version.version_no,
        "summary": version.summary,
        "result_note": version.result_note,
        "issue_note": version.issue_note,
        "action_note": version.action_note,
        "change_reason": version.change_reason,
        "created_by": version.created_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def _validate_source_set(sources: list[ReportSourceInput]) -> None:
    distinct_types = {_normalize_source_type(source.source_type) for source in sources}
    if len(distinct_types) < 2:
        raise HTTPException(
            status_code=422,
            detail="A report requires at least two distinct source types.",
        )
    identities = [
        (
            _normalize_source_type(source.source_type),
            source.source_id.strip(),
            _clean_optional(source.source_version_id) or "",
        )
        for source in sources
    ]
    if len(identities) != len(set(identities)):
        raise HTTPException(status_code=409, detail="Duplicate report sources are not allowed.")


def _replace_report_sources(
    session: Session,
    report_id: str,
    sources: list[ReportSourceInput],
    current_user: CurrentUser,
) -> list[ReportSource]:
    validated_sources = [
        _validate_source(session, source, current_user)
        for source in sources
    ]
    _validate_source_set(sources)
    session.query(ReportSource).filter(ReportSource.report_id == report_id).delete(synchronize_session=False)
    session.flush()
    report_sources: list[ReportSource] = []
    for source_type, source_id, source_version_id, source_revision, relation_type, source_hash in validated_sources:
        report_source = ReportSource(
            report_id=report_id,
            source_type=source_type,
            source_id=source_id,
            source_version_id=source_version_id,
            source_revision=source_revision,
            trace_id=_new_public_id("trace"),
            source_hash_sha256=source_hash,
            relation_type=relation_type,
        )
        session.add(report_source)
        report_sources.append(report_source)
    session.flush()
    return report_sources


def _validate_frozen_sources(
    session: Session,
    sources: list[ReportSource],
    current_user: CurrentUser,
) -> None:
    if len({source.source_type for source in sources}) < 2:
        raise HTTPException(status_code=422, detail="A report requires at least two distinct source types.")
    for source in sources:
        try:
            validated_type, validated_id, validated_version, current_revision, _, current_hash = _validate_source(
                session,
                FrozenReportSourceInput(
                    source_type=source.source_type,
                    source_id=source.source_id,
                    source_version_id=source.source_version_id,
                    relation_type=source.relation_type,
                ),
                current_user,
            )
        except HTTPException as exc:
            if exc.status_code in {
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            }:
                raise
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_SOURCE_STALE_OR_ORPHAN",
                    "message": f"보고서 원천이 변경되었거나 더 이상 사용할 수 없습니다: {source.trace_id}.",
                },
            ) from exc
        if (validated_type, validated_id, validated_version) != (
            source.source_type,
            source.source_id,
            source.source_version_id,
        ):
            raise HTTPException(status_code=409, detail=f"Report source version changed: {source.trace_id}.")
        if current_hash != source.source_hash_sha256:
            raise HTTPException(status_code=409, detail=f"Report source hash mismatch: {source.trace_id}.")
        if source.source_revision is not None and current_revision != source.source_revision:
            raise HTTPException(status_code=409, detail=f"Report source revision changed: {source.trace_id}.")
