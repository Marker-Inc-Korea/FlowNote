from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.reports import (
    ReportResponse,
    ReportSourceRequest,
    _record_activity,
    _report_content_hash,
    _report_response,
    _source_set_hash,
)
from app.core.auth import ReportWriteUser, get_current_user
from app.db.models import Report, ReportMutationReceipt, ReportSource
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    canonical_hash,
    check_common_mutation_replay,
    mutation_trace,
    record_common_mutation_failure,
    record_common_mutation_result,
)
from app.services.report_source_service import (
    FrozenReportSourceInput,
    _clean_idempotency_key,
    _replace_report_sources,
    _validate_frozen_sources,
)

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


class ReportCorrectionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    correction_reason: str = Field(alias="correctionReason", min_length=1, max_length=1000)
    base_report_revision: int = Field(alias="baseReportRevision", ge=1)
    mutation_key: str = Field(alias="mutationKey", min_length=1, max_length=160)
    source_set_hash_sha256: str | None = Field(default=None, alias="sourceSetHashSha256")
    sources: list[ReportSourceRequest] | None = None


def _source_intent_hash(request: ReportCorrectionCreateRequest, base: Report) -> str:
    if request.sources is None:
        return request.source_set_hash_sha256 or base.source_set_hash_sha256 or ""
    return canonical_hash([
        source.model_dump(by_alias=True, mode="json")
        for source in request.sources
    ])


def _intent_hash(request: ReportCorrectionCreateRequest, base: Report) -> str:
    return canonical_hash({
        "operation": "report.correction_created",
        "reportFamilyId": base.report_family_id or base.report_id,
        "replacesReportId": base.report_id,
        "replacesReportRevision": request.base_report_revision,
        "sourceSetHash": _source_intent_hash(request, base),
        "correctionReason": request.correction_reason.strip(),
    })


def _replay(
    session: Session,
    mutation_key: str,
    intent_hash: str,
) -> ReportResponse | None:
    common = check_common_mutation_replay(
        session,
        operation_key=mutation_key,
        intent_hash=intent_hash,
        event_type="report.correction_created",
        target_type="report",
        target_id=None,
    )
    receipt = session.scalar(
        select(ReportMutationReceipt).where(ReportMutationReceipt.mutation_key == mutation_key)
    )
    if receipt is None:
        if common is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMMON_RECEIPT_LINK_BROKEN", "message": "정정본 receipt 연결이 끊어졌습니다."},
            )
        return None
    if receipt.intent_hash_sha256 != intent_hash:
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "같은 mutation key를 다른 정정 요청에 사용할 수 없습니다."},
        )
    return ReportResponse.model_validate_json(receipt.response_json)


def _source_inputs(
    session: Session,
    base: Report,
    request: ReportCorrectionCreateRequest,
) -> list[ReportSourceRequest | FrozenReportSourceInput]:
    if request.sources is not None:
        return list(request.sources)
    rows = session.scalars(
        select(ReportSource).where(ReportSource.report_id == base.report_id).order_by(ReportSource.id)
    ).all()
    return [
        FrozenReportSourceInput(
            source_type=row.source_type,
            source_id=row.source_id,
            source_version_id=row.source_version_id,
            relation_type=row.relation_type,
            source_revision=row.source_revision,
            source_hash_sha256=row.source_hash_sha256,
        )
        for row in rows
    ]


def _source_conflict(error: HTTPException) -> HTTPException:
    conflict_kind = "SOURCE_ACCESS_CHANGED" if error.status_code in {403, 404} else "SOURCE_SNAPSHOT_CHANGED"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "REPORT_CORRECTION_SOURCE_CONFLICT",
            "conflictKind": conflict_kind,
            "message": "정정본 원천의 버전·변경 번호·검증값 또는 채널 권한이 달라졌습니다.",
            "sourcePreserved": True,
            "allowedActions": ["담당 검토자에게 문의", "현재 원천을 다시 선택", "기존 확정본 유지"],
        },
    )


@router.post("/{report_id}/corrections", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report_correction(
    report_id: str,
    http_request: Request,
    request: ReportCorrectionCreateRequest,
    current_user: ReportWriteUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    mutation_key = _clean_idempotency_key(request.mutation_key)
    assert mutation_key is not None
    trace = mutation_trace(current_user, http_request)
    base = session.scalar(select(Report).where(Report.report_id == report_id))
    if base is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "보고서를 찾을 수 없습니다."})
    intent_hash = _intent_hash(request, base)
    try:
        replay = _replay(session, mutation_key, intent_hash)
        if replay is not None:
            return replay
        if (
            base.status != "APPROVED"
            or base.superseded_by_report_id is not None
            or base.report_revision != request.base_report_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_CORRECTION_BASE_CONFLICT",
                    "message": "현재 유효한 확정본의 최신 revision에서만 정정본을 만들 수 있습니다.",
                    "expectedRevision": request.base_report_revision,
                    "currentRevision": base.report_revision,
                    "currentStatus": "SUPERSEDED" if base.superseded_by_report_id else base.status,
                },
            )
        existing = session.scalar(
            select(Report).where(Report.replaces_report_id == base.report_id)
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_CORRECTION_ALREADY_EXISTS",
                    "message": "이 확정본을 대상으로 한 정정본이 이미 있습니다.",
                    "targetId": existing.report_id,
                    "currentStatus": existing.status,
                },
            )

        correction = Report(
            report_id=f"report_{uuid4().hex}",
            report_type=base.report_type,
            title=base.title,
            summary=base.summary,
            analysis_content=base.analysis_content,
            conclusion=base.conclusion,
            action_plan=base.action_plan,
            work_record_id=base.work_record_id,
            structure_item_id=base.structure_item_id,
            period_start=base.period_start,
            period_end=base.period_end,
            status="DRAFT",
            ai_draft_used=False,
            created_by=current_user.user_id,
            report_family_id=base.report_family_id or base.report_id,
            replaces_report_id=base.report_id,
            replaces_report_revision=base.report_revision,
            correction_reason=request.correction_reason.strip(),
        )
        session.add(correction)
        session.flush()
        try:
            sources = _replace_report_sources(
                session,
                correction.report_id,
                _source_inputs(session, base, request),
                current_user,
            )
            _validate_frozen_sources(session, sources, current_user)
        except HTTPException as error:
            raise _source_conflict(error) from error
        correction.content_hash_sha256 = _report_content_hash(correction)
        correction.source_set_hash_sha256 = _source_set_hash(sources)
        if (
            request.source_set_hash_sha256 is not None
            and request.source_set_hash_sha256.lower() != correction.source_set_hash_sha256
        ):
            raise _source_conflict(HTTPException(status_code=409, detail="source set hash changed"))

        _record_activity(
            session,
            "report.correction_created",
            current_user.user_id,
            correction,
            f"Report correction draft created for {base.report_id}.",
        )
        session.flush()
        response = _report_response(session, correction, current_user)
        receipt = ReportMutationReceipt(
            mutation_key=mutation_key,
            intent_hash_sha256=intent_hash,
            report_id=correction.report_id,
            report_revision=correction.report_revision,
            content_hash_sha256=correction.content_hash_sha256,
            source_set_hash_sha256=correction.source_set_hash_sha256,
            generated_document_id=None,
            generated_version_id=None,
            report_family_id=correction.report_family_id,
            replaces_report_id=base.report_id,
            replaces_report_revision=base.report_revision,
            response_json=response.model_dump_json(),
        )
        session.add(receipt)
        session.flush()
        record_common_mutation_result(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="report.correction_created",
            trace=trace,
            target_type="report",
            target_id=correction.report_id,
            target_version_id=None,
            target_revision=correction.report_revision,
            reason=correction.correction_reason,
            before_hash=canonical_hash({"reportId": base.report_id, "revision": base.report_revision}),
            after_hash=canonical_hash({
                "reportId": correction.report_id,
                "familyId": correction.report_family_id,
                "replacesReportId": base.report_id,
                "sourceSetHash": correction.source_set_hash_sha256,
            }),
            result="SUCCESS",
            result_code="CORRECTION_DRAFT_CREATED",
            http_status=status.HTTP_201_CREATED,
            response_detail={
                "code": "CORRECTION_DRAFT_CREATED",
                "targetId": correction.report_id,
                "targetRevision": correction.report_revision,
            },
            domain_receipt_type="report_mutation_receipts",
            domain_receipt_id=str(receipt.id),
            approval_status="PENDING",
            related_target_type="report",
            related_target_id=base.report_id,
            related_target_revision=base.report_revision,
        )
        session.commit()
        session.refresh(correction)
        return _report_response(session, correction, current_user)
    except IntegrityError as error:
        session.rollback()
        conflict = HTTPException(
            status_code=409,
            detail={"code": "REPORT_CORRECTION_RACE", "message": "다른 사용자가 정정본을 먼저 만들었습니다."},
        )
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="report.correction_created",
            trace=trace,
            target_type="report",
            target_id=base.report_id,
            target_version_id=None,
            target_revision=request.base_report_revision,
            reason=request.correction_reason,
            error=conflict,
        )
        raise conflict from error
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="report.correction_created",
            trace=trace,
            target_type="report",
            target_id=base.report_id,
            target_version_id=None,
            target_revision=request.base_report_revision,
            reason=request.correction_reason,
            error=error,
        )
        raise
