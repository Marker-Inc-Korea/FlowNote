from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import UserAccount
from app.db.session import get_db_session

TOKEN_TYPE = "Bearer"

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    role: str
    display_name: str


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
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expires_minutes)
    payload = {
        "sub": account.user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{encoded_payload}.{_sign(encoded_payload, settings.access_token_secret)}", expires_at


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
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
