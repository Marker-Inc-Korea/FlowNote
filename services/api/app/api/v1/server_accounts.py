from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import ROLE_SYSTEM_ADMIN, USER_MANAGEMENT_ROLES, AuthenticatedUser, require_roles
from app.db.init_db import ALLOWED_USER_ROLES, hash_password
from app.db.models import ActivityHistory, AuthSession, UserAccount
from app.db.session import get_db_session

router = APIRouter(prefix="/server-accounts", tags=["server-accounts"])

ACCOUNT_STATUSES = frozenset({"ACTIVE", "LOCKED", "DISABLED"})
UserManagementUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*USER_MANAGEMENT_ROLES)),
]


class AccountCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    role: str
    temporary_password: str = Field(min_length=8, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class AccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = None
    status: str | None = None
    reason: str = Field(min_length=1, max_length=1000)


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=8, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class RevokeSessionsRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AccountResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    status: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime


class AccountMutationResponse(BaseModel):
    account: AccountResponse
    sessions_revoked: int


class SessionResponse(BaseModel):
    session_id: str
    device_id: str | None
    status: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None
    created_at: datetime


class RevokeSessionsResponse(BaseModel):
    sessions_revoked: int


def _account_response(account: UserAccount) -> AccountResponse:
    return AccountResponse(
        user_id=account.user_id,
        username=account.username,
        display_name=account.display_name,
        role=account.role,
        status=account.status,
        is_active=account.is_active,
        must_change_password=account.must_change_password,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _account_state(account: UserAccount) -> dict[str, object]:
    return {
        "user_id": account.user_id,
        "username": account.username,
        "display_name": account.display_name,
        "role": account.role,
        "status": account.status,
        "is_active": account.is_active,
        "must_change_password": account.must_change_password,
    }


def _json_state(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_account(session: Session, user_id: str) -> UserAccount:
    account = session.scalar(select(UserAccount).where(UserAccount.user_id == user_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server account was not found.")
    return account


def _validate_role(role: str) -> str:
    cleaned = role.strip()
    if cleaned not in ALLOWED_USER_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role is not allowed.")
    return cleaned


def _validate_status(account_status: str) -> str:
    cleaned = account_status.strip().upper()
    if cleaned not in ACCOUNT_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Account status is not allowed.")
    return cleaned


def _protect_system_admin(actor: AuthenticatedUser, target: UserAccount | None, requested_role: str | None = None) -> None:
    touches_system_admin = requested_role == ROLE_SYSTEM_ADMIN or (
        target is not None and target.role == ROLE_SYSTEM_ADMIN
    )
    if touches_system_admin and actor.role != ROLE_SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system-admin can operate a system-admin account.",
        )


def _protect_last_system_admin(
    session: Session,
    target: UserAccount,
    *,
    requested_role: str,
    requested_status: str,
) -> None:
    removes_active_system_admin = (
        target.role == ROLE_SYSTEM_ADMIN
        and target.status == "ACTIVE"
        and (requested_role != ROLE_SYSTEM_ADMIN or requested_status != "ACTIVE")
    )
    if not removes_active_system_admin:
        return
    other_count = session.scalar(
        select(func.count(UserAccount.id)).where(
            UserAccount.user_id != target.user_id,
            UserAccount.role == ROLE_SYSTEM_ADMIN,
            UserAccount.status == "ACTIVE",
            UserAccount.is_active.is_(True),
        )
    )
    if not other_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active system-admin cannot be removed or disabled.",
        )


def _revoke_active_sessions(session: Session, user_id: str, reason: str) -> int:
    now = datetime.now(timezone.utc)
    rows = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.status == "ACTIVE",
        )
    ).all()
    for row in rows:
        row.status = "REVOKED"
        row.revoked_at = now
        row.revoked_reason = reason[:120]
        session.add(row)
    return len(rows)


def _record_activity(
    session: Session,
    *,
    event_type: str,
    actor: AuthenticatedUser,
    target: UserAccount,
    message: str,
    reason: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    session.add(
        ActivityHistory(
            history_id=f"history-{uuid4().hex}",
            event_type=event_type,
            actor_id=actor.user_id,
            target_type="user_account",
            target_id=target.user_id,
            target_title=target.display_name,
            message=message,
            before_value=None if before is None else _json_state(before),
            after_value=None if after is None else _json_state(after),
            change_reason=reason.strip(),
        )
    )


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
    query: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AccountResponse]:
    statement = select(UserAccount).order_by(UserAccount.username)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(UserAccount.username.ilike(pattern), UserAccount.display_name.ilike(pattern))
        )
    accounts = session.scalars(statement).all()
    if current_user.role != ROLE_SYSTEM_ADMIN:
        accounts = [account for account in accounts if account.role != ROLE_SYSTEM_ADMIN]
    return [_account_response(account) for account in accounts]


@router.post("", response_model=AccountMutationResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    request: AccountCreateRequest,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> AccountMutationResponse:
    username = request.username.strip()
    display_name = request.display_name.strip()
    role = _validate_role(request.role)
    _protect_system_admin(current_user, None, role)
    account = UserAccount(
        user_id=f"user-{uuid4().hex}",
        username=username,
        login_id=username,
        display_name=display_name,
        role=role,
        password_hash=hash_password(request.temporary_password),
        is_active=True,
        status="ACTIVE",
        must_change_password=True,
    )
    session.add(account)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.") from exc
    _record_activity(
        session,
        event_type="user.created",
        actor=current_user,
        target=account,
        message="서버 계정을 생성했습니다.",
        reason=request.reason,
        before=None,
        after=_account_state(account),
    )
    session.commit()
    session.refresh(account)
    return AccountMutationResponse(account=_account_response(account), sessions_revoked=0)


@router.patch("/{user_id}", response_model=AccountMutationResponse)
def update_account(
    user_id: str,
    request: AccountUpdateRequest,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> AccountMutationResponse:
    account = _require_account(session, user_id)
    role = account.role if request.role is None else _validate_role(request.role)
    account_status = account.status if request.status is None else _validate_status(request.status)
    _protect_system_admin(current_user, account, role)
    if account.user_id == current_user.user_id and account_status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot disable or lock your own account.")
    _protect_last_system_admin(session, account, requested_role=role, requested_status=account_status)

    before = _account_state(account)
    role_changed = role != account.role
    status_changed = account_status != account.status
    if request.display_name is not None:
        account.display_name = request.display_name.strip()
    account.role = role
    account.status = account_status
    account.is_active = account_status == "ACTIVE"
    sessions_revoked = 0
    if role_changed or (status_changed and account_status != "ACTIVE"):
        sessions_revoked = _revoke_active_sessions(
            session,
            account.user_id,
            "role_changed" if role_changed else f"account_{account_status.lower()}",
        )
    after = _account_state(account)
    after["sessions_revoked"] = sessions_revoked
    session.add(account)
    _record_activity(
        session,
        event_type="user.updated",
        actor=current_user,
        target=account,
        message="서버 계정 상태 또는 역할을 변경했습니다.",
        reason=request.reason,
        before=before,
        after=after,
    )
    session.commit()
    session.refresh(account)
    return AccountMutationResponse(account=_account_response(account), sessions_revoked=sessions_revoked)


@router.post("/{user_id}/password-reset", response_model=AccountMutationResponse)
def reset_password(
    user_id: str,
    request: PasswordResetRequest,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> AccountMutationResponse:
    account = _require_account(session, user_id)
    _protect_system_admin(current_user, account)
    before = _account_state(account)
    account.password_hash = hash_password(request.temporary_password)
    account.must_change_password = True
    account.password_changed_at = None
    sessions_revoked = _revoke_active_sessions(session, account.user_id, "password_reset")
    after = _account_state(account)
    after["sessions_revoked"] = sessions_revoked
    session.add(account)
    _record_activity(
        session,
        event_type="user.password_reset",
        actor=current_user,
        target=account,
        message="서버 계정 비밀번호를 임시 비밀번호로 재설정했습니다.",
        reason=request.reason,
        before=before,
        after=after,
    )
    session.commit()
    session.refresh(account)
    return AccountMutationResponse(account=_account_response(account), sessions_revoked=sessions_revoked)


@router.get("/{user_id}/sessions", response_model=list[SessionResponse])
def list_sessions(
    user_id: str,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
    active_only: bool = True,
) -> list[SessionResponse]:
    account = _require_account(session, user_id)
    _protect_system_admin(current_user, account)
    statement = select(AuthSession).where(AuthSession.user_id == user_id)
    if active_only:
        statement = statement.where(AuthSession.status == "ACTIVE")
    rows = session.scalars(statement.order_by(AuthSession.created_at.desc())).all()
    return [SessionResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{user_id}/sessions/revoke", response_model=RevokeSessionsResponse)
def revoke_all_sessions(
    user_id: str,
    request: RevokeSessionsRequest,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> RevokeSessionsResponse:
    account = _require_account(session, user_id)
    _protect_system_admin(current_user, account)
    before = _account_state(account)
    active_session_ids = [
        row.session_id
        for row in session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.status == "ACTIVE",
            )
        ).all()
    ]
    before["active_session_ids"] = active_session_ids
    revoked = _revoke_active_sessions(session, user_id, "administrator_revoked")
    after = _account_state(account)
    after["revoked_session_ids"] = active_session_ids
    _record_activity(
        session,
        event_type="user.sessions_revoked",
        actor=current_user,
        target=account,
        message=f"서버 계정의 활성 세션 {revoked}개를 강제 폐기했습니다.",
        reason=request.reason,
        before=before,
        after=after,
    )
    session.commit()
    return RevokeSessionsResponse(sessions_revoked=revoked)


@router.post("/{user_id}/sessions/{session_id}/revoke", response_model=RevokeSessionsResponse)
def revoke_session(
    user_id: str,
    session_id: str,
    request: RevokeSessionsRequest,
    current_user: UserManagementUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> RevokeSessionsResponse:
    account = _require_account(session, user_id)
    _protect_system_admin(current_user, account)
    auth_session = session.scalar(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.session_id == session_id,
        )
    )
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authentication session was not found.")
    before = _account_state(account)
    before["session"] = {
        "session_id": auth_session.session_id,
        "status": auth_session.status,
        "revoked_at": None if auth_session.revoked_at is None else auth_session.revoked_at.isoformat(),
    }
    revoked = 0
    if auth_session.status == "ACTIVE":
        auth_session.status = "REVOKED"
        auth_session.revoked_at = datetime.now(timezone.utc)
        auth_session.revoked_reason = "administrator_revoked"
        session.add(auth_session)
        revoked = 1
    after = _account_state(account)
    after["session"] = {
        "session_id": auth_session.session_id,
        "status": auth_session.status,
        "revoked_at": None if auth_session.revoked_at is None else auth_session.revoked_at.isoformat(),
    }
    _record_activity(
        session,
        event_type="user.session_revoked",
        actor=current_user,
        target=account,
        message=f"서버 계정 세션 {session_id}을 강제 폐기했습니다.",
        reason=request.reason,
        before=before,
        after=after,
    )
    session.commit()
    return RevokeSessionsResponse(sessions_revoked=revoked)
