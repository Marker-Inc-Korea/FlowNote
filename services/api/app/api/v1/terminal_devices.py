from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, AuthenticatedUser, require_roles
from app.db.models import ActivityHistory, AuthSession, TerminalDevice
from app.db.session import get_db_session

router = APIRouter(prefix="/terminal-devices", tags=["terminal-devices"])

DEVICE_STATUSES = {"ACTIVE", "INACTIVE", "RETIRED"}
DEVICE_MODES = {"viewer", "admin_support"}
TerminalDeviceAdmin = Annotated[
    AuthenticatedUser,
    Depends(require_roles(ROLE_ADMIN, ROLE_SYSTEM_ADMIN)),
]


class TerminalDeviceCreateRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    device_name: str = Field(min_length=1, max_length=120)
    device_mode: str = "viewer"
    location_code: str | None = Field(default=None, max_length=64)
    group_id: str | None = Field(default=None, max_length=64)
    status: str = "ACTIVE"

    @field_validator("device_id", "device_name")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("location_code", "group_id")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("device_mode")
    @classmethod
    def validate_device_mode(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in DEVICE_MODES:
            raise ValueError(f"must be one of {sorted(DEVICE_MODES)}")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in DEVICE_STATUSES:
            raise ValueError(f"must be one of {sorted(DEVICE_STATUSES)}")
        return cleaned


class TerminalDeviceUpdateRequest(BaseModel):
    device_name: str | None = Field(default=None, min_length=1, max_length=120)
    device_mode: str | None = None
    location_code: str | None = Field(default=None, max_length=64)
    group_id: str | None = Field(default=None, max_length=64)
    change_reason: str | None = Field(default=None, max_length=500)

    @field_validator("device_name")
    @classmethod
    def clean_device_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("device_mode")
    @classmethod
    def validate_device_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned not in DEVICE_MODES:
            raise ValueError(f"must be one of {sorted(DEVICE_MODES)}")
        return cleaned

    @field_validator("location_code", "group_id", "change_reason")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class TerminalDeviceStatusRequest(BaseModel):
    status: str
    change_reason: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in DEVICE_STATUSES:
            raise ValueError(f"must be one of {sorted(DEVICE_STATUSES)}")
        return cleaned

    @field_validator("change_reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class TerminalDeviceReplaceRequest(TerminalDeviceCreateRequest):
    change_reason: str | None = Field(default=None, max_length=500)


class TerminalDeviceResponse(BaseModel):
    device_id: str
    device_name: str
    device_mode: str
    location_code: str | None
    group_id: str | None
    status: str
    last_seen_at: datetime | None
    registered_by: str | None
    updated_by: str | None
    replaced_device_id: str | None
    created_at: datetime
    updated_at: datetime


class TerminalDeviceLastSeenResponse(BaseModel):
    device_id: str
    status: str
    last_seen_at: datetime | None


def _get_device(session: Session, device_id: str) -> TerminalDevice:
    device = session.scalar(
        select(TerminalDevice).where(TerminalDevice.device_id == device_id.strip())
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal device not found.")
    return device


def _as_response(device: TerminalDevice) -> TerminalDeviceResponse:
    return TerminalDeviceResponse(
        device_id=device.device_id,
        device_name=device.device_name,
        device_mode=device.device_mode,
        location_code=device.location_code,
        group_id=device.group_id,
        status=device.status,
        last_seen_at=device.last_seen_at,
        registered_by=device.registered_by,
        updated_by=device.updated_by,
        replaced_device_id=device.replaced_device_id,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _snapshot(device: TerminalDevice) -> str:
    return json.dumps(
        {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "device_mode": device.device_mode,
            "location_code": device.location_code,
            "group_id": device.group_id,
            "status": device.status,
            "registered_by": device.registered_by,
            "updated_by": device.updated_by,
            "replaced_device_id": device.replaced_device_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _record_activity(
    session: Session,
    *,
    event_type: str,
    actor_id: str,
    device: TerminalDevice,
    message: str,
    before_value: str | None = None,
    after_value: str | None = None,
    change_reason: str | None = None,
) -> None:
    session.add(
        ActivityHistory(
            history_id=f"hist-{uuid4().hex}",
            event_type=event_type,
            actor_id=actor_id,
            target_type="TERMINAL_DEVICE",
            target_id=device.device_id,
            target_title=device.device_name,
            message=message,
            before_value=before_value,
            after_value=after_value,
            change_reason=change_reason,
        )
    )


def _new_device(payload: TerminalDeviceCreateRequest, actor_id: str) -> TerminalDevice:
    return TerminalDevice(
        device_id=payload.device_id,
        device_name=payload.device_name,
        device_mode=payload.device_mode,
        location_code=payload.location_code,
        group_id=payload.group_id,
        status=payload.status,
        registered_by=actor_id,
        updated_by=actor_id,
    )


def _revoke_active_device_sessions(session: Session, device_id: str, reason: str) -> None:
    active_sessions = session.scalars(
        select(AuthSession).where(
            AuthSession.device_id == device_id,
            AuthSession.status == "ACTIVE",
        )
    ).all()
    revoked_at = datetime.now(timezone.utc)
    for auth_session in active_sessions:
        auth_session.status = "REVOKED"
        auth_session.revoked_at = revoked_at
        auth_session.revoked_reason = reason
        session.add(auth_session)


@router.get("", response_model=list[TerminalDeviceResponse])
def list_terminal_devices(
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
    device_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[TerminalDeviceResponse]:
    statement = select(TerminalDevice)
    if device_status is not None:
        normalized = device_status.strip().upper()
        if normalized not in DEVICE_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported terminal device status.")
        statement = statement.where(TerminalDevice.status == normalized)
    devices = session.scalars(statement.order_by(TerminalDevice.device_name, TerminalDevice.device_id)).all()
    return [_as_response(device) for device in devices]


@router.post("", response_model=TerminalDeviceResponse, status_code=status.HTTP_201_CREATED)
def create_terminal_device(
    payload: TerminalDeviceCreateRequest,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceResponse:
    device = _new_device(payload, current_user.user_id)
    session.add(device)
    try:
        session.flush()
    except IntegrityError as exception:
        session.rollback()
        raise HTTPException(status_code=409, detail="Terminal device_id already exists.") from exception
    _record_activity(
        session,
        event_type="terminal_device.registered",
        actor_id=current_user.user_id,
        device=device,
        message=f"승인 단말을 등록했습니다: {device.device_name} ({device.device_id}).",
        after_value=_snapshot(device),
    )
    session.commit()
    session.refresh(device)
    return _as_response(device)


@router.get("/{device_id}", response_model=TerminalDeviceResponse)
def get_terminal_device(
    device_id: str,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceResponse:
    return _as_response(_get_device(session, device_id))


@router.get("/{device_id}/last-seen", response_model=TerminalDeviceLastSeenResponse)
def get_terminal_device_last_seen(
    device_id: str,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceLastSeenResponse:
    device = _get_device(session, device_id)
    return TerminalDeviceLastSeenResponse(
        device_id=device.device_id,
        status=device.status,
        last_seen_at=device.last_seen_at,
    )


@router.patch("/{device_id}", response_model=TerminalDeviceResponse)
def update_terminal_device(
    device_id: str,
    payload: TerminalDeviceUpdateRequest,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceResponse:
    device = _get_device(session, device_id)
    before_value = _snapshot(device)
    changed = False
    for field_name in ("device_name", "device_mode", "location_code", "group_id"):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if getattr(device, field_name) != value:
                setattr(device, field_name, value)
                changed = True
    if changed:
        device.updated_by = current_user.user_id
        _record_activity(
            session,
            event_type="terminal_device.updated",
            actor_id=current_user.user_id,
            device=device,
            message=f"승인 단말 정보를 변경했습니다: {device.device_name} ({device.device_id}).",
            before_value=before_value,
            after_value=_snapshot(device),
            change_reason=payload.change_reason,
        )
        session.add(device)
        session.commit()
        session.refresh(device)
    return _as_response(device)


@router.patch("/{device_id}/status", response_model=TerminalDeviceResponse)
def update_terminal_device_status(
    device_id: str,
    payload: TerminalDeviceStatusRequest,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceResponse:
    device = _get_device(session, device_id)
    if device.status == "RETIRED" and payload.status != "RETIRED":
        raise HTTPException(status_code=409, detail="A retired terminal device cannot be reactivated.")
    if device.status != payload.status:
        before_value = _snapshot(device)
        previous_status = device.status
        device.status = payload.status
        device.updated_by = current_user.user_id
        if device.status != "ACTIVE":
            _revoke_active_device_sessions(
                session,
                device.device_id,
                f"terminal_device_{device.status.lower()}",
            )
        _record_activity(
            session,
            event_type="terminal_device.status_changed",
            actor_id=current_user.user_id,
            device=device,
            message=(
                f"승인 단말 상태를 변경했습니다: {device.device_name} "
                f"({previous_status} → {device.status})."
            ),
            before_value=before_value,
            after_value=_snapshot(device),
            change_reason=payload.change_reason,
        )
        session.add(device)
        session.commit()
        session.refresh(device)
    return _as_response(device)


@router.post("/{device_id}/replace", response_model=TerminalDeviceResponse, status_code=201)
def replace_terminal_device(
    device_id: str,
    payload: TerminalDeviceReplaceRequest,
    current_user: TerminalDeviceAdmin,
    session: Annotated[Session, Depends(get_db_session)],
) -> TerminalDeviceResponse:
    previous_device = _get_device(session, device_id)
    if previous_device.status == "RETIRED":
        raise HTTPException(status_code=409, detail="Terminal device is already retired.")
    if payload.device_id == previous_device.device_id:
        raise HTTPException(status_code=409, detail="Replacement device_id must be different.")

    before_value = _snapshot(previous_device)
    previous_device.status = "RETIRED"
    previous_device.updated_by = current_user.user_id
    _revoke_active_device_sessions(session, previous_device.device_id, "terminal_device_replaced")
    replacement = _new_device(payload, current_user.user_id)
    replacement.replaced_device_id = previous_device.device_id
    session.add_all([previous_device, replacement])
    try:
        session.flush()
    except IntegrityError as exception:
        session.rollback()
        raise HTTPException(status_code=409, detail="Replacement device_id already exists.") from exception

    _record_activity(
        session,
        event_type="terminal_device.retired_for_replacement",
        actor_id=current_user.user_id,
        device=previous_device,
        message=f"단말 교체를 위해 기존 단말을 폐기 처리했습니다: {previous_device.device_name}.",
        before_value=before_value,
        after_value=_snapshot(previous_device),
        change_reason=payload.change_reason,
    )
    _record_activity(
        session,
        event_type="terminal_device.replacement_registered",
        actor_id=current_user.user_id,
        device=replacement,
        message=(
            f"교체 승인 단말을 등록했습니다: {replacement.device_name} "
            f"(기존 {previous_device.device_id})."
        ),
        after_value=_snapshot(replacement),
        change_reason=payload.change_reason,
    )
    session.commit()
    session.refresh(replacement)
    return _as_response(replacement)
