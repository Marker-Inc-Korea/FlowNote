from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AIOperationAuditEvent,
    AIOperationalPolicy,
    AIQuery,
    AIQueryLegalHold,
    AIRetentionAudit,
)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def audit_event(
    session: Session,
    *,
    event_type: str,
    actor_id: str | None,
    customer_scope: str,
    site_scope: str,
    target_type: str,
    target_id: str,
    reason_code: str | None = None,
    detail: dict[str, object] | None = None,
) -> AIOperationAuditEvent:
    row = AIOperationAuditEvent(
        event_id=f"aiaud-{uuid4().hex}",
        event_type=event_type,
        actor_id=actor_id,
        customer_scope=customer_scope,
        site_scope=site_scope,
        target_type=target_type,
        target_id=target_id,
        reason_code=reason_code,
        detail_json=json.dumps(detail or {}, ensure_ascii=False, sort_keys=True),
    )
    session.add(row)
    return row


def active_policy(
    session: Session, customer_scope: str, site_scope: str
) -> tuple[AIOperationalPolicy | None, AIOperationalPolicy | None]:
    global_policy = session.scalar(
        select(AIOperationalPolicy).where(
            AIOperationalPolicy.customer_scope == "*", AIOperationalPolicy.site_scope == "*"
        )
    )
    site_policy = session.scalar(
        select(AIOperationalPolicy).where(
            AIOperationalPolicy.customer_scope == customer_scope,
            AIOperationalPolicy.site_scope == site_scope,
        )
    )
    return global_policy, site_policy


def run_retention(
    session: Session,
    *,
    now: datetime | None = None,
    query_id: str | None = None,
    customer_scope: str | None = None,
    site_scope: str | None = None,
    operation_key: str | None = None,
) -> dict[str, int]:
    """Redacts expired payloads without deleting referential audit metadata."""
    current = now or datetime.now(timezone.utc)
    statement = select(AIQuery).where(
        ~select(AIQueryLegalHold.id).where(
            AIQueryLegalHold.query_id == AIQuery.query_id,
            AIQueryLegalHold.status == "ACTIVE",
        ).exists(),
        or_(
            (AIQuery.retention_until <= current) & (AIQuery.query_text != "[EXPIRED]"),
            (AIQuery.response_text.is_not(None))
            & or_(
                AIQuery.response_retention_until <= current,
                (AIQuery.response_retention_until.is_(None)) & (AIQuery.retention_until <= current),
            ),
        ),
    )
    if query_id is not None:
        statement = statement.where(AIQuery.query_id == query_id)
    if customer_scope is not None:
        statement = statement.where(AIQuery.customer_scope == customer_scope)
    if site_scope is not None:
        statement = statement.where(AIQuery.site_scope == site_scope)
    rows = session.scalars(statement).all()
    query_redacted = 0
    response_deleted = 0
    for query in rows:
        query_action = "UNCHANGED"
        response_action = "UNCHANGED"
        if utc(query.retention_until) <= current and query.query_text != "[EXPIRED]":
            query.query_text = "[EXPIRED]"
            query_action = "DEIDENTIFIED"
            query_redacted += 1
        response_until = query.response_retention_until or query.retention_until
        if utc(response_until) <= current and query.response_text is not None:
            query.response_text = None
            response_action = "DELETED"
            response_deleted += 1
        session.add(
            AIRetentionAudit(
                retention_audit_id=f"airet-{uuid4().hex}",
                query_id=query.query_id,
                action="RETENTION_EXPIRED",
                query_text_action=query_action,
                response_text_action=response_action,
                query_hash=query.query_hash,
                response_hash=query.response_hash,
                operation_key=operation_key if query_id == query.query_id else None,
                processed_at=current,
            )
        )
    session.commit()
    return {
        "processed": len(rows),
        "queryPayloadsDeidentified": query_redacted,
        "responsesDeleted": response_deleted,
    }
