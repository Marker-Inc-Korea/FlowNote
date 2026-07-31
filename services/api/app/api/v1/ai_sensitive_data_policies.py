from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.auth import ROLE_SYSTEM_ADMIN, AuthenticatedUser, require_roles
from app.core.config import Settings, get_settings
from app.db.models import AISensitiveDataPolicy, AISensitiveDataPolicyOperation
from app.db.session import get_db_session
from app.services.ai_operations import active_policy, audit_event
from app.services.ai_readiness import database_scope, scope_readiness

router = APIRouter(prefix="/ai-operations/sensitive-data-policies", tags=["ai-operations"])
SystemAdmin = Annotated[AuthenticatedUser, Depends(require_roles(ROLE_SYSTEM_ADMIN))]
Db = Annotated[Session, Depends(get_db_session)]
Cfg = Annotated[Settings, Depends(get_settings)]

NON_RETIRABLE_STATUSES = {"SUPERSEDED", "RETIRED"}
ACTION_CONFIRMATIONS = {
    "REVIEWED": "REVIEW",
    "APPROVED": "APPROVE",
    "ACTIVATED": "ACTIVATE",
    "REPLACED": "REPLACE",
    "APPROVAL_WITHDRAWN": "WITHDRAW_APPROVAL",
    "RETIRED": "RETIRE",
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _state_tag(row: AISensitiveDataPolicy) -> str:
    return _hash("|".join((
        row.policy_id,
        row.version,
        row.status,
        str(row.state_revision),
        row.content_hash,
        row.replaced_by_policy_id or "",
    )))


def _next_action(row: AISensitiveDataPolicy) -> dict[str, str]:
    actions = {
        "DRAFT": ("검토 담당자", "작성자와 다른 system-admin이 정책을 검토하세요."),
        "REVIEWED": ("승인 담당자", "작성자·검토자와 다른 system-admin이 정책을 승인하세요."),
        "APPROVED": ("AI 시스템 운영자", "현재 활성 정책이 없으면 활성화하고, 있으면 대체를 실행하세요."),
        "ACTIVE": ("AI 시스템 운영자", "적용 상태를 유지하거나 새 승인 버전으로 대체하세요."),
        "SUPERSEDED": ("AI 시스템 운영자", "대체 이력을 보존하세요. 수정이 필요하면 새 버전을 작성하세요."),
        "APPROVAL_WITHDRAWN": ("AI 시스템 운영자", "외부 호출 차단을 확인하고 새 정책 버전을 작성하세요."),
        "RETIRED": ("AI 시스템 운영자", "폐기 이력을 보존하세요. 수정이 필요하면 새 버전을 작성하세요."),
    }
    owner, action = actions[row.status]
    return {"responsibleOwner": owner, "nextAction": action}


def _policy_dict(
    row: AISensitiveDataPolicy, *, idempotent_replay: bool = False
) -> dict[str, object]:
    guidance = _next_action(row)
    return {
        "policyId": row.policy_id,
        "scopeType": "CURRENT_CUSTOMER_SITE",
        "scopeDisplay": "현재 고객·현장",
        "version": row.version,
        "status": row.status,
        "isActive": row.status == "ACTIVE" and row.is_active,
        "contentHash": row.content_hash,
        "forbiddenTermCount": len(_json_list(row.forbidden_terms_json)),
        "customerIdentifierCount": len(_json_list(row.customer_identifiers_json)),
        "createdBy": row.created_by,
        "reviewedBy": row.reviewed_by,
        "approvedBy": row.approved_by,
        "activatedBy": row.activated_by,
        "approvalWithdrawnBy": row.approval_withdrawn_by,
        "retiredBy": row.retired_by,
        "createdAt": row.created_at,
        "reviewedAt": row.reviewed_at,
        "approvedAt": row.approved_at,
        "activatedAt": row.activated_at,
        "approvalWithdrawnAt": row.approval_withdrawn_at,
        "retiredAt": row.retired_at,
        "replacedByPolicyId": row.replaced_by_policy_id,
        "stateTag": _state_tag(row),
        "rawPolicyExposed": False,
        "idempotentReplay": idempotent_replay,
        **guidance,
    }


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _scope_statement(settings: Settings):
    return select(AISensitiveDataPolicy).where(
        AISensitiveDataPolicy.customer_scope == settings.ai_customer_scope,
        AISensitiveDataPolicy.site_scope == settings.ai_site_scope,
    )


def _policy(policy_id: str, settings: Settings, session: Session) -> AISensitiveDataPolicy:
    row = session.scalar(_scope_statement(settings).where(
        AISensitiveDataPolicy.policy_id == policy_id
    ))
    if row is None:
        raise HTTPException(404, "현재 고객·현장 범위에서 민감정보 정책을 찾을 수 없습니다.")
    return row


def _begin_mutation(session: Session) -> None:
    if session.bind is not None and session.bind.dialect.name == "sqlite" and not session.in_transaction():
        session.execute(text("BEGIN IMMEDIATE"))


def _canonical_values(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()}, key=str.casefold)


class SensitivePolicyCreate(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    forbidden_terms: list[str] = Field(alias="forbiddenTerms", max_length=500)
    customer_identifiers: list[str] = Field(alias="customerIdentifiers", max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    operation_key: str = Field(alias="operationKey", min_length=8, max_length=160)

    @field_validator("forbidden_terms", "customer_identifiers")
    @classmethod
    def clean_values(cls, value: list[str]) -> list[str]:
        cleaned = _canonical_values(value)
        if any(len(item) > 500 for item in cleaned):
            raise ValueError("policy items must be at most 500 characters")
        return cleaned

    @model_validator(mode="after")
    def at_least_one_rule(self) -> SensitivePolicyCreate:
        if not self.forbidden_terms and not self.customer_identifiers:
            raise ValueError("at least one forbidden term or customer identifier is required")
        return self


class SensitivePolicyAction(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    operation_key: str = Field(alias="operationKey", min_length=8, max_length=160)
    expected_state_tag: str = Field(alias="expectedStateTag", min_length=64, max_length=64)
    confirm_action: str = Field(alias="confirmAction", min_length=1, max_length=40)
    replaces_policy_id: str | None = Field(default=None, alias="replacesPolicyId", max_length=64)


def _request_hash(action: str, payload: dict[str, object]) -> str:
    return _hash(json.dumps({"action": action, **payload}, ensure_ascii=False, sort_keys=True))


def _replay(
    session: Session,
    settings: Settings,
    operation_key: str,
    action: str,
    request_hash: str,
) -> dict[str, object] | None:
    receipt = session.scalar(select(AISensitiveDataPolicyOperation).where(
        AISensitiveDataPolicyOperation.operation_key == operation_key
    ))
    if receipt is None:
        return None
    if receipt.action != action or receipt.request_hash != request_hash:
        raise HTTPException(409, "동일 멱등 키가 다른 민감정보 정책 조작에 사용되었습니다.")
    row = _policy(receipt.policy_id, settings, session)
    return _policy_dict(row, idempotent_replay=True)


def _receipt(
    session: Session,
    row: AISensitiveDataPolicy,
    user: AuthenticatedUser,
    operation_key: str,
    action: str,
    request_hash: str,
) -> None:
    session.add(AISensitiveDataPolicyOperation(
        operation_id=f"aisdpo-{uuid4().hex}",
        operation_key=operation_key,
        policy_id=row.policy_id,
        action=action,
        request_hash=request_hash,
        result_state_tag=_state_tag(row),
        created_by=user.user_id,
    ))


def _audit(
    session: Session,
    settings: Settings,
    user: AuthenticatedUser,
    row: AISensitiveDataPolicy,
    action: str,
    reason: str,
    *,
    replaced_policy_id: str | None = None,
) -> None:
    detail: dict[str, object] = {
        "version": row.version,
        "status": row.status,
        "contentHash": row.content_hash,
        "forbiddenTermCount": len(_json_list(row.forbidden_terms_json)),
        "customerIdentifierCount": len(_json_list(row.customer_identifiers_json)),
        "reasonHash": _hash(reason),
        "rawPolicyExposed": False,
    }
    if replaced_policy_id:
        detail["replacedPolicyId"] = replaced_policy_id
    audit_event(
        session,
        event_type=f"AI_SENSITIVE_POLICY_{action}",
        actor_id=user.user_id,
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        target_type="AI_SENSITIVE_DATA_POLICY",
        target_id=row.policy_id,
        reason_code="AI_SENSITIVE_POLICY_NOT_ACTIVE" if action in {"APPROVAL_WITHDRAWN", "RETIRED"} else None,
        detail=detail,
    )


@router.get("")
def list_sensitive_policies(
    _: SystemAdmin, settings: Cfg, session: Db
) -> list[dict[str, object]]:
    rows = session.scalars(
        _scope_statement(settings).order_by(
            AISensitiveDataPolicy.created_at.desc(), AISensitiveDataPolicy.id.desc()
        )
    ).all()
    return [_policy_dict(row) for row in rows]


@router.get("/current")
def current_sensitive_policy(
    _: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    rows = session.scalars(
        _scope_statement(settings).order_by(
            AISensitiveDataPolicy.created_at.desc(), AISensitiveDataPolicy.id.desc()
        )
    ).all()
    active = next((row for row in rows if row.status == "ACTIVE" and row.is_active), None)
    latest = rows[0] if rows else None
    global_policy, site_policy = active_policy(
        session, settings.ai_customer_scope, settings.ai_site_scope
    )
    readiness = None
    if settings.ai_readiness_gate_enabled:
        readiness = scope_readiness(
            session,
            customer_scope=settings.ai_customer_scope,
            site_scope=settings.ai_site_scope,
            line_scope=None,
            database_scope_value=database_scope(settings.database_url),
            provider=settings.ai_provider,
            model_scope=settings.ai_model,
            purpose="EVIDENCE_SUMMARY",
        )
    if not settings.ai_external_call_enabled:
        category, code = "EXTERNAL_CALL_DISABLED", "AI_EXTERNAL_CALL_DISABLED"
        reason = "외부 호출 비활성: 기능 플래그가 꺼져 있으며 이 조회는 외부 전송을 실행하지 않습니다."
        owner, next_action = "AI 시스템 운영자", "계약·승인·정책·준비도를 확인한 뒤 기능 플래그 활성화를 검토하세요."
    elif global_policy and global_policy.kill_switch_enabled:
        category, code = "KILL_SWITCH", "AI_GLOBAL_KILL_SWITCH"
        reason = "kill switch: 전역 외부 AI 즉시 중지가 우선 적용됩니다."
        owner, next_action = "AI 시스템 운영자", "중지 사유를 확인하고 전역 kill switch 유지 또는 해제를 결정하세요."
    elif site_policy and site_policy.kill_switch_enabled:
        category, code = "KILL_SWITCH", "AI_SITE_KILL_SWITCH"
        reason = "kill switch: 현재 현장 외부 AI 즉시 중지가 우선 적용됩니다."
        owner, next_action = "현장 AI 운영자", "중지 사유를 확인하고 현장 kill switch 유지 또는 해제를 결정하세요."
    elif readiness is not None and not readiness["provider_start_ready"]:
        category, code = "READINESS_NOT_MET", "AI_READINESS_NOT_MET"
        reason = "준비도 미달: 승인된 ANONYMOUS_FIELD 자료와 provider 착수 근거가 부족합니다."
        owner, next_action = "현장 데이터·평가 담당자", "FIELD_READINESS 자료와 독립 평가·승인 상태를 보강하세요."
    elif active is None and any(
        row.status in {"APPROVAL_WITHDRAWN", "RETIRED"} for row in rows
    ):
        category, code = "POLICY_BLOCK", "AI_SENSITIVE_POLICY_NOT_ACTIVE"
        reason = "정책 차단: 승인 철회 또는 폐기로 현재 적용할 민감정보 정책이 없습니다."
        owner, next_action = "정보보호 승인 담당자", "새 정책 버전을 분리 검토·승인한 뒤 활성화하세요."
    else:
        category, code = "POLICY_APPLIED", None
        reason = (
            "민감정보 정책이 적용 중입니다. 이 상태 조회 자체는 외부 전송을 실행하지 않습니다."
            if active else
            "기본 provider 경계 필터가 적용 중입니다. 이 상태 조회 자체는 외부 전송을 실행하지 않습니다."
        )
        owner, next_action = "AI 시스템 운영자", "질의별 전송 여부는 감사 화면의 외부 전송 열에서 확인하세요."
    return {
        "scopeDisplay": "현재 고객·현장",
        "activePolicy": _policy_dict(active) if active else None,
        "latestPolicy": _policy_dict(latest) if latest else None,
        "blockCategory": category,
        "reasonCode": code,
        "reason": reason,
        "responsibleOwner": owner,
        "nextAction": next_action,
        "externalTransferOccurred": False,
        "providerStartReady": bool(readiness and readiness["provider_start_ready"]),
    }


@router.get("/{policy_id}")
def get_sensitive_policy(
    policy_id: str, _: SystemAdmin, settings: Cfg, session: Db
) -> dict[str, object]:
    return _policy_dict(_policy(policy_id, settings, session))


@router.post("", status_code=201)
def create_sensitive_policy(
    payload: SensitivePolicyCreate,
    user: SystemAdmin,
    settings: Cfg,
    session: Db,
) -> dict[str, object]:
    _begin_mutation(session)
    content = {
        "forbiddenTerms": payload.forbidden_terms,
        "customerIdentifiers": payload.customer_identifiers,
    }
    content_hash = _hash(json.dumps(content, ensure_ascii=False, sort_keys=True))
    request_hash = _request_hash("CREATED", {
        "version": payload.version.strip(),
        "contentHash": content_hash,
        "reason": payload.reason.strip(),
    })
    replay = _replay(session, settings, payload.operation_key, "CREATED", request_hash)
    if replay is not None:
        return replay
    duplicate = session.scalar(_scope_statement(settings).where(
        AISensitiveDataPolicy.version == payload.version.strip()
    ))
    if duplicate is not None:
        raise HTTPException(409, "현재 고객·현장에 같은 정책 버전이 이미 있습니다.")
    row = AISensitiveDataPolicy(
        policy_id=f"aisdp-{uuid4().hex}",
        customer_scope=settings.ai_customer_scope,
        site_scope=settings.ai_site_scope,
        version=payload.version.strip(),
        forbidden_terms_json=json.dumps(payload.forbidden_terms, ensure_ascii=False),
        customer_identifiers_json=json.dumps(payload.customer_identifiers, ensure_ascii=False),
        content_hash=content_hash,
        status="DRAFT",
        is_active=False,
        state_revision=1,
        created_by=user.user_id,
    )
    session.add(row)
    session.flush()
    _audit(session, settings, user, row, "CREATED", payload.reason.strip())
    _receipt(session, row, user, payload.operation_key, "CREATED", request_hash)
    try:
        session.commit()
    except (IntegrityError, StaleDataError):
        session.rollback()
        raise HTTPException(409, "다른 관리자가 같은 버전 또는 멱등 키를 먼저 사용했습니다.")
    return _policy_dict(row)


def _change(
    policy_id: str,
    action: Literal[
        "REVIEWED", "APPROVED", "ACTIVATED", "REPLACED", "APPROVAL_WITHDRAWN", "RETIRED"
    ],
    payload: SensitivePolicyAction,
    user: AuthenticatedUser,
    settings: Settings,
    session: Session,
) -> dict[str, object]:
    _begin_mutation(session)
    request_hash = _request_hash(action, {
        "policyId": policy_id,
        "reason": payload.reason.strip(),
        "confirmAction": payload.confirm_action,
        "replacesPolicyId": payload.replaces_policy_id,
    })
    replay = _replay(session, settings, payload.operation_key, action, request_hash)
    if replay is not None:
        return replay
    expected_confirmation = ACTION_CONFIRMATIONS[action]
    if payload.confirm_action != expected_confirmation:
        raise HTTPException(422, f"confirmAction은 {expected_confirmation}이어야 합니다.")
    row = _policy(policy_id, settings, session)
    if payload.expected_state_tag != _state_tag(row):
        raise HTTPException(409, {
            "code": "AI_SENSITIVE_POLICY_STALE_STATE",
            "message": "다른 관리자가 정책 상태를 변경했습니다. 상세를 새로고침한 뒤 다시 확인하세요.",
            "currentStateTag": _state_tag(row),
        })
    now = datetime.now(timezone.utc)
    replaced_policy_id = None
    if action == "REVIEWED":
        if row.status != "DRAFT":
            raise HTTPException(409, "초안 정책만 검토할 수 있습니다.")
        if user.user_id == row.created_by:
            raise HTTPException(409, "정책 작성자는 같은 버전을 검토할 수 없습니다.")
        row.status, row.reviewed_by, row.reviewed_at = "REVIEWED", user.user_id, now
    elif action == "APPROVED":
        if row.status != "REVIEWED":
            raise HTTPException(409, "검토 완료 정책만 승인할 수 있습니다.")
        if user.user_id in {row.created_by, row.reviewed_by}:
            raise HTTPException(409, "정책 승인자는 작성자·검토자와 달라야 합니다.")
        row.status, row.approved_by, row.approved_at = "APPROVED", user.user_id, now
    elif action == "ACTIVATED":
        if row.status != "APPROVED":
            raise HTTPException(409, "승인 완료 정책만 활성화할 수 있습니다.")
        current = session.scalar(_scope_statement(settings).where(
            AISensitiveDataPolicy.status == "ACTIVE",
            AISensitiveDataPolicy.is_active.is_(True),
        ))
        if current is not None:
            raise HTTPException(409, "현재 활성 정책이 있습니다. 대체 작업을 사용하세요.")
        row.status, row.is_active = "ACTIVE", True
        row.activated_by, row.activated_at = user.user_id, now
    elif action == "REPLACED":
        if row.status != "APPROVED":
            raise HTTPException(409, "승인 완료 정책만 현재 정책을 대체할 수 있습니다.")
        current = session.scalar(_scope_statement(settings).where(
            AISensitiveDataPolicy.status == "ACTIVE",
            AISensitiveDataPolicy.is_active.is_(True),
        ))
        if current is None or current.policy_id != payload.replaces_policy_id:
            raise HTTPException(409, "대체 대상이 현재 활성 정책과 다릅니다. 목록을 새로고침하세요.")
        if current.policy_id == row.policy_id:
            raise HTTPException(409, "정책은 자기 자신을 대체할 수 없습니다.")
        current.status, current.is_active = "SUPERSEDED", False
        current.replaced_by_policy_id = row.policy_id
        current.state_revision += 1
        replaced_policy_id = current.policy_id
        _audit(session, settings, user, current, "SUPERSEDED", payload.reason.strip(),
               replaced_policy_id=row.policy_id)
        row.status, row.is_active = "ACTIVE", True
        row.activated_by, row.activated_at = user.user_id, now
    elif action == "APPROVAL_WITHDRAWN":
        if row.status not in {"APPROVED", "ACTIVE"}:
            raise HTTPException(409, "승인 또는 활성 정책만 승인을 철회할 수 있습니다.")
        row.status, row.is_active = "APPROVAL_WITHDRAWN", False
        row.approval_withdrawn_by, row.approval_withdrawn_at = user.user_id, now
    else:
        if row.status in NON_RETIRABLE_STATUSES:
            raise HTTPException(409, "이미 대체·승인 철회·폐기된 정책입니다.")
        row.status, row.is_active = "RETIRED", False
        row.retired_by, row.retired_at = user.user_id, now
    row.state_revision += 1
    row.updated_at = now
    session.flush()
    _audit(
        session, settings, user, row, action, payload.reason.strip(),
        replaced_policy_id=replaced_policy_id,
    )
    _receipt(session, row, user, payload.operation_key, action, request_hash)
    try:
        session.commit()
    except (IntegrityError, StaleDataError):
        session.rollback()
        raise HTTPException(409, "다른 관리자의 정책 변경과 충돌했습니다. 목록을 새로고침하세요.")
    return _policy_dict(row)


@router.post("/{policy_id}/review")
def review_sensitive_policy(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "REVIEWED", payload, user, settings, session)


@router.post("/{policy_id}/approve")
def approve_sensitive_policy(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "APPROVED", payload, user, settings, session)


@router.post("/{policy_id}/activate")
def activate_sensitive_policy(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "ACTIVATED", payload, user, settings, session)


@router.post("/{policy_id}/replace")
def replace_sensitive_policy(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "REPLACED", payload, user, settings, session)


@router.post("/{policy_id}/withdraw-approval")
def withdraw_sensitive_policy_approval(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "APPROVAL_WITHDRAWN", payload, user, settings, session)


@router.post("/{policy_id}/retire")
def retire_sensitive_policy(
    policy_id: str, payload: SensitivePolicyAction, user: SystemAdmin, settings: Cfg, session: Db
):
    return _change(policy_id, "RETIRED", payload, user, settings, session)
