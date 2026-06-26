from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import TagDefinition
from app.db.session import get_db_session

router = APIRouter(prefix="/tags", tags=["tags"])

ALLOWED_TAG_TYPES = {"equipment", "item", "process", "error_type", "line", "location", "custom"}


class TagResponse(BaseModel):
    tag_id: str
    tag_type: str
    code: str
    name: str
    parent_tag_id: str | None
    external_system: str | None
    external_ref_id: str | None
    is_active: bool
    created_at: datetime


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    tag_type: str = Field(default="custom", alias="tagType")
    code: str | None = None
    parent_tag_id: str | None = Field(default=None, alias="parentTagId")
    external_system: str | None = Field(default=None, alias="externalSystem")
    external_ref_id: str | None = Field(default=None, alias="externalRefId")


def _new_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _normalize_code(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _tag_response(tag: TagDefinition) -> TagResponse:
    return TagResponse(
        tag_id=tag.tag_id,
        tag_type=tag.tag_type,
        code=tag.code,
        name=tag.name,
        parent_tag_id=tag.parent_tag_id,
        external_system=tag.external_system,
        external_ref_id=tag.external_ref_id,
        is_active=tag.is_active,
        created_at=tag.created_at,
    )


@router.get("", response_model=list[TagResponse])
def list_tags(
    session: Annotated[Session, Depends(get_db_session)],
    tag_type: Annotated[str | None, Query(alias="tagType")] = None,
    active_only: Annotated[bool, Query(alias="activeOnly")] = True,
) -> list[TagResponse]:
    statement = select(TagDefinition).order_by(TagDefinition.tag_type, TagDefinition.name)
    if tag_type is not None:
        statement = statement.where(TagDefinition.tag_type == tag_type)
    if active_only:
        statement = statement.where(TagDefinition.is_active.is_(True))
    return [_tag_response(tag) for tag in session.scalars(statement).all()]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    request: TagCreateRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> TagResponse:
    tag_type = request.tag_type.strip()
    if tag_type not in ALLOWED_TAG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"tagType must be one of: {', '.join(sorted(ALLOWED_TAG_TYPES))}.",
        )

    name = request.name.strip()
    code = _normalize_code(request.code or name)
    existing = session.scalar(
        select(TagDefinition).where(TagDefinition.tag_type == tag_type, TagDefinition.code == code)
    )
    if existing is not None:
        return _tag_response(existing)

    tag = TagDefinition(
        tag_id=_new_public_id("tag"),
        tag_type=tag_type,
        code=code,
        name=name,
        parent_tag_id=_clean_optional(request.parent_tag_id),
        external_system=_clean_optional(request.external_system),
        external_ref_id=_clean_optional(request.external_ref_id),
    )
    session.add(tag)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag could not be saved because of a database constraint.",
        ) from exc
    session.refresh(tag)
    return _tag_response(tag)
