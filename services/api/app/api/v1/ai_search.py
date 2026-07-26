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
from app.core.config import Settings, get_settings
from app.db.models import (
    AIEvaluationDatasetBinding,
    AIGroundTruthDatasetCase,
    AIGroundTruthDatasetVersion,
    AISearchCandidate,
    AISearchEvaluationCase,
    AISearchEvaluationRun,
    AISearchGroundTruthCase,
    AISearchGroundTruthProvenance,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    Report,
    ReportSource,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceBoard,
    WorkSequenceItem,
    TagDefinition,
    NotificationChannel,
    NotificationChannelMember,
    UserAccount,
)
from app.db.session import get_db_session
from app.services.ai_provider_gate import BLOCK_RULES, MASK_RULES, SensitiveContentFilter, load_sensitive_filter
from app.services.ai_readiness import (
    GROUND_TRUTH_MINIMUM,
    GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM,
    QUESTION_CATEGORIES,
    SCENARIO_TYPES,
    database_scope,
    scope_readiness,
)
from app.services.ai_operations import audit_event

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
    "sensitive_content": {
        "label": "민감정보 포함 원천 제외",
        "operator_action": "민감정보를 제거한 승인 원천을 별도로 만들고 원천 기록은 그대로 보존한다.",
        "source_type": "ALL",
    },
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
    content_hash: str | None = Field(default=None, alias="contentHash")
    exclusion_reason: str | None = Field(default=None, alias="exclusionReason")
    rationale: str | None = Field(default=None, min_length=1, max_length=1000)


class AISearchEvaluationCaseRequest(BaseModel):
    case_key: str = Field(alias="caseKey", min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    expected_outcome: str = Field(alias="expectedOutcome")
    expected_evidence: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedEvidence")
    expected_excluded: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedExcluded")
    allowed_rank_min: int = Field(default=1, alias="allowedRankMin", ge=1, le=100)
    allowed_rank_max: int = Field(default=20, alias="allowedRankMax", ge=1, le=100)
    as_of: datetime | None = Field(default=None, alias="asOf")
    limit: int = Field(default=20, ge=1, le=100)
    category: str | None = Field(default=None, exclude=True)
    scenario_type: str | None = Field(default=None, exclude=True)


class AISearchEvaluationRequest(BaseModel):
    run_label: str = Field(alias="runLabel", min_length=1, max_length=160)
    evaluate_as_user_id: str | None = Field(default=None, alias="evaluateAsUserId")
    line_scope: str | None = Field(default=None, alias="lineScope", max_length=64)
    ground_truth_case_ids: list[str] = Field(default_factory=list, alias="groundTruthCaseIds", max_length=100)
    cases: list[AISearchEvaluationCaseRequest] = Field(default_factory=list, max_length=100)
    evaluator_version: str = Field(default="candidate-ranking-v1", alias="evaluatorVersion", max_length=80)
    prompt_version_id: str | None = Field(default=None, alias="promptVersionId", max_length=64)
    policy_version: str | None = Field(default=None, alias="policyVersion", max_length=80)
    dataset_version_id: str | None = Field(default=None, alias="datasetVersionId", max_length=64)


class AISearchGroundTruthCaseRequest(BaseModel):
    case_key: str = Field(alias="caseKey", min_length=1, max_length=100)
    category: str
    scenario_type: str = Field(alias="scenarioType")
    question: str = Field(min_length=1, max_length=2000)
    expected_outcome: str = Field(alias="expectedOutcome")
    expected_evidence: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedEvidence")
    expected_excluded: list[AISearchEvidenceReference] = Field(default_factory=list, alias="expectedExcluded")
    allowed_rank_min: int = Field(default=1, alias="allowedRankMin", ge=1, le=100)
    allowed_rank_max: int = Field(default=20, alias="allowedRankMax", ge=1, le=100)
    as_of: datetime = Field(alias="asOf")
    line_scope: str | None = Field(default=None, alias="lineScope", max_length=64)
    data_classification: str = Field(alias="dataClassification")
    provenance_note: str = Field(alias="provenanceNote", min_length=1, max_length=1000)


class AIGroundTruthDatasetCreateRequest(BaseModel):
    dataset_key: str = Field(alias="datasetKey", min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    readiness_track: str = Field(alias="readinessTrack")
    line_scope: str | None = Field(default=None, alias="lineScope", max_length=64)
    ground_truth_case_ids: list[str] = Field(alias="groundTruthCaseIds", min_length=1, max_length=100)
    change_reason: str = Field(alias="changeReason", min_length=1, max_length=2000)
    replaces_dataset_version_id: str | None = Field(
        default=None, alias="replacesDatasetVersionId", max_length=64
    )


class AIGroundTruthDatasetCasesRequest(BaseModel):
    ground_truth_case_ids: list[str] = Field(alias="groundTruthCaseIds", min_length=1, max_length=100)
    change_reason: str = Field(alias="changeReason", min_length=1, max_length=2000)


class AIGroundTruthDatasetTransitionRequest(BaseModel):
    action: str
    reason: str = Field(min_length=1, max_length=2000)


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot_iso(value: datetime) -> str:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat()


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


def _contains_sensitive_content(value: str, content_filter: SensitiveContentFilter | None = None) -> bool:
    statically_sensitive = any(pattern.search(value) for _, pattern in BLOCK_RULES) or any(
        pattern.search(value) for _, pattern, _ in MASK_RULES
    )
    if statically_sensitive or content_filter is None:
        return statically_sensitive
    filtered = content_filter.filter(value)
    return not filtered.allowed or bool(filtered.detections)


def _document_line_scopes(session: Session, document_id: str) -> list[str]:
    return list(
        session.scalars(
            select(TagDefinition.code)
            .join(DocumentTag, DocumentTag.tag_id == TagDefinition.tag_id)
            .where(DocumentTag.document_id == document_id, TagDefinition.tag_type == "line")
            .order_by(TagDefinition.code)
        ).all()
    )


def _document_readiness_track(session: Session, document_id: str | None) -> str:
    if document_id is None:
        return "FIELD_READINESS"
    smoke_marker = session.scalar(
        select(DocumentTag.id)
        .join(TagDefinition, DocumentTag.tag_id == TagDefinition.tag_id)
        .where(
            DocumentTag.document_id == document_id,
            TagDefinition.tag_type == "custom",
            TagDefinition.code == "smoke-regression",
            TagDefinition.is_active.is_(True),
        )
        .limit(1)
    )
    return "SMOKE_REGRESSION" if smoke_marker is not None else "FIELD_READINESS"


def _history_readiness_track(session: Session, history: WorkSequenceChangeHistory) -> str:
    document_id = session.scalar(
        select(WorkSequenceItem.document_id).where(WorkSequenceItem.item_id == history.item_id)
    ) if history.item_id else None
    return _document_readiness_track(session, document_id)


def _report_source_readiness_track(session: Session, source: ReportSource) -> str:
    source_type = source.source_type.strip().upper()
    if source_type == "DOCUMENT":
        return _document_readiness_track(session, source.source_id)
    if source_type == "FIELD_COMMENT":
        document_id = session.scalar(
            select(FieldComment.document_id).where(FieldComment.comment_id == source.source_id)
        )
        return _document_readiness_track(session, document_id)
    if source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(
            select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == source.source_id)
        )
        return _history_readiness_track(session, history) if history else "FIELD_READINESS"
    if source_type == "WORK_SEQUENCE_ITEM":
        document_id = session.scalar(
            select(WorkSequenceItem.document_id).where(WorkSequenceItem.item_id == source.source_id)
        )
        return _document_readiness_track(session, document_id)
    return "FIELD_READINESS"


def _history_line_scope(session: Session, history: WorkSequenceChangeHistory) -> str | None:
    return session.scalar(
        select(WorkSequenceBoard.line_code).where(WorkSequenceBoard.board_id == history.board_id)
    )


def _report_line_scope(session: Session, source: ReportSource) -> str | list[str] | None:
    source_type = source.source_type.strip().upper()
    if source_type == "FIELD_COMMENT":
        return session.scalar(
            select(FieldComment.location_code).where(FieldComment.comment_id == source.source_id)
        )
    if source_type == "DOCUMENT":
        return _document_line_scopes(session, source.source_id)
    if source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(
            select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == source.source_id)
        )
        return _history_line_scope(session, history) if history else None
    if source_type == "WORK_SEQUENCE_ITEM":
        return session.scalar(
            select(WorkSequenceBoard.line_code)
            .join(WorkSequenceItem, WorkSequenceItem.board_id == WorkSequenceBoard.board_id)
            .where(WorkSequenceItem.item_id == source.source_id)
        )
    return None


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


def rebuild_ai_search_candidates(
    session: Session,
    content_filter: SensitiveContentFilter | None = None,
) -> AISearchRebuildResponse:
    refreshed_at = datetime.now(timezone.utc)
    session.query(AISearchCandidate).delete(synchronize_session=False)

    for document, version in _published_document_rows(session):
        search_text = _clean_text(
            document.title,
            document.description,
            version.version_label,
            version.change_reason,
        )
        if _contains_sensitive_content(search_text, content_filter):
            continue
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
                "line_scope": _document_line_scopes(session, document.document_id),
                "readiness_track": _document_readiness_track(session, document.document_id),
            },
            refreshed_at=refreshed_at,
        )

    for comment in _field_comment_rows(session):
        content_text = _field_comment_content_text(comment)
        if not content_text:
            continue
        search_text = _clean_text(content_text, comment.category, comment.signal_level)
        if _contains_sensitive_content(search_text, content_filter):
            continue
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
                "line_scope": comment.location_code,
                "readiness_track": _document_readiness_track(session, comment.document_id),
            },
            refreshed_at=refreshed_at,
        )

    for history in _work_sequence_history_rows(session):
        trace_text = _work_sequence_history_trace_text(history)
        if not trace_text:
            continue
        search_text = _clean_text(history.change_type, trace_text)
        if _contains_sensitive_content(search_text, content_filter):
            continue
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
                "line_scope": _history_line_scope(session, history),
                "readiness_track": _history_readiness_track(session, history),
            },
            refreshed_at=refreshed_at,
        )

    for source, report in _report_source_rows(session):
        if not _report_source_origin_exists(session, source):
            continue
        search_text = _report_source_text(source, report)
        if _contains_sensitive_content(search_text, content_filter):
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
            search_text=search_text,
            review_status=report.status,
            metadata={
                "report_id": report.report_id,
                "report_source_type": source.source_type,
                "report_source_id": source.source_id,
                "generated_document_id": report.generated_document_id,
                "line_scope": _report_line_scope(session, source),
                "readiness_track": _report_source_readiness_track(session, source),
            },
            refreshed_at=refreshed_at,
        )

    session.commit()
    return AISearchRebuildResponse(
        candidate_count=_candidate_count(session),
        counts_by_source_type=_candidate_counts_by_source_type(session),
        excluded_counts_by_reason=_excluded_counts_by_reason(session, content_filter),
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


def _excluded_counts_by_reason(
    session: Session,
    content_filter: SensitiveContentFilter | None = None,
) -> dict[str, int]:
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

    sensitive_content = 0
    sensitive_content += sum(
        _contains_sensitive_content(_clean_text(document.title, document.description, version.version_label, version.change_reason), content_filter)
        for document, version in _published_document_rows(session)
    )
    sensitive_content += sum(
        _contains_sensitive_content(_clean_text(_field_comment_content_text(comment), comment.category, comment.signal_level), content_filter)
        for comment in _field_comment_rows(session)
    )
    sensitive_content += sum(
        _contains_sensitive_content(_clean_text(history.change_type, _work_sequence_history_trace_text(history)), content_filter)
        for history in _work_sequence_history_rows(session)
    )
    sensitive_content += sum(
        _contains_sensitive_content(_report_source_text(source, report), content_filter)
        for source, report in _report_source_rows(session)
        if _report_source_origin_exists(session, source)
    )

    return {
        "sensitive_content": sensitive_content,
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


def _quality_response(
    session: Session,
    content_filter: SensitiveContentFilter | None = None,
) -> AISearchQualityResponse:
    latest_run = session.scalar(
        select(AISearchEvaluationRun).order_by(desc(AISearchEvaluationRun.created_at), desc(AISearchEvaluationRun.id))
    )
    return AISearchQualityResponse(
        candidate_count=_candidate_count(session),
        counts_by_source_type=_candidate_counts_by_source_type(session),
        excluded_counts_by_reason=_excluded_counts_by_reason(session, content_filter),
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


def _candidate_created_at(session: Session, candidate: AISearchCandidate) -> datetime | None:
    if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION" and candidate.source_version_id:
        return session.scalar(select(DocumentVersion.created_at).where(DocumentVersion.version_id == candidate.source_version_id))
    if candidate.source_type == "FIELD_COMMENT":
        return session.scalar(select(FieldComment.created_at).where(FieldComment.comment_id == candidate.source_id))
    if candidate.source_type == "WORK_SEQUENCE_HISTORY":
        return session.scalar(
            select(WorkSequenceChangeHistory.created_at).where(WorkSequenceChangeHistory.change_id == candidate.source_id)
        )
    if candidate.source_type == "REPORT_SOURCE" and candidate.source_id.isdigit():
        return session.scalar(select(ReportSource.created_at).where(ReportSource.id == int(candidate.source_id)))
    return None


def _candidate_created_at_map(
    session: Session, candidates: list[AISearchCandidate]
) -> dict[str, datetime | None]:
    result: dict[str, datetime | None] = {candidate.candidate_id: None for candidate in candidates}
    document_versions = {
        candidate.source_version_id for candidate in candidates
        if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION" and candidate.source_version_id
    }
    comments = {
        candidate.source_id for candidate in candidates if candidate.source_type == "FIELD_COMMENT"
    }
    histories = {
        candidate.source_id for candidate in candidates if candidate.source_type == "WORK_SEQUENCE_HISTORY"
    }
    report_sources = {
        int(candidate.source_id) for candidate in candidates
        if candidate.source_type == "REPORT_SOURCE" and candidate.source_id.isdigit()
    }
    version_times = dict(session.execute(
        select(DocumentVersion.version_id, DocumentVersion.created_at).where(
            DocumentVersion.version_id.in_(document_versions)
        )
    ).all()) if document_versions else {}
    comment_times = dict(session.execute(
        select(FieldComment.comment_id, FieldComment.created_at).where(FieldComment.comment_id.in_(comments))
    ).all()) if comments else {}
    history_times = dict(session.execute(
        select(WorkSequenceChangeHistory.change_id, WorkSequenceChangeHistory.created_at).where(
            WorkSequenceChangeHistory.change_id.in_(histories)
        )
    ).all()) if histories else {}
    report_times = dict(session.execute(
        select(ReportSource.id, ReportSource.created_at).where(ReportSource.id.in_(report_sources))
    ).all()) if report_sources else {}
    for candidate in candidates:
        if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
            result[candidate.candidate_id] = version_times.get(candidate.source_version_id)
        elif candidate.source_type == "FIELD_COMMENT":
            result[candidate.candidate_id] = comment_times.get(candidate.source_id)
        elif candidate.source_type == "WORK_SEQUENCE_HISTORY":
            result[candidate.candidate_id] = history_times.get(candidate.source_id)
        elif candidate.source_type == "REPORT_SOURCE" and candidate.source_id.isdigit():
            result[candidate.candidate_id] = report_times.get(int(candidate.source_id))
    return result


def _rank_candidates(
    session: Session,
    question: str,
    user: UserAccount,
    limit: int,
    as_of: datetime | None = None,
) -> tuple[list[AISearchCandidate], dict[str, str]]:
    question_tokens = _tokens(question)
    candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    created_at_by_candidate = _candidate_created_at_map(session, candidates) if as_of is not None else {}
    document_frequency = {
        token: sum(1 for candidate in candidates if token in candidate.search_text.lower())
        for token in question_tokens
    }
    denied: dict[str, str] = {}
    ranked: list[tuple[float, AISearchCandidate]] = []
    for candidate in candidates:
        created_at = created_at_by_candidate.get(candidate.candidate_id)
        if as_of is not None and created_at is not None:
            comparable_created_at = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
            comparable_as_of = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of
            if comparable_created_at > comparable_as_of:
                continue
        score = _candidate_rank(candidate, question_tokens, document_frequency)
        if score <= 0:
            continue
        if not _can_evaluate_candidate(session, candidate, user):
            denied[candidate.candidate_id] = "CHANNEL_ACCESS_DENIED"
            continue
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1].candidate_id))
    return [candidate for _, candidate in ranked[:limit]], denied


def _candidate_trace_exists(session: Session, candidate: AISearchCandidate) -> bool:
    if candidate.source_type == "PUBLISHED_DOCUMENT_VERSION":
        return session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == candidate.trace_id,
                DocumentVersion.version_id == candidate.trace_version_id,
            )
        ) is not None
    if candidate.source_type == "FIELD_COMMENT":
        return session.scalar(select(FieldComment.id).where(FieldComment.comment_id == candidate.trace_id)) is not None
    if candidate.source_type == "WORK_SEQUENCE_HISTORY":
        return session.scalar(
            select(WorkSequenceChangeHistory.id).where(WorkSequenceChangeHistory.change_id == candidate.trace_id)
        ) is not None
    if candidate.source_type == "REPORT_SOURCE" and candidate.trace_id.isdigit():
        return session.scalar(select(ReportSource.id).where(ReportSource.id == int(candidate.trace_id))) is not None
    return False


def _previous_case_delta(
    session: Session,
    *,
    run_id: str,
    case_key: str,
    actual_evidence: list[dict[str, str | None]],
    ranking_hash: str,
) -> dict[str, object] | None:
    previous = session.scalar(
        select(AISearchEvaluationCase)
        .where(
            AISearchEvaluationCase.case_key == case_key,
            AISearchEvaluationCase.run_id != run_id,
        )
        .order_by(desc(AISearchEvaluationCase.id))
    )
    if previous is None:
        return None
    previous_items = json.loads(previous.actual_evidence_json)
    previous_hashes = {item["candidate_id"]: item["content_hash"] for item in previous_items}
    current_hashes = {item["candidate_id"]: item["content_hash"] for item in actual_evidence}
    previous_ids = set(previous_hashes)
    current_ids = set(current_hashes)
    return {
        "previous_evaluation_case_id": previous.evaluation_case_id,
        "candidate_ids_added": sorted(current_ids - previous_ids),
        "candidate_ids_removed": sorted(previous_ids - current_ids),
        "content_hash_changed": sorted(
            candidate_id
            for candidate_id in previous_ids.intersection(current_ids)
            if previous_hashes[candidate_id] != current_hashes[candidate_id]
        ),
        "ranking_changed": previous.ranking_hash != ranking_hash,
    }


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
        and (reference.content_hash is None or candidate.content_hash == reference.content_hash)
    )


def _reference_key(reference: AISearchEvidenceReference) -> str:
    if reference.candidate_id:
        return reference.candidate_id
    return "|".join(
        [reference.source_type.strip().upper(), reference.source_id, reference.source_version_id or ""]
    )


def _source_reference_exists(session: Session, reference: AISearchEvidenceReference) -> bool:
    source_type = reference.source_type.strip().upper()
    if source_type == "PUBLISHED_DOCUMENT_VERSION":
        statement = select(Document.id).where(Document.document_id == reference.source_id)
        if reference.source_version_id:
            statement = (
                select(DocumentVersion.id)
                .join(Document, Document.document_id == DocumentVersion.document_id)
                .where(
                    Document.document_id == reference.source_id,
                    DocumentVersion.version_id == reference.source_version_id,
                )
            )
        return session.scalar(statement) is not None
    if source_type == "FIELD_COMMENT":
        return session.scalar(select(FieldComment.id).where(FieldComment.comment_id == reference.source_id)) is not None
    if source_type == "WORK_SEQUENCE_HISTORY":
        return session.scalar(
            select(WorkSequenceChangeHistory.id).where(WorkSequenceChangeHistory.change_id == reference.source_id)
        ) is not None
    if source_type == "REPORT_SOURCE" and reference.source_id.isdigit():
        return session.scalar(select(ReportSource.id).where(ReportSource.id == int(reference.source_id))) is not None
    return False


def _source_reference_snapshot(session: Session, reference: AISearchEvidenceReference) -> dict[str, object]:
    value = reference.model_dump(by_alias=True, mode="json")
    source_type = reference.source_type.strip().upper()
    source_text = ""
    if source_type == "PUBLISHED_DOCUMENT_VERSION":
        row = session.execute(
            select(Document, DocumentVersion)
            .join(DocumentVersion, DocumentVersion.document_id == Document.document_id)
            .where(
                Document.document_id == reference.source_id,
                DocumentVersion.version_id == reference.source_version_id,
            )
        ).first()
        if row is not None:
            document, version = row
            source_text = _clean_text(document.title, document.description, version.version_label, version.change_reason)
    elif source_type == "FIELD_COMMENT":
        comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == reference.source_id))
        if comment is not None:
            source_text = _clean_text(_field_comment_content_text(comment), comment.category, comment.signal_level)
            value["sourceVersionId"] = comment.document_version_id
            value["traceId"] = comment.comment_id
            value["traceVersionId"] = comment.document_version_id
    elif source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(
            select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == reference.source_id)
        )
        if history is not None:
            source_text = _clean_text(history.change_type, _work_sequence_history_trace_text(history))
            value["traceId"] = history.change_id
    elif source_type == "REPORT_SOURCE" and reference.source_id.isdigit():
        source = session.scalar(select(ReportSource).where(ReportSource.id == int(reference.source_id)))
        report = session.scalar(select(Report).where(Report.report_id == source.report_id)) if source else None
        if source is not None and report is not None:
            source_text = _report_source_text(source, report)
            value["sourceVersionId"] = source.source_version_id
            value["traceId"] = str(source.id)
            value["traceVersionId"] = source.source_version_id
    value["sourceType"] = source_type
    value["contentHash"] = _hash(source_text)
    return value


def _approved_reference(candidate: AISearchCandidate, reference: AISearchEvidenceReference) -> dict[str, object]:
    value = reference.model_dump(by_alias=True, mode="json")
    value.update({
        "candidateId": candidate.candidate_id,
        "sourceType": candidate.source_type,
        "sourceId": candidate.source_id,
        "sourceVersionId": candidate.source_version_id,
        "traceId": candidate.trace_id,
        "traceVersionId": candidate.trace_version_id,
        "contentHash": candidate.content_hash,
    })
    return value


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
    current_snapshot = _source_reference_snapshot(session, reference)
    content_hash_matches = (
        reference.content_hash is None
        or current_snapshot.get("contentHash") == reference.content_hash
    )
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
        "content_hash_matches": content_hash_matches,
    }


def _ground_truth_response(
    case: AISearchGroundTruthCase,
    provenance: AISearchGroundTruthProvenance | None = None,
) -> dict[str, object]:
    response = {
        "ground_truth_case_id": case.ground_truth_case_id,
        "case_key": case.case_key,
        "customer_scope": case.customer_scope,
        "site_scope": case.site_scope,
        "line_scope": case.line_scope,
        "database_scope": case.database_scope,
        "category": case.category,
        "scenario_type": case.scenario_type,
        "question": case.question,
        "expected_outcome": case.expected_outcome,
        "expected_evidence": json.loads(case.expected_evidence_json),
        "expected_excluded": json.loads(case.excluded_evidence_json),
        "allowed_rank_min": case.allowed_rank_min,
        "allowed_rank_max": case.allowed_rank_max,
        "as_of": case.as_of,
        "approved_by": case.approved_by,
        "approved_at": case.approved_at,
        "is_active": case.is_active,
    }
    response["provenance"] = None if provenance is None else {
        "provenance_id": provenance.provenance_id,
        "data_classification": provenance.data_classification,
        "readiness_track": provenance.readiness_track,
        "provenance_note": provenance.provenance_note,
        "source_snapshot_hash": provenance.source_snapshot_hash,
        "contains_sensitive_data": provenance.contains_sensitive_data,
        "approval_status": provenance.approval_status,
        "first_approved_by": provenance.first_approved_by,
        "first_approved_at": provenance.first_approved_at,
        "second_approved_by": provenance.second_approved_by,
        "second_approved_at": provenance.second_approved_at,
    }
    return response


@router.post("/ground-truth-cases", status_code=status.HTTP_201_CREATED)
def approve_ground_truth_case(
    payload: AISearchGroundTruthCaseRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    if current_user.role not in {
        "admin", "system-admin", "document-admin", "manager", "assistant-manager", "department-manager"
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ground-truth approval role required")
    category = payload.category.strip().upper()
    scenario_type = payload.scenario_type.strip().upper()
    expected_outcome = payload.expected_outcome.strip().upper()
    data_classification = payload.data_classification.strip().upper().replace("-", "_")
    if category not in QUESTION_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {', '.join(QUESTION_CATEGORIES)}")
    if scenario_type not in SCENARIO_TYPES:
        raise HTTPException(status_code=422, detail=f"scenarioType must be one of {', '.join(SCENARIO_TYPES)}")
    if expected_outcome not in {"SUFFICIENT", "INSUFFICIENT_EVIDENCE"}:
        raise HTTPException(status_code=422, detail="expectedOutcome must be SUFFICIENT or INSUFFICIENT_EVIDENCE")
    if data_classification not in {"SYNTHETIC", "TEST", "ANONYMOUS_FIELD", "PILOT"}:
        raise HTTPException(
            status_code=422,
            detail="dataClassification must be SYNTHETIC, TEST, ANONYMOUS_FIELD, or PILOT",
        )
    if payload.allowed_rank_min > payload.allowed_rank_max:
        raise HTTPException(status_code=422, detail="allowedRankMin must not exceed allowedRankMax")
    if scenario_type == "NORMAL" and not payload.expected_evidence:
        raise HTTPException(status_code=422, detail="NORMAL case requires expectedEvidence")
    if scenario_type == "EXCLUSION" and not payload.expected_excluded:
        raise HTTPException(status_code=422, detail="EXCLUSION case requires expectedExcluded")
    if scenario_type == "CONFLICT" and len(payload.expected_evidence) < 2:
        raise HTTPException(status_code=422, detail="CONFLICT case requires at least two expectedEvidence items")
    db_scope = database_scope(settings.database_url)
    duplicate = session.scalar(
        select(AISearchGroundTruthCase.id).where(
            AISearchGroundTruthCase.customer_scope == settings.ai_customer_scope,
            AISearchGroundTruthCase.site_scope == settings.ai_site_scope,
            AISearchGroundTruthCase.case_key == payload.case_key,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="caseKey already exists in this customer/site scope")
    content_filter = load_sensitive_filter(session, settings)
    case_text_filter = content_filter.filter("\n".join(
        [payload.question, payload.provenance_note]
        + [reference.rationale or "" for reference in payload.expected_evidence]
        + [
            value
            for reference in payload.expected_excluded
            for value in (reference.rationale or "", reference.exclusion_reason or "")
        ]
    ))
    if not case_text_filter.allowed or case_text_filter.detections:
        raise HTTPException(
            status_code=422,
            detail="ground-truth question and provenance must contain no sensitive or identifying data",
        )
    rebuild_ai_search_candidates(session, content_filter)
    candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    approver = session.scalar(select(UserAccount).where(UserAccount.user_id == current_user.user_id))
    assert approver is not None
    approved_evidence: list[dict[str, object]] = []
    for reference in payload.expected_evidence:
        if not reference.rationale:
            raise HTTPException(status_code=422, detail="every expectedEvidence item requires rationale")
        candidate = next((item for item in candidates if _matches_reference(item, reference)), None)
        if candidate is None:
            raise HTTPException(status_code=422, detail=f"expectedEvidence is not an eligible candidate: {_reference_key(reference)}")
        if not _can_evaluate_candidate(session, candidate, approver):
            raise HTTPException(status_code=403, detail=f"approver cannot access expectedEvidence: {_reference_key(reference)}")
        created_at = _candidate_created_at(session, candidate)
        if created_at is not None:
            comparable_created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
            comparable_as_of = payload.as_of.replace(tzinfo=timezone.utc) if payload.as_of.tzinfo is None else payload.as_of
            if comparable_created > comparable_as_of:
                raise HTTPException(status_code=422, detail=f"expectedEvidence is newer than asOf: {_reference_key(reference)}")
        approved_evidence.append(_approved_reference(candidate, reference))
    for reference in payload.expected_excluded:
        if not reference.rationale or not reference.exclusion_reason:
            raise HTTPException(
                status_code=422,
                detail="every expectedExcluded item requires rationale and exclusionReason",
            )
        if not _source_reference_exists(session, reference):
            raise HTTPException(status_code=422, detail=f"expectedExcluded cannot be traced: {_reference_key(reference)}")
    excluded_snapshots = [_source_reference_snapshot(session, item) for item in payload.expected_excluded]
    now = datetime.now(timezone.utc)
    readiness_track = (
        "SMOKE_REGRESSION" if data_classification in {"SYNTHETIC", "TEST"} else "FIELD_READINESS"
    )
    snapshot_payload = {
        "caseKey": payload.case_key,
        "scope": {
            "customer": settings.ai_customer_scope,
            "site": settings.ai_site_scope,
            "line": payload.line_scope.strip() if payload.line_scope and payload.line_scope.strip() else None,
            "database": db_scope,
        },
        "asOf": _snapshot_iso(payload.as_of),
        "expectedEvidence": approved_evidence,
        "expectedExcluded": excluded_snapshots,
    }
    source_snapshot_hash = _hash(json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    case = AISearchGroundTruthCase(
        ground_truth_case_id=_new_public_id("aigt"),
        case_key=payload.case_key,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        line_scope=payload.line_scope.strip() if payload.line_scope and payload.line_scope.strip() else None,
        database_scope=db_scope,
        category=category,
        scenario_type=scenario_type,
        question=payload.question.strip(),
        expected_outcome=expected_outcome,
        expected_evidence_json=json.dumps(
            approved_evidence, ensure_ascii=False
        ),
        excluded_evidence_json=json.dumps(
            excluded_snapshots, ensure_ascii=False
        ),
        allowed_rank_min=payload.allowed_rank_min,
        allowed_rank_max=payload.allowed_rank_max,
        as_of=payload.as_of,
        approved_by=current_user.user_id,
        approved_at=now,
        is_active=False,
    )
    session.add(case)
    provenance = AISearchGroundTruthProvenance(
        provenance_id=_new_public_id("aigtprov"),
        ground_truth_case_id=case.ground_truth_case_id,
        data_classification=data_classification,
        readiness_track=readiness_track,
        provenance_note=payload.provenance_note.strip(),
        source_snapshot_hash=source_snapshot_hash,
        contains_sensitive_data=False,
        approval_status="PENDING_SECOND_APPROVAL",
        first_approved_by=current_user.user_id,
        first_approved_at=now,
    )
    session.add(provenance)
    session.commit()
    return _ground_truth_response(case, provenance)


@router.post("/ground-truth-cases/{ground_truth_case_id}/second-approval")
def second_approve_ground_truth_case(
    ground_truth_case_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    if current_user.role not in {
        "admin", "system-admin", "document-admin", "manager", "assistant-manager", "department-manager"
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ground-truth approval role required")
    case = session.scalar(
        select(AISearchGroundTruthCase).where(
            AISearchGroundTruthCase.ground_truth_case_id == ground_truth_case_id,
            AISearchGroundTruthCase.customer_scope == settings.ai_customer_scope,
            AISearchGroundTruthCase.site_scope == settings.ai_site_scope,
            AISearchGroundTruthCase.database_scope == database_scope(settings.database_url),
        )
    )
    provenance = session.scalar(
        select(AISearchGroundTruthProvenance).where(
            AISearchGroundTruthProvenance.ground_truth_case_id == ground_truth_case_id
        )
    )
    if case is None or provenance is None:
        raise HTTPException(status_code=404, detail="ground-truth case does not exist")
    if provenance.first_approved_by == current_user.user_id:
        raise HTTPException(status_code=409, detail="second approver must differ from first approver")
    if provenance.approval_status == "APPROVED":
        raise HTTPException(status_code=409, detail="ground-truth case is already approved")
    content_filter = load_sensitive_filter(session, settings)
    rebuild_ai_search_candidates(session, content_filter)
    candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    second_approver = session.scalar(select(UserAccount).where(UserAccount.user_id == current_user.user_id))
    assert second_approver is not None
    expected_evidence = json.loads(case.expected_evidence_json)
    expected_excluded = json.loads(case.excluded_evidence_json)
    for stored in expected_evidence:
        reference = AISearchEvidenceReference.model_validate(stored)
        candidate = next((item for item in candidates if _matches_reference(item, reference)), None)
        if candidate is None:
            raise HTTPException(status_code=409, detail=f"expectedEvidence changed after first approval: {_reference_key(reference)}")
        if not _can_evaluate_candidate(session, candidate, second_approver):
            raise HTTPException(status_code=403, detail=f"second approver cannot access expectedEvidence: {_reference_key(reference)}")
    for stored in expected_excluded:
        reference = AISearchEvidenceReference.model_validate(stored)
        if not _source_reference_exists(session, reference):
            raise HTTPException(status_code=409, detail=f"expectedExcluded changed after first approval: {_reference_key(reference)}")
        current_snapshot = _source_reference_snapshot(session, reference)
        if current_snapshot.get("contentHash") != stored.get("contentHash"):
            raise HTTPException(status_code=409, detail=f"expectedExcluded hash changed after first approval: {_reference_key(reference)}")
    snapshot_payload = {
        "caseKey": case.case_key,
        "scope": {
            "customer": case.customer_scope,
            "site": case.site_scope,
            "line": case.line_scope,
            "database": case.database_scope,
        },
        "asOf": _snapshot_iso(case.as_of),
        "expectedEvidence": expected_evidence,
        "expectedExcluded": expected_excluded,
    }
    current_snapshot_hash = _hash(json.dumps(
        snapshot_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ))
    if current_snapshot_hash != provenance.source_snapshot_hash:
        raise HTTPException(status_code=409, detail="ground-truth source snapshot changed after first approval")
    now = datetime.now(timezone.utc)
    provenance.second_approved_by = current_user.user_id
    provenance.second_approved_at = now
    provenance.approval_status = "APPROVED"
    case.is_active = True
    session.commit()
    return _ground_truth_response(case, provenance)


@router.get("/ground-truth-cases")
def list_ground_truth_cases(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
    line_scope: Annotated[str | None, Query(alias="lineScope")] = None,
    include_pending: Annotated[bool, Query(alias="includePending")] = False,
) -> list[dict[str, object]]:
    statement = select(AISearchGroundTruthCase).where(
        AISearchGroundTruthCase.customer_scope == settings.ai_customer_scope,
        AISearchGroundTruthCase.site_scope == settings.ai_site_scope,
        AISearchGroundTruthCase.database_scope == database_scope(settings.database_url),
    )
    if not include_pending:
        statement = statement.where(AISearchGroundTruthCase.is_active.is_(True))
    statement = statement.where(
        AISearchGroundTruthCase.line_scope == line_scope if line_scope else AISearchGroundTruthCase.line_scope.is_(None)
    )
    cases = session.scalars(statement.order_by(AISearchGroundTruthCase.case_key)).all()
    provenance_by_case = {
        item.ground_truth_case_id: item
        for item in session.scalars(
            select(AISearchGroundTruthProvenance).where(
                AISearchGroundTruthProvenance.ground_truth_case_id.in_(
                    [case.ground_truth_case_id for case in cases]
                )
            )
        ).all()
    } if cases else {}
    return [_ground_truth_response(case, provenance_by_case.get(case.ground_truth_case_id)) for case in cases]


GROUND_TRUTH_OPERATOR_ROLES = {
    "admin", "system-admin", "document-admin", "manager", "assistant-manager", "department-manager"
}
GROUND_TRUTH_APPROVER_ROLES = {
    "admin", "system-admin", "document-admin", "department-manager"
}


def _require_ground_truth_role(user: CurrentUser, *, approver: bool = False) -> None:
    allowed = GROUND_TRUTH_APPROVER_ROLES if approver else GROUND_TRUTH_OPERATOR_ROLES
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail="ground-truth dataset operation role required")


def _case_snapshot(case: AISearchGroundTruthCase) -> dict[str, object]:
    return {
        "ground_truth_case_id": case.ground_truth_case_id,
        "case_key": case.case_key,
        "category": case.category,
        "scenario_type": case.scenario_type,
        "question": case.question,
        "expected_outcome": case.expected_outcome,
        "expected_evidence": json.loads(case.expected_evidence_json),
        "expected_excluded": json.loads(case.excluded_evidence_json),
        "allowed_rank_min": case.allowed_rank_min,
        "allowed_rank_max": case.allowed_rank_max,
        "as_of": _snapshot_iso(case.as_of),
    }


def _dataset_members(
    session: Session, dataset_version_id: str
) -> list[tuple[AIGroundTruthDatasetCase, AISearchGroundTruthCase]]:
    return session.execute(
        select(AIGroundTruthDatasetCase, AISearchGroundTruthCase)
        .join(
            AISearchGroundTruthCase,
            AISearchGroundTruthCase.ground_truth_case_id == AIGroundTruthDatasetCase.ground_truth_case_id,
        )
        .where(AIGroundTruthDatasetCase.dataset_version_id == dataset_version_id)
        .order_by(AIGroundTruthDatasetCase.case_key)
    ).all()


def _dataset_snapshot_hash(members: list[tuple[AIGroundTruthDatasetCase, AISearchGroundTruthCase]]) -> str:
    snapshots = [_case_snapshot(case) for _, case in members]
    return _hash(json.dumps(snapshots, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _dataset_response(
    session: Session, dataset: AIGroundTruthDatasetVersion, *, include_cases: bool = True
) -> dict[str, object]:
    members = _dataset_members(session, dataset.dataset_version_id)
    coverage = {
        (category, scenario): 0 for category in QUESTION_CATEGORIES for scenario in SCENARIO_TYPES
    }
    for _, case in members:
        coverage[(case.category, case.scenario_type)] += 1
    coverage_rows = [
        {
            "category": category,
            "scenario_type": scenario,
            "count": coverage[(category, scenario)],
            "required": GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM,
            "missing": max(GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM - coverage[(category, scenario)], 0),
        }
        for category in QUESTION_CATEGORIES for scenario in SCENARIO_TYPES
    ]
    response: dict[str, object] = {
        "dataset_version_id": dataset.dataset_version_id,
        "dataset_key": dataset.dataset_key,
        "version": dataset.version,
        "title": dataset.title,
        "status": dataset.status,
        "readiness_track": dataset.readiness_track,
        "customer_scope": dataset.customer_scope,
        "site_scope": dataset.site_scope,
        "line_scope": dataset.line_scope,
        "database_scope": dataset.database_scope,
        "author_id": dataset.author_id,
        "reviewer_id": dataset.reviewer_id,
        "first_approved_by": dataset.first_approved_by,
        "second_approved_by": dataset.second_approved_by,
        "snapshot_hash": dataset.snapshot_hash,
        "replaces_dataset_version_id": dataset.replaces_dataset_version_id,
        "change_reason": dataset.change_reason,
        "case_count": len(members),
        "coverage": coverage_rows,
        "coverage_complete": len(members) >= GROUND_TRUTH_MINIMUM and not any(
            item["missing"] for item in coverage_rows
        ),
        "submitted_at": dataset.submitted_at,
        "reviewed_at": dataset.reviewed_at,
        "first_approved_at": dataset.first_approved_at,
        "second_approved_at": dataset.second_approved_at,
        "retired_at": dataset.retired_at,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }
    if include_cases:
        response["cases"] = [
            {**_ground_truth_response(case), "dataset_case_snapshot_hash": member.snapshot_hash}
            for member, case in members
        ]
    return response


def _replace_dataset_members(
    session: Session,
    dataset: AIGroundTruthDatasetVersion,
    case_ids: list[str],
    actor_id: str,
) -> None:
    if dataset.status != "DRAFT":
        raise HTTPException(status_code=409, detail="only a DRAFT dataset version can be changed")
    unique_ids = list(dict.fromkeys(case_ids))
    if len(unique_ids) != len(case_ids):
        raise HTTPException(status_code=422, detail="groundTruthCaseIds must be unique")
    cases = session.scalars(select(AISearchGroundTruthCase).where(
        AISearchGroundTruthCase.ground_truth_case_id.in_(unique_ids),
        AISearchGroundTruthCase.customer_scope == dataset.customer_scope,
        AISearchGroundTruthCase.site_scope == dataset.site_scope,
        AISearchGroundTruthCase.database_scope == dataset.database_scope,
        AISearchGroundTruthCase.line_scope == dataset.line_scope,
        AISearchGroundTruthCase.is_active.is_(True),
    )).all()
    if len(cases) != len(unique_ids):
        raise HTTPException(status_code=422, detail="one or more cases are not active in the dataset scope")
    provenance = {
        item.ground_truth_case_id: item
        for item in session.scalars(select(AISearchGroundTruthProvenance).where(
            AISearchGroundTruthProvenance.ground_truth_case_id.in_(unique_ids),
            AISearchGroundTruthProvenance.approval_status == "APPROVED",
            AISearchGroundTruthProvenance.readiness_track == dataset.readiness_track,
        )).all()
    }
    if len(provenance) != len(unique_ids):
        raise HTTPException(status_code=422, detail="all cases must be approved in the dataset readiness track")
    if dataset.readiness_track == "FIELD_READINESS" and any(
        item.data_classification != "ANONYMOUS_FIELD" for item in provenance.values()
    ):
        raise HTTPException(
            status_code=422,
            detail="FIELD_READINESS datasets require only ANONYMOUS_FIELD cases",
        )
    session.query(AIGroundTruthDatasetCase).filter(
        AIGroundTruthDatasetCase.dataset_version_id == dataset.dataset_version_id
    ).delete(synchronize_session=False)
    by_id = {case.ground_truth_case_id: case for case in cases}
    for case_id in unique_ids:
        case = by_id[case_id]
        snapshot_hash = _hash(json.dumps(
            _case_snapshot(case), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ))
        session.add(AIGroundTruthDatasetCase(
            dataset_version_id=dataset.dataset_version_id,
            ground_truth_case_id=case_id,
            case_key=case.case_key,
            snapshot_hash=snapshot_hash,
            added_by=actor_id,
        ))
    session.flush()


@router.get("/ground-truth-datasets")
def list_ground_truth_datasets(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
    line_scope: Annotated[str | None, Query(alias="lineScope")] = None,
) -> list[dict[str, object]]:
    normalized_line = line_scope.strip() if line_scope and line_scope.strip() else None
    rows = session.scalars(select(AIGroundTruthDatasetVersion).where(
        AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
        AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
        AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
        AIGroundTruthDatasetVersion.line_scope == normalized_line,
    ).order_by(desc(AIGroundTruthDatasetVersion.created_at))).all()
    return [_dataset_response(session, row, include_cases=False) for row in rows]


@router.get("/ground-truth-datasets/{dataset_version_id}")
def get_ground_truth_dataset(
    dataset_version_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    row = session.scalar(select(AIGroundTruthDatasetVersion).where(
        AIGroundTruthDatasetVersion.dataset_version_id == dataset_version_id,
        AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
        AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
        AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="ground-truth dataset version does not exist")
    return _dataset_response(session, row)


@router.post("/ground-truth-datasets", status_code=201)
def create_ground_truth_dataset(
    payload: AIGroundTruthDatasetCreateRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    _require_ground_truth_role(current_user)
    track = payload.readiness_track.strip().upper()
    if track not in {"SMOKE_REGRESSION", "FIELD_READINESS"}:
        raise HTTPException(status_code=422, detail="invalid readinessTrack")
    normalized_line = payload.line_scope.strip() if payload.line_scope and payload.line_scope.strip() else None
    latest_version = session.scalar(select(func.max(AIGroundTruthDatasetVersion.version)).where(
        AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
        AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
        AIGroundTruthDatasetVersion.dataset_key == payload.dataset_key.strip(),
    )) or 0
    if payload.replaces_dataset_version_id:
        replaced = session.scalar(select(AIGroundTruthDatasetVersion).where(
            AIGroundTruthDatasetVersion.dataset_version_id == payload.replaces_dataset_version_id,
            AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
            AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
            AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
            AIGroundTruthDatasetVersion.line_scope == normalized_line,
            AIGroundTruthDatasetVersion.readiness_track == track,
            AIGroundTruthDatasetVersion.status.in_(("APPROVED", "SUPERSEDED", "RETIRED")),
        ))
        if replaced is None:
            raise HTTPException(status_code=422, detail="replacement target must be an approved immutable version")
        if replaced.dataset_key != payload.dataset_key.strip():
            raise HTTPException(status_code=422, detail="replacement must use the same datasetKey")
    row = AIGroundTruthDatasetVersion(
        dataset_version_id=_new_public_id("aigtds"),
        dataset_key=payload.dataset_key.strip(), version=latest_version + 1,
        title=payload.title.strip(), customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope, line_scope=normalized_line,
        database_scope=database_scope(settings.database_url), readiness_track=track,
        status="DRAFT", author_id=current_user.user_id,
        replaces_dataset_version_id=payload.replaces_dataset_version_id,
        change_reason=payload.change_reason.strip(),
    )
    session.add(row)
    session.flush()
    _replace_dataset_members(session, row, payload.ground_truth_case_ids, current_user.user_id)
    audit_event(session, event_type="GROUND_TRUTH_DATASET_CREATED", actor_id=current_user.user_id,
                customer_scope=row.customer_scope, site_scope=row.site_scope,
                target_type="GROUND_TRUTH_DATASET", target_id=row.dataset_version_id,
                detail={"datasetKey": row.dataset_key, "version": row.version})
    session.commit()
    return _dataset_response(session, row)


@router.put("/ground-truth-datasets/{dataset_version_id}/cases")
def update_ground_truth_dataset_cases(
    dataset_version_id: str,
    payload: AIGroundTruthDatasetCasesRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    _require_ground_truth_role(current_user)
    row = session.scalar(select(AIGroundTruthDatasetVersion).where(
        AIGroundTruthDatasetVersion.dataset_version_id == dataset_version_id,
        AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
        AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
        AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="ground-truth dataset version does not exist")
    if row.author_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="only the dataset author can change a draft")
    _replace_dataset_members(session, row, payload.ground_truth_case_ids, current_user.user_id)
    row.change_reason = payload.change_reason.strip()
    audit_event(session, event_type="GROUND_TRUTH_DATASET_CASES_CHANGED", actor_id=current_user.user_id,
                customer_scope=row.customer_scope, site_scope=row.site_scope,
                target_type="GROUND_TRUTH_DATASET", target_id=row.dataset_version_id,
                detail={"caseCount": len(payload.ground_truth_case_ids)})
    session.commit()
    return _dataset_response(session, row)


@router.post("/ground-truth-datasets/{dataset_version_id}/transition")
def transition_ground_truth_dataset(
    dataset_version_id: str,
    payload: AIGroundTruthDatasetTransitionRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    action = payload.action.strip().upper()
    _require_ground_truth_role(current_user, approver=action in {"FIRST_APPROVE", "SECOND_APPROVE", "RETIRE"})
    row = session.scalar(select(AIGroundTruthDatasetVersion).where(
        AIGroundTruthDatasetVersion.dataset_version_id == dataset_version_id,
        AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
        AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
        AIGroundTruthDatasetVersion.database_scope == database_scope(settings.database_url),
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="ground-truth dataset version does not exist")
    now = datetime.now(timezone.utc)
    if action == "SUBMIT_REVIEW":
        if row.status != "DRAFT" or row.author_id != current_user.user_id:
            raise HTTPException(status_code=409, detail="only the author can submit a DRAFT dataset")
        row.status, row.submitted_at = "IN_REVIEW", now
    elif action == "REVIEW":
        if row.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail="dataset is not waiting for review")
        if current_user.user_id == row.author_id:
            raise HTTPException(status_code=409, detail="reviewer must differ from author")
        row.status, row.reviewer_id, row.reviewed_at = "PENDING_FIRST_APPROVAL", current_user.user_id, now
    elif action == "FIRST_APPROVE":
        if row.status != "PENDING_FIRST_APPROVAL":
            raise HTTPException(status_code=409, detail="dataset is not waiting for first approval")
        if current_user.user_id in {row.author_id, row.reviewer_id}:
            raise HTTPException(status_code=409, detail="first approver must differ from author and reviewer")
        row.status, row.first_approved_by, row.first_approved_at = (
            "PENDING_SECOND_APPROVAL", current_user.user_id, now
        )
    elif action == "SECOND_APPROVE":
        if row.status != "PENDING_SECOND_APPROVAL":
            raise HTTPException(status_code=409, detail="dataset is not waiting for second approval")
        if current_user.user_id in {row.author_id, row.reviewer_id, row.first_approved_by}:
            raise HTTPException(status_code=409, detail="second approver must be independent")
        response = _dataset_response(session, row, include_cases=False)
        if not response["coverage_complete"]:
            raise HTTPException(status_code=422, detail="48-case category/scenario coverage is incomplete")
        members = _dataset_members(session, row.dataset_version_id)
        row.snapshot_hash = _dataset_snapshot_hash(members)
        if any(member.snapshot_hash != _hash(json.dumps(
            _case_snapshot(case), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )) for member, case in members):
            raise HTTPException(status_code=409, detail="a ground-truth case changed after dataset composition")
        row.status, row.second_approved_by, row.second_approved_at = "APPROVED", current_user.user_id, now
        if row.replaces_dataset_version_id:
            replaced = session.scalar(select(AIGroundTruthDatasetVersion).where(
                AIGroundTruthDatasetVersion.dataset_version_id == row.replaces_dataset_version_id,
                AIGroundTruthDatasetVersion.status == "APPROVED",
            ))
            if replaced is not None:
                replaced.status = "SUPERSEDED"
    elif action == "RETIRE":
        if row.status != "APPROVED":
            raise HTTPException(status_code=409, detail="only an APPROVED dataset can be retired")
        row.status, row.retired_at = "RETIRED", now
    else:
        raise HTTPException(status_code=422, detail="invalid dataset transition action")
    audit_event(session, event_type=f"GROUND_TRUTH_DATASET_{action}", actor_id=current_user.user_id,
                customer_scope=row.customer_scope, site_scope=row.site_scope,
                target_type="GROUND_TRUTH_DATASET", target_id=row.dataset_version_id,
                detail={"reason": payload.reason, "status": row.status})
    session.commit()
    return _dataset_response(session, row)


@router.get("/readiness")
def get_scope_readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
    line_scope: Annotated[str | None, Query(alias="lineScope")] = None,
) -> dict[str, object]:
    return scope_readiness(
        session,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        line_scope=line_scope.strip() if line_scope and line_scope.strip() else None,
        database_scope_value=database_scope(settings.database_url),
        provider=settings.ai_provider,
        model_scope=settings.ai_model,
    )


@router.post("/evaluations")
def run_evaluation(
    payload: AISearchEvaluationRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
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

    cases = list(payload.cases)
    selected_readiness_tracks: set[str] = set()
    db_scope = database_scope(settings.database_url)
    evaluation_line_scope = payload.line_scope.strip() if payload.line_scope and payload.line_scope.strip() else None
    selected_dataset: AIGroundTruthDatasetVersion | None = None
    selected_ground_truth_ids = list(payload.ground_truth_case_ids)
    if payload.dataset_version_id:
        if payload.cases or payload.ground_truth_case_ids:
            raise HTTPException(status_code=422, detail="datasetVersionId cannot be mixed with cases or groundTruthCaseIds")
        selected_dataset = session.scalar(select(AIGroundTruthDatasetVersion).where(
            AIGroundTruthDatasetVersion.dataset_version_id == payload.dataset_version_id,
            AIGroundTruthDatasetVersion.customer_scope == settings.ai_customer_scope,
            AIGroundTruthDatasetVersion.site_scope == settings.ai_site_scope,
            AIGroundTruthDatasetVersion.database_scope == db_scope,
            AIGroundTruthDatasetVersion.line_scope == evaluation_line_scope,
            AIGroundTruthDatasetVersion.status == "APPROVED",
        ))
        if selected_dataset is None:
            raise HTTPException(status_code=404, detail="approved dataset version does not exist in this scope")
        selected_ground_truth_ids = [
            member.ground_truth_case_id
            for member, _ in _dataset_members(session, selected_dataset.dataset_version_id)
        ]
        if _dataset_snapshot_hash(_dataset_members(session, selected_dataset.dataset_version_id)) != selected_dataset.snapshot_hash:
            raise HTTPException(status_code=409, detail="approved dataset snapshot integrity check failed")
    if selected_ground_truth_ids:
        stored_cases = session.scalars(
            select(AISearchGroundTruthCase).where(
                AISearchGroundTruthCase.ground_truth_case_id.in_(selected_ground_truth_ids),
                AISearchGroundTruthCase.customer_scope == settings.ai_customer_scope,
                AISearchGroundTruthCase.site_scope == settings.ai_site_scope,
                AISearchGroundTruthCase.database_scope == db_scope,
                AISearchGroundTruthCase.line_scope == evaluation_line_scope,
                AISearchGroundTruthCase.is_active.is_(True),
            )
        ).all()
        if len(stored_cases) != len(set(selected_ground_truth_ids)):
            raise HTTPException(status_code=404, detail="one or more approved ground-truth cases do not exist in this scope")
        selected_readiness_tracks = set(
            session.scalars(
                select(AISearchGroundTruthProvenance.readiness_track).where(
                    AISearchGroundTruthProvenance.ground_truth_case_id.in_(selected_ground_truth_ids),
                    AISearchGroundTruthProvenance.approval_status == "APPROVED",
                )
            ).all()
        )
        if not selected_readiness_tracks or len(selected_readiness_tracks) != 1:
            raise HTTPException(
                status_code=422,
                detail="groundTruthCaseIds must all have approved provenance in one readiness track",
            )
        for stored in stored_cases:
            cases.append(
                AISearchEvaluationCaseRequest(
                    caseKey=stored.case_key,
                    question=stored.question,
                    expectedOutcome=stored.expected_outcome,
                    expectedEvidence=json.loads(stored.expected_evidence_json),
                    expectedExcluded=json.loads(stored.excluded_evidence_json),
                    allowedRankMin=stored.allowed_rank_min,
                    allowedRankMax=stored.allowed_rank_max,
                    asOf=stored.as_of,
                    limit=max(stored.allowed_rank_max, 20),
                    category=stored.category,
                    scenario_type=stored.scenario_type,
                )
            )
    if not cases:
        raise HTTPException(status_code=422, detail="cases or groundTruthCaseIds must contain at least one case")
    if len({case.case_key for case in cases}) != len(cases):
        raise HTTPException(status_code=422, detail="caseKey must be unique within an evaluation run")
    if any(case.allowed_rank_min > case.allowed_rank_max for case in cases):
        raise HTTPException(status_code=422, detail="allowedRankMin must not exceed allowedRankMax")

    content_filter = load_sensitive_filter(session, settings)
    rebuild_ai_search_candidates(session, content_filter)
    first_candidates = session.scalars(select(AISearchCandidate).order_by(AISearchCandidate.candidate_id)).all()
    first_identity = {item.candidate_id: item.content_hash for item in first_candidates}
    first_rankings = {
        case.case_key: [
            item.candidate_id
            for item in _rank_candidates(session, case.question, evaluate_as, case.limit, case.as_of)[0]
        ]
        for case in cases
    }
    session.expunge_all()
    rebuild_ai_search_candidates(session, content_filter)
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
    if selected_dataset is not None:
        session.add(AIEvaluationDatasetBinding(
            run_id=run_id,
            dataset_version_id=selected_dataset.dataset_version_id,
            dataset_snapshot_hash=selected_dataset.snapshot_hash or "",
        ))
    case_results: list[dict[str, object]] = []
    source_types: set[str] = set()
    excluded_reasons: set[str] = set()
    ranking_stable = True
    precision_values: list[float] = []
    recall_values: list[float] = []
    excluded_source_violations = 0
    trace_success_count = 0
    trace_total_count = 0
    permission_leak_violations = 0
    nonexistent_citation_violations = 0
    semantic_match_count = 0
    semantic_match_total = 0
    conflict_case_count = 0
    conflict_disclosed_count = 0
    for case in cases:
        expected_outcome = case.expected_outcome.strip().upper()
        if expected_outcome not in {"SUFFICIENT", "INSUFFICIENT_EVIDENCE"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="expectedOutcome must be SUFFICIENT or INSUFFICIENT_EVIDENCE",
            )
        actual, denied = _rank_candidates(session, case.question, evaluate_as, case.limit, case.as_of)
        actual_ids = [item.candidate_id for item in actual]
        stable_for_case = first_rankings[case.case_key] == actual_ids
        ranking_stable = ranking_stable and stable_for_case
        expected_candidates = [
            next((item for item in all_candidates if _matches_reference(item, reference)), None)
            for reference in case.expected_evidence
        ]
        expected_ids = [item.candidate_id for item in expected_candidates if item is not None]
        allowed_actual_ids = actual_ids[case.allowed_rank_min - 1:case.allowed_rank_max]
        missing_expected = [
            _reference_key(reference)
            for reference, candidate in zip(case.expected_evidence, expected_candidates)
            if candidate is None or candidate.candidate_id not in allowed_actual_ids
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
        excluded_passed = all(
            item["excluded"] and item["reason_matches"] and item["content_hash_matches"]
            for item in excluded
        )
        excluded_source_violations += sum(1 for item in excluded if not item["excluded"])
        expected_id_set = set(expected_ids)
        precision_k = (
            len(expected_id_set.intersection(allowed_actual_ids)) / len(allowed_actual_ids)
            if allowed_actual_ids else (1.0 if not expected_id_set else 0.0)
        )
        recall_k = (
            len(expected_id_set.intersection(allowed_actual_ids)) / len(expected_id_set)
            if expected_id_set else 1.0
        )
        precision_values.append(precision_k)
        recall_values.append(recall_k)
        case_trace_success = sum(1 for item in actual if _candidate_trace_exists(session, item))
        trace_success_count += case_trace_success
        trace_total_count += len(actual)
        nonexistent_citation_violations += len(actual) - case_trace_success
        permission_leak_violations += sum(1 for item in actual if not _can_evaluate_candidate(session, item, evaluate_as))
        expected_semantic_matches = [
            candidate
            for candidate in expected_candidates
            if candidate is not None and _candidate_rank(candidate, _tokens(case.question), {
                token: sum(1 for item in all_candidates if token in item.search_text.lower())
                for token in _tokens(case.question)
            }) > 0
        ]
        semantic_match_count += len(expected_semantic_matches)
        semantic_match_total += len(case.expected_evidence)
        conflict_disclosed = None
        if case.scenario_type == "CONFLICT":
            conflict_case_count += 1
            conflict_disclosed = len(expected_ids) >= 2 and not missing_expected
            conflict_disclosed_count += int(conflict_disclosed)
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
        previous_run_delta = _previous_case_delta(
            session,
            run_id=run_id,
            case_key=case.case_key,
            actual_evidence=actual_evidence,
            ranking_hash=ranking_hash,
        )
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
                "allowed_rank_range": [case.allowed_rank_min, case.allowed_rank_max],
                "as_of": case.as_of.isoformat() if case.as_of else None,
                "precision_at_k": round(precision_k, 4),
                "recall_at_k": round(recall_k, 4),
                "excluded_source_violation": sum(1 for item in excluded if not item["excluded"]),
                "citation_trace_success_rate": round(case_trace_success / len(actual), 4) if actual else 1.0,
                "permission_leak_violation": sum(
                    1 for item in actual if not _can_evaluate_candidate(session, item, evaluate_as)
                ),
                "nonexistent_citation_violation": len(actual) - case_trace_success,
                "citation_semantic_match_rate": (
                    round(len(expected_semantic_matches) / len(case.expected_evidence), 4)
                    if case.expected_evidence else 1.0
                ),
                "conflict_disclosed": conflict_disclosed,
                "ranking_hash": ranking_hash,
                "previous_run_delta": previous_run_delta,
                "ranking_stable": stable_for_case,
                "passed": passed,
            }
        )

    passed_count = sum(1 for item in case_results if item["passed"])
    readiness = _field_comment_review_readiness(session)
    all_passed = passed_count == len(case_results)
    source_coverage_complete = source_types == set(AI_SEARCH_SOURCE_TYPES)
    scoped_readiness = scope_readiness(
        session,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        line_scope=evaluation_line_scope,
        database_scope_value=db_scope,
        provider=settings.ai_provider,
        model_scope=settings.ai_model,
    )
    top_k_inclusion_rate = round(sum(recall_values) / len(recall_values), 4)
    citation_semantic_match_rate = (
        round(semantic_match_count / semantic_match_total, 4) if semantic_match_total else 1.0
    )
    conflict_disclosure_rate = (
        round(conflict_disclosed_count / conflict_case_count, 4) if conflict_case_count else 1.0
    )
    quality_gate_passed = bool(
        top_k_inclusion_rate >= 1.0
        and excluded_source_violations == 0
        and permission_leak_violations == 0
        and nonexistent_citation_violations == 0
        and citation_semantic_match_rate >= 1.0
        and conflict_disclosure_rate >= 1.0
    )
    readiness_track = next(iter(selected_readiness_tracks), "AD_HOC")
    provider_start_ready = bool(
        all_passed and candidate_identity_stable and ranking_stable
        and quality_gate_passed
        and source_coverage_complete and readiness.missing_reviewed_count == 0
        and scoped_readiness["source_ready"] and scoped_readiness["ground_truth_ready"]
        and scoped_readiness["human_sample_review_ready"]
        and scoped_readiness["provider_review_ready"]
        and selected_dataset is not None
        and len(selected_ground_truth_ids) == len(case_results)
        and len(case_results) >= scoped_readiness["ground_truth_minimum"]
        and readiness_track == "FIELD_READINESS"
    )
    metrics = {
        "case_count": len(case_results),
        "passed_count": passed_count,
        "source_types_covered": sorted(source_types),
        "source_coverage_complete": source_coverage_complete,
        "excluded_reasons_observed": sorted(excluded_reasons),
        "field_comment_reviewed_count": readiness.reviewed_status_count,
        "field_comment_missing_reviewed_count": readiness.missing_reviewed_count,
        "precision_at_k": round(sum(precision_values) / len(precision_values), 4),
        "recall_at_k": round(sum(recall_values) / len(recall_values), 4),
        "top_k_inclusion_rate": top_k_inclusion_rate,
        "excluded_source_violation": excluded_source_violations,
        "permission_leak_violation": permission_leak_violations,
        "nonexistent_citation_violation": nonexistent_citation_violations,
        "citation_trace_success_rate": round(trace_success_count / trace_total_count, 4) if trace_total_count else 1.0,
        "citation_semantic_match_rate": citation_semantic_match_rate,
        "conflict_disclosure_rate": conflict_disclosure_rate,
        "quality_gate_passed": quality_gate_passed,
        "customer_scope": settings.ai_customer_scope,
        "site_scope": settings.ai_site_scope,
        "line_scope": evaluation_line_scope,
        "database_scope": db_scope,
        "evaluator_version": payload.evaluator_version,
        "prompt_version_id": payload.prompt_version_id,
        "policy_version": payload.policy_version,
        "provider_start_ready": provider_start_ready,
        "readiness_track": readiness_track,
        "dataset_version_id": selected_dataset.dataset_version_id if selected_dataset else None,
        "dataset_snapshot_hash": selected_dataset.snapshot_hash if selected_dataset else None,
    }
    result_status = (
        "PASSED"
        if all_passed and candidate_identity_stable and ranking_stable and quality_gate_passed
        else "FAILED"
    )
    evaluation_run.status = result_status
    evaluation_run.ranking_stable = ranking_stable
    evaluation_run.metrics_json = json.dumps(metrics, ensure_ascii=False)
    session.commit()
    return {
        "run_id": run_id,
        "status": result_status,
        "evaluated_as_user_id": evaluate_as_user_id,
        "candidate_identity_stable": candidate_identity_stable,
        "ranking_stable": ranking_stable,
        **metrics,
        "cases": case_results,
    }


def _evaluation_response(session: Session, run: AISearchEvaluationRun) -> dict[str, object]:
    try:
        metrics = json.loads(run.metrics_json)
    except (TypeError, ValueError):
        metrics = {}
    binding = session.scalar(select(AIEvaluationDatasetBinding).where(
        AIEvaluationDatasetBinding.run_id == run.run_id
    ))
    cases = session.scalars(select(AISearchEvaluationCase).where(
        AISearchEvaluationCase.run_id == run.run_id
    ).order_by(AISearchEvaluationCase.case_key)).all()
    case_rows = []
    for case in cases:
        actual = json.loads(case.actual_evidence_json or "[]")
        excluded = json.loads(case.excluded_evidence_json or "[]")
        failures: list[str] = []
        if case.expected_outcome != case.actual_outcome:
            failures.append("EXPECTED_OUTCOME_MISMATCH")
        if not case.passed:
            failures.append("EXPECTED_SOURCE_MISSING_OR_RANK_OUTSIDE_ALLOWED_RANGE")
        if any(not item.get("excluded", False) for item in excluded if isinstance(item, dict)):
            failures.append("EXCLUDED_SOURCE_EXPOSED")
        case_rows.append({
            "evaluation_case_id": case.evaluation_case_id,
            "case_key": case.case_key,
            "question": case.question,
            "expected_outcome": case.expected_outcome,
            "actual_outcome": case.actual_outcome,
            "expected_evidence": json.loads(case.expected_evidence_json or "[]"),
            "actual_evidence": actual,
            "excluded_evidence": excluded,
            "ranking_hash": case.ranking_hash,
            "passed": case.passed,
            "failure_reasons": failures,
        })
    return {
        "run_id": run.run_id,
        "run_label": run.run_label,
        "status": run.status,
        "requested_by": run.requested_by,
        "evaluated_as_user_id": run.evaluated_as_user_id,
        "candidate_identity_stable": run.candidate_identity_stable,
        "ranking_stable": run.ranking_stable,
        "dataset_version_id": binding.dataset_version_id if binding else metrics.get("dataset_version_id"),
        "dataset_snapshot_hash": binding.dataset_snapshot_hash if binding else metrics.get("dataset_snapshot_hash"),
        "metrics": metrics,
        "cases": case_rows,
        "created_at": run.created_at,
    }


@router.get("/evaluations")
def list_evaluations(
    session: Annotated[Session, Depends(get_db_session)],
    dataset_version_id: Annotated[str | None, Query(alias="datasetVersionId")] = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    statement = select(AISearchEvaluationRun).order_by(
        desc(AISearchEvaluationRun.created_at), desc(AISearchEvaluationRun.id)
    )
    if dataset_version_id:
        statement = statement.join(
            AIEvaluationDatasetBinding,
            AIEvaluationDatasetBinding.run_id == AISearchEvaluationRun.run_id,
        ).where(AIEvaluationDatasetBinding.dataset_version_id == dataset_version_id)
    rows = session.scalars(statement.limit(min(max(limit, 1), 500))).all()
    return [_evaluation_response(session, row) for row in rows]


@router.get("/evaluations/{run_id}")
def get_evaluation(
    run_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    compare_to_run_id: Annotated[str | None, Query(alias="compareToRunId")] = None,
) -> dict[str, object]:
    run = session.scalar(select(AISearchEvaluationRun).where(AISearchEvaluationRun.run_id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation run does not exist")
    response = _evaluation_response(session, run)
    if compare_to_run_id:
        previous = session.scalar(select(AISearchEvaluationRun).where(
            AISearchEvaluationRun.run_id == compare_to_run_id
        ))
        if previous is None:
            raise HTTPException(status_code=404, detail="comparison evaluation run does not exist")
        previous_response = _evaluation_response(session, previous)
        previous_cases = {item["case_key"]: item for item in previous_response["cases"]}
        response["comparison"] = {
            "run_id": compare_to_run_id,
            "status_changed": run.status != previous.status,
            "case_deltas": [
                {
                    "case_key": item["case_key"],
                    "previous_passed": previous_cases.get(item["case_key"], {}).get("passed"),
                    "current_passed": item["passed"],
                    "ranking_changed": previous_cases.get(item["case_key"], {}).get("ranking_hash")
                    not in {None, item["ranking_hash"]},
                }
                for item in response["cases"]
            ],
        }
    return response


@router.post("/candidates/rebuild", response_model=AISearchRebuildResponse)
def rebuild_candidates(
    _current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AISearchRebuildResponse:
    return rebuild_ai_search_candidates(session, load_sensitive_filter(session, settings))


@router.get("/candidates", response_model=list[AISearchCandidateResponse])
def list_candidates(
    current_user: CurrentUser,
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
    rows = session.scalars(statement.limit(500)).all()
    user = session.scalar(select(UserAccount).where(UserAccount.user_id == current_user.user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="authenticated user does not exist")
    visible = [candidate for candidate in rows if _can_evaluate_candidate(session, candidate, user)]
    return [_candidate_response(candidate) for candidate in visible[: min(max(limit, 1), 500)]]


@router.get("/quality", response_model=AISearchQualityResponse)
def get_quality(
    _current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AISearchQualityResponse:
    return _quality_response(session, load_sensitive_filter(session, settings))
