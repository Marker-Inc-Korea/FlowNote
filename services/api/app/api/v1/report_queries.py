from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.models import Report
from app.db.session import get_db_session
from app.api.v1.reports import (
    ReportResponse,
    ReportSourceResponse,
    _record_report_access,
    _report_is_readable,
    _report_response,
)

REPORT_NOT_VISIBLE_DETAIL = {
    "code": "RESOURCE_NOT_FOUND",
    "message": "요청한 보고서를 찾을 수 없습니다.",
}

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


class ReportLineageItemResponse(BaseModel):
    report_id: str
    title: str
    status: str
    report_revision: int
    replaces_report_id: str | None
    correction_reason: str | None
    generated_document_id: str | None
    approved_at: datetime | None
    superseded_at: datetime | None
    is_current_effective: bool


@router.get("", response_model=list[ReportResponse])
def list_reports(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportResponse]:
    reports = session.scalars(select(Report).order_by(desc(Report.updated_at), desc(Report.id))).all()
    readable = [report for report in reports if _report_is_readable(session, report, current_user)]
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.list_read",
        report_id=None,
        title=None,
        message=f"보고서 목록 권한 재검사 완료: 반환 {len(readable)}건, 비노출 {len(reports) - len(readable)}건.",
    )
    session.commit()
    return [_report_response(session, report, current_user) for report in readable]


def _readable_report(session: Session, report_id: str, current_user: CurrentUser) -> Report:
    report = session.scalar(select(Report).where(Report.report_id == report_id))
    if report is None or not _report_is_readable(session, report, current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=REPORT_NOT_VISIBLE_DETAIL)
    return report


@router.get("/{report_id}/lineage", response_model=list[ReportLineageItemResponse])
def list_report_lineage(
    report_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportLineageItemResponse]:
    report = _readable_report(session, report_id, current_user)
    family_id = report.report_family_id or report.report_id
    family = session.scalars(
        select(Report).where(Report.report_family_id == family_id).order_by(Report.created_at, Report.id)
    ).all()
    visible = [item for item in family if _report_is_readable(session, item, current_user)]
    return [
        ReportLineageItemResponse(
            report_id=item.report_id,
            title=item.title,
            status="SUPERSEDED" if item.superseded_by_report_id else item.status,
            report_revision=item.report_revision,
            replaces_report_id=(
                item.replaces_report_id
                if item.replaces_report_id in {row.report_id for row in visible}
                else None
            ),
            correction_reason=item.correction_reason,
            generated_document_id=item.generated_document_id,
            approved_at=item.approved_at,
            superseded_at=item.superseded_at,
            is_current_effective=item.status == "APPROVED" and item.superseded_by_report_id is None,
        )
        for item in visible
    ]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ReportResponse:
    try:
        report = _readable_report(session, report_id, current_user)
    except HTTPException:
        _record_report_access(
            session,
            actor_id=current_user.user_id,
            event_type="report.read_denied",
            report_id=report_id,
            title=None,
            message="보고서 또는 원천을 현재 권한으로 열람할 수 없어 존재를 숨겼습니다.",
        )
        session.commit()
        raise
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.read_granted",
        report_id=report.report_id,
        title=report.title,
        message="보고서와 모든 원천의 현재 열람 권한을 재검사해 조회를 허용했습니다.",
    )
    session.commit()
    return _report_response(session, report, current_user)


@router.get("/{report_id}/sources", response_model=list[ReportSourceResponse])
def list_report_sources(
    report_id: str,
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ReportSourceResponse]:
    try:
        report = _readable_report(session, report_id, current_user)
    except HTTPException:
        _record_report_access(
            session,
            actor_id=current_user.user_id,
            event_type="report.source_read_denied",
            report_id=report_id,
            title=None,
            message="보고서 원천 열람 권한 재검사에 실패해 보고서와 원천의 존재를 숨겼습니다.",
        )
        session.commit()
        raise
    _record_report_access(
        session,
        actor_id=current_user.user_id,
        event_type="report.source_read_granted",
        report_id=report.report_id,
        title=report.title,
        message="보고서의 모든 원천에 대한 현재 열람 권한을 재검사해 조회를 허용했습니다.",
    )
    session.commit()
    return _report_response(session, report, current_user).sources
