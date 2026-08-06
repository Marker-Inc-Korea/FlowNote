from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
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
from app.services.report_source_service import (
    _clean_idempotency_key,
    _clean_optional,
    _clean_required,
    _ensure_source_channel_access,
    _hash_payload,
    _normalize_choice,
    _report_event_type,
    _replace_report_sources,
    _validate_frozen_sources,
    _validate_report_transition,
    _validate_work_record,
)
from app.services.report_lifecycle_service import (
    archive_generated_document,
    finalize_report_replacement,
    validate_correction_contract,
)

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])

DOCUMENT_STATUSES = {"WORKING", "IN_REVIEW", "PUBLISHED", "ARCHIVED"}
REPORT_SAVE_STATUSES = {"DRAFT", "REVIEWED", "APPROVED", "ARCHIVED"}


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
    report_status: str = Field(default="APPROVED", alias="reportStatus")
    report_family_id: str | None = Field(default=None, alias="reportFamilyId")
    replaces_report_id: str | None = Field(default=None, alias="replacesReportId")
    replaces_report_revision: int | None = Field(default=None, alias="replacesReportRevision", ge=1)


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
    report_family_id: str
    replaces_report_id: str | None
    replaces_report_revision: int | None
    correction_reason: str | None
    superseded_by_report_id: str | None
    superseded_at: datetime | None
    current_effective_report_id: str | None
    is_current_effective: bool
    requires_re_review: bool
    replacement_state: str


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


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
        "report_family_id": report.report_family_id,
        "replaces_report_id": report.replaces_report_id,
        "replaces_report_revision": report.replaces_report_revision,
        "correction_reason": report.correction_reason,
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


def _report_response(
    session: Session,
    report: Report,
    current_user: CurrentUser | None = None,
) -> ReportResponse:
    sources = session.scalars(
        select(ReportSource).where(ReportSource.report_id == report.report_id).order_by(ReportSource.id)
    ).all()
    document = None
    if report.generated_document_id is not None:
        document = session.scalar(select(Document).where(Document.document_id == report.generated_document_id))
    family_id = report.report_family_id or report.report_id
    current_effective = session.scalar(
        select(Report).where(
            Report.report_family_id == family_id,
            Report.status == "APPROVED",
            Report.superseded_by_report_id.is_(None),
        )
    )

    def visible_id(target_id: str | None) -> str | None:
        if target_id is None or current_user is None:
            return target_id
        target = session.scalar(select(Report).where(Report.report_id == target_id))
        if target is None or not _report_is_readable(session, target, current_user):
            return None
        return target_id

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
        status="SUPERSEDED" if report.superseded_by_report_id else report.status,
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
        report_family_id=family_id,
        replaces_report_id=visible_id(report.replaces_report_id),
        replaces_report_revision=report.replaces_report_revision,
        correction_reason=report.correction_reason,
        superseded_by_report_id=visible_id(report.superseded_by_report_id),
        superseded_at=report.superseded_at,
        current_effective_report_id=visible_id(
            current_effective.report_id if current_effective is not None else None
        ),
        is_current_effective=(
            current_effective is not None and current_effective.report_id == report.report_id
        ),
        requires_re_review=report.replaces_report_id is not None and report.status != "APPROVED",
        replacement_state=(
            "SUPERSEDED" if report.superseded_by_report_id
            else "REPLACEMENT_COMMITTED" if report.replaces_report_id and report.status == "APPROVED"
            else "CORRECTION_PENDING" if report.replaces_report_id
            else "NONE"
        ),
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
        for source in _report_sources(session, report.report_id):
            # 읽기에서는 당시 고정 snapshot을 보존한다. 현재 적격 상태와 hash 재검증은
            # 상태 전이/문서 저장 때만 수행하고, 여기서는 현재 채널 권한만 다시 확인한다.
            _ensure_source_channel_access(
                session,
                current_user,
                source.source_type,
                source.source_id,
            )
    except HTTPException:
        return False
    return True


def _report_idempotent_response(
    session: Session,
    mutation_key: str | None,
    intent_hash: str,
    event_type: str,
) -> ReportResponse | None:
    if mutation_key is None:
        return None
    common_receipt = check_common_mutation_replay(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type=event_type,
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
    report.report_family_id = report.report_id
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
    return _report_response(session, report, current_user)


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
    target_status = _normalize_choice(request.report_status, REPORT_SAVE_STATUSES, "reportStatus")
    event_type = _report_event_type(target_status)
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
            target_status=target_status,
            event_type=event_type,
        )
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type=event_type,
            trace=trace,
            target_type="report",
            target_id=target_id,
            target_version_id=None,
            target_revision=request.base_report_revision,
            reason=None,
            error=error,
            related_target_type="report" if request.replaces_report_id else None,
            related_target_id=request.replaces_report_id,
            related_target_revision=request.replaces_report_revision,
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
    target_status: str,
    event_type: str,
) -> ReportResponse:
    now = datetime.now(timezone.utc)
    replay = _report_idempotent_response(session, mutation_key, intent_hash, event_type)
    if replay is not None:
        return replay
    if idempotency_key is not None:
        existing = session.scalar(select(Report).where(Report.idempotency_key == idempotency_key))
        if existing is not None:
            return _report_response(session, existing, current_user)

    if request.draft_report_id is not None:
        report = session.scalar(select(Report).where(Report.report_id == request.draft_report_id))
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report draft not found.")
        if report.superseded_by_report_id is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "REPORT_IMMUTABLE", "message": "대체된 확정 보고서는 제자리에서 변경할 수 없습니다."},
            )
        validate_correction_contract(report, request)
        if target_status == "DRAFT" and report.replaces_report_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "REPORT_STATUS_TRANSITION_NOT_ALLOWED", "message": "일반 보고서는 검토 뒤 초안으로 되돌릴 수 없습니다."},
            )
        if report.status == "REVIEWED" and target_status == "APPROVED" and any(
            value is not None for value in (
                request.report_type,
                request.title,
                request.summary,
                request.analysis_content,
                request.conclusion,
                request.action_plan,
                request.work_record_id,
                request.structure_item_id,
                request.period_start,
                request.period_end,
                request.sources,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_REVIEW_INVALIDATED",
                    "message": "검토 뒤 내용이 바뀌었습니다. 정정본을 초안으로 되돌린 뒤 다시 검토하세요.",
                },
            )
        _validate_report_transition(report.status, target_status)
        if request.sources is not None and report.status not in {"DRAFT", "AI_DRAFTED"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reviewed, approved or archived report sources cannot be replaced.",
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
        report.report_family_id = report.report_id
        session.add(report)
        session.flush()
        if target_status == "ARCHIVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "REPORT_STATUS_TRANSITION_NOT_ALLOWED",
                    "message": "새 보고서를 보관 상태로 바로 만들 수 없습니다.",
                    "currentStatus": "DRAFT",
                    "targetStatus": target_status,
                },
            )

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
    report.status = target_status
    if target_status == "DRAFT":
        report.reviewed_by = None
        report.reviewed_at = None
        report.approved_by = None
        report.approved_at = None
    if target_status in {"REVIEWED", "APPROVED"}:
        report.reviewed_by = current_user.user_id
        report.reviewed_at = now
    if target_status == "APPROVED":
        report.approved_by = current_user.user_id
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
    if request.save_as_document and target_status != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REPORT_DOCUMENT_STATUS_MISMATCH",
                "message": "확정(APPROVED) 단계에서만 보고서 문서를 생성할 수 있습니다.",
                "reportStatus": target_status,
            },
        )
    if report.replaces_report_id is not None and target_status == "APPROVED":
        if not request.save_as_document or request.document_status.strip().upper() != "IN_REVIEW":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_CORRECTION_PUBLICATION_REVIEW_REQUIRED",
                    "message": "정정본 확정 문서는 검토중 상태로 새로 생성해 공개 승인을 다시 받아야 합니다.",
                },
            )
    if request.save_as_document and report.generated_document_id is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REPORT_DOCUMENT_ALREADY_CREATED",
                "message": "이 보고서에는 이미 생성 문서가 연결되어 있습니다.",
                "generatedDocumentId": report.generated_document_id,
            },
        )
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

    replaced_report = None
    if report.replaces_report_id is not None and target_status == "APPROVED":
        replaced_report = finalize_report_replacement(session, report, now)
    if target_status == "ARCHIVED":
        archive_generated_document(session, report.generated_document_id)

    _record_activity(
        session,
        event_type,
        current_user.user_id,
        report,
        f"Report status changed to {target_status}: {report.title}.",
    )
    try:
        session.flush()
        response = _report_response(session, report, current_user)
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
                report_family_id=report.report_family_id,
                replaces_report_id=report.replaces_report_id,
                replaces_report_revision=report.replaces_report_revision,
                response_json=response.model_dump_json(),
            )
            session.add(receipt)
            session.flush()
            record_common_mutation_result(
                session,
                operation_key=mutation_key,
                intent_hash=intent_hash,
                event_type=event_type,
                trace=trace,
                target_type="report",
                target_id=report.report_id,
                target_version_id=(
                    response.generated_document.latest_version_id
                    if response.generated_document
                    else None
                ),
                target_revision=report.report_revision,
                reason=report.correction_reason,
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
                approval_status="APPROVED" if target_status in {"APPROVED", "ARCHIVED"} else "PENDING",
                approved_by=current_user.user_id if target_status in {"APPROVED", "ARCHIVED"} else None,
                related_target_type="report" if report.replaces_report_id else None,
                related_target_id=report.replaces_report_id,
                related_target_revision=(
                    report.replaces_report_revision if replaced_report is not None else None
                ),
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report could not be saved.") from exc
    session.refresh(report)
    return _report_response(session, report, current_user)
