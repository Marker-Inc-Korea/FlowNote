from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.field_comment_contracts import FieldCommentResponse
from app.core.auth import CurrentUser
from app.db.models import (
    FieldComment,
    FieldCommentAttachment,
    NotificationChannel,
    NotificationChannelMember,
    ReportSource,
    UserAccount,
)
from app.services.field_comment_support import _clean_optional, _effective_status, _source_hash

def _field_comment_response(
    note: FieldComment,
    *,
    workbench_flags: list[str] | None = None,
    workbench_priority: int = 0,
    attachment_count: int = 0,
    channel_access: str = "NOT_LINKED",
    assigned_role: str | None = None,
    channel_labels: list[str] | None = None,
) -> FieldCommentResponse:
    return FieldCommentResponse(
        comment_id=note.comment_id,
        document_id=note.document_id,
        document_version_id=note.document_version_id,
        structure_item_id=note.structure_item_id,
        work_record_id=note.work_record_id,
        comment_type=note.comment_type,
        input_mode=note.input_mode,
        signal_level=note.signal_level,
        template_id=note.template_id,
        raw_content=note.raw_content,
        normalized_content=note.normalized_content,
        analysis_content=note.analysis_content,
        author_id=note.author_id,
        reported_by=note.reported_by,
        operator_id=note.operator_id,
        entry_source=note.entry_source,
        device_id=note.device_id,
        location_code=note.location_code,
        category=note.category,
        priority=note.priority,
        status=_effective_status(note),
        reviewed_by=note.reviewed_by,
        analyzed_by=note.analyzed_by,
        assigned_to=note.assigned_to,
        assigned_role=assigned_role,
        review_due_at=note.review_due_at,
        last_transition_reason=note.last_transition_reason,
        conflict_flag=note.conflict_flag,
        conflict_basis=note.conflict_basis,
        selected_at=note.selected_at,
        source_hash_sha256=_source_hash(note),
        created_at=note.created_at,
        updated_at=note.updated_at,
        reviewed_at=note.reviewed_at,
        analyzed_at=note.analyzed_at,
        review_revision=note.review_revision,
        workbench_flags=workbench_flags or [],
        workbench_priority=workbench_priority,
        attachment_count=attachment_count,
        channel_access=channel_access,
        channel_labels=channel_labels or [],
    )


def _attachment_count(session: Session, comment_id: str) -> int:
    return session.scalar(select(func.count()).select_from(FieldCommentAttachment).where(
        FieldCommentAttachment.comment_id == comment_id
    )) or 0


def _channel_access(session: Session, note: FieldComment, current_user: CurrentUser) -> str:
    channel_ids = list(session.scalars(select(NotificationChannel.channel_id).where(
        NotificationChannel.status == "ACTIVE",
        NotificationChannel.source_type == "FIELD_COMMENT",
        NotificationChannel.source_id == note.comment_id,
    )).all())
    if not channel_ids:
        return "NOT_LINKED"
    if current_user.role in {"admin", "system-admin"}:
        return "ALLOWED"
    membership = session.scalar(select(NotificationChannelMember.id).where(
        NotificationChannelMember.channel_id.in_(channel_ids),
        NotificationChannelMember.user_id == current_user.user_id,
        NotificationChannelMember.status == "ACTIVE",
    ).limit(1))
    return "ALLOWED" if membership is not None else "DENIED"


def _assigned_role(session: Session, note: FieldComment) -> str | None:
    if note.assigned_to is None:
        return None
    return session.scalar(select(UserAccount.role).where(UserAccount.user_id == note.assigned_to))


def _channel_labels(session: Session, note: FieldComment) -> list[str]:
    rows = session.execute(
        select(NotificationChannel.channel_id, NotificationChannel.name, NotificationChannel.channel_type)
        .where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == "FIELD_COMMENT",
            NotificationChannel.source_id == note.comment_id,
        )
        .order_by(NotificationChannel.name, NotificationChannel.channel_id)
    ).all()
    return [f"{name} ({channel_type}, {channel_id})" for channel_id, name, channel_type in rows]


def _workbench_flags(session: Session, note: FieldComment, now: datetime) -> list[str]:
    flags: list[str] = []
    active = note.status not in {"SELECTED", "EXCLUDED", "ARCHIVED"}
    if note.status in {"NEW", "NEEDS_REVIEW"}:
        flags.append("UNREVIEWED")
    if note.conflict_flag:
        flags.append("CONFLICT")
    due_at = note.review_due_at
    if due_at is not None:
        normalized_due = due_at.replace(tzinfo=timezone.utc) if due_at.tzinfo is None else due_at
        if active and normalized_due < now:
            flags.append("OVERDUE")
    if active and note.assigned_to is None:
        flags.append("UNASSIGNED")
    if not note.document_version_id or not note.author_id or not _clean_optional(note.analysis_content):
        flags.append("MISSING_EVIDENCE")
    duplicate = session.scalar(
        select(FieldComment.id).where(
            FieldComment.comment_id != note.comment_id,
            FieldComment.raw_content == note.raw_content,
        ).limit(1)
    )
    if duplicate is not None:
        flags.append("DUPLICATE_SUSPECTED")
    linked = session.scalar(
        select(ReportSource.id).where(
            ReportSource.source_type == "FIELD_COMMENT",
            ReportSource.source_id == note.comment_id,
        ).limit(1)
    )
    if linked is None:
        flags.append("REPORT_UNLINKED")
    return flags


WORKBENCH_FLAG_WEIGHTS = {
    "CONFLICT": 128,
    "OVERDUE": 64,
    "UNASSIGNED": 32,
    "MISSING_EVIDENCE": 16,
    "DUPLICATE_SUSPECTED": 8,
    "UNREVIEWED": 4,
    "REPORT_UNLINKED": 2,
}


def _workbench_priority(flags: list[str]) -> int:
    return sum(WORKBENCH_FLAG_WEIGHTS[flag] for flag in flags)
