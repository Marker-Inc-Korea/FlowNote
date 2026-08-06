from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.db.models import (
    AuditEventEnvelope,
    DocumentApprovalMutationReceipt,
    DocumentMutationReceipt,
    FieldCommentReviewMutationReceipt,
    ReportMutationReceipt,
    SyncMutationReceipt,
    WorkSequenceMutationReceipt,
)

_SECRET_PATTERN = re.compile(
    r"(?i)(access[_ -]?token|refresh[_ -]?token|password|passwd|secret|authorization)\s*[:=]\s*\S+"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[a-z]:\\[^\s]+")
_UNIX_ABSOLUTE_PATH = re.compile(r"(?<![\w.])/(?:Users|home|var|tmp|opt|srv)/[^\s]+")


@dataclass(frozen=True)
class MutationTrace:
    actor_id: str
    actor_role: str
    session_id: str
    device_id: str | None
    run_id: str | None
    correlation_id: str


def mutation_trace(current_user: AuthenticatedUser, request: Request | None = None) -> MutationTrace:
    run_id = _clean_header(request.headers.get("X-FlowNote-Run-Id")) if request else None
    correlation_id = (
        _clean_header(request.headers.get("X-Correlation-Id")) if request else None
    ) or f"corr_{uuid4().hex}"
    return MutationTrace(
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        session_id=current_user.session_id,
        device_id=current_user.device_id,
        run_id=run_id,
        correlation_id=correlation_id,
    )


def canonical_hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def sanitize_audit_text(value: str | None) -> str | None:
    return _redact_sensitive_text(value)


def check_common_mutation_replay(
    session: Session,
    *,
    operation_key: str | None,
    intent_hash: str,
    event_type: str,
    target_type: str,
    target_id: str | None,
) -> SyncMutationReceipt | None:
    if operation_key is None:
        return None
    receipt = session.scalar(
        select(SyncMutationReceipt).where(
            SyncMutationReceipt.operation_key == operation_key
        )
    )
    if receipt is None:
        _reject_cross_domain_legacy_key_reuse(
            session,
            operation_key=operation_key,
            target_type=target_type,
        )
        return None
    if (
        receipt.intent_hash_sha256 != intent_hash
        or receipt.event_type != event_type
        or receipt.target_type != target_type
        or (target_id is not None and receipt.target_id != target_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "IDEMPOTENCY_KEY_REUSED",
                "message": "The operation key is already bound to a different mutation intent.",
            },
        )
    if receipt.result != "SUCCESS":
        raise HTTPException(
            status_code=receipt.http_status,
            detail=json.loads(receipt.response_json),
        )
    return receipt


def _reject_cross_domain_legacy_key_reuse(
    session: Session,
    *,
    operation_key: str,
    target_type: str,
) -> None:
    owners: set[str] = set()
    if session.scalar(
        select(DocumentApprovalMutationReceipt.id).where(
            DocumentApprovalMutationReceipt.mutation_key == operation_key
        )
    ) is not None:
        owners.add("document_approval")
    if session.scalar(
        select(DocumentMutationReceipt.id).where(
            DocumentMutationReceipt.mutation_key == operation_key
        )
    ) is not None:
        owners.add("document")
    if session.scalar(
        select(FieldCommentReviewMutationReceipt.id).where(
            FieldCommentReviewMutationReceipt.mutation_key == operation_key
        )
    ) is not None:
        owners.add("field_comment")
    if session.scalar(
        select(ReportMutationReceipt.id).where(
            ReportMutationReceipt.mutation_key == operation_key
        )
    ) is not None:
        owners.add("report")
    if session.scalar(
        select(WorkSequenceMutationReceipt.id).where(
            WorkSequenceMutationReceipt.mutation_key == operation_key
        )
    ) is not None:
        owners.add("work_sequence_board")
    if not owners:
        return
    if len(owners) == 1 and target_type in owners:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "IDEMPOTENCY_KEY_REUSED",
            "message": "The operation key is already used by a legacy domain receipt.",
        },
    )


def record_common_mutation_result(
    session: Session,
    *,
    operation_key: str,
    intent_hash: str,
    event_type: str,
    trace: MutationTrace,
    target_type: str,
    target_id: str,
    target_version_id: str | None,
    target_revision: int | None,
    reason: str | None,
    before_hash: str | None,
    after_hash: str | None,
    result: str,
    result_code: str,
    http_status: int,
    response_detail: Any,
    domain_receipt_type: str | None = None,
    domain_receipt_id: str | None = None,
    domain_audit_type: str | None = None,
    domain_audit_id: str | None = None,
    approval_status: str = "NOT_REQUIRED",
    approved_by: str | None = None,
    approval_reference: str | None = None,
) -> SyncMutationReceipt:
    event = _new_event(
        event_type=event_type,
        trace=trace,
        target_type=target_type,
        target_id=target_id,
        target_version_id=target_version_id,
        target_revision=target_revision,
        reason=reason,
        before_hash=before_hash,
        after_hash=after_hash,
        result=result,
        result_code=result_code,
        http_status=http_status,
        safe_payload={
            "operationKey": operation_key,
            "receiptSchema": "sync-mutation-receipt-v1",
        },
        domain_audit_type=domain_audit_type,
        domain_audit_id=domain_audit_id,
        approval_status=approval_status,
        approved_by=approved_by,
        approval_reference=approval_reference,
    )
    session.add(event)
    session.flush()
    receipt = SyncMutationReceipt(
        receipt_id=f"mrcpt_{uuid4().hex}",
        operation_key=operation_key,
        intent_hash_sha256=intent_hash,
        event_id=event.event_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        result=result,
        result_code=result_code,
        http_status=http_status,
        response_json=json.dumps(
            _safe_response_detail(response_detail),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        domain_receipt_type=domain_receipt_type,
        domain_receipt_id=domain_receipt_id,
    )
    session.add(receipt)
    session.flush()
    return receipt


def record_common_mutation_failure(
    session: Session,
    *,
    operation_key: str | None,
    intent_hash: str,
    event_type: str,
    trace: MutationTrace,
    target_type: str,
    target_id: str,
    target_version_id: str | None,
    target_revision: int | None,
    reason: str | None,
    error: HTTPException,
) -> None:
    if operation_key is None:
        return
    session.rollback()
    existing = session.scalar(
        select(SyncMutationReceipt).where(
            SyncMutationReceipt.operation_key == operation_key
        )
    )
    detail = _exception_detail(error)
    error.detail = detail
    result = "CONFLICT" if error.status_code == status.HTTP_409_CONFLICT else "REJECTED"
    detail_code = detail.get("code") if isinstance(detail, dict) else None
    result_code = str(detail_code or f"HTTP_{error.status_code}")[:80]
    if existing is not None:
        if (
            existing.intent_hash_sha256 == intent_hash
            and existing.event_type == event_type
            and existing.target_type == target_type
            and existing.target_id == target_id
        ):
            return
        session.add(
            _new_event(
                event_type=event_type,
                trace=trace,
                target_type=target_type,
                target_id=target_id,
                target_version_id=target_version_id,
                target_revision=target_revision,
                reason=reason,
                before_hash=None,
                after_hash=None,
                result="CONFLICT",
                result_code="IDEMPOTENCY_KEY_REUSED",
                http_status=status.HTTP_409_CONFLICT,
                safe_payload={
                    "operationKey": operation_key,
                    "existingReceiptId": existing.receipt_id,
                },
            )
        )
        session.commit()
        return
    record_common_mutation_result(
        session,
        operation_key=operation_key,
        intent_hash=intent_hash,
        event_type=event_type,
        trace=trace,
        target_type=target_type,
        target_id=target_id,
        target_version_id=target_version_id,
        target_revision=target_revision,
        reason=reason,
        before_hash=None,
        after_hash=None,
        result=result,
        result_code=result_code,
        http_status=error.status_code,
        response_detail=detail,
    )
    session.commit()


def record_common_audit_event(
    session: Session,
    *,
    event_type: str,
    trace: MutationTrace,
    target_type: str,
    target_id: str,
    target_version_id: str | None,
    reason: str | None,
    result_code: str,
    http_status: int,
    safe_payload: dict[str, Any],
    domain_audit_type: str | None = None,
    domain_audit_id: str | None = None,
) -> AuditEventEnvelope:
    event = _new_event(
        event_type=event_type,
        trace=trace,
        target_type=target_type,
        target_id=target_id,
        target_version_id=target_version_id,
        target_revision=None,
        reason=reason,
        before_hash=None,
        after_hash=None,
        result="SUCCESS",
        result_code=result_code,
        http_status=http_status,
        safe_payload=safe_payload,
        domain_audit_type=domain_audit_type,
        domain_audit_id=domain_audit_id,
    )
    session.add(event)
    session.flush()
    return event


def _new_event(
    *,
    event_type: str,
    trace: MutationTrace,
    target_type: str,
    target_id: str,
    target_version_id: str | None,
    target_revision: int | None,
    reason: str | None,
    before_hash: str | None,
    after_hash: str | None,
    result: str,
    result_code: str,
    http_status: int,
    safe_payload: dict[str, Any],
    domain_audit_type: str | None = None,
    domain_audit_id: str | None = None,
    approval_status: str = "NOT_REQUIRED",
    approved_by: str | None = None,
    approval_reference: str | None = None,
) -> AuditEventEnvelope:
    return AuditEventEnvelope(
        event_id=f"aevt_{uuid4().hex}",
        schema_version=1,
        event_type=event_type,
        actor_id=trace.actor_id,
        actor_role=trace.actor_role,
        session_id=trace.session_id,
        device_id=trace.device_id,
        target_type=target_type,
        target_id=target_id,
        target_version_id=target_version_id,
        target_revision=target_revision,
        reason=_redact_sensitive_text(reason),
        approval_status=approval_status,
        approved_by=approved_by,
        approval_reference=approval_reference,
        before_hash_sha256=before_hash,
        after_hash_sha256=after_hash,
        result=result,
        result_code=result_code,
        http_status=http_status,
        run_id=trace.run_id,
        correlation_id=trace.correlation_id,
        domain_audit_type=domain_audit_type,
        domain_audit_id=domain_audit_id,
        safe_payload_json=json.dumps(
            safe_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _safe_response_detail(detail: Any) -> Any:
    if not isinstance(detail, dict):
        return _redact_sensitive_text(str(detail)) or "Mutation rejected."
    allowed = {
        "schemaVersion",
        "code",
        "conflictKind",
        "message",
        "documentId",
        "expectedRevision",
        "currentRevision",
        "currentStatus",
        "currentLatestVersionId",
        "currentPublishedVersionId",
        "serverValue",
        "authoritativeSnapshot",
        "localRequest",
        "baseSnapshotHash",
        "allowedActions",
        "autoMergeAllowed",
        "sourcePreserved",
        "retryPolicy",
        "autoMerge",
        "userChoice",
        "expectedIntentHash",
        "requestIntentHash",
        "expectedFileHash",
        "actualFileHash",
        "existingFileHash",
        "requestFileHash",
        "expectedPublishedVersionId",
        "expectedLatestVersionId",
        "targetId",
        "targetVersionId",
        "targetRevision",
    }
    return {
        key: _safe_response_value(value)
        for key, value in detail.items()
        if key in allowed
    }


def _safe_response_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_response_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_response_value(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_sensitive_text(str(value))


def _exception_detail(error: HTTPException) -> Any:
    if isinstance(error.detail, dict):
        return _safe_response_detail(error.detail)
    return _redact_sensitive_text(str(error.detail)) or "Mutation rejected."


def _redact_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()[:1000]
    cleaned = _SECRET_PATTERN.sub(r"\1=[REDACTED]", cleaned)
    cleaned = _WINDOWS_ABSOLUTE_PATH.sub("[LOCAL_PATH_REDACTED]", cleaned)
    cleaned = _UNIX_ABSOLUTE_PATH.sub("[LOCAL_PATH_REDACTED]", cleaned)
    return cleaned or None


def _clean_header(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:100] or None
