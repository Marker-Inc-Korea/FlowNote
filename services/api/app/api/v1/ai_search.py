from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.models import (
    AISearchCandidate,
    AISearchEvaluationCase,
    AISearchEvaluationRun,
    Document,
    DocumentVersion,
    FieldComment,
    Report,
    ReportSource,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
    NotificationChannel,
    NotificationChannelMember,
    UserAccount,
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
    content_hash: str
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
    latest_evaluation: dict[str, object] | None = None


class AISearchEvidenceReference(BaseModel):
    candidate_id: str | None = Field(default=None, alias="candidateId")
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    trace_id: str | None = Field(default=None, alias="traceId")
    trace_version_id: str | None = Field(default=None, alias="traceVersionId")
    exclusion_reason: str | None = Field(default=None, alias="exclusionReason")


class AISearchEvaluationCaseRequest(BaseModel):
    case_key: str = Field(alias="caseKey", min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    expected_outcome: str = Field(alias="expectedOutcome")
    expected_evidence: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedEvidence")
    expected_excluded: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedExcluded")
    limit: int = Field(default=20, ge=1, le=100)


class AISearchEvaluationRequest(BaseModel):
    run_label: str = Field(alias="runLabel", min_length=1, max_length=160)
    evaluate_as_user_id: str | None = Field(default=None, alias="evaluateAsUserId")
    cases: list[AISearchEvaluationCaseRequest] = Field(min_length=1, max_length=100)


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_public_id(source_type: str, source_id: str, source_version_id: str | None) -> str:
    identity = json.dumps([source_type, source_id, source_version_id], ensure_ascii=False, separators=(",", ":"))
    return f"aisrc_{_hash(identity)[:48]}"


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
        content_hash=candidate.content_hash,
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
            candidate_id=_candidate_public_id(source_type, source_id, source_version_id),
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
            content_hash=_hash(search_text),
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
        statement = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.document_id == source_id,
                Document.deleted_at.is_(None),
                Document.status != "DELETED",
            )
        )
        if source.source_version_id:
            statement = (
                select(func.count())
                .select_from(DocumentVersion)
                .join(Document, Document.document_id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.document_id == source_id,
                    DocumentVersion.version_id == source.source_version_id,
                    Document.deleted_at.is_(None),
                    Document.status != "DELETED",
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
    latest_run = session.scalar(
        select(AISearchEvaluationRun).order_by(desc(AISearchEvaluationRun.created_at), desc(AISearchEvaluationRun.id))
    )
    return AISearchQualityResponse(
        candidate_count=_candidate_count(session),
        counts_by_source_type=_candidate_counts_by_source_type(session),
        excluded_counts_by_reason=_excluded_counts_by_reason(session),
        excluded_reason_guidance=EXCLUDED_REASON_GUIDANCE,
        field_comment_review_readiness=_field_comment_review_readiness(session),
        latest_evaluation=(
            {
                "run_id": latest_run.run_id,
                "run_label": latest_run.run_label,
                "status": latest_run.status,
                "candidate_identity_stable": latest_run.candidate_identity_stable,
                "ranking_stable": latest_run.ranking_stable,
                **json.loads(latest_run.metrics_json),
            }
            if latest_run is not None
            else None
        ),
    )


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_-]+", value)}


def _candidate_rank(
    candidate: AISearchCandidate,
    question_tokens: set[str],
    document_frequency: dict[str, int],
) -> float:
    search = candidate.search_text.lower()
    title = candidate.title.lower()
    return sum(
        (3.0 if token in title else 1.0) / max(document_frequency.get(token, 1), 1)
        for token in question_tokens
        if token in search
    )


def _linked_channel_ids(session: Session, candidate: AISearchCandidate) -> list[str]:
    source_pairs = [(candidate.source_type, candidate.source_id)]
    if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
        source_pairs.append(("DOCUMENT", candidate.source_id))
    elif candidate.source_type == "REPORT_SOURCE" and candidate.parent_id:
        source_pairs.append(("REPORT", candidate.parent_id))
    conditions = [
        (NotificationChannel.source_type == source_type) & (NotificationChannel.source_id == source_id)
        for source_type, source_id in source_pairs
    ]
    if not conditions:
        return []
    return list(
        session.scalars(
            select(NotificationChannel.channel_id).where(NotificationChannel.status == "ACTIVE", or_(*conditions))
        ).all()
    )


def _can_evaluate_candidate(session: Session, candidate: AISearchCandidate, user: UserAccount) -> bool:
    if user.role in {"admin", "system-admin"}:
        return True
    channel_ids = _linked_channel_ids(session, candidate)
    if not channel_ids:
        return True
    return bool(
        session.scalar(
            select(func.count()).select_from(NotificationChannelMember).where(
                NotificationChannelMember.channel_id.in_(channel_ids),
                NotificationChannelMember.user_id == user.user_id,
                NotificationChannelMember.status == "ACTIVE",
            )
        )
    )


def _rank_candidates(session: Session, question: str, user: UserAccount, limit: int) -> tuple[list[AISearchCandidate], dict[str, str]]:
    question_tokens = _tokens(question)
    candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    document_frequency = {
        token: sum(1 for candidate in candidates if token in candidate.search_text.lower())
        for token in question_tokens
    }
    denied: dict[str, str] = {}
    ranked: list[tuple[float, AISearchCandidate]] = []
    for candidate in candidates:
        score = _candidate_rank(candidate, question_tokens, document_frequency)
        if score <= 0:
            continue
        if not _can_evaluate_candidate(session, candidate, user):
            denied[candidate.candidate_id] = "CHANNEL_ACCESS_DENIED"
            continue
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1].candidate_id))
    return [candidate for _, candidate in ranked[:limit]], denied


def _candidate_identity(candidate: AISearchCandidate) -> dict[str, str | None]:
    return {
        "candidate_id": candidate.candidate_id,
        "source_type": candidate.source_type,
        "source_id": candidate.source_id,
        "source_version_id": candidate.source_version_id,
        "trace_table": candidate.trace_table,
        "trace_id": candidate.trace_id,
        "trace_version_id": candidate.trace_version_id,
        "content_hash": candidate.content_hash,
        "internal_source_uri": f"flownote://{candidate.trace_table}/{candidate.trace_id}",
    }


def _matches_reference(candidate: AISearchCandidate, reference: AISearchEvidenceReference) -> bool:
    return bool(
        (reference.candidate_id is None or candidate.candidate_id == reference.candidate_id)
        and candidate.source_type == reference.source_type.strip().upper()
        and candidate.source_id == reference.source_id
        and (reference.source_version_id is None or candidate.source_version_id == reference.source_version_id)
        and (reference.trace_id is None or candidate.trace_id == reference.trace_id)
        and (reference.trace_version_id is None or candidate.trace_version_id == reference.trace_version_id)
    )


def _reference_key(reference: AISearchEvidenceReference) -> str:
    if reference.candidate_id:
        return reference.candidate_id
    return "|".join(
        [reference.source_type.strip().upper(), reference.source_id, reference.source_version_id or ""]
    )


def _excluded_reference_result(
    session: Session,
    reference: AISearchEvidenceReference,
    all_candidates: list[AISearchCandidate],
    actual: list[AISearchCandidate],
    denied: dict[str, str],
) -> dict[str, object]:
    matching = next((item for item in all_candidates if _matches_reference(item, reference)), None)
    actual_match = next((item for item in actual if _matches_reference(item, reference)), None)
    actual_reason = None
    if matching is not None and matching.candidate_id in denied:
        actual_reason = denied[matching.candidate_id]
    elif matching is None:
        source_type = reference.source_type.strip().upper()
        if source_type == "PUBLISHED_DOCUMENT_VERSION":
            actual_reason = "document_version_not_published"
        elif source_type == "FIELD_COMMENT":
            comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == reference.source_id))
            if comment is not None and comment.status in FIELD_COMMENT_EXCLUDED_STATUSES:
                actual_reason = "field_comment_excluded_status"
            elif comment is not None and comment.input_mode in FIELD_COMMENT_EXCLUDED_INPUT_MODES:
                actual_reason = "field_comment_mes_integration"
            else:
                actual_reason = "SOURCE_NOT_CANDIDATE"
        elif source_type == "REPORT_SOURCE":
            source = (
                session.scalar(select(ReportSource).where(ReportSource.id == int(reference.source_id)))
                if reference.source_id.isdigit()
                else None
            )
            report = (
                session.scalar(select(Report).where(Report.report_id == source.report_id))
                if source is not None
                else None
            )
            actual_reason = (
                "report_source_archived_report"
                if report is not None and report.status == "ARCHIVED"
                else "report_source_missing_origin"
            )
        else:
            actual_reason = "SOURCE_NOT_CANDIDATE"
    return {
        "reference": reference.model_dump(by_alias=False),
        "candidate_id": matching.candidate_id if matching else None,
        "excluded": actual_match is None,
        "actual_reason": actual_reason,
        "reason_matches": reference.exclusion_reason is None or reference.exclusion_reason == actual_reason,
    }


@router.post("/evaluations")
def run_evaluation(
    payload: AISearchEvaluationRequest,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    evaluate_as_user_id = payload.evaluate_as_user_id or current_user.user_id
    if evaluate_as_user_id != current_user.user_id and current_user.role not in {"admin", "system-admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="evaluateAsUserId requires admin or system-admin",
        )
    evaluate_as = session.scalar(select(UserAccount).where(UserAccount.user_id == evaluate_as_user_id))
    if evaluate_as is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="evaluateAsUserId does not exist")

    rebuild_ai_search_candidates(session)
    first_candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    first_identity = {item.candidate_id: item.content_hash for item in first_candidates}
    first_rankings = {
        case.case_key: [item.candidate_id for item in _rank_candidates(session, case.question, evaluate_as, case.limit)[0]]
        for case in payload.cases
    }
    session.expunge_all()
    rebuild_ai_search_candidates(session)
    all_candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    second_identity = {item.candidate_id: item.content_hash for item in all_candidates}
    candidate_identity_stable = first_identity == second_identity

    run_id = _new_public_id("aiseval")
    evaluation_run = AISearchEvaluationRun(
        run_id=run_id,
        run_label=payload.run_label,
        requested_by=current_user.user_id,
        evaluated_as_user_id=evaluate_as_user_id,
        status="FAILED",
        candidate_identity_stable=candidate_identity_stable,
        ranking_stable=False,
        metrics_json="{}",
    )
    session.add(evaluation_run)
    session.flush()
    case_results: list[dict[str, object]] = []
    source_types: set[str] = set()
    excluded_reasons: set[str] = set()
    ranking_stable = True
    for case in payload.cases:
        expected_outcome = case.expected_outcome.strip().upper()
        if expected_outcome not in {"SUFFICIENT", "INSUFFICIENT_EVIDENCE"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="expectedOutcome must be SUFFICIENT or INSUFFICIENT_EVIDENCE",
            )
        actual, denied = _rank_candidates(session, case.question, evaluate_as, case.limit)
        actual_ids = [item.candidate_id for item in actual]
        stable_for_case = first_rankings[case.case_key] == actual_ids
        ranking_stable = ranking_stable and stable_for_case
        expected_candidates = [
            next((item for item in all_candidates if _matches_reference(item, reference)), None)
            for reference in case.expected_evidence
        ]
        expected_ids = [item.candidate_id for item in expected_candidates if item is not None]
        top_actual_ids = actual_ids[: len(expected_ids)]
        missing_expected = [
            _reference_key(reference)
            for reference, candidate in zip(case.expected_evidence, expected_candidates)
            if candidate is None or candidate.candidate_id not in top_actual_ids
        ]
        excluded = [
            _excluded_reference_result(session, reference, all_candidates, actual, denied)
            for reference in case.expected_excluded
        ]
        for item in excluded:
            reason = item.get("actual_reason")
            if isinstance(reason, str):
                excluded_reasons.add(reason)
        actual_outcome = "SUFFICIENT" if actual else "INSUFFICIENT_EVIDENCE"
        excluded_passed = all(item["excluded"] and item["reason_matches"] for item in excluded)
        passed = bool(
            actual_outcome == expected_outcome
            and not missing_expected
            and len(expected_ids) == len(case.expected_evidence)
            and excluded_passed
            and stable_for_case
        )
        actual_evidence = [_candidate_identity(item) for item in actual]
        for item in expected_candidates:
            if item is not None:
                source_types.add(item.source_type)
        ranking_hash = _hash(json.dumps(actual_ids, ensure_ascii=False, separators=(",", ":")))
        evaluation_case_id = _new_public_id("aisevalcase")
        session.add(
            AISearchEvaluationCase(
                evaluation_case_id=evaluation_case_id,
                run_id=run_id,
                case_key=case.case_key,
                question=case.question,
                expected_outcome=expected_outcome,
                actual_outcome=actual_outcome,
                expected_evidence_json=json.dumps(
                    [reference.model_dump(by_alias=False) for reference in case.expected_evidence], ensure_ascii=False
                ),
                actual_evidence_json=json.dumps(actual_evidence, ensure_ascii=False),
                excluded_evidence_json=json.dumps(excluded, ensure_ascii=False),
                ranking_hash=ranking_hash,
                passed=passed,
            )
        )
        case_results.append(
            {
                "evaluation_case_id": evaluation_case_id,
                "case_key": case.case_key,
                "expected_outcome": expected_outcome,
                "actual_outcome": actual_outcome,
                "expected_candidate_ids": expected_ids,
                "actual_evidence": actual_evidence,
                "missing_expected": missing_expected,
                "excluded_evidence": excluded,
                "ranking_hash": ranking_hash,
                "ranking_stable": stable_for_case,
                "passed": passed,
            }
        )

    passed_count = sum(1 for item in case_results if item["passed"])
    readiness = _field_comment_review_readiness(session)
    all_passed = passed_count == len(case_results)
    source_coverage_complete = source_types == set(AI_SEARCH_SOURCE_TYPES)
    provider_start_ready = bool(
        all_passed and candidate_identity_stable and ranking_stable
        and source_coverage_complete and readiness.missing_reviewed_count == 0
    )
    metrics = {
        "case_count": len(case_results),
        "passed_count": passed_count,
        "source_types_covered": sorted(source_types),
        "source_coverage_complete": source_coverage_complete,
        "excluded_reasons_observed": sorted(excluded_reasons),
        "field_comment_reviewed_count": readiness.reviewed_status_count,
        "field_comment_missing_reviewed_count": readiness.missing_reviewed_count,
        "provider_start_ready": provider_start_ready,
    }
    status = "PASSED" if all_passed and candidate_identity_stable and ranking_stable else "FAILED"
    evaluation_run.status = status
    evaluation_run.ranking_stable = ranking_stable
    evaluation_run.metrics_json = json.dumps(metrics, ensure_ascii=False)
    session.commit()
    return {
        "run_id": run_id,
        "status": status,
        "evaluated_as_user_id": evaluate_as_user_id,
        "candidate_identity_stable": candidate_identity_stable,
        "ranking_stable": ranking_stable,
        **metrics,
        "cases": case_results,
    }


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
