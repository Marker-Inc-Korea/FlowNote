from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select, update
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
    ReportMutationReceipt,
    ReportSource,
    NotificationChannel,
    NotificationChannelMember,
    TagDefinition,
    WorkRecord,
    WorkRecordVersion,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    MutationTrace,
    canonical_hash,
    check_common_mutation_replay,
    mutation_trace,
    record_common_mutation_failure,
    record_common_mutation_result,
)

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])

REPORT_SOURCE_TYPES = {
    "FIELD_COMMENT",
    "DOCUMENT",
    "WORK_SEQUENCE_ITEM",
    "WORK_SEQUENCE_HISTORY",
    "WORK_RECORD",
    "WORK_RECORD_VERSION",
}
FIELD_COMMENT_REPORT_SOURCE_STATUS = "SELECTED"
DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}
SOURCE_NOT_VISIBLE_DETAIL = {
    "code": "SOURCE_NOT_VISIBLE",
    "message": "요청한 원천을 찾을 수 없거나 현재 공개 범위에서 열람할 수 없습니다.",
}
REPORT_NOT_VISIBLE_DETAIL = {
    "code": "RESOURCE_NOT_FOUND",
    "message": "요청한 보고서를 찾을 수 없습니다.",
}


class ReportSourceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_type: str = Field(alias="sourceType", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1)
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    relation_type: str | None = Field(default=None, alias="relationType")
    source_revision: int | None = Field(default=None, alias="sourceRevision", ge=1)
    source_hash_sha256: str | None = Field(default=None, alias="sourceHashSha256", min_length=64, max_length=64)


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

    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
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
    base_report_revision: int | None = Field(default=None, alias="baseReportRevision", ge=1)
    mutation_key: str | None = Field(default=None, alias="mutationKey", max_length=160)
    content_hash_sha256: str | None = Field(default=None, alias="contentHashSha256")
    source_set_hash_sha256: str | None = Field(default=None, alias="sourceSetHashSha256")


class ReportSourceResponse(BaseModel):
    source_type: str
    source_id: str
    source_version_id: str | None
    source_revision: int | None
    trace_id: str
    source_hash_sha256: str
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
    report_revision: int
    content_hash_sha256: str | None
    source_set_hash_sha256: str | None


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
    source: ReportSourceRequest,
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


def _report_content_hash(report: Report) -> str:
    return _hash_payload({
        "report_type": report.report_type,
        "title": report.title,
        "summary": report.summary,
        "analysis_content": report.analysis_content,
        "conclusion": report.conclusion,
        "action_plan": report.action_plan,
        "work_record_id": report.work_record_id,
        "structure_item_id": report.structure_item_id,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "status": report.status,
    })


def _source_set_hash(sources: list[ReportSource]) -> str:
    normalized = sorted(
        ({
            "source_type": source.source_type,
            "source_id": source.source_id,
            "source_version_id": source.source_version_id,
            "source_revision": source.source_revision,
            "source_hash_sha256": source.source_hash_sha256,
            "relation_type": source.relation_type,
        } for source in sources),
        key=lambda item: (
            item["source_type"], item["source_id"], item["source_version_id"] or "",
            item["relation_type"] or "", item["source_hash_sha256"],
        ),
    )
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _report_intent_hash(request: ReportSaveRequest) -> str:
    payload = request.model_dump(
        by_alias=True,
        exclude={"mutation_key", "idempotency_key"},
    )
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _validate_source_set(sources: list[ReportSourceRequest]) -> None:
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
    sources: list[ReportSourceRequest],
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
                ReportSourceRequest(
                    sourceType=source.source_type,
                    sourceId=source.source_id,
                    sourceVersionId=source.source_version_id,
                    relationType=source.relation_type,
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
                + (f" revision={source.source_revision}" if source.source_revision is not None else "")
                + f" trace={source.trace_id} sha256={source.source_hash_sha256}"
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
                source_revision=source.source_revision,
                trace_id=source.trace_id,
                source_hash_sha256=source.source_hash_sha256,
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
        report_revision=report.report_revision,
        content_hash_sha256=report.content_hash_sha256,
        source_set_hash_sha256=report.source_set_hash_sha256,
    )


def _report_sources(session: Session, report_id: str) -> list[ReportSource]:
    return list(
        session.scalars(
            select(ReportSource)
            .where(ReportSource.report_id == report_id)
            .order_by(ReportSource.id)
        ).all()
    )


def _record_report_access(
    session: Session,
    *,
    actor_id: str,
    event_type: str,
    report_id: str | None,
    title: str | None,
    message: str,
) -> None:
    session.add(
        ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type=event_type,
            actor_id=actor_id,
            target_type="report",
            target_id=report_id,
            target_title=title,
            message=message,
        )
    )


def _report_is_readable(
    session: Session,
    report: Report,
    current_user: CurrentUser,
) -> bool:
    try:
        _validate_frozen_sources(
            session,
            _report_sources(session, report.report_id),
            current_user,
        )
    except HTTPException:
        return False
    return True


def _report_idempotent_response(
    session: Session,
    mutation_key: str | None,
    intent_hash: str,
) -> ReportResponse | None:
    if mutation_key is None:
        return None
    common_receipt = check_common_mutation_replay(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type="report.approved",
        target_type="report",
        target_id=None,
    )
    receipt = session.scalar(
        select(ReportMutationReceipt).where(ReportMutationReceipt.mutation_key == mutation_key)
    )
    if receipt is None:
        if common_receipt is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COMMON_RECEIPT_LINK_BROKEN",
                    "message": "공통 receipt와 보고서 receipt 연결이 끊어졌습니다.",
                },
            )
        return None
    if receipt.intent_hash_sha256 != intent_hash:
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "같은 mutation key를 다른 보고서 저장에 사용할 수 없습니다."},
        )
    return ReportResponse.model_validate_json(receipt.response_json)


def _claim_report_revision(session: Session, report: Report, base_revision: int) -> int:
    next_revision = base_revision + 1
    result = session.execute(
        update(Report)
        .where(Report.report_id == report.report_id, Report.report_revision == base_revision)
        .values(report_revision=next_revision, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        session.rollback()
        current_revision = session.scalar(
            select(Report.report_revision).where(Report.report_id == report.report_id)
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REPORT_STALE_REVISION",
                "message": "다른 사용자가 보고서를 먼저 변경했습니다. 새로고침 후 다시 저장하세요.",
                "expectedRevision": base_revision,
                "currentRevision": current_revision,
            },
        )
    report.report_revision = next_revision
    return next_revision


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
    _replace_report_sources(session, report.report_id, request.sources, current_user)
    draft_sources = list(session.scalars(
        select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
    ).all())
    report.content_hash_sha256 = _report_content_hash(report)
    report.source_set_hash_sha256 = _source_set_hash(draft_sources)
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
    http_request: Request,
    request: ReportSaveRequest,
    current_user: ReportWriteUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    idempotency_key = _clean_idempotency_key(request.idempotency_key)
    mutation_key = _clean_idempotency_key(request.mutation_key) or idempotency_key
    intent_hash = _report_intent_hash(request)
    trace = mutation_trace(current_user, http_request)
    target_id = request.draft_report_id or f"report-intent-{intent_hash[:32]}"
    try:
        return _save_report_mutation(
            request=request,
            current_user=current_user,
            app_settings=app_settings,
            session=session,
            idempotency_key=idempotency_key,
            mutation_key=mutation_key,
            intent_hash=intent_hash,
            trace=trace,
        )
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="report.approved",
            trace=trace,
            target_type="report",
            target_id=target_id,
            target_version_id=None,
            target_revision=request.base_report_revision,
            reason=None,
            error=error,
        )
        raise


def _save_report_mutation(
    *,
    request: ReportSaveRequest,
    current_user: CurrentUser,
    app_settings: Settings,
    session: Session,
    idempotency_key: str | None,
    mutation_key: str | None,
    intent_hash: str,
    trace: MutationTrace,
) -> ReportResponse:
    now = datetime.now(timezone.utc)
    replay = _report_idempotent_response(session, mutation_key, intent_hash)
    if replay is not None:
        return replay
    if idempotency_key is not None:
        existing = session.scalar(select(Report).where(Report.idempotency_key == idempotency_key))
        if existing is not None:
            return _report_response(session, existing)

    if request.draft_report_id is not None:
        report = session.scalar(select(Report).where(Report.report_id == request.draft_report_id))
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report draft not found.")
        if report.status not in {"DRAFT", "AI_DRAFTED"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approved or archived report sources cannot be replaced.",
            )
        before_hash = canonical_hash(
            {
                "reportId": report.report_id,
                "reportRevision": report.report_revision,
                "status": report.status,
                "contentHash": report.content_hash_sha256,
                "sourceSetHash": report.source_set_hash_sha256,
            }
        )
        _claim_report_revision(session, report, request.base_report_revision or report.report_revision)
    else:
        before_hash = None
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

    if idempotency_key is not None:
        report.idempotency_key = idempotency_key

    saved_sources: list[ReportSource] | None = None
    if request.sources is not None:
        saved_sources = _replace_report_sources(session, report.report_id, request.sources, current_user)

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

    sources = saved_sources
    if sources is None:
        sources = session.scalars(
            select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
        ).all()
    _validate_frozen_sources(session, list(sources), current_user)
    report.content_hash_sha256 = _report_content_hash(report)
    report.source_set_hash_sha256 = _source_set_hash(list(sources))
    if request.content_hash_sha256 is not None and request.content_hash_sha256.lower() != report.content_hash_sha256:
        raise HTTPException(status_code=409, detail={"code": "REPORT_CONTENT_HASH_MISMATCH", "message": "보고서 내용 hash가 서버 정규화 결과와 다릅니다."})
    if request.source_set_hash_sha256 is not None and request.source_set_hash_sha256.lower() != report.source_set_hash_sha256:
        raise HTTPException(status_code=409, detail={"code": "REPORT_SOURCE_SET_HASH_MISMATCH", "message": "보고서 원천 집합 hash가 서버 정규화 결과와 다릅니다."})

    # 파일/문서 생성 직전 원천 상태·버전·hash·채널 권한을 다시 읽어 검증한다.
    session.flush()
    session.expire_all()
    sources = list(session.scalars(
        select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
    ).all())
    _validate_frozen_sources(session, sources, current_user)
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
        session.flush()
        response = _report_response(session, report)
        if mutation_key is not None:
            receipt = ReportMutationReceipt(
                mutation_key=mutation_key,
                intent_hash_sha256=intent_hash,
                report_id=report.report_id,
                report_revision=report.report_revision,
                content_hash_sha256=report.content_hash_sha256,
                source_set_hash_sha256=report.source_set_hash_sha256,
                generated_document_id=report.generated_document_id,
                generated_version_id=(response.generated_document.latest_version_id if response.generated_document else None),
                response_json=response.model_dump_json(),
            )
            session.add(receipt)
            session.flush()
            record_common_mutation_result(
                session,
                operation_key=mutation_key,
                intent_hash=intent_hash,
                event_type="report.approved",
                trace=trace,
                target_type="report",
                target_id=report.report_id,
                target_version_id=(
                    response.generated_document.latest_version_id
                    if response.generated_document
                    else None
                ),
                target_revision=report.report_revision,
                reason=None,
                before_hash=before_hash,
                after_hash=canonical_hash(
                    {
                        "reportId": report.report_id,
                        "reportRevision": report.report_revision,
                        "status": report.status,
                        "contentHash": report.content_hash_sha256,
                        "sourceSetHash": report.source_set_hash_sha256,
                        "generatedDocumentId": report.generated_document_id,
                    }
                ),
                result="SUCCESS",
                result_code="APPLIED",
                http_status=status.HTTP_201_CREATED,
                response_detail={
                    "code": "APPLIED",
                    "targetId": report.report_id,
                    "targetVersionId": (
                        response.generated_document.latest_version_id
                        if response.generated_document
                        else None
                    ),
                    "targetRevision": report.report_revision,
                },
                domain_receipt_type="report_mutation_receipts",
                domain_receipt_id=str(receipt.id),
                approval_status="APPROVED",
                approved_by=current_user.user_id,
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report could not be saved.") from exc
    session.refresh(report)
    return _report_response(session, report)


@router.get("", response_model=list[ReportResponse])
def list_reports(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportResponse]:
    reports = session.scalars(select(Report).order_by(desc(Report.updated_at), desc(Report.id))).all()
    readable: list[Report] = []
    filtered_count = 0
    for report in reports:
        if _report_is_readable(session, report, current_user):
            readable.append(report)
        else:
            filtered_count += 1
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.list_read",
        report_id=None,
        title=None,
        message=f"보고서 목록 권한 재검사 완료: 반환 {len(readable)}건, 비노출 {filtered_count}건.",
    )
    session.commit()
    return [_report_response(session, report) for report in readable]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    report = session.scalar(select(Report).where(Report.report_id == report_id))
    if report is None or not _report_is_readable(session, report, current_user):
        _record_report_access(
            session,
            actor_id=current_user.user_id,
            event_type="report.read_denied",
            report_id=report_id,
            title=None,
            message="보고서 또는 원천을 현재 권한으로 열람할 수 없어 존재를 숨겼습니다.",
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REPORT_NOT_VISIBLE_DETAIL,
        )
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.read_granted",
        report_id=report.report_id,
        title=report.title,
        message="보고서와 모든 원천의 현재 열람 권한을 재검사해 조회를 허용했습니다.",
    )
    session.commit()
    return _report_response(session, report)


@router.get("/{report_id}/sources", response_model=list[ReportSourceResponse])
def list_report_sources(
    report_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportSourceResponse]:
    report = session.scalar(select(Report).where(Report.report_id == report_id))
    if report is None or not _report_is_readable(session, report, current_user):
        _record_report_access(
            session,
            actor_id=current_user.user_id,
            event_type="report.source_read_denied",
            report_id=report_id,
            title=None,
            message="보고서 원천 열람 권한 재검사에 실패해 보고서와 원천의 존재를 숨겼습니다.",
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=REPORT_NOT_VISIBLE_DETAIL,
        )
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.source_read_granted",
        report_id=report.report_id,
        title=report.title,
        message="보고서의 모든 원천에 대한 현재 열람 권한을 재검사해 조회를 허용했습니다.",
    )
    session.commit()
    return _report_response(session, report).sources
