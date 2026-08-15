from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    PasswordChangeUser,
    _as_utc,
    create_auth_session,
    hash_refresh_token,
    rotate_auth_session_tokens,
)
from app.core.config import Settings, get_settings
from app.core.scope import ensure_server_scope
from app.db.init_db import (
    MAX_ACCOUNT_PASSWORD_LENGTH,
    MIN_ACCOUNT_PASSWORD_LENGTH,
    hash_password,
    verify_password,
)
from app.db.models import ActivityHistory, AuthSession, TerminalDevice, UserAccount
from app.db.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = {"populate_by_name": True}

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=MAX_ACCOUNT_PASSWORD_LENGTH)
    device_id: str | None = Field(default=None, alias="deviceId", max_length=64)
    customer_scope: str | None = Field(default=None, alias="customerScope", max_length=200)
    site_scope: str | None = Field(default=None, alias="siteScope", max_length=200)


class LoginResponse(BaseModel):
    user_id: str
    username: str
    role: str
    display_name: str
    device_id: str | None = None
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    must_change_password: bool
    customer_scope: str
    site_scope: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)
    customer_scope: str | None = Field(default=None, alias="customerScope", max_length=200)
    site_scope: str | None = Field(default=None, alias="siteScope", max_length=200)


class LogoutResponse(BaseModel):
    revoked: bool


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    display_name: str
    must_change_password: bool
    customer_scope: str
    site_scope: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_ACCOUNT_PASSWORD_LENGTH)
    new_password: str = Field(
        min_length=MIN_ACCOUNT_PASSWORD_LENGTH,
        max_length=MAX_ACCOUNT_PASSWORD_LENGTH,
    )


class ChangePasswordResponse(BaseModel):
    changed: bool
    sessions_revoked: int


def _password_matches(password: str, stored_password_hash: str) -> bool:
    return verify_password(password, stored_password_hash)


def _clean_device_id(device_id: str | None) -> str | None:
    if device_id is None:
        return None
    cleaned = device_id.strip()
    return cleaned or None


def _validate_active_terminal_device(session: Session, device_id: str | None) -> str | None:
    cleaned = _clean_device_id(device_id)
    if cleaned is None:
        return None
    terminal = session.scalar(
        select(TerminalDevice).where(TerminalDevice.device_id == cleaned)
    )
    if terminal is None or terminal.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DEVICE_NOT_APPROVED",
                "message": "승인되지 않았거나 비활성 상태인 단말입니다.",
            },
        )
    terminal.last_seen_at = datetime.now(timezone.utc)
    session.add(terminal)
    return cleaned


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    http_request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    ensure_server_scope(
        http_request,
        app_settings,
        session,
        customer_scope=request.customer_scope,
        site_scope=request.site_scope,
    )
    username = request.username.strip()
    account = session.scalar(select(UserAccount).where(UserAccount.username == username))
    if account is None or not _password_matches(request.password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    if not account.is_active or account.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_NOT_ACTIVE",
                "message": "현재 계정은 활성 상태가 아닙니다.",
            },
        )
    device_id = _validate_active_terminal_device(session, request.device_id)

    _, tokens = create_auth_session(account, app_settings, session, device_id=device_id)
    return LoginResponse(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        device_id=device_id,
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        refresh_token=tokens.refresh_token,
        refresh_expires_at=tokens.refresh_expires_at,
        must_change_password=account.must_change_password,
        customer_scope=app_settings.effective_customer_scope,
        site_scope=app_settings.effective_site_scope,
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: RefreshRequest,
    http_request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    ensure_server_scope(
        http_request,
        app_settings,
        session,
        customer_scope=request.customer_scope,
        site_scope=request.site_scope,
    )
    token_hash = hash_refresh_token(request.refresh_token)
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
    )
    now = datetime.now(timezone.utc)
    if (
        auth_session is None
        or auth_session.status != "ACTIVE"
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.refresh_expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired.",
        )

    account = session.scalar(select(UserAccount).where(UserAccount.user_id == auth_session.user_id))
    if account is None or not account.is_active or account.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired.",
        )
    if auth_session.device_id is not None:
        terminal = session.scalar(
            select(TerminalDevice).where(TerminalDevice.device_id == auth_session.device_id)
        )
        if terminal is None or terminal.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or expired.",
            )
    if account.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is required before refreshing this session.",
        )

    tokens = rotate_auth_session_tokens(auth_session, account, app_settings, session, now)
    return LoginResponse(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        device_id=auth_session.device_id,
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        refresh_token=tokens.refresh_token,
        refresh_expires_at=tokens.refresh_expires_at,
        must_change_password=account.must_change_password,
        customer_scope=app_settings.effective_customer_scope,
        site_scope=app_settings.effective_site_scope,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    current_user: CurrentUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> LogoutResponse:
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.session_id == current_user.session_id)
    )
    if auth_session is not None and auth_session.status == "ACTIVE":
        auth_session.status = "REVOKED"
        auth_session.revoked_at = datetime.now(timezone.utc)
        auth_session.revoked_reason = "logout"
        session.add(auth_session)
        session.commit()
    return LogoutResponse(revoked=True)


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role,
        display_name=current_user.display_name,
        must_change_password=current_user.must_change_password,
        customer_scope=current_user.customer_scope,
        site_scope=current_user.site_scope,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: PasswordChangeUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> ChangePasswordResponse:
    account = session.scalar(
        select(UserAccount).where(UserAccount.user_id == current_user.user_id)
    )
    if account is None or not _password_matches(request.current_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is invalid.",
        )
    if _password_matches(request.new_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )

    now = datetime.now(timezone.utc)
    before_must_change_password = account.must_change_password
    account.password_hash = hash_password(request.new_password)
    account.must_change_password = False
    account.password_changed_at = now
    active_sessions = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == account.user_id,
            AuthSession.status == "ACTIVE",
        )
    ).all()
    for auth_session in active_sessions:
        auth_session.status = "REVOKED"
        auth_session.revoked_at = now
        auth_session.revoked_reason = "password_changed"
        session.add(auth_session)
    session.add(account)
    session.add(
        ActivityHistory(
            history_id=f"history-{uuid4().hex}",
            event_type="user.password_changed",
            actor_id=account.user_id,
            target_type="user_account",
            target_id=account.user_id,
            target_title=account.display_name,
            message="사용자가 비밀번호를 변경했습니다.",
            before_value=(
                f'{{"active_sessions":{len(active_sessions)},'
                f'"must_change_password":{str(before_must_change_password).lower()}}}'
            ),
            after_value=(
                f'{{"must_change_password":false,"sessions_revoked":{len(active_sessions)}}}'
            ),
            change_reason="사용자 본인 비밀번호 변경",
        )
    )
    session.commit()
    return ChangePasswordResponse(changed=True, sessions_revoked=len(active_sessions))
