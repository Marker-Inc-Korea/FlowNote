from __future__ import annotations

from datetime import datetime, timezone
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    _as_utc,
    create_auth_session,
    hash_refresh_token,
    rotate_auth_session_tokens,
)
from app.core.config import Settings, get_settings
from app.db.init_db import hash_password_for_dev
from app.db.models import AuthSession, UserAccount
from app.db.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    user_id: str
    username: str
    role: str
    display_name: str
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutResponse(BaseModel):
    revoked: bool


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    display_name: str


def _password_matches(password: str, stored_password_hash: str) -> bool:
    return compare_digest(hash_password_for_dev(password), stored_password_hash)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    session: Annotated[Session, Depends(get_db_session)],
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
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
            detail="User account is not active.",
        )

    _, tokens = create_auth_session(account, app_settings, session)
    return LoginResponse(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        refresh_token=tokens.refresh_token,
        refresh_expires_at=tokens.refresh_expires_at,
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: RefreshRequest,
    session: Annotated[Session, Depends(get_db_session)],
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
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

    tokens = rotate_auth_session_tokens(auth_session, account, app_settings, session, now)
    return LoginResponse(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        refresh_token=tokens.refresh_token,
        refresh_expires_at=tokens.refresh_expires_at,
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
    )
