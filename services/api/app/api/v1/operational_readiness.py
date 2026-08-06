from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import DOCUMENT_GOVERNANCE_ROLES, AuthenticatedUser, require_roles
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.services.operational_readiness import (
    ReadinessFilters,
    get_operational_readiness_detail,
    list_operational_readiness,
)

router = APIRouter(prefix="/operational-readiness", tags=["operational-readiness"])
OperationalReadinessUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*DOCUMENT_GOVERNANCE_ROLES)),
]


@router.get("")
def list_readiness(
    current_user: OperationalReadinessUser,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    area_code: Annotated[str | None, Query(alias="areaCode")] = None,
    severity: Annotated[str | None, Query()] = None,
    blocker_code: Annotated[str | None, Query(alias="blockerCode")] = None,
    target_query: Annotated[str | None, Query(alias="targetQuery")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    filters = ReadinessFilters(
        area_code=_upper(area_code),
        severity=_upper(severity),
        blocker_code=_upper(blocker_code),
        target_query=_clean(target_query),
    )
    return list_operational_readiness(
        session,
        current_user,
        filters,
        limit=limit,
        cursor=cursor,
        settings=settings,
    )


@router.get("/{item_id}")
def read_readiness_item(
    item_id: str,
    current_user: OperationalReadinessUser,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return get_operational_readiness_detail(
        session,
        current_user,
        item_id,
        settings=settings,
    )


def _upper(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
