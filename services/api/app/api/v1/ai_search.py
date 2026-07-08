from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.models import (
    AISearchCandidate,
    Document,
    DocumentVersion,
    FieldComment,
    Report,
    ReportSource,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/ai-search", tags=["ai-search"], dependencies=[Depends(get_current_user)])

FIELD_COMMENT_REVIEWED_STATUSES = {"ANALYZED", "REVIEWED", "SELECTED"}
FIELD_COMMENT_EXCLUDED_STATUSES = {"EXCLUDED", "ARCHIVED"}
FIELD_COMMENT_EXCLUDED_INPUT_MODES = {"mes_integration"}
FIELD_COMMENT_REVIEWED_MINIMUM = 100
AI_SEARCH_SOURCE_TYPES = (
    "PUBLISHED_DOCUMENT_VERSION",
    "FIELD_COMMENT",
    "WORK_SEQUENCE_HISTORY",
    "REPORT_SOURCE",
)
EXCLUDED_REASON_GUIDANCE = {
    "document_version_not_published": {
        "label": "공개 문서 버전 미충족",
        "operator_action": "문서 상태와 공개 버전을 확인하고 현장 사용 가능 버전을 publish한다.",
        "source_type": "PUBLISHED_DOCUMENT_VERSION",
    },
    "field_comment_excluded_status": {
        "label": "FieldComment 보관/제외",
        "operator_action": "보관 또는 제외 처리된 FieldComment가 의도한 결정인지 검토한다.",
        "source_type": "FIELD_COMMENT",
    },
    "field_comment_mes_integration": {
        "label": "FieldComment MES 통합 입력 제외",
        "operator_action": "MES/ERP 어댑터 정책 확정 전에는 수동 검토 FieldComment를 우선 축적한다.",
        "source_type": "FIELD_COMMENT",
    },
    "field_comment_without_content": {
        "label": "FieldComment 빈 내용",
        "operator_action": "원문, 정리 내용, 분석 내용 중 하나를 채우거나 검토 대상에서 제외한다.",
        "source_type": "FIELD_COMMENT",
    },
    "work_sequence_history_without_trace_text": {
        "label": "작업순서 이력 텍스트 없음",
        "operator_action": "변경 전/후 값 또는 변경 사유가 남도록 작업순서 변경 기록 방식을 점검한다.",
        "source_type": "WORK_SEQUENCE_HISTORY",
    },
    "report_source_missing_report": {
        "label": "보고서 source의 보고서 누락",
        "operator_action": "report_sources의 report_id가 실제 보고서와 연결되는지 정리한다.",
        "source_type": "REPORT_SOURCE",
    },
    "report_source_archived_report": {
        "label": "보관 보고서 source 제외",
        "operator_action": "보관된 보고서를 후보로 쓸 필요가 있으면 보고서 상태를 먼저 검토한다.",
        "source_type": "REPORT_SOURCE",
    },
    "report_source_without_trace_id": {
        "label": "보고서 source 식별자 누락",
        "operator_action": "source_type과 source_id가 비어 있는 보고서 근거를 보완하거나 삭제한다.",
        "source_type": "REPORT_SOURCE",
    },
    "report_source_missing_origin": {
        "label": "보고서 source 원천 누락",
        "operator_action": "보고서 근거가 가리키는 문서, FieldComment, 작업순서 이력 row를 복구하거나 source를 정리한다.",
        "source_type": "REPORT_SOURCE",
    },
}


class AISearchCandidateResponse(BaseModel):
    candidate_id: str
    source_type: str
    source_id: str
    source_version_id: str | None
    trace_table: str
    trace_id: str
    trace_version_id: str | None
    parent_type: str | None
    parent_id: str | None
    title: str
    summary: str | None
    review_status: str | None
    refreshed_at: datetime


class AISearchRebuildResponse(BaseModel):
    candidate_count: int
    counts_by_source_type: dict[str, int]
    excluded_counts_by_reason: dict[str, int]
    excluded_reason_guidance: dict[str, dict[str, str]]
    rebuilt_at: datetime


class FieldCommentReviewReadinessResponse(BaseModel):
    total_count: int
    counts_by_status: dict[str, int]
    reviewed_status_count: int
    required_reviewed_count: int
    missing_reviewed_count: int
    reviewed_ratio: float


class AISearchQualityResponse(BaseModel):
    candidate_count: int
    counts_by_source_type: dict[str, int]
    excluded_counts_by_reason: dict[str, int]
    excluded_reason_guidance: dict[str, dict[str, str]]
    field_comment_review_readiness: FieldCommentReviewReadinessResponse


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_text(*values: str | None) -> str:
    parts = [value.strip() for value in values if value is not None and value.strip()]
    return "\n".join(parts)


def _field_comment_content_text(comment: FieldComment) -> str:
    return _clean_text(comment.normalized_content, comment.raw_content, comment.analysis_content)


def _work_sequence_history_trace_text(history: WorkSequenceChangeHistory) -> str:
    return _clean_text(history.before_value, history.after_value, history.change_reason)


def _candidate_response(candidate: AISearchCandidate) -> AISearchCandidateResponse:
    return AISearchCandidateResponse(
        candidate_id=candidate.candidate_id,
        source_type=candidate.source_type,
        source_id=candidate.source_id,
        source_version_id=candidate.source_version_id,
        trace_table=candidate.trace_table,
        trace_id=candidate.trace_id,
        trace_version_id=candidate.trace_version_id,
        parent_type=candidate.parent_type,
        parent_id=candidate.parent_id,
        title=candidate.title,
        summary=candidate.summary,
        review_status=candidate.review_status,
        refreshed_at=candidate.refreshed_at,
    )


def _add_candidate(
    session: Session,
    *,
    source_type: str,
    source_id: str,
    source_version_id: str | None,
    trace_table: str,
    trace_id: str,
    trace_version_id: str | None = None,
    parent_type: str | None = None,
    parent_id: str | None = None,
    title: str,
    summary: str | None = None,
    search_text: str,
    review_status: str | None = None,
    metadata: dict[str, str | int | bool | None] | None = None,
    refreshed_at: datetime,
) -> None:
    session.add(
        AISearchCandidate(
            candidate_id=_new_public_id("aisrc"),
            source_type=source_type,
            source_id=source_id,
            source_version_id=source_version_id,
            trace_table=trace_table,
            trace_id=trace_id,
            trace_version_id=trace_version_id,
            parent_type=parent_type,
            parent_id=parent_id,
            title=title,
            summary=summary,
            search_text=search_text,
            review_status=review_status,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            refreshed_at=refreshed_at,
        )
    )


def _published_document_rows(session: Session) -> list[tuple[Document, DocumentVersion]]:
    return session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.document_id)
        .where(
            Document.status == "PUBLISHED",
            Document.deleted_at.is_(None),
            Document.published_version_id == DocumentVersion.version_id,
            DocumentVersion.version_status == "PUBLISHED",
            DocumentVersion.is_published.is_(True),
        )
        .order_by(desc(DocumentVersion.created_at), desc(DocumentVersion.id))
    ).all()


def _field_comment_rows(session: Session) -> list[FieldComment]:
    return session.scalars(
        select(FieldComment)
        .where(
            FieldComment.status.not_in(FIELD_COMMENT_EXCLUDED_STATUSES),
            FieldComment.input_mode.not_in(FIELD_COMMENT_EXCLUDED_INPUT_MODES),
        )
        .order_by(desc(FieldComment.created_at), desc(FieldComment.id))
    ).all()


def _work_sequence_history_rows(session: Session) -> list[WorkSequenceChangeHistory]:
    return session.scalars(
        select(WorkSequenceChangeHistory).order_by(
            desc(WorkSequenceChangeHistory.created_at),
            desc(WorkSequenceChangeHistory.id),
        )
    ).all()


def _report_source_rows(session: Session) -> list[tuple[ReportSource, Report]]:
    return session.execute(
        select(ReportSource, Report)
        .join(Report, Report.report_id == ReportSource.report_id)
        .where(
            Report.status != "ARCHIVED",
            func.trim(func.coalesce(ReportSource.source_type, "")) != "",
            func.trim(func.coalesce(ReportSource.source_id, "")) != "",
        )
        .order_by(desc(ReportSource.created_at), desc(ReportSource.id))
    ).all()


def _report_source_origin_exists(session: Session, source: ReportSource) -> bool:
    source_type = source.source_type.strip().upper()
    source_id = source.source_id.strip()
    if source_type == "FIELD_COMMENT":
        return session.scalar(
            select(func.count())
            .select_from(FieldComment)
            .where(
                FieldComment.comment_id == source_id,
                FieldComment.status.not_in(FIELD_COMMENT_EXCLUDED_STATUSES),
                FieldComment.input_mode.not_in(FIELD_COMMENT_EXCLUDED_INPUT_MODES),
            )
        ) > 0
    if source_type == "DOCUMENT":
        statement = select(func.count()).select_from(Document).where(Document.document_id == source_id)
        if source.source_version_id:
            statement = (
                select(func.count())
                .select_from(DocumentVersion)
                .where(
                    DocumentVersion.document_id == source_id,
                    DocumentVersion.version_id == source.source_version_id,
                )
            )
        return session.scalar(statement) > 0
    if source_type == "WORK_SEQUENCE_ITEM":
        return session.scalar(
            select(func.count()).select_from(WorkSequenceItem).where(WorkSequenceItem.item_id == source_id)
        ) > 0
    if source_type == "WORK_SEQUENCE_HISTORY":
        return session.scalar(
            select(func.count())
            .select_from(WorkSequenceChangeHistory)
            .where(WorkSequenceChangeHistory.change_id == source_id)
        ) > 0
    if source_type == "WORK_RECORD":
        return session.scalar(
            select(func.count()).select_from(WorkRecord).where(WorkRecord.work_record_id == source_id)
        ) > 0
    if source_type == "WORK_RECORD_VERSION":
        return session.scalar(
            select(func.count())
            .select_from(WorkRecordVersion)
            .where(WorkRecordVersion.version_id == source_id)
        ) > 0
    return False


def _report_source_text(source: ReportSource, report: Report) -> str:
    return _clean_text(
        report.title,
        report.summary,
        report.analysis_content,
        report.conclusion,
        report.action_plan,
        f"{source.source_type}: {source.source_id}",
        source.source_version_id,
        source.relation_type,
    )


def rebuild_ai_search_candidates(session: Session) -> AISearchRebuildResponse:
    refreshed_at = datetime.now(timezone.utc)
    session.query(AISearchCandidate).delete(synchronize_session=False)

    for document, version in _published_document_rows(session):
        search_text = _clean_text(
            document.title,
            document.description,
            version.version_label,
            version.change_reason,
        )
        _add_candidate(
            session,
            source_type="PUBLISHED_DOCUMENT_VERSION",
            source_id=document.document_id,
            source_version_id=version.version_id,
            trace_table="document_versions",
            trace_id=document.document_id,
            trace_version_id=version.version_id,
            parent_type="DOCUMENT",
            parent_id=document.document_id,
            title=document.title,
            summary=version.change_reason,
            search_text=search_text,
            review_status=version.version_status,
            metadata={
                "document_type": document.document_type,
                "version_no": version.version_no,
                "is_published": version.is_published,
            },
            refreshed_at=refreshed_at,
        )

    for comment in _field_comment_rows(session):
        content_text = _field_comment_content_text(comment)
        if not content_text:
            continue
        search_text = _clean_text(content_text, comment.category, comment.signal_level)
        _add_candidate(
            session,
            source_type="FIELD_COMMENT",
            source_id=comment.comment_id,
            source_version_id=comment.document_version_id,
            trace_table="field_comments",
            trace_id=comment.comment_id,
            trace_version_id=comment.document_version_id,
            parent_type="DOCUMENT" if comment.document_id else "WORK_RECORD",
            parent_id=comment.document_id or comment.work_record_id,
            title=comment.category or comment.comment_type,
            summary=comment.normalized_content or comment.raw_content,
            search_text=search_text,
            review_status=comment.status,
            metadata={
                "document_id": comment.document_id,
                "work_record_id": comment.work_record_id,
                "input_mode": comment.input_mode,
                "entry_source": comment.entry_source,
            },
            refreshed_at=refreshed_at,
        )

    for history in _work_sequence_history_rows(session):
        trace_text = _work_sequence_history_trace_text(history)
        if not trace_text:
            continue
        search_text = _clean_text(history.change_type, trace_text)
        _add_candidate(
            session,
            source_type="WORK_SEQUENCE_HISTORY",
            source_id=history.change_id,
            source_version_id=None,
            trace_table="work_sequence_change_history",
            trace_id=history.change_id,
            parent_type="WORK_SEQUENCE_ITEM" if history.item_id else "WORK_SEQUENCE_BOARD",
            parent_id=history.item_id or history.board_id,
            title=history.change_type,
            summary=history.change_reason,
            search_text=search_text,
            metadata={
                "board_id": history.board_id,
                "item_id": history.item_id,
                "actor_id": history.actor_id,
            },
            refreshed_at=refreshed_at,
        )

    for source, report in _report_source_rows(session):
        if not _report_source_origin_exists(session, source):
            continue
        source_row_id = str(source.id)
        _add_candidate(
            session,
            source_type="REPORT_SOURCE",
            source_id=source_row_id,
            source_version_id=source.source_version_id,
            trace_table="report_sources",
            trace_id=source_row_id,
            trace_version_id=source.source_version_id,
            parent_type="REPORT",
            parent_id=report.report_id,
            title=report.title,
            summary=source.relation_type,
            search_text=_report_source_text(source, report),
            review_status=report.status,
            metadata={
                "report_id": report.report_id,
                "report_source_type": source.source_type,
                "report_source_id": source.source_id,
                "generated_document_id": report.generated_document_id,
            },
            refreshed_at=refreshed_at,
        )

    session.commit()
    return AISearchRebuildResponse(
        candidate_count=_candidate_count(session),
        counts_by_source_type=_candidate_counts_by_source_type(session),
        excluded_counts_by_reason=_excluded_counts_by_reason(session),
        excluded_reason_guidance=EXCLUDED_REASON_GUIDANCE,
        rebuilt_at=refreshed_at,
    )


def _candidate_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AISearchCandidate)) or 0


def _candidate_counts_by_source_type(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(AISearchCandidate.source_type, func.count())
        .group_by(AISearchCandidate.source_type)
        .order_by(AISearchCandidate.source_type)
    ).all()
    counts = {source_type: 0 for source_type in AI_SEARCH_SOURCE_TYPES}
    counts.update({source_type: count for source_type, count in rows})
    return counts


def _excluded_counts_by_reason(session: Session) -> dict[str, int]:
    eligible_document_versions = session.scalar(
        select(func.count())
        .select_from(DocumentVersion)
        .join(Document, DocumentVersion.document_id == Document.document_id)
        .where(
            Document.status == "PUBLISHED",
            Document.deleted_at.is_(None),
            Document.published_version_id == DocumentVersion.version_id,
            DocumentVersion.version_status == "PUBLISHED",
            DocumentVersion.is_published.is_(True),
        )
    ) or 0
    total_document_versions = session.scalar(select(func.count()).select_from(DocumentVersion)) or 0
    field_comments_excluded = session.scalar(
        select(func.count())
        .select_from(FieldComment)
        .where(FieldComment.status.in_(FIELD_COMMENT_EXCLUDED_STATUSES))
    ) or 0
    field_comments_mes_integration = session.scalar(
        select(func.count())
        .select_from(FieldComment)
        .where(
            FieldComment.status.not_in(FIELD_COMMENT_EXCLUDED_STATUSES),
            FieldComment.input_mode.in_(FIELD_COMMENT_EXCLUDED_INPUT_MODES),
        )
    ) or 0
    field_comments_empty = session.scalar(
        select(func.count())
        .select_from(FieldComment)
        .where(
            FieldComment.status.not_in(FIELD_COMMENT_EXCLUDED_STATUSES),
            FieldComment.input_mode.not_in(FIELD_COMMENT_EXCLUDED_INPUT_MODES),
            func.trim(func.coalesce(FieldComment.raw_content, "")) == "",
            func.trim(func.coalesce(FieldComment.normalized_content, "")) == "",
            func.trim(func.coalesce(FieldComment.analysis_content, "")) == "",
        )
    ) or 0
    work_sequence_history_empty = session.scalar(
        select(func.count())
        .select_from(WorkSequenceChangeHistory)
        .where(
            func.trim(func.coalesce(WorkSequenceChangeHistory.before_value, "")) == "",
            func.trim(func.coalesce(WorkSequenceChangeHistory.after_value, "")) == "",
            func.trim(func.coalesce(WorkSequenceChangeHistory.change_reason, "")) == "",
        )
    ) or 0
    report_sources_missing_report = session.scalar(
        select(func.count())
        .select_from(ReportSource)
        .outerjoin(Report, ReportSource.report_id == Report.report_id)
        .where(Report.id.is_(None))
    ) or 0
    report_sources_archived_report = session.scalar(
        select(func.count())
        .select_from(ReportSource)
        .join(Report, ReportSource.report_id == Report.report_id)
        .where(Report.status == "ARCHIVED")
    ) or 0
    report_sources_blank_trace = session.scalar(
        select(func.count())
        .select_from(ReportSource)
        .where(
            or_(
                func.trim(func.coalesce(ReportSource.source_type, "")) == "",
                func.trim(func.coalesce(ReportSource.source_id, "")) == "",
            )
        )
    ) or 0
    report_sources_missing_origin = 0
    for source, report in _report_source_rows(session):
        if report.status == "ARCHIVED":
            continue
        if not _report_source_origin_exists(session, source):
            report_sources_missing_origin += 1

    return {
        "document_version_not_published": max(total_document_versions - eligible_document_versions, 0),
        "field_comment_excluded_status": field_comments_excluded,
        "field_comment_mes_integration": field_comments_mes_integration,
        "field_comment_without_content": field_comments_empty,
        "work_sequence_history_without_trace_text": work_sequence_history_empty,
        "report_source_missing_report": report_sources_missing_report,
        "report_source_archived_report": report_sources_archived_report,
        "report_source_without_trace_id": report_sources_blank_trace,
        "report_source_missing_origin": report_sources_missing_origin,
    }


def _field_comment_review_readiness(session: Session) -> FieldCommentReviewReadinessResponse:
    rows = session.execute(
        select(FieldComment.status, func.count()).group_by(FieldComment.status).order_by(FieldComment.status)
    ).all()
    counts_by_status = {status: count for status, count in rows}
    total_count = sum(counts_by_status.values())
    reviewed_status_count = sum(
        count for status, count in counts_by_status.items() if status in FIELD_COMMENT_REVIEWED_STATUSES
    )
    missing_reviewed_count = max(FIELD_COMMENT_REVIEWED_MINIMUM - reviewed_status_count, 0)
    reviewed_ratio = reviewed_status_count / total_count if total_count else 0.0
    return FieldCommentReviewReadinessResponse(
        total_count=total_count,
        counts_by_status=counts_by_status,
        reviewed_status_count=reviewed_status_count,
        required_reviewed_count=FIELD_COMMENT_REVIEWED_MINIMUM,
        missing_reviewed_count=missing_reviewed_count,
        reviewed_ratio=round(reviewed_ratio, 4),
    )


def _quality_response(session: Session) -> AISearchQualityResponse:
    return AISearchQualityResponse(
        candidate_count=_candidate_count(session),
        counts_by_source_type=_candidate_counts_by_source_type(session),
        excluded_counts_by_reason=_excluded_counts_by_reason(session),
        excluded_reason_guidance=EXCLUDED_REASON_GUIDANCE,
        field_comment_review_readiness=_field_comment_review_readiness(session),
    )


@router.post("/candidates/rebuild", response_model=AISearchRebuildResponse)
def rebuild_candidates(
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> AISearchRebuildResponse:
    return rebuild_ai_search_candidates(session)


@router.get("/candidates", response_model=list[AISearchCandidateResponse])
def list_candidates(
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
    source_type: Annotated[str | None, Query(alias="sourceType")] = None,
    source_id: Annotated[str | None, Query(alias="sourceId")] = None,
    limit: int = 100,
) -> list[AISearchCandidateResponse]:
    statement = select(AISearchCandidate).order_by(
        desc(AISearchCandidate.refreshed_at),
        desc(AISearchCandidate.id),
    )
    if source_type is not None:
        statement = statement.where(AISearchCandidate.source_type == source_type.strip().upper())
    if source_id is not None and source_id.strip():
        statement = statement.where(AISearchCandidate.source_id == source_id.strip())
    rows = session.scalars(statement.limit(min(max(limit, 1), 500))).all()
    return [_candidate_response(candidate) for candidate in rows]


@router.get("/quality", response_model=AISearchQualityResponse)
def get_quality(
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> AISearchQualityResponse:
    return _quality_response(session)
