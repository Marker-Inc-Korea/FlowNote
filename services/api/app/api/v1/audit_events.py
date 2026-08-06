from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import AccessLogReadUser, get_current_user
from app.db.models import ActivityHistory, AuditEventEnvelope
from app.db.session import get_db_session

router = APIRouter(
    prefix="/audit-events",
    tags=["audit-events"],
    dependencies=[Depends(get_current_user)],
)


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(alias="sourceId")
    format_status: str = Field(alias="formatStatus")
    schema_version: int | None = Field(alias="schemaVersion")
    event_type: str = Field(alias="eventType")
    actor_id: str | None = Field(alias="actorId")
    actor_role: str | None = Field(alias="actorRole")
    session_id: str | None = Field(alias="sessionId")
    device_id: str | None = Field(alias="deviceId")
    target_type: str = Field(alias="targetType")
    target_id: str | None = Field(alias="targetId")
    target_version_id: str | None = Field(alias="targetVersionId")
    target_revision: int | None = Field(alias="targetRevision")
    related_target_type: str | None = Field(alias="relatedTargetType")
    related_target_id: str | None = Field(alias="relatedTargetId")
    related_target_revision: int | None = Field(alias="relatedTargetRevision")
    reason: str | None
    approval_status: str | None = Field(alias="approvalStatus")
    approved_by: str | None = Field(alias="approvedBy")
    approval_reference: str | None = Field(alias="approvalReference")
    before_hash_sha256: str | None = Field(alias="beforeHashSha256")
    after_hash_sha256: str | None = Field(alias="afterHashSha256")
    result: str | None
    result_code: str | None = Field(alias="resultCode")
    http_status: int | None = Field(alias="httpStatus")
    run_id: str | None = Field(alias="runId")
    correlation_id: str | None = Field(alias="correlationId")
    server_time: datetime = Field(alias="serverTime")
    missing_fields: list[str] = Field(alias="missingFields")


@router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    _current_user: AccessLogReadUser,
    session: Annotated[Session, Depends(get_db_session)],
    target_type: Annotated[str | None, Query(alias="targetType")] = None,
    target_id: Annotated[str | None, Query(alias="targetId")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventResponse]:
    common_query = select(AuditEventEnvelope)
    legacy_query = select(ActivityHistory)
    if target_type is not None:
        common_query = common_query.where(AuditEventEnvelope.target_type == target_type)
        legacy_query = legacy_query.where(ActivityHistory.target_type == target_type)
    if target_id is not None:
        common_query = common_query.where(AuditEventEnvelope.target_id == target_id)
        legacy_query = legacy_query.where(ActivityHistory.target_id == target_id)

    common_rows = session.scalars(
        common_query.order_by(
            desc(AuditEventEnvelope.server_time), desc(AuditEventEnvelope.id)
        ).limit(limit)
    ).all()
    legacy_rows = session.scalars(
        legacy_query.order_by(desc(ActivityHistory.created_at), desc(ActivityHistory.id)).limit(limit)
    ).all()
    combined = [_common_response(row) for row in common_rows]
    combined.extend(_legacy_response(row) for row in legacy_rows)
    combined.sort(key=lambda item: item.server_time, reverse=True)
    return combined[:limit]


def _common_response(row: AuditEventEnvelope) -> AuditEventResponse:
    return AuditEventResponse(
        source_id=row.event_id,
        format_status="공통 형식",
        schema_version=row.schema_version,
        event_type=row.event_type,
        actor_id=row.actor_id,
        actor_role=row.actor_role,
        session_id=row.session_id,
        device_id=row.device_id,
        target_type=row.target_type,
        target_id=row.target_id,
        target_version_id=row.target_version_id,
        target_revision=row.target_revision,
        related_target_type=row.related_target_type,
        related_target_id=row.related_target_id,
        related_target_revision=row.related_target_revision,
        reason=row.reason,
        approval_status=row.approval_status,
        approved_by=row.approved_by,
        approval_reference=row.approval_reference,
        before_hash_sha256=row.before_hash_sha256,
        after_hash_sha256=row.after_hash_sha256,
        result=row.result,
        result_code=row.result_code,
        http_status=row.http_status,
        run_id=row.run_id,
        correlation_id=row.correlation_id,
        server_time=row.server_time,
        missing_fields=[],
    )


def _legacy_response(row: ActivityHistory) -> AuditEventResponse:
    return AuditEventResponse(
        source_id=row.history_id,
        format_status="이전 형식·일부 필드 없음",
        schema_version=None,
        event_type=row.event_type,
        actor_id=row.actor_id,
        actor_role=None,
        session_id=None,
        device_id=None,
        target_type=row.target_type,
        target_id=row.target_id,
        target_version_id=None,
        target_revision=None,
        related_target_type=None,
        related_target_id=None,
        related_target_revision=None,
        reason=row.change_reason,
        approval_status=None,
        approved_by=None,
        approval_reference=None,
        before_hash_sha256=None,
        after_hash_sha256=None,
        result=None,
        result_code=None,
        http_status=None,
        run_id=None,
        correlation_id=None,
        server_time=row.created_at,
        missing_fields=[
            "actorRole",
            "sessionId",
            "deviceId",
            "targetVersionId",
            "targetRevision",
            "relatedTargetType",
            "relatedTargetId",
            "relatedTargetRevision",
            "approvalStatus",
            "beforeHashSha256",
            "afterHashSha256",
            "result",
            "resultCode",
            "httpStatus",
            "runId",
            "correlationId",
        ],
    )
