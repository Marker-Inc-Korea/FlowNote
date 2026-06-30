from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import AuthSession, UserAccount
from app.db.session import get_db_session

TOKEN_TYPE = "Bearer"
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_VIEWER = "viewer"
ROLE_SYSTEM_ADMIN = "system-admin"
ROLE_DOCUMENT_ADMIN = "document-admin"
ROLE_ASSISTANT_MANAGER = "assistant-manager"
ROLE_DEPARTMENT_MANAGER = "department-manager"
ROLE_LINE_FOREMAN = "line-foreman"
ROLE_TEAM_LEAD = "team-lead"
ROLE_TEAM_MEMBER = "team-member"

DOCUMENT_WRITE_ROLES = frozenset(
    {
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_SYSTEM_ADMIN,
        ROLE_DOCUMENT_ADMIN,
        ROLE_ASSISTANT_MANAGER,
        ROLE_DEPARTMENT_MANAGER,
        ROLE_LINE_FOREMAN,
        ROLE_TEAM_LEAD,
    }
)
FIELD_COMMENT_CREATE_ROLES = DOCUMENT_WRITE_ROLES | frozenset({ROLE_VIEWER, ROLE_TEAM_MEMBER})
ACCESS_LOG_READ_ROLES = frozenset({ROLE_ADMIN, ROLE_SYSTEM_ADMIN})
REPORT_WRITE_ROLES = frozenset(
    {
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_SYSTEM_ADMIN,
        ROLE_DOCUMENT_ADMIN,
        ROLE_ASSISTANT_MANAGER,
        ROLE_DEPARTMENT_MANAGER,
    }
)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    role: str
    display_name: str
    session_id: str
    access_token_id: str


@dataclass(frozen=True)
class IssuedAuthTokens:
    session_id: str
    access_token: str
    access_token_id: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _sign(payload: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _base64url_encode(signature)


def create_access_token(
    account: UserAccount,
    settings: Settings,
    *,
    session_id: str | None = None,
    access_token_id: str | None = None,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expires_minutes)
    payload = {
        "sub": account.user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if session_id is not None:
        payload["sid"] = session_id
    if access_token_id is not None:
        payload["jti"] = access_token_id
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{encoded_payload}.{_sign(encoded_payload, settings.access_token_secret)}", expires_at


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def issue_auth_tokens(
    account: UserAccount,
    settings: Settings,
    now: datetime | None = None,
) -> IssuedAuthTokens:
    issued_at = now or datetime.now(timezone.utc)
    session_id = f"session-{uuid4().hex}"
    access_token_id = f"access-{uuid4().hex}"
    refresh_token = create_refresh_token()
    access_token, access_expires_at = create_access_token(
        account,
        settings,
        session_id=session_id,
        access_token_id=access_token_id,
        now=issued_at,
    )
    return IssuedAuthTokens(
        session_id=session_id,
        access_token=access_token,
        access_token_id=access_token_id,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=issued_at + timedelta(days=settings.refresh_token_expires_days),
    )


def create_auth_session(
    account: UserAccount,
    settings: Settings,
    db_session: Session,
    now: datetime | None = None,
) -> tuple[AuthSession, IssuedAuthTokens]:
    issued_at = now or datetime.now(timezone.utc)
    tokens = issue_auth_tokens(account, settings, issued_at)
    auth_session = AuthSession(
        session_id=tokens.session_id,
        user_id=account.user_id,
        access_token_id=tokens.access_token_id,
        refresh_token_hash=hash_refresh_token(tokens.refresh_token),
        status="ACTIVE",
        access_expires_at=tokens.access_expires_at,
        refresh_expires_at=tokens.refresh_expires_at,
        last_used_at=issued_at,
    )
    db_session.add(auth_session)
    db_session.commit()
    db_session.refresh(auth_session)
    return auth_session, tokens


def rotate_auth_session_tokens(
    auth_session: AuthSession,
    account: UserAccount,
    settings: Settings,
    db_session: Session,
    now: datetime | None = None,
) -> IssuedAuthTokens:
    issued_at = now or datetime.now(timezone.utc)
    access_token_id = f"access-{uuid4().hex}"
    refresh_token = create_refresh_token()
    access_token, access_expires_at = create_access_token(
        account,
        settings,
        session_id=auth_session.session_id,
        access_token_id=access_token_id,
        now=issued_at,
    )
    auth_session.access_token_id = access_token_id
    auth_session.refresh_token_hash = hash_refresh_token(refresh_token)
    auth_session.access_expires_at = access_expires_at
    auth_session.refresh_expires_at = issued_at + timedelta(days=settings.refresh_token_expires_days)
    auth_session.last_used_at = issued_at
    db_session.add(auth_session)
    db_session.commit()
    db_session.refresh(auth_session)
    return IssuedAuthTokens(
        session_id=auth_session.session_id,
        access_token=access_token,
        access_token_id=access_token_id,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=auth_session.refresh_expires_at,
    )


def _decode_access_token(token: str, settings: Settings) -> dict[str, int | str]:
    try:
        payload_part, signature_part = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise _invalid_credentials() from exc

    expected_signature = _sign(payload_part, settings.access_token_secret)
    if not hmac.compare_digest(signature_part, expected_signature):
        raise _invalid_credentials()

    try:
        payload = json.loads(_base64url_decode(payload_part))
    except (ValueError, json.JSONDecodeError) as exc:
        raise _invalid_credentials() from exc

    if not isinstance(payload, dict):
        raise _invalid_credentials()
    if not isinstance(payload.get("sub"), str) or not isinstance(payload.get("exp"), int):
        raise _invalid_credentials()
    if payload["exp"] <= int(datetime.now(timezone.utc).timestamp()):
        raise _invalid_credentials("Authentication token has expired.")
    return payload


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_auth_session(
    payload: dict[str, int | str],
    db_session: Session,
) -> AuthSession:
    session_id = payload.get("sid")
    access_token_id = payload.get("jti")
    if not isinstance(session_id, str) or not isinstance(access_token_id, str):
        raise _invalid_credentials("Authentication session is missing or invalid.")

    auth_session = db_session.scalar(
        select(AuthSession).where(AuthSession.session_id == session_id)
    )
    if (
        auth_session is None
        or auth_session.status != "ACTIVE"
        or auth_session.revoked_at is not None
    ):
        raise _invalid_credentials("Authentication session has been revoked.")
    if auth_session.access_token_id != access_token_id:
        raise _invalid_credentials("Authentication token has been replaced.")
    if _as_utc(auth_session.access_expires_at) <= datetime.now(timezone.utc):
        raise _invalid_credentials("Authentication token has expired.")
    return auth_session


def _invalid_credentials(
    detail: str = "Authentication credentials were not provided or are invalid.",
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": TOKEN_TYPE},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _invalid_credentials()

    payload = _decode_access_token(credentials.credentials, settings)
    auth_session = _validate_auth_session(payload, session)
    account = session.scalar(
        select(UserAccount).where(UserAccount.user_id == payload["sub"])
    )
    if account is None or not account.is_active or account.status != "ACTIVE":
        raise _invalid_credentials()

    return AuthenticatedUser(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
        session_id=auth_session.session_id,
        access_token_id=auth_session.access_token_id,
    )


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Current user role is not allowed to perform this action.",
            )
        return current_user

    return dependency


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
DocumentWriteUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*DOCUMENT_WRITE_ROLES)),
]
FieldCommentCreateUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*FIELD_COMMENT_CREATE_ROLES)),
]
AccessLogReadUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*ACCESS_LOG_READ_ROLES)),
]
ReportWriteUser = Annotated[
    AuthenticatedUser,
    Depends(require_roles(*REPORT_WRITE_ROLES)),
]
