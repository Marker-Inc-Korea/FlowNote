from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import (
    DOCUMENT_GOVERNANCE_ROLES,
    AuthenticatedUser,
    require_roles,
)
from app.db.session import get_db_session
from app.services.change_history_read_model import (
    ChangeHistoryFilters,
    get_change_history_detail,
    list_change_history,
)

router = APIRouter(prefix="/change-history", tags=["change-history"])
ChangeHistoryUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*DOCUMENT_GOVERNANCE_ROLES)),
]


@router.get("")
def list_integrated_change_history(
    current_user: ChangeHistoryUser,
    session: Annotated[Session, Depends(get_db_session)],
    occurred_from: Annotated[datetime | None, Query(alias="occurredFrom")] = None,
    occurred_to: Annotated[datetime | None, Query(alias="occurredTo")] = None,
    actor_id: Annotated[str | None, Query(alias="actorId")] = None,
    actor_role: Annotated[str | None, Query(alias="actorRole")] = None,
    device_id: Annotated[str | None, Query(alias="deviceId")] = None,
    target_type: Annotated[str | None, Query(alias="targetType")] = None,
    target_id: Annotated[str | None, Query(alias="targetId")] = None,
    target_query: Annotated[str | None, Query(alias="targetQuery")] = None,
    target_version_id: Annotated[str | None, Query(alias="targetVersionId")] = None,
    target_revision: Annotated[int | None, Query(alias="targetRevision", ge=1)] = None,
    result: Annotated[str | None, Query()] = None,
    risk_level: Annotated[str | None, Query(alias="riskLevel")] = None,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    correlation_id: Annotated[str | None, Query(alias="correlationId")] = None,
    action_required: Annotated[bool | None, Query(alias="actionRequired")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    filters = ChangeHistoryFilters(
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=_clean(actor_id),
        actor_role=_clean(actor_role),
        device_id=_clean(device_id),
        target_type=_clean(target_type),
        target_id=_clean(target_id),
        target_query=_clean(target_query),
        target_version_id=_clean(target_version_id),
        target_revision=target_revision,
        result=_clean(result),
        risk_level=_clean(risk_level),
        run_id=_clean(run_id),
        correlation_id=_clean(correlation_id),
        action_required=action_required,
    )
    return list_change_history(
        session,
        current_user,
        filters,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{event_id}")
def read_integrated_change_history(
    event_id: str,
    current_user: ChangeHistoryUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    return get_change_history_detail(session, current_user, event_id)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
