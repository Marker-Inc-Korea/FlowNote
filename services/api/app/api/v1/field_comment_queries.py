from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, exists, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.field_comment_contracts import (
    STATUSES,
    FieldCommentAttachmentResponse,
    FieldCommentAuditResponse,
    FieldCommentQualityItemResponse,
    FieldCommentResponse,
    FieldCommentTraceDocumentResponse,
    FieldCommentTraceReportResponse,
    FieldCommentTraceResponse,
    FieldCommentTraceWorkSequenceResponse,
)
from app.core.auth import CurrentUser, FieldCommentAnalyzeUser, get_current_user
from app.db.models import (
    ActivityHistory,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    FieldCommentAttachment,
    FileObject,
    NotificationChannel,
    Report,
    ReportSource,
    TagDefinition,
    UserAccount,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.db.session import get_db_session
from app.services.field_comment_attachment_service import _attachment_response
from app.services.field_comment_query_service import (
    _assigned_role,
    _attachment_count,
    _channel_access,
    _channel_labels,
    _field_comment_response,
    _workbench_flags,
    _workbench_priority,
)
from app.services.field_comment_support import _clean_optional, _source_hash, _validate_choice

router = APIRouter(
    prefix="/field-comments",
    tags=["field-comments"],
    dependencies=[Depends(get_current_user)],
)
document_field_comments_router = APIRouter(
    prefix="/documents",
    tags=["field-comments"],
    dependencies=[Depends(get_current_user)],
)

@router.get("/{comment_id}/attachments", response_model=list[FieldCommentAttachmentResponse])
def list_field_comment_attachments(
    comment_id: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentAttachmentResponse]:
    comment_exists = session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id))
    if comment_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    rows = session.execute(
        select(FieldCommentAttachment, FileObject)
        .join(FileObject, FieldCommentAttachment.file_object_id == FileObject.id)
        .where(FieldCommentAttachment.comment_id == comment_id)
        .order_by(desc(FieldCommentAttachment.created_at), desc(FieldCommentAttachment.id))
    ).all()
    return [_attachment_response(attachment, file_object) for attachment, file_object in rows]


@router.get("", response_model=list[FieldCommentResponse])
def list_field_comments(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    document_id: Annotated[str | None, Query(alias="documentId")] = None,
    comment_status: Annotated[str | None, Query(alias="status")] = None,
    document_text: Annotated[str | None, Query(alias="documentText")] = None,
    author_text: Annotated[str | None, Query(alias="author")] = None,
    assigned_to: Annotated[str | None, Query(alias="assignedTo")] = None,
    assigned_role: Annotated[str | None, Query(alias="assignedRole")] = None,
    signal_level: Annotated[str | None, Query(alias="signalLevel")] = None,
    channel_text: Annotated[str | None, Query(alias="channel")] = None,
    document_version_id: Annotated[str | None, Query(alias="documentVersionId")] = None,
    review_due_from: Annotated[datetime | None, Query(alias="reviewDueFrom")] = None,
    review_due_to: Annotated[datetime | None, Query(alias="reviewDueTo")] = None,
    tag_text: Annotated[str | None, Query(alias="tag")] = None,
    line_text: Annotated[str | None, Query(alias="line")] = None,
    equipment_text: Annotated[str | None, Query(alias="equipment")] = None,
    process_text: Annotated[str | None, Query(alias="process")] = None,
    error_type_text: Annotated[str | None, Query(alias="errorType")] = None,
    created_from: Annotated[datetime | None, Query(alias="createdFrom")] = None,
    created_to: Annotated[datetime | None, Query(alias="createdTo")] = None,
    old_new_days: Annotated[int | None, Query(alias="oldNewDays", ge=1, le=3650)] = None,
    unreviewed: Annotated[bool | None, Query(alias="unreviewed")] = None,
    overdue: Annotated[bool | None, Query(alias="overdue")] = None,
    unassigned: Annotated[bool | None, Query(alias="unassigned")] = None,
    missing_evidence: Annotated[bool | None, Query(alias="missingEvidence")] = None,
    duplicate_suspected: Annotated[bool | None, Query(alias="duplicateSuspected")] = None,
    conflict: Annotated[bool | None, Query(alias="conflict")] = None,
    priority_min: Annotated[int | None, Query(alias="priorityMin", ge=0)] = None,
    priority_max: Annotated[int | None, Query(alias="priorityMax", ge=0)] = None,
    has_attachments: Annotated[bool | None, Query(alias="hasAttachments")] = None,
    report_linked: Annotated[bool | None, Query(alias="reportLinked")] = None,
    priority_order: Annotated[bool, Query(alias="priorityOrder")] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldCommentResponse]:
    statement = select(FieldComment)
    if document_id is not None:
        statement = statement.where(FieldComment.document_id == document_id)
    if comment_status is not None:
        _validate_choice(comment_status, STATUSES, "status")
        if comment_status == "ASSIGNED":
            statement = statement.where(FieldComment.status == "NEW", FieldComment.assigned_to.is_not(None))
        elif comment_status == "NEW":
            statement = statement.where(FieldComment.status == "NEW", FieldComment.assigned_to.is_(None))
        else:
            statement = statement.where(FieldComment.status == comment_status)
    if document_text := _clean_optional(document_text):
        pattern = f"%{document_text}%"
        document_ids = select(Document.document_id).where(
            Document.deleted_at.is_(None),
            or_(Document.document_id.ilike(pattern), Document.title.ilike(pattern)),
        )
        statement = statement.where(FieldComment.document_id.in_(document_ids))
    if author_text := _clean_optional(author_text):
        pattern = f"%{author_text}%"
        statement = statement.where(
            or_(
                FieldComment.author_id.ilike(pattern),
                FieldComment.reported_by.ilike(pattern),
                FieldComment.operator_id.ilike(pattern),
            )
        )
    if assigned_to := _clean_optional(assigned_to):
        statement = statement.where(FieldComment.assigned_to == assigned_to)
    if assigned_role := _clean_optional(assigned_role):
        assigned_user_ids = select(UserAccount.user_id).where(UserAccount.role == assigned_role)
        statement = statement.where(FieldComment.assigned_to.in_(assigned_user_ids))
    if signal_level := _clean_optional(signal_level):
        statement = statement.where(func.lower(FieldComment.signal_level) == signal_level.lower())
    if document_version_id := _clean_optional(document_version_id):
        statement = statement.where(FieldComment.document_version_id == document_version_id)
    if review_due_from is not None:
        statement = statement.where(FieldComment.review_due_at >= review_due_from)
    if review_due_to is not None:
        statement = statement.where(FieldComment.review_due_at <= review_due_to)
    if channel_text := _clean_optional(channel_text):
        channel_pattern = f"%{channel_text}%"
        linked_comment_ids = select(NotificationChannel.source_id).where(
            NotificationChannel.status == "ACTIVE",
            NotificationChannel.source_type == "FIELD_COMMENT",
            or_(
                NotificationChannel.channel_id.ilike(channel_pattern),
                NotificationChannel.name.ilike(channel_pattern),
                NotificationChannel.channel_type.ilike(channel_pattern),
            ),
        )
        statement = statement.where(FieldComment.comment_id.in_(linked_comment_ids))
    if tag_text := _clean_optional(tag_text):
        pattern = f"%{tag_text}%"
        tagged_document_ids = (
            select(DocumentTag.document_id)
            .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
            .where(
                TagDefinition.is_active.is_(True),
                or_(TagDefinition.name.ilike(pattern), TagDefinition.code.ilike(pattern)),
            )
        )
        statement = statement.where(FieldComment.document_id.in_(tagged_document_ids))
    for tag_type, value in (
        ("line", line_text),
        ("equipment", equipment_text),
        ("process", process_text),
        ("error_type", error_type_text),
    ):
        if cleaned := _clean_optional(value):
            pattern = f"%{cleaned}%"
            matching_documents = (
                select(DocumentTag.document_id)
                .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
                .where(
                    TagDefinition.is_active.is_(True),
                    TagDefinition.tag_type == tag_type,
                    or_(TagDefinition.name.ilike(pattern), TagDefinition.code.ilike(pattern)),
                )
            )
            statement = statement.where(FieldComment.document_id.in_(matching_documents))
    if created_from is not None:
        statement = statement.where(FieldComment.created_at >= created_from)
    if created_to is not None:
        statement = statement.where(FieldComment.created_at <= created_to)
    if old_new_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=old_new_days)
        statement = statement.where(FieldComment.status == "NEW", FieldComment.created_at <= cutoff)
    if unreviewed is not None:
        condition = FieldComment.status.in_({"NEW", "NEEDS_REVIEW"})
        statement = statement.where(condition if unreviewed else ~condition)
    if overdue is not None:
        condition = (
            FieldComment.review_due_at.is_not(None)
            & (FieldComment.review_due_at < datetime.now(timezone.utc))
            & ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"})
        )
        statement = statement.where(condition if overdue else ~condition)
    if unassigned is not None:
        condition = FieldComment.assigned_to.is_(None)
        statement = statement.where(condition if unassigned else ~condition)
    if missing_evidence is not None:
        condition = or_(
            FieldComment.document_version_id.is_(None),
            FieldComment.author_id.is_(None),
            FieldComment.analysis_content.is_(None),
            func.trim(FieldComment.analysis_content) == "",
        )
        statement = statement.where(condition if missing_evidence else ~condition)
    attachment_exists = exists(select(FieldCommentAttachment.id).where(FieldCommentAttachment.comment_id == FieldComment.comment_id))
    if has_attachments is not None:
        statement = statement.where(attachment_exists if has_attachments else ~attachment_exists)
    report_source_exists = exists(
        select(ReportSource.id).where(
            ReportSource.source_type == "FIELD_COMMENT",
            ReportSource.source_id == FieldComment.comment_id,
        )
    )
    if report_linked is not None:
        statement = statement.where(report_source_exists if report_linked else ~report_source_exists)
    if conflict is not None:
        statement = statement.where(FieldComment.conflict_flag.is_(conflict))
    if priority_min is not None:
        statement = statement.where(FieldComment.priority >= priority_min)
    if priority_max is not None:
        statement = statement.where(FieldComment.priority <= priority_max)
    statement = statement.order_by(desc(FieldComment.created_at), desc(FieldComment.id))
    if not priority_order and duplicate_suspected is None:
        statement = statement.limit(limit)
    notes = list(session.scalars(statement).all())
    now = datetime.now(timezone.utc)
    rows = []
    for note in notes:
        flags = _workbench_flags(session, note, now)
        if duplicate_suspected is not None and (("DUPLICATE_SUSPECTED" in flags) != duplicate_suspected):
            continue
        rows.append(_field_comment_response(
            note,
            workbench_flags=flags,
            workbench_priority=_workbench_priority(flags),
            attachment_count=_attachment_count(session, note.comment_id),
            channel_access=_channel_access(session, note, current_user),
            assigned_role=_assigned_role(session, note),
            channel_labels=_channel_labels(session, note),
        ))
    if priority_order:
        rows.sort(
            key=lambda item: (item.workbench_priority, item.created_at, item.comment_id),
            reverse=True,
        )
    return rows[:limit]


@document_field_comments_router.get("/{document_id}/field-comments", response_model=list[FieldCommentResponse])
def list_document_field_comments(
    document_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FieldCommentResponse]:
    document_exists = session.scalar(
        select(Document.id).where(Document.document_id == document_id, Document.deleted_at.is_(None))
    )
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    notes = session.scalars(
        select(FieldComment)
        .where(FieldComment.document_id == document_id)
        .order_by(desc(FieldComment.created_at), desc(FieldComment.id))
        .limit(limit)
    ).all()
    return [_field_comment_response(note) for note in notes]


@router.get("/quality-workbench", response_model=list[FieldCommentQualityItemResponse])
def field_comment_quality_workbench(
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
    aging_days: Annotated[int, Query(alias="agingDays", ge=1, le=3650)] = 7,
) -> list[FieldCommentQualityItemResponse]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=aging_days)
    result: list[FieldCommentQualityItemResponse] = []
    old_notes = session.scalars(
        select(FieldComment).where(FieldComment.status == "NEW", FieldComment.created_at <= cutoff)
    ).all()
    for note in old_notes:
        created = note.created_at.replace(tzinfo=timezone.utc) if note.created_at.tzinfo is None else note.created_at
        result.append(FieldCommentQualityItemResponse(
            issue_type="OLD_NEW",
            comment_id=note.comment_id,
            age_days=max((now - created).days, 0),
            detail="검토 기한 없이 오래 대기한 신규 FieldComment",
        ))

    selected = session.scalars(select(FieldComment).where(FieldComment.status == "SELECTED")).all()
    for note in selected:
        attachment_count = session.scalar(
            select(func.count()).select_from(FieldCommentAttachment).where(
                FieldCommentAttachment.comment_id == note.comment_id
            )
        ) or 0
        audit_count = session.scalar(
            select(func.count()).select_from(ActivityHistory).where(
                ActivityHistory.target_type == "field_comment",
                ActivityHistory.target_id == note.comment_id,
                ActivityHistory.event_type == "field_comment.review_changed",
            )
        ) or 0
        missing = []
        if not note.document_version_id:
            missing.append("문서 버전")
        if not note.author_id:
            missing.append("작성자")
        if not note.analysis_content:
            missing.append("분석")
        if attachment_count == 0:
            missing.append("첨부")
        if audit_count < 3:
            missing.append("단계별 검토 이력")
        if missing:
            result.append(FieldCommentQualityItemResponse(
                issue_type="WEAK_SELECTED",
                comment_id=note.comment_id,
                detail=f"SELECTED 근거 보강 필요: {', '.join(missing)}",
            ))

    sources = session.scalars(select(ReportSource).where(ReportSource.source_type == "FIELD_COMMENT")).all()
    for source in sources:
        source_comment = session.scalar(
            select(FieldComment).where(FieldComment.comment_id == source.source_id)
        )
        if source_comment is None:
            result.append(FieldCommentQualityItemResponse(
                issue_type="MISSING_REPORT_SOURCE",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서 source가 존재하지 않는 FieldComment를 참조함",
            ))
            continue
        if not source.trace_id or not source.source_version_id or source.source_revision is None:
            result.append(FieldCommentQualityItemResponse(
                issue_type="INCOMPLETE_REPORT_TRACE",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서 source의 trace ID, 관찰 문서 버전 또는 선정 revision이 누락됨",
            ))
        if source.source_hash_sha256 != _source_hash(source_comment):
            result.append(FieldCommentQualityItemResponse(
                issue_type="SOURCE_HASH_MISMATCH",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서에 고정한 원천 hash와 현재 FieldComment 원천 hash가 다름",
            ))
        if source.source_revision is not None and source.source_revision != source_comment.review_revision:
            result.append(FieldCommentQualityItemResponse(
                issue_type="SOURCE_REVISION_MISMATCH",
                comment_id=source.source_id,
                report_id=source.report_id,
                detail="보고서에 고정한 선정 revision과 현재 FieldComment 검토 revision이 다름",
            ))
    return result


@router.get("/quality-metrics")
def field_comment_quality_metrics(
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict:
    def distribution(column) -> dict[str, int]:
        return {str(key or "(없음)"): count for key, count in session.execute(
            select(column, func.count()).group_by(column).order_by(column)
        ).all()}

    total = session.scalar(select(func.count()).select_from(FieldComment)) or 0
    logical_status_distribution = dict(sorted(Counter(
        "ASSIGNED" if row.status == "NEW" and _clean_optional(row.assigned_to) else row.status
        for row in session.scalars(select(FieldComment)).all()
    ).items()))
    now = datetime.now(timezone.utc)
    overdue_count = session.scalar(select(func.count()).select_from(FieldComment).where(
        FieldComment.review_due_at.is_not(None),
        FieldComment.review_due_at < now,
        ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"}),
    )) or 0
    unassigned_count = session.scalar(select(func.count()).select_from(FieldComment).where(
        FieldComment.assigned_to.is_(None),
        ~FieldComment.status.in_({"SELECTED", "EXCLUDED", "ARCHIVED"}),
    )) or 0
    linked = session.scalar(
        select(func.count(func.distinct(ReportSource.source_id))).where(
            ReportSource.source_type == "FIELD_COMMENT"
        )
    ) or 0
    document_total = session.scalar(
        select(func.count()).select_from(Document).where(Document.deleted_at.is_(None))
    ) or 0
    documents_with_comments = session.scalar(
        select(func.count(func.distinct(FieldComment.document_id))).where(FieldComment.document_id.is_not(None))
    ) or 0
    source_type_count = session.scalar(
        select(func.count(func.distinct(ReportSource.source_type)))
    ) or 0
    report_total = session.scalar(select(func.count()).select_from(Report)) or 0
    multi_source_reports = session.scalar(
        select(func.count()).select_from(
            select(ReportSource.report_id)
            .group_by(ReportSource.report_id)
            .having(func.count(func.distinct(ReportSource.source_type)) >= 2)
            .subquery()
        )
    ) or 0
    work_sequence_source_count = session.scalar(
        select(func.count()).select_from(ReportSource).where(
            ReportSource.source_type.in_({"WORK_SEQUENCE_ITEM", "WORK_SEQUENCE_HISTORY"})
        )
    ) or 0
    report_source_total = session.scalar(select(func.count()).select_from(ReportSource)) or 0
    def source_origin_exists(source: ReportSource) -> bool:
        model_and_key = {
            "FIELD_COMMENT": (FieldComment, FieldComment.comment_id),
            "DOCUMENT": (Document, Document.document_id),
            "WORK_SEQUENCE_ITEM": (WorkSequenceItem, WorkSequenceItem.item_id),
            "WORK_SEQUENCE_HISTORY": (WorkSequenceChangeHistory, WorkSequenceChangeHistory.change_id),
            "WORK_RECORD": (WorkRecord, WorkRecord.work_record_id),
            "WORK_RECORD_VERSION": (WorkRecordVersion, WorkRecordVersion.version_id),
        }.get(source.source_type)
        if model_and_key is None:
            return False
        model, key = model_and_key
        return session.scalar(select(func.count()).select_from(model).where(key == source.source_id)) > 0

    report_sources = session.scalars(select(ReportSource)).all()
    orphan_count = sum(
        1
        for source in report_sources
        if session.scalar(select(Report.id).where(Report.report_id == source.report_id)) is None
        or not source_origin_exists(source)
    )
    incomplete_trace_count = sum(
        1 for source in report_sources
        if not source.trace_id or not source.source_version_id or not source.source_hash_sha256
        or (source.source_type == "FIELD_COMMENT" and source.source_revision is None)
    )
    field_comment_hash_mismatch_count = 0
    field_comment_revision_mismatch_count = 0
    for source in report_sources:
        if source.source_type != "FIELD_COMMENT" or not source.source_hash_sha256:
            continue
        comment = session.scalar(
            select(FieldComment).where(FieldComment.comment_id == source.source_id)
        )
        if comment is not None and source.source_hash_sha256 != _source_hash(comment):
            field_comment_hash_mismatch_count += 1
        if comment is not None and source.source_revision is not None and source.source_revision != comment.review_revision:
            field_comment_revision_mismatch_count += 1
    duplicate_report_source_count = session.scalar(
        select(func.count()).select_from(
            select(ReportSource.report_id)
            .group_by(
                ReportSource.report_id,
                ReportSource.source_type,
                ReportSource.source_id,
                ReportSource.source_version_id,
            )
            .having(func.count() > 1)
            .subquery()
        )
    ) or 0
    tag_axis_coverage: dict[str, dict[str, int | float]] = {}
    for axis in ("line", "equipment", "item", "process", "error_type"):
        tagged_documents = session.scalar(
            select(func.count(func.distinct(DocumentTag.document_id)))
            .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
            .where(TagDefinition.is_active.is_(True), TagDefinition.tag_type == axis)
        ) or 0
        tag_axis_coverage[axis] = {
            "document_count": tagged_documents,
            "document_rate": round(tagged_documents / document_total, 4) if document_total else 0.0,
        }
    return {
        "total": total,
        "status_distribution": logical_status_distribution,
        "sla": {"overdue_count": overdue_count, "unassigned_active_count": unassigned_count},
        "signal_distribution": distribution(FieldComment.signal_level),
        "actor_distribution": distribution(FieldComment.author_id),
        "line_distribution": distribution(FieldComment.location_code),
        "error_type_distribution": distribution(FieldComment.category),
        "report_linked_count": linked,
        "report_link_rate": round(linked / total, 4) if total else 0.0,
        "connection_quality": {
            "document_total": document_total,
            "documents_with_field_comments": documents_with_comments,
            "document_field_comment_rate": round(documents_with_comments / document_total, 4) if document_total else 0.0,
            "field_comment_total": total,
            "field_comments_linked_to_reports": linked,
            "field_comment_report_rate": round(linked / total, 4) if total else 0.0,
            "work_sequence_report_source_count": work_sequence_source_count,
            "report_total": report_total,
            "reports_with_two_or_more_source_types": multi_source_reports,
            "multi_source_report_rate": round(multi_source_reports / report_total, 4) if report_total else 0.0,
            "report_source_total": report_source_total,
            "report_source_type_count": source_type_count,
            "orphan_report_source_count": orphan_count,
            "orphan_report_source_rate": round(orphan_count / report_source_total, 4) if report_source_total else 0.0,
            "incomplete_report_trace_count": incomplete_trace_count,
            "field_comment_source_hash_mismatch_count": field_comment_hash_mismatch_count,
            "field_comment_source_revision_mismatch_count": field_comment_revision_mismatch_count,
            "duplicate_report_source_count": duplicate_report_source_count,
        },
        "tag_axis_coverage": tag_axis_coverage,
    }


def _audit_responses(session: Session, comment_id: str) -> list[FieldCommentAuditResponse]:
    rows = session.scalars(
        select(ActivityHistory).where(
            ActivityHistory.target_type == "field_comment",
            ActivityHistory.target_id == comment_id,
        ).order_by(ActivityHistory.created_at, ActivityHistory.id)
    ).all()
    return [FieldCommentAuditResponse(
        history_id=row.history_id,
        event_type=row.event_type,
        actor_id=row.actor_id,
        before_snapshot=json.loads(row.before_value) if row.before_value else None,
        after_snapshot=json.loads(row.after_value) if row.after_value else None,
        change_reason=row.change_reason,
        created_at=row.created_at,
    ) for row in rows]


@router.get("/{comment_id}/traceability", response_model=FieldCommentTraceResponse)
def get_field_comment_traceability(
    comment_id: str,
    current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentTraceResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=404, detail="Field comment not found.")
    source_rows = session.execute(
        select(ReportSource, Report)
        .join(Report, Report.report_id == ReportSource.report_id)
        .where(ReportSource.source_type == "FIELD_COMMENT", ReportSource.source_id == comment_id)
        .order_by(Report.created_at, Report.report_id)
    ).all()
    reports: list[FieldCommentTraceReportResponse] = []
    for source, report in source_rows:
        document_response = None
        if report.generated_document_id:
            document = session.scalar(
                select(Document).where(Document.document_id == report.generated_document_id)
            )
            if document is not None:
                version_ids = list(session.scalars(
                    select(DocumentVersion.version_id)
                    .where(DocumentVersion.document_id == document.document_id)
                    .order_by(DocumentVersion.version_no)
                ).all())
                document_response = FieldCommentTraceDocumentResponse(
                    document_id=document.document_id,
                    title=document.title,
                    status=document.status,
                    latest_version_id=document.latest_version_id,
                    published_version_id=document.published_version_id,
                    generated_version_ids=version_ids,
                )
        reports.append(FieldCommentTraceReportResponse(
            report_id=report.report_id,
            report_type=report.report_type,
            title=report.title,
            status="SUPERSEDED" if report.superseded_by_report_id else report.status,
            relation_type=source.relation_type,
            source_version_id=source.source_version_id,
            source_revision=source.source_revision,
            source_hash_sha256=source.source_hash_sha256,
            trace_id=source.trace_id,
            generated_document=document_response,
        ))
    source_document = None
    if note.document_id:
        document = session.scalar(select(Document).where(Document.document_id == note.document_id))
        if document is not None:
            version_ids = list(session.scalars(
                select(DocumentVersion.version_id)
                .where(DocumentVersion.document_id == document.document_id)
                .order_by(DocumentVersion.version_no)
            ).all())
            source_document = FieldCommentTraceDocumentResponse(
                document_id=document.document_id,
                title=document.title,
                status=document.status,
                latest_version_id=document.latest_version_id,
                published_version_id=document.published_version_id,
                generated_version_ids=version_ids,
                observed_version_id=note.document_version_id,
            )
    attachment_rows = session.execute(
        select(FieldCommentAttachment, FileObject)
        .join(FileObject, FieldCommentAttachment.file_object_id == FileObject.id)
        .where(FieldCommentAttachment.comment_id == comment_id)
        .order_by(FieldCommentAttachment.created_at, FieldCommentAttachment.id)
    ).all()
    work_sequence_rows = []
    if note.source_type == "WORK_SEQUENCE_ITEM" and note.source_id:
        work_sequence_rows = session.execute(
            select(WorkSequenceItem, WorkSequenceBoard)
            .join(WorkSequenceBoard, WorkSequenceBoard.board_id == WorkSequenceItem.board_id)
            .where(WorkSequenceItem.item_id == note.source_id)
        ).all()
    elif note.document_id:
        work_sequence_rows = session.execute(
            select(WorkSequenceItem, WorkSequenceBoard)
            .join(WorkSequenceBoard, WorkSequenceBoard.board_id == WorkSequenceItem.board_id)
            .where(WorkSequenceItem.document_id == note.document_id)
            .order_by(WorkSequenceBoard.board_date, WorkSequenceItem.sort_order, WorkSequenceItem.item_id)
        ).all()
    flags = _workbench_flags(session, note, datetime.now(timezone.utc))
    return FieldCommentTraceResponse(
        field_comment=_field_comment_response(
            note,
            workbench_flags=flags,
            workbench_priority=_workbench_priority(flags),
            attachment_count=len(attachment_rows),
            channel_access=_channel_access(session, note, current_user),
            assigned_role=_assigned_role(session, note),
            channel_labels=_channel_labels(session, note),
        ),
        source_document=source_document,
        attachments=[_attachment_response(attachment, file_object) for attachment, file_object in attachment_rows],
        audit=_audit_responses(session, comment_id),
        work_sequences=[FieldCommentTraceWorkSequenceResponse(
            board_id=board.board_id,
            board_title=board.title,
            item_id=item.item_id,
            item_title=item.title,
            status=item.status,
            assigned_to=item.assigned_to,
            document_id=item.document_id,
        ) for item, board in work_sequence_rows],
        reports=reports,
    )


@router.get("/{comment_id}/audit", response_model=list[FieldCommentAuditResponse])
def list_field_comment_audit(
    comment_id: str,
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentAuditResponse]:
    if session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id)) is None:
        raise HTTPException(status_code=404, detail="Field comment not found.")
    return _audit_responses(session, comment_id)


@router.get("/{comment_id}", response_model=FieldCommentResponse)
def get_field_comment(
    comment_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    note = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")
    return _field_comment_response(
        note,
        attachment_count=_attachment_count(session, note.comment_id),
        channel_access=_channel_access(session, note, current_user),
        assigned_role=_assigned_role(session, note),
        channel_labels=_channel_labels(session, note),
    )
