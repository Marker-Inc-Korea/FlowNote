from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status


def filter_signature(filters: object) -> str:
    payload = json.dumps(filters.__dict__, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def encode_cursor(
    *,
    version: int,
    anchor_id: int,
    as_of: datetime,
    last_item_id: str,
    filter_signature_value: str,
    expires_at: datetime,
) -> str:
    payload = json.dumps({
        "version": version,
        "anchorId": anchor_id,
        "asOf": _utc(as_of).isoformat(),
        "lastItemId": last_item_id,
        "filterSignature": filter_signature_value,
        "expiresAt": _utc(expires_at).isoformat(),
    }, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, now: datetime, *, version: int) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if value.get("version") != version:
            raise ValueError
        if parse_datetime(value["expiresAt"]) <= now:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "code": "OPERATIONAL_READINESS_CURSOR_EXPIRED",
                    "message": "페이지 snapshot이 만료되었습니다. 새로고침해 첫 페이지부터 조회하세요.",
                },
            )
        int(value["anchorId"])
        if not isinstance(value["lastItemId"], str) or not value["lastItemId"]:
            raise ValueError
        parse_datetime(value["asOf"])
        return value
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise invalid_cursor("페이지 커서가 올바르지 않습니다. 첫 페이지부터 다시 조회하세요.")


def invalid_cursor(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "OPERATIONAL_READINESS_CURSOR_INVALID", "message": message},
    )


def parse_datetime(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
