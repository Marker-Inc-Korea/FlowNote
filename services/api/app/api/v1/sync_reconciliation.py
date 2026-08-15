from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, require_roles
from app.core.config import Settings, get_settings
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Document,
    DocumentAccessLog,
    DocumentMutationReceipt,
    DocumentVersion,
    FieldComment,
    FieldCommentAttachment,
    FileObject,
    ReconciliationItem,
    ReconciliationRun,
    Report,
    ServerIdentity,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/sync", tags=["sync-reconciliation"])
SyncAdministrator = Annotated[
    AuthenticatedUser, Depends(require_roles("admin", "system-admin"))
]


class ReconciliationInventoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    client_item_id: str = Field(alias="clientItemId", min_length=1, max_length=120)
    entity_type: str = Field(alias="entityType", min_length=1, max_length=40)
    local_id: str = Field(alias="localId", min_length=1, max_length=64)
    local_version_no: int = Field(default=0, alias="localVersionNo", ge=0)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1, max_length=160)
    local_hash_sha256: str | None = Field(default=None, alias="localHashSha256", max_length=64)
    previous_server_document_id: str | None = Field(
        default=None, alias="previousServerDocumentId", max_length=64
    )
    previous_server_version_id: str | None = Field(
        default=None, alias="previousServerVersionId", max_length=64
    )


class ReconciliationRunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    client_id: str = Field(alias="clientId", min_length=1, max_length=100)
    previous_server_instance_id: str | None = Field(
        default=None, alias="previousServerInstanceId", max_length=64
    )
    previous_server_epoch: int | None = Field(default=None, alias="previousServerEpoch", ge=1)
    trigger_reason: str = Field(alias="triggerReason", min_length=1, max_length=40)
    client_cursor: int = Field(default=0, alias="clientCursor", ge=0)
    items: list[ReconciliationInventoryItem] = Field(max_length=10000)


class ReconciliationResolution(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    item_id: str = Field(alias="itemId", min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)


class ReconciliationApplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    approval_reason: str = Field(alias="approvalReason", min_length=1, max_length=1000)
    resolutions: list[ReconciliationResolution] = Field(max_length=10000)


def _identity(session: Session) -> ServerIdentity:
    identity = session.get(ServerIdentity, 1)
    if identity is None:
        raise HTTPException(status_code=503, detail="서버 식별 정보가 초기화되지 않았습니다.")
    return identity


RESTORE_FAULT_CODES = {
    "partial_restore",
    "old_database_new_files",
    "missing_file",
    "wrong_server_epoch",
}


def manifest_payload(session: Session, settings: Settings) -> dict[str, object]:
    identity = _identity(session)
    server_cursor = session.scalar(select(func.max(ChannelMessage.id))) or 0
    payload: dict[str, object] = {
        "server_instance_id": identity.server_instance_id,
        "server_epoch": identity.server_epoch,
        "schema_contract": identity.schema_contract,
        "api_contract_min": identity.api_contract_min,
        "api_contract_max": identity.api_contract_max,
        "server_cursor": server_cursor,
    }
    fault_code = settings.restore_fault_code.strip().lower()
    if not fault_code:
        return payload
    if fault_code not in RESTORE_FAULT_CODES:
        raise HTTPException(
            status_code=503,
            detail="FLOWNOTE_RESTORE_FAULT_CODE가 지원하는 복구 장애 코드가 아닙니다.",
        )
    required = {
        "restore_pilot_run_id": settings.restore_pilot_run_id,
        "restore_backup_set_id": settings.restore_backup_set_id,
        "restore_approval_id": settings.restore_approval_id,
        "restore_responsible_owner": settings.restore_responsible_owner,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise HTTPException(
            status_code=503,
            detail="복구 장애 manifest 필수 식별자가 없습니다: " + ", ".join(missing),
        )
    payload.update(
        {
            "restore_fault_code": fault_code,
            "restore_block_reason": settings.restore_block_reason.strip()
            or "복구 장애 실기 run의 관리자 재결합 승인이 필요합니다.",
            "restore_pilot_run_id": settings.restore_pilot_run_id.strip(),
            "restore_backup_set_id": settings.restore_backup_set_id.strip(),
            "restore_approval_id": settings.restore_approval_id.strip(),
            "restore_responsible_owner": settings.restore_responsible_owner.strip(),
            "safe_convergence": False,
        }
    )
    return payload


def _classify(
    session: Session, item: ReconciliationInventoryItem
) -> tuple[str, str, str | None, str | None, int | None, str | None, str]:
    entity_type = item.entity_type.strip().lower()
    server_document_id = None
    server_version_id = None
    server_revision = None
    server_hash = None

    if entity_type == "document":
        document = session.scalar(
            select(Document).where(Document.idempotency_key == item.idempotency_key)
        )
        if document is None:
            return "ABSENT", "REQUEUE", None, None, None, None, "동일 idempotency key가 서버에 없습니다."
        version_row = session.execute(
            select(DocumentVersion, FileObject)
            .join(FileObject, FileObject.id == DocumentVersion.file_object_id)
            .where(DocumentVersion.document_id == document.document_id)
            .order_by(DocumentVersion.version_no.desc())
        ).first()
        server_document_id = document.document_id
        server_revision = document.revision
        if version_row:
            server_version_id = version_row[0].version_id
            server_hash = version_row[1].hash_sha256
    elif entity_type == "document_version":
        version_row = session.execute(
            select(DocumentVersion, FileObject, Document)
            .join(FileObject, FileObject.id == DocumentVersion.file_object_id)
            .join(Document, Document.document_id == DocumentVersion.document_id)
            .where(DocumentVersion.idempotency_key == item.idempotency_key)
        ).first()
        if version_row is None:
            return "ABSENT", "REQUEUE", None, None, None, None, "동일 idempotency key가 서버에 없습니다."
        version, file_object, document = version_row
        server_document_id = document.document_id
        server_version_id = version.version_id
        server_revision = document.revision
        server_hash = file_object.hash_sha256
    elif entity_type in {"document_publish", "document_status", "document_tags"}:
        receipt = session.scalar(
            select(DocumentMutationReceipt).where(
                DocumentMutationReceipt.mutation_key == item.idempotency_key
            )
        )
        if receipt is None:
            return "ABSENT", "REQUEUE", None, None, None, None, "동일 mutation key receipt가 서버에 없습니다."
        response = json.loads(receipt.response_json)
        server_document_id = receipt.document_id
        server_version_id = response.get("latest_version_id")
        server_revision = receipt.applied_revision
        latest_version = response.get("latest_version") or {}
        server_hash = (latest_version.get("file") or {}).get("hash_sha256")
    else:
        model_and_id = {
            "field_comment": (FieldComment, FieldComment.comment_id),
            "field_comment_attachment": (FieldCommentAttachment, FieldCommentAttachment.attachment_id),
            "document_access_log": (DocumentAccessLog, DocumentAccessLog.id),
            "report": (Report, Report.report_id),
        }.get(entity_type)
        if model_and_id is None:
            return "ABSENT", "REQUEUE", None, None, None, None, "서버에 독립 원천을 만들지 않는 후속 작업이므로 원천 재결합 뒤 같은 key로 재실행합니다."
        model, id_column = model_and_id
        found = session.scalar(select(model).where(model.idempotency_key == item.idempotency_key))
        if found is None:
            return "ABSENT", "REQUEUE", None, None, None, None, "동일 idempotency key가 서버에 없습니다."
        if entity_type == "field_comment":
            server_document_id = found.document_id
            server_version_id = found.comment_id
        elif entity_type == "field_comment_attachment":
            server_version_id = found.attachment_id
        elif entity_type == "report":
            server_document_id = found.generated_document_id
            server_version_id = found.report_id
            server_revision = found.report_revision
            server_hash = found.content_hash_sha256
        else:
            server_version_id = str(found.id)

    if item.local_hash_sha256 and not server_hash:
        return "DIVERGED", "CONFLICT", server_document_id, server_version_id, server_revision, server_hash, "서버 원천에 비교할 hash가 없습니다."
    if item.local_hash_sha256 and server_hash and item.local_hash_sha256.lower() != server_hash.lower():
        return "DIVERGED", "CONFLICT", server_document_id, server_version_id, server_revision, server_hash, "동일 idempotency key의 payload/hash가 다릅니다."
    return "CONFIRMED", "REBOUND", server_document_id, server_version_id, server_revision, server_hash, "동일 key/hash 원천을 확인했습니다."


def _item_payload(item: ReconciliationItem) -> dict[str, object | None]:
    return {
        "item_id": item.item_id,
        "client_item_id": item.client_item_id,
        "entity_type": item.entity_type,
        "local_id": item.local_id,
        "local_version_no": item.local_version_no,
        "idempotency_key": item.idempotency_key,
        "local_hash_sha256": item.local_hash_sha256,
        "verdict": item.verdict,
        "proposed_action": item.proposed_action,
        "server_document_id": item.server_document_id,
        "server_version_id": item.server_version_id,
        "server_revision": item.server_revision,
        "server_hash_sha256": item.server_hash_sha256,
        "details": item.details,
        "resolution_action": item.resolution_action,
        "resolution_status": item.resolution_status,
        "resolution_reason": item.resolution_reason,
        "resolved_by": item.resolved_by,
        "resolved_at": item.resolved_at,
    }


def _run_payload(session: Session, run: ReconciliationRun) -> dict[str, object]:
    items = list(
        session.scalars(
            select(ReconciliationItem)
            .where(ReconciliationItem.run_id == run.run_id)
            .order_by(ReconciliationItem.id)
        )
    )
    return {
        "run_id": run.run_id,
        "client_id": run.client_id,
        "server_instance_id": run.server_instance_id,
        "server_epoch": run.server_epoch,
        "trigger_reason": run.trigger_reason,
        "status": run.status,
        "client_cursor": run.client_cursor,
        "server_cursor": run.server_cursor,
        "created_by": run.created_by,
        "approved_by": run.approved_by,
        "approval_reason": run.approval_reason,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "items": [_item_payload(item) for item in items],
    }


@router.get("/manifest")
def get_sync_manifest(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    return manifest_payload(session, settings)


@router.post("/reconciliation-runs", status_code=status.HTTP_201_CREATED)
def create_reconciliation_run(
    payload: ReconciliationRunCreateRequest,
    current_user: SyncAdministrator,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    identity = _identity(session)
    run = ReconciliationRun(
        run_id=f"recon-{uuid4().hex}",
        client_id=payload.client_id.strip(),
        server_instance_id=identity.server_instance_id,
        server_epoch=identity.server_epoch,
        previous_server_instance_id=payload.previous_server_instance_id,
        previous_server_epoch=payload.previous_server_epoch,
        trigger_reason=payload.trigger_reason.strip().upper(),
        status="REVIEW_REQUIRED",
        client_cursor=payload.client_cursor,
        server_cursor=session.scalar(select(func.max(ChannelMessage.id))) or 0,
        created_by=current_user.user_id,
    )
    session.add(run)
    session.flush()
    for inventory in payload.items:
        verdict, action, document_id, version_id, revision, server_hash, details = _classify(
            session, inventory
        )
        session.add(
            ReconciliationItem(
                item_id=f"recon-item-{uuid4().hex}",
                run_id=run.run_id,
                client_item_id=inventory.client_item_id,
                entity_type=inventory.entity_type.strip().lower(),
                local_id=inventory.local_id,
                local_version_no=inventory.local_version_no,
                idempotency_key=inventory.idempotency_key,
                local_hash_sha256=inventory.local_hash_sha256,
                previous_server_document_id=inventory.previous_server_document_id,
                previous_server_version_id=inventory.previous_server_version_id,
                verdict=verdict,
                proposed_action=action,
                server_document_id=document_id,
                server_version_id=version_id,
                server_revision=revision,
                server_hash_sha256=server_hash,
                details=details,
            )
        )
    session.commit()
    session.refresh(run)
    return _run_payload(session, run)


@router.get("/reconciliation-runs/{run_id}")
def get_reconciliation_run(
    run_id: str,
    _current_user: SyncAdministrator,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.run_id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Reconciliation run을 찾을 수 없습니다.")
    return _run_payload(session, run)


@router.post("/reconciliation-runs/{run_id}/apply")
def approve_reconciliation_run(
    run_id: str,
    payload: ReconciliationApplyRequest,
    current_user: SyncAdministrator,
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.run_id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Reconciliation run을 찾을 수 없습니다.")
    if run.status == "APPLIED":
        return _run_payload(session, run)
    if run.status != "REVIEW_REQUIRED":
        raise HTTPException(status_code=409, detail="적용할 수 없는 reconciliation run입니다.")
    items = {
        item.item_id: item
        for item in session.scalars(
            select(ReconciliationItem).where(ReconciliationItem.run_id == run_id)
        )
    }
    resolutions = {resolution.item_id: resolution for resolution in payload.resolutions}
    if set(items) != set(resolutions):
        raise HTTPException(status_code=422, detail="모든 reconciliation 항목의 승인 조치가 필요합니다.")
    now = datetime.now(timezone.utc)
    for item_id, item in items.items():
        resolution = resolutions[item_id]
        action = resolution.action.strip().upper()
        if action != item.proposed_action:
            raise HTTPException(status_code=409, detail=f"{item_id} 판정과 승인 조치가 일치하지 않습니다.")
        item.resolution_action = action
        item.resolution_status = {
            "REBOUND": "REBOUND_CONFIRMED",
            "REQUEUE": "REQUEUED_FOR_RETRY",
            "CONFLICT": "APPROVED_CONFLICT",
        }[action]
        item.resolution_reason = resolution.reason.strip()
        item.resolved_by = current_user.user_id
        item.resolved_at = now
    run.status = "APPLIED"
    run.approved_by = current_user.user_id
    run.approval_reason = payload.approval_reason.strip()
    run.completed_at = now
    session.add(
        ActivityHistory(
            history_id=f"history-{uuid4().hex}",
            event_type="sync.reconciliation.approved",
            actor_id=current_user.user_id,
            target_type="reconciliation_run",
            target_id=run.run_id,
            target_title=run.client_id,
            message="모든 reconciliation 항목을 감사하고 클라이언트 적용을 승인했습니다.",
            change_reason=run.approval_reason,
        )
    )
    session.commit()
    session.refresh(run)
    return _run_payload(session, run)


@router.post("/server-epoch/increment")
def increment_server_epoch(
    current_user: SyncAdministrator,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, object]:
    identity = _identity(session)
    manifest_payload(session, settings)
    identity.server_epoch += 1
    session.add(
        ActivityHistory(
            history_id=f"history-{uuid4().hex}",
            event_type="sync.server_epoch.incremented",
            actor_id=current_user.user_id,
            target_type="server_identity",
            target_id=identity.server_instance_id,
            target_title="서버 epoch",
            message=f"복구 경계 확인을 위해 서버 epoch를 {identity.server_epoch}로 증가시켰습니다.",
        )
    )
    session.commit()
    return manifest_payload(session, settings)
