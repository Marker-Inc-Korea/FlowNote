from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import FieldCommentAnalyzeUser, get_current_user
from app.db.models import FieldComment, ReportSource
from app.db.session import get_db_session


router = APIRouter(
    prefix="/field-comments",
    tags=["field-comments"],
    dependencies=[Depends(get_current_user)],
)

TERMINAL_STATUSES = {"SELECTED", "EXCLUDED", "ARCHIVED"}


class FieldCommentReviewActionResponse(BaseModel):
    code: str
    title: str
    count: int
    owner: str
    next_action: str
    workbench_filter: str


class FieldCommentReviewDashboardResponse(BaseModel):
    total_count: int
    counts_by_status: dict[str, int]
    unreviewed_count: int
    conflict_count: int
    safety_quality_risk_count: int
    report_unlinked_count: int
    unassigned_count: int
    overdue_count: int
    actions: list[FieldCommentReviewActionResponse]


def _count(session: Session, *conditions: object) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(FieldComment).where(*conditions)
        )
        or 0
    )


def _action(
    code: str,
    title: str,
    count: int,
    owner: str,
    next_action: str,
    workbench_filter: str,
) -> FieldCommentReviewActionResponse:
    return FieldCommentReviewActionResponse(
        code=code,
        title=title,
        count=count,
        owner=owner,
        next_action=next_action,
        workbench_filter=workbench_filter,
    )


@router.get("/review-dashboard", response_model=FieldCommentReviewDashboardResponse)
def field_comment_review_dashboard(
    _current_user: FieldCommentAnalyzeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentReviewDashboardResponse:
    notes = session.execute(select(FieldComment.status, FieldComment.assigned_to)).all()
    logical_statuses = Counter(
        "ASSIGNED" if status == "NEW" and assigned_to else status
        for status, assigned_to in notes
    )
    active = ~FieldComment.status.in_(TERMINAL_STATUSES)
    unreviewed_count = _count(
        session,
        FieldComment.status.in_({"NEW", "NEEDS_REVIEW"}),
    )
    conflict_count = _count(session, active, FieldComment.conflict_flag.is_(True))
    safety_quality_risk_count = _count(
        session,
        active,
        or_(
            func.lower(func.coalesce(FieldComment.signal_level, "")) == "red",
            FieldComment.conflict_flag.is_(True),
        ),
    )
    linked_comment_ids = select(ReportSource.source_id).where(
        ReportSource.source_type == "FIELD_COMMENT"
    ).distinct()
    report_unlinked_count = _count(
        session,
        active,
        FieldComment.comment_id.not_in(linked_comment_ids),
    )
    unassigned_count = _count(session, active, FieldComment.assigned_to.is_(None))
    overdue_count = _count(
        session,
        active,
        FieldComment.review_due_at.is_not(None),
        FieldComment.review_due_at < func.now(),
    )

    candidates = [
        _action(
            "SAFETY_QUALITY_RISK",
            "안전·품질 위험",
            safety_quality_risk_count,
            "분석자와 다른 결정 역할 검토자",
            "빨간 신호 또는 상충 원천을 먼저 확인하고 독립 검토자를 배정하세요.",
            "HIGH_RISK",
        ),
        _action(
            "CONFLICT",
            "상충 판단 대기",
            conflict_count,
            "라인 책임자·보고서 책임자",
            "양쪽 원천을 유지한 채 상충 근거와 선정·제외 사유를 기록하세요.",
            "CONFLICT",
        ),
        _action(
            "UNREVIEWED",
            "미검토 FieldComment",
            unreviewed_count,
            "조장·반장 또는 지정 분석자",
            "담당자와 기한을 정하고 분석완료 또는 검토필요로 분류하세요.",
            "UNREVIEWED",
        ),
        _action(
            "REPORT_UNLINKED",
            "보고서 미연결",
            report_unlinked_count,
            "보고서 책임자",
            "검토된 후보를 선정 또는 제외하고 선정 원천은 보고서 근거로 고정하세요.",
            "REPORT_UNLINKED",
        ),
        _action(
            "UNASSIGNED",
            "담당자 없음",
            unassigned_count,
            "라인·공정 책임자",
            "담당자와 검토 기한을 지정하고 기존 미처리 기간을 감사 이력에 남기세요.",
            "UNASSIGNED",
        ),
        _action(
            "OVERDUE",
            "기한 초과",
            overdue_count,
            "지정 담당자와 담당 역할 책임자",
            "기한을 넘긴 원천의 진행 상태를 확인하고 새 기한 또는 처리 결과를 기록하세요.",
            "OVERDUE",
        ),
    ]
    return FieldCommentReviewDashboardResponse(
        total_count=len(notes),
        counts_by_status=dict(sorted(logical_statuses.items())),
        unreviewed_count=unreviewed_count,
        conflict_count=conflict_count,
        safety_quality_risk_count=safety_quality_risk_count,
        report_unlinked_count=report_unlinked_count,
        unassigned_count=unassigned_count,
        overdue_count=overdue_count,
        actions=[item for item in candidates if item.count > 0],
    )
