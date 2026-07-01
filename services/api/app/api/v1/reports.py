from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, ReportWriteUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.storage import resolve_storage_root
from app.db.models import (
    ActivityHistory,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    FileObject,
    Report,
    ReportSource,
    TagDefinition,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])

REPORT_SOURCE_TYPES = {
    "FIELD_COMMENT",
    "DOCUMENT",
    "WORK_SEQUENCE_ITEM",
    "WORK_SEQUENCE_HISTORY",
    "WORK_RECORD",
    "WORK_RECORD_VERSION",
}
DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}


class ReportSourceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_type: str = Field(alias="sourceType", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1)
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    relation_type: str | None = Field(default=None, alias="relationType")


class ReportDraftCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    report_type: str = Field(alias="reportType", min_length=1)
    title: str = Field(min_length=1)
    summary: str | None = None
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    conclusion: str | None = None
    action_plan: str | None = Field(default=None, alias="actionPlan")
    work_record_id: str | None = Field(default=None, alias="workRecordId")
    structure_item_id: str | None = Field(default=None, alias="structureItemId")
    period_start: datetime | None = Field(default=None, alias="periodStart")
    period_end: datetime | None = Field(default=None, alias="periodEnd")
    sources: list[ReportSourceRequest] = Field(min_length=1)


class ReportSaveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    draft_report_id: str | None = Field(default=None, alias="draftReportId")
    report_type: str | None = Field(default=None, alias="reportType")
    title: str | None = None
    summary: str | None = None
    analysis_content: str | None = Field(default=None, alias="analysisContent")
    conclusion: str | None = None
    action_plan: str | None = Field(default=None, alias="actionPlan")
    work_record_id: str | None = Field(default=None, alias="workRecordId")
    structure_item_id: str | None = Field(default=None, alias="structureItemId")
    period_start: datetime | None = Field(default=None, alias="periodStart")
    period_end: datetime | None = Field(default=None, alias="periodEnd")
    sources: list[ReportSourceRequest] | None = None
    save_as_document: bool = Field(default=False, alias="saveAsDocument")
    document_title: str | None = Field(default=None, alias="documentTitle")
    document_status: str = Field(default="IN_REVIEW", alias="documentStatus")


class ReportSourceResponse(BaseModel):
    source_type: str
    source_id: str
    source_version_id: str | None
    relation_type: str | None
    summary: str | None
    created_at: datetime


class ReportDocumentSummary(BaseModel):
    document_id: str
    title: str
    status: str
    latest_version_id: str | None
    published_version_id: str | None


class ReportResponse(BaseModel):
    report_id: str
    report_type: str
    title: str
    summary: str | None
    analysis_content: str | None
    conclusion: str | None
    action_plan: str | None
    work_record_id: str | None
    structure_item_id: str | None
    period_start: datetime | None
    period_end: datetime | None
    status: str
    ai_draft_used: bool
    generated_document_id: str | None
    created_by: str | None
    reviewed_by: str | None
    approved_by: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    approved_at: datetime | None
    sources: list[ReportSourceResponse]
    generated_document: ReportDocumentSummary | None = None


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


def _validate_source(session: Session, source: ReportSourceRequest) -> tuple[str, str, str | None, str | None]:
    source_type = _normalize_source_type(source.source_type)
    source_id = source.source_id.strip()
    source_version_id = _clean_optional(source.source_version_id)
    relation_type = _clean_optional(source.relation_type)

    if source_type == "FIELD_COMMENT":
        exists = session.scalar(select(FieldComment.id).where(FieldComment.comment_id == source_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="FIELD_COMMENT source is unknown.")
    elif source_type == "DOCUMENT":
        document = session.scalar(
            select(Document).where(Document.document_id == source_id, Document.deleted_at.is_(None))
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="DOCUMENT source is unknown.")
        if source_version_id is not None:
            version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == source_version_id))
            if version is None or version.document_id != document.document_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="sourceVersionId must belong to the DOCUMENT source.",
                )
    elif source_type == "WORK_SEQUENCE_ITEM":
        exists = session.scalar(select(WorkSequenceItem.id).where(WorkSequenceItem.item_id == source_id))
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="WORK_SEQUENCE_ITEM source is unknown.",
            )
    elif source_type == "WORK_SEQUENCE_HISTORY":
        exists = session.scalar(select(WorkSequenceChangeHistory.id).where(WorkSequenceChangeHistory.change_id == source_id))
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="WORK_SEQUENCE_HISTORY source is unknown.",
            )
    elif source_type == "WORK_RECORD":
        exists = session.scalar(select(WorkRecord.id).where(WorkRecord.work_record_id == source_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="WORK_RECORD source is unknown.")
    elif source_type == "WORK_RECORD_VERSION":
        exists = session.scalar(select(WorkRecordVersion.id).where(WorkRecordVersion.version_id == source_id))
        if exists is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="WORK_RECORD_VERSION source is unknown.",
            )

    return source_type, source_id, source_version_id, relation_type


def _replace_report_sources(session: Session, report_id: str, sources: list[ReportSourceRequest]) -> None:
    session.query(ReportSource).filter(ReportSource.report_id == report_id).delete(synchronize_session=False)
    for source in sources:
        source_type, source_id, source_version_id, relation_type = _validate_source(session, source)
        session.add(
            ReportSource(
                report_id=report_id,
                source_type=source_type,
                source_id=source_id,
                source_version_id=source_version_id,
                relation_type=relation_type,
            )
        )


def _source_summary(session: Session, source: ReportSource) -> str | None:
    if source.source_type == "FIELD_COMMENT":
        comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == source.source_id))
        return comment.raw_content if comment is not None else None
    if source.source_type == "DOCUMENT":
        document = session.scalar(select(Document).where(Document.document_id == source.source_id))
        if document is None:
            return None
        return f"{document.title} ({source.source_version_id or document.latest_version_id or 'no version'})"
    if source.source_type == "WORK_SEQUENCE_ITEM":
        item = session.scalar(select(WorkSequenceItem).where(WorkSequenceItem.item_id == source.source_id))
        return item.title if item is not None else None
    if source.source_type == "WORK_SEQUENCE_HISTORY":
        history = session.scalar(select(WorkSequenceChangeHistory).where(WorkSequenceChangeHistory.change_id == source.source_id))
        if history is None:
            return None
        return f"{history.change_type}: {history.before_value or ''} -> {history.after_value or ''}".strip()
    if source.source_type == "WORK_RECORD":
        work_record = session.scalar(select(WorkRecord).where(WorkRecord.work_record_id == source.source_id))
        return work_record.title if work_record is not None else None
    if source.source_type == "WORK_RECORD_VERSION":
        version = session.scalar(select(WorkRecordVersion).where(WorkRecordVersion.version_id == source.source_id))
        return version.summary if version is not None else None
    return None


def _report_body(report: Report, sources: list[ReportSource]) -> bytes:
    sections = [
        ("Title", report.title),
        ("Type", report.report_type),
        ("Summary", report.summary),
        ("Analysis", report.analysis_content),
        ("Conclusion", report.conclusion),
        ("Action Plan", report.action_plan),
        (
            "Sources",
            "\n".join(
                f"- {source.source_type}: {source.source_id}"
                + (f" ({source.source_version_id})" if source.source_version_id else "")
                for source in sources
            ),
        ),
    ]
    text = "\n\n".join(f"# {name}\n{value}" for name, value in sections if value)
    return text.encode("utf-8")


def _save_report_document(
    session: Session,
    report: Report,
    sources: list[ReportSource],
    app_settings: Settings,
    actor_id: str,
    document_title: str,
    document_status: str,
) -> Document:
    document_status = _normalize_choice(document_status, DOCUMENT_STATUSES, "documentStatus")
    document_id = _new_public_id("doc")
    version_id = _new_public_id("ver")
    file_name = f"{report.report_id}.txt"
    body = _report_body(report, sources)
    storage_root = resolve_storage_root(app_settings.storage_root)
    report_dir = storage_root / "reports" / report.report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    file_path = report_dir / file_name
    file_path.write_bytes(body)
    storage_key = str(file_path.relative_to(storage_root)).replace("\\", "/")
    now = datetime.now(timezone.utc)
    is_published = document_status == "PUBLISHED"

    file_object = FileObject(
        storage_key=storage_key,
        original_filename=file_name,
        extension=".txt",
        mime_type="text/plain",
        file_family="text",
        size_bytes=len(body),
        hash_sha256=hashlib.sha256(body).hexdigest(),
    )
    session.add(file_object)
    session.flush()

    document = Document(
        document_id=document_id,
        title=document_title,
        description=f"Manual report document from {report.report_id}.",
        document_type="report",
        owner_id=actor_id,
        status=document_status,
        latest_version_id=version_id,
        published_version_id=version_id if is_published else None,
    )
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        file_object_id=file_object.id,
        version_no=1,
        version_label="v1",
        change_reason=f"Manual report save from {report.report_id}.",
        version_status="PUBLISHED" if is_published else "APPROVED",
        is_latest=True,
        is_published=is_published,
        published_at=now if is_published else None,
        created_by=actor_id,
    )
    session.add(document)
    session.add(version)
    session.flush()
    _apply_report_document_tags(session, document_id, sources)
    return document


def _record_activity(session: Session, event_type: str, actor_id: str, report: Report, message: str) -> None:
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type=event_type,
            actor_id=actor_id,
            target_type="report",
            target_id=report.report_id,
            target_title=report.title,
            message=message,
        )
    )


def _normalize_tag_code(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _ensure_tag(session: Session, name: str) -> TagDefinition:
    code = _normalize_tag_code(name)
    existing = session.scalar(
        select(TagDefinition).where(TagDefinition.tag_type == "custom", TagDefinition.code == code)
    )
    if existing is not None:
        if existing.name != name:
            existing.name = name
        if not existing.is_active:
            existing.is_active = True
        return existing

    tag = TagDefinition(
        tag_id=_new_public_id("tag"),
        tag_type="custom",
        code=code,
        name=name,
    )
    session.add(tag)
    session.flush()
    return tag


def _source_tag_names(sources: list[ReportSource]) -> list[str]:
    tags = ["Report"]
    source_tags = {
        "FIELD_COMMENT": "FieldComment",
        "DOCUMENT": "Document",
        "WORK_SEQUENCE_ITEM": "WorkSequence",
        "WORK_SEQUENCE_HISTORY": "WorkSequence",
        "WORK_RECORD": "WorkRecord",
        "WORK_RECORD_VERSION": "WorkRecord",
    }
    for source in sources:
        tag = source_tags.get(source.source_type)
        if tag is not None and tag not in tags:
            tags.append(tag)
    return tags


def _apply_report_document_tags(
    session: Session,
    document_id: str,
    sources: list[ReportSource],
) -> None:
    for name in _source_tag_names(sources):
        tag = _ensure_tag(session, name)
        session.add(DocumentTag(document_id=document_id, tag_id=tag.tag_id))


def _report_response(session: Session, report: Report) -> ReportResponse:
    sources = session.scalars(
        select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
    ).all()
    document = None
    if report.generated_document_id is not None:
        document = session.scalar(select(Document).where(Document.document_id == report.generated_document_id))

    return ReportResponse(
        report_id=report.report_id,
        report_type=report.report_type,
        title=report.title,
        summary=report.summary,
        analysis_content=report.analysis_content,
        conclusion=report.conclusion,
        action_plan=report.action_plan,
        work_record_id=report.work_record_id,
        structure_item_id=report.structure_item_id,
        period_start=report.period_start,
        period_end=report.period_end,
        status=report.status,
        ai_draft_used=report.ai_draft_used,
        generated_document_id=report.generated_document_id,
        created_by=report.created_by,
        reviewed_by=report.reviewed_by,
        approved_by=report.approved_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
        reviewed_at=report.reviewed_at,
        approved_at=report.approved_at,
        sources=[
            ReportSourceResponse(
                source_type=source.source_type,
                source_id=source.source_id,
                source_version_id=source.source_version_id,
                relation_type=source.relation_type,
                summary=_source_summary(session, source),
                created_at=source.created_at,
            )
            for source in sources
        ],
        generated_document=(
            ReportDocumentSummary(
                document_id=document.document_id,
                title=document.title,
                status=document.status,
                latest_version_id=document.latest_version_id,
                published_version_id=document.published_version_id,
            )
            if document is not None
            else None
        ),
    )


@router.post("/drafts", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report_draft(
    request: ReportDraftCreateRequest,
    current_user: ReportWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    report = Report(
        report_id=_new_public_id("report"),
        report_type=request.report_type.strip(),
        title=request.title.strip(),
        summary=_clean_optional(request.summary),
        analysis_content=_clean_optional(request.analysis_content),
        conclusion=_clean_optional(request.conclusion),
        action_plan=_clean_optional(request.action_plan),
        work_record_id=_validate_work_record(session, request.work_record_id),
        structure_item_id=_clean_optional(request.structure_item_id),
        period_start=request.period_start,
        period_end=request.period_end,
        status="DRAFT",
        ai_draft_used=False,
        created_by=current_user.user_id,
    )
    session.add(report)
    session.flush()
    _replace_report_sources(session, report.report_id, request.sources)
    _record_activity(session, "report.draft_created", current_user.user_id, report, f"Report draft created: {report.title}.")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report draft could not be saved.") from exc
    session.refresh(report)
    return _report_response(session, report)


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def save_report(
    request: ReportSaveRequest,
    current_user: ReportWriteUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    now = datetime.now(timezone.utc)
    if request.draft_report_id is not None:
        report = session.scalar(select(Report).where(Report.report_id == request.draft_report_id))
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report draft not found.")
    else:
        if not request.sources:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="sources is required.")
        report = Report(
            report_id=_new_public_id("report"),
            report_type=_clean_required(request.report_type, "reportType"),
            title=_clean_required(request.title, "title"),
            created_by=current_user.user_id,
        )
        session.add(report)
        session.flush()
        _replace_report_sources(session, report.report_id, request.sources)

    if request.sources is not None:
        _replace_report_sources(session, report.report_id, request.sources)

    report.report_type = _clean_optional(request.report_type) or report.report_type
    report.title = _clean_optional(request.title) or report.title
    report.summary = _clean_optional(request.summary) if request.summary is not None else report.summary
    report.analysis_content = _clean_optional(request.analysis_content) if request.analysis_content is not None else report.analysis_content
    report.conclusion = _clean_optional(request.conclusion) if request.conclusion is not None else report.conclusion
    report.action_plan = _clean_optional(request.action_plan) if request.action_plan is not None else report.action_plan
    report.work_record_id = _validate_work_record(session, request.work_record_id) if request.work_record_id is not None else report.work_record_id
    report.structure_item_id = _clean_optional(request.structure_item_id) if request.structure_item_id is not None else report.structure_item_id
    report.period_start = request.period_start if request.period_start is not None else report.period_start
    report.period_end = request.period_end if request.period_end is not None else report.period_end
    report.status = "APPROVED"
    report.reviewed_by = current_user.user_id
    report.approved_by = current_user.user_id
    report.reviewed_at = now
    report.approved_at = now

    sources = session.scalars(
        select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
    ).all()
    if request.save_as_document:
        document = _save_report_document(
            session,
            report,
            sources,
            app_settings,
            current_user.user_id,
            _clean_optional(request.document_title) or report.title,
            request.document_status,
        )
        report.generated_document_id = document.document_id

    _record_activity(session, "report.approved", current_user.user_id, report, f"Report approved: {report.title}.")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report could not be saved.") from exc
    session.refresh(report)
    return _report_response(session, report)


@router.get("", response_model=list[ReportResponse])
def list_reports(
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportResponse]:
    reports = session.scalars(select(Report).order_by(desc(Report.updated_at), desc(Report.id))).all()
    return [_report_response(session, report) for report in reports]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    _current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    report = session.scalar(select(Report).where(Report.report_id == report_id))
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return _report_response(session, report)
