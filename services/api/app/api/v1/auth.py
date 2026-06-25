from __future__ import annotations

from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.init_db import hash_password_for_dev
from app.db.models import UserAccount
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


def _password_matches(password: str, stored_password_hash: str) -> bool:
    return compare_digest(hash_password_for_dev(password), stored_password_hash)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    session: Annotated[Session, Depends(get_db_session)],
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

    return LoginResponse(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        display_name=account.display_name,
    )
