from __future__ import annotations

import json
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ActivityHistory

CUSTOMER_SCOPE_HEADER = "X-FlowNote-Customer-Scope"
SITE_SCOPE_HEADER = "X-FlowNote-Site-Scope"
SCOPE_NOT_FOUND_DETAIL = {
    "code": "SCOPE_NOT_FOUND",
    "message": "요청한 고객·현장 범위에서 항목을 찾을 수 없습니다.",
}


def _clean_scope(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def ensure_server_scope(
    request: Request,
    settings: Settings,
    session: Session,
    *,
    actor_id: str | None = None,
    customer_scope: str | None = None,
    site_scope: str | None = None,
) -> None:
    header_customer = _clean_scope(request.headers.get(CUSTOMER_SCOPE_HEADER))
    header_site = _clean_scope(request.headers.get(SITE_SCOPE_HEADER))
    body_customer = _clean_scope(customer_scope)
    body_site = _clean_scope(site_scope)
    requested_customer = body_customer or header_customer
    requested_site = body_site or header_site
    header_body_conflict = (
        header_customer is not None
        and body_customer is not None
        and header_customer != body_customer
    ) or (
        header_site is not None
        and body_site is not None
        and header_site != body_site
    )
    mismatch = (
        header_body_conflict
        or (
            requested_customer is not None
            and requested_customer != settings.effective_customer_scope
        )
        or (
            requested_site is not None
            and requested_site != settings.effective_site_scope
        )
    )
    if not mismatch:
        return

    session.rollback()
    session.add(
        ActivityHistory(
            history_id=f"hist_{uuid4().hex}",
            event_type="scope.access_denied",
            actor_id=actor_id,
            target_type="scope_boundary",
            target_id=None,
            target_title="단일 고객·현장 경계",
            message="단일 고객·현장 경계와 다른 scope 요청을 거부했습니다.",
            before_value=json.dumps(
                {
                    "customer_scope": requested_customer,
                    "site_scope": requested_site,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            after_value=json.dumps(
                {
                    "customer_scope": settings.effective_customer_scope,
                    "site_scope": settings.effective_site_scope,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            change_reason="fail-closed scope boundary",
        )
    )
    session.commit()
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=SCOPE_NOT_FOUND_DETAIL,
    )
