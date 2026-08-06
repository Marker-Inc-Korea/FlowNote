from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentVersion, Report


def archive_generated_document(session: Session, document_id: str | None) -> None:
    if document_id is None:
        return
    document = session.scalar(select(Document).where(Document.document_id == document_id))
    if document is None:
        return
    document.status = "ARCHIVED"
    document.published_version_id = None
    document.revision += 1
    versions = session.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == document.document_id)
    ).all()
    for version in versions:
        version.version_status = "ARCHIVED"
        version.is_published = False
        version.published_at = None


def validate_correction_contract(report: Report, request: object) -> None:
    if report.replaces_report_id is None:
        return
    values = (
        getattr(request, "report_family_id", None),
        getattr(request, "replaces_report_id", None),
        getattr(request, "replaces_report_revision", None),
        getattr(request, "source_set_hash_sha256", None),
    )
    expected = (
        report.report_family_id,
        report.replaces_report_id,
        report.replaces_report_revision,
        report.source_set_hash_sha256,
    )
    if values != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "REPORT_CORRECTION_CONTRACT_MISMATCH",
                "message": "정정본 계열·대체 대상·기준 revision·원천 집합이 현재 서버 계약과 다릅니다.",
                "expectedRevision": report.replaces_report_revision,
                "currentRevision": report.report_revision,
            },
        )


def finalize_report_replacement(
    session: Session,
    correction: Report,
    now: datetime,
) -> Report:
    if correction.replaces_report_id is None or correction.replaces_report_revision is None:
        raise HTTPException(status_code=409, detail="Correction replacement target is incomplete.")
    base = session.scalar(
        select(Report).where(Report.report_id == correction.replaces_report_id)
    )
    if base is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "REPORT_REPLACEMENT_TARGET_MISSING", "message": "대체할 확정본을 찾을 수 없습니다."},
        )
    result = session.execute(
        update(Report)
        .where(
            Report.report_id == base.report_id,
            Report.status == "APPROVED",
            Report.superseded_by_report_id.is_(None),
            Report.report_revision == correction.replaces_report_revision,
        )
        .values(
            superseded_by_report_id=correction.report_id,
            superseded_at=now,
            report_revision=correction.replaces_report_revision + 1,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REPORT_REPLACEMENT_RACE",
                "message": "대체 대상이 변경되었거나 다른 정정본이 먼저 확정되었습니다.",
                "expectedRevision": correction.replaces_report_revision,
                "currentRevision": base.report_revision,
                "currentStatus": "SUPERSEDED" if base.superseded_by_report_id else base.status,
            },
        )
    archive_generated_document(session, base.generated_document_id)
    session.flush()
    session.refresh(base)
    return base
