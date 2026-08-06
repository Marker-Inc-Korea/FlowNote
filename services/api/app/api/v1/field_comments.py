from __future__ import annotations

from datetime import datetime
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (
    FieldCommentAnalyzeUser,
    FieldCommentCreateUser,
    get_current_user,
)
from app.core.config import Settings, get_settings
from app.core.storage import UploadTooLargeError
from app.core.storage import resolve_storage_root, store_upload_file_at
from app.db.models import (
    ActivityHistory,
    FieldComment,
    FieldCommentAttachment,
    FieldCommentReviewMutationReceipt,
    FileObject,
    WorkSequenceBoard,
    WorkSequenceItem,
)
from app.db.session import get_db_session
from app.services.mutation_receipts import (
    canonical_hash,
    mutation_trace,
    record_common_mutation_failure,
    sanitize_audit_text,
)
from app.api.v1.work_sequence_field_views import (
    _approved_field_user,
    _published_document,
    _visible_items,
)
from app.api.v1.field_comment_contracts import (
    COMMENT_TYPES,
    INPUT_MODES,
    FieldCommentAttachmentResponse,
    FieldCommentBulkReviewItemResponse,
    FieldCommentBulkReviewRequest,
    FieldCommentBulkReviewResponse,
    FieldCommentBulkReviewV2Request,
    FieldCommentCreateRequest,
    FieldCommentResponse,
    FieldCommentReviewRequest,
)
from app.api.v1.field_comment_queries import (
    document_field_comments_router as field_comment_query_document_router,
    router as field_comment_query_router,
)
from app.services.field_comment_attachment_service import (
    _attachment_response,
    _clean_attachment_type,
    _delete_stored_file,
    _validate_attachment_file,
)
from app.services.field_comment_query_service import _field_comment_response
from app.services.field_comment_review_service import (
    _apply_field_comment_review_mutation,
    _apply_review_change,
    _bulk_failure,
    _bulk_item_review_request,
    _claim_review_revision,
    _preview_review_change,
    _review_idempotent_response,
    _review_intent_hash,
    bulk_review_outcome,
)
from app.services.field_comment_support import (
    _clean_idempotency_key,
    _clean_optional,
    _effective_status,
    _new_public_id,
    _source_hash,
    _validate_choice,
    _validate_target,
)


router = APIRouter(prefix="/field-comments", tags=["field-comments"], dependencies=[Depends(get_current_user)])
document_field_comments_router = APIRouter(
    prefix="/documents",
    tags=["field-comments"],
    dependencies=[Depends(get_current_user)],
)


def _work_sequence_source_intent(
    request: FieldCommentCreateRequest,
    current_user: FieldCommentCreateUser,
) -> dict[str, object]:
    return {
        "serverScope": request.server_scope,
        "customerScope": current_user.customer_scope,
        "siteScope": current_user.site_scope,
        "userId": current_user.user_id,
        "deviceId": request.device_id,
        "sourceType": request.source_type,
        "sourceId": request.source_id,
        "sourceRevision": request.source_revision,
        "documentId": request.document_id,
        "documentVersionId": request.document_version_id,
        "workRecordId": request.work_record_id,
        "rawContent": request.raw_content,
        "inputMode": request.input_mode,
        "signalLevel": request.signal_level,
    }


def _validate_work_sequence_source(
    session: Session,
    request: FieldCommentCreateRequest,
    current_user: FieldCommentCreateUser,
) -> str | None:
    if request.source_type is None:
        return None
    _approved_field_user(session, current_user)
    if request.device_id != current_user.device_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "DEVICE_NOT_APPROVED", "message": "원천 기록 단말이 현재 승인 세션과 다릅니다."},
        )
    item = session.scalar(select(WorkSequenceItem).where(WorkSequenceItem.item_id == request.source_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Work sequence source item not found.")
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == item.board_id))
    if board is None or board.board_revision != request.source_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORK_SEQUENCE_REVISION_CHANGED",
                "message": "기록을 시작한 뒤 작업순서가 바뀌었습니다. 현재 항목을 다시 확인하세요.",
                "currentRevision": board.board_revision if board is not None else None,
            },
        )
    if not any(row.item_id == item.item_id for row in _visible_items(session, current_user, board.board_id)):
        raise HTTPException(
            status_code=404,
            detail={"code": "WORK_SEQUENCE_NOT_VISIBLE", "message": "현재 역할·채널에서 원천 항목을 찾을 수 없습니다."},
        )
    document_access, published = _published_document(session, item.document_id)
    if document_access != "AVAILABLE" or published is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SOURCE_DOCUMENT_NOT_PUBLISHED",
                "message": "연결 문서가 더 이상 공개 상태가 아닙니다. 입력은 단말에 보존하고 관리자에게 문의하세요.",
            },
        )
    if request.document_id != published.document_id or request.document_version_id != published.version_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SOURCE_DOCUMENT_CHANGED",
                "message": "작업순서에 연결된 공개 문서가 바뀌었습니다. 현재 문서를 다시 확인하세요.",
            },
        )
    return canonical_hash(_work_sequence_source_intent(request, current_user))


def _requested_work_sequence_intent(
    request: FieldCommentCreateRequest,
    current_user: FieldCommentCreateUser,
) -> str | None:
    values = (request.source_type, request.source_id, request.source_revision)
    if all(value is None for value in values):
        return None
    if request.source_type != "WORK_SEQUENCE_ITEM" or request.source_id is None or request.source_revision is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "WORK_SEQUENCE_SOURCE_INCOMPLETE",
                "message": "작업순서 원천 종류, ID와 revision을 함께 보내야 합니다.",
            },
        )
    if request.entry_source.strip() != "android_field_terminal":
        raise HTTPException(status_code=422, detail="WORK_SEQUENCE_ITEM source requires Android field entry.")
    if not request.server_scope:
        raise HTTPException(status_code=422, detail="serverScope is required for Android work-sequence source.")
    computed = canonical_hash(_work_sequence_source_intent(request, current_user))
    if (request.intent_hash_sha256 or "").lower() != computed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INTENT_HASH_MISMATCH",
                "message": "단말에 고정한 작업순서 원천 hash가 서버 검증값과 다릅니다.",
            },
        )
    return computed

@router.post("", response_model=FieldCommentResponse, status_code=status.HTTP_201_CREATED)
def create_field_comment(
    request: FieldCommentCreateRequest,
    current_user: FieldCommentCreateUser,
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    request.document_id = _clean_optional(request.document_id)
    request.document_version_id = _clean_optional(request.document_version_id)
    request.structure_item_id = _clean_optional(request.structure_item_id)
    request.work_record_id = _clean_optional(request.work_record_id)
    request.source_type = _clean_optional(request.source_type)
    request.source_id = _clean_optional(request.source_id)
    request.server_scope = _clean_optional(request.server_scope)
    request.raw_content = request.raw_content.strip()
    request.idempotency_key = _clean_idempotency_key(request.idempotency_key)
    _validate_choice(request.comment_type, COMMENT_TYPES, "commentType")
    _validate_choice(request.input_mode, INPUT_MODES, "inputMode")
    intent_hash = _requested_work_sequence_intent(request, current_user)
    is_proxy_entry = request.input_mode == "admin_proxy" or request.entry_source.strip() == "admin_proxy"
    if is_proxy_entry and not (_clean_optional(request.reported_by) or _clean_optional(request.operator_id)):
        raise HTTPException(
            status_code=422,
            detail="admin_proxy requires reportedBy or operatorId so the actual reporter/operator is distinct from the entering account.",
        )

    if request.idempotency_key is not None:
        existing = session.scalar(
            select(FieldComment).where(FieldComment.idempotency_key == request.idempotency_key)
        )
        if existing is not None:
            if intent_hash is not None and existing.intent_hash_sha256 != intent_hash:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_KEY_REUSED",
                        "message": "같은 FieldComment 멱등키가 다른 작업순서 원천에 사용되었습니다.",
                    },
                )
            return _field_comment_response(existing)

    _validate_target(session, request)
    validated_intent_hash = _validate_work_sequence_source(session, request, current_user)
    if validated_intent_hash != intent_hash:
        raise HTTPException(status_code=409, detail="Work-sequence source intent changed during validation.")

    note = FieldComment(
        comment_id=_new_public_id("comment"),
        idempotency_key=request.idempotency_key,
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        structure_item_id=request.structure_item_id,
        work_record_id=request.work_record_id,
        source_type=request.source_type,
        source_id=request.source_id,
        source_revision=request.source_revision,
        server_scope=request.server_scope,
        intent_hash_sha256=intent_hash,
        comment_type=request.comment_type,
        input_mode=request.input_mode,
        signal_level=_clean_optional(request.signal_level),
        template_id=_clean_optional(request.template_id),
        raw_content=request.raw_content,
        author_id=_clean_optional(request.author_id) or current_user.user_id,
        reported_by=_clean_optional(request.reported_by) if is_proxy_entry else (_clean_optional(request.reported_by) or current_user.display_name),
        operator_id=_clean_optional(request.operator_id),
        entry_source=request.entry_source.strip() or "field_user",
        device_id=_clean_optional(request.device_id),
        location_code=_clean_optional(request.location_code),
        category=_clean_optional(request.category),
        priority=request.priority,
        status="NEW",
    )
    session.add(note)
    session.flush()
    if note.source_type == "WORK_SEQUENCE_ITEM":
        session.add(ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="field_comment.work_sequence_source_linked",
            actor_id=current_user.user_id,
            target_type="field_comment",
            target_id=note.comment_id,
            target_title=note.comment_id,
            message="FieldComment를 Android 작업순서 원천과 고정 연결했습니다.",
            after_value=json.dumps({
                "source_type": note.source_type,
                "source_id": note.source_id,
                "source_revision": note.source_revision,
                "document_id": note.document_id,
                "document_version_id": note.document_version_id,
                "server_scope": note.server_scope,
                "intent_hash_sha256": note.intent_hash_sha256,
                "device_id": note.device_id,
            }, ensure_ascii=False, sort_keys=True),
            change_reason="Android 작업순서에서 현장 기록 시작",
        ))
    if is_proxy_entry:
        session.add(ActivityHistory(
            history_id=_new_public_id("hist"),
            event_type="field_comment.proxy_created",
            actor_id=current_user.user_id,
            target_type="field_comment",
            target_id=note.comment_id,
            target_title=note.comment_id,
            message="관리자 대리 입력: 입력자와 실제 전달자/작업자를 분리 기록",
            after_value=json.dumps({
                "entered_by": current_user.user_id,
                "reported_by": note.reported_by,
                "operator_id": note.operator_id,
                "entry_source": note.entry_source,
                "source_hash_sha256": _source_hash(note),
            }, ensure_ascii=False, sort_keys=True),
            change_reason="관리자 대리 입력 원천 생성",
        ))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment could not be saved because of a database constraint.",
        ) from exc
    session.refresh(note)
    return _field_comment_response(note)


@router.post(
    "/{comment_id}/attachments",
    response_model=FieldCommentAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_field_comment_attachment(
    comment_id: str,
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db_session)],
    attachment_type: Annotated[str | None, Form(alias="attachmentType")] = None,
    caption: Annotated[str | None, Form()] = None,
    captured_at: Annotated[datetime | None, Form(alias="capturedAt")] = None,
    created_by: Annotated[str | None, Form(alias="createdBy")] = None,
    idempotency_key: Annotated[str | None, Form(alias="idempotencyKey")] = None,
    parent_comment_id: Annotated[str | None, Form(alias="parentCommentId")] = None,
    file_sha256: Annotated[str | None, Form(alias="fileSha256")] = None,
    app_settings: Annotated[Settings, Depends(get_settings)] = None,
) -> FieldCommentAttachmentResponse:
    if parent_comment_id is not None and parent_comment_id.strip() != comment_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "ATTACHMENT_PARENT_MISMATCH", "message": "첨부 부모 FieldComment가 요청 경로와 다릅니다."},
        )
    expected_hash = _clean_optional(file_sha256)
    if expected_hash is not None and (len(expected_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_hash)):
        raise HTTPException(status_code=422, detail="fileSha256 must be a 64-character SHA-256 hex value.")
    comment_exists = session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id))
    if comment_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field comment not found.")

    idempotency_key = _clean_idempotency_key(idempotency_key)
    if idempotency_key is not None:
        existing = session.scalar(
            select(FieldCommentAttachment).where(
                FieldCommentAttachment.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            if existing.comment_id != comment_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotencyKey is already used by another field comment.",
                )
            existing_file = session.get(FileObject, existing.file_object_id)
            if existing_file is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotent field comment attachment has no file object.",
                )
            if expected_hash is not None and (
                not existing_file.hash_sha256
                or existing_file.hash_sha256.lower() != expected_hash.lower()
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "같은 첨부 멱등키의 파일 SHA-256이 다릅니다."},
                )
            return _attachment_response(existing, existing_file)

    _validate_attachment_file(file)
    storage_root = resolve_storage_root(app_settings.storage_root)
    try:
        stored = await store_upload_file_at(
            file,
            storage_root=storage_root,
            path_parts=("field-comments", comment_id, "attachments"),
            max_size_bytes=app_settings.field_comment_attachment_max_bytes,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Attachment file is too large.",
        ) from exc
    if expected_hash is not None and stored.hash_sha256.lower() != expected_hash.lower():
        _delete_stored_file(storage_root, stored.storage_key)
        raise HTTPException(
            status_code=409,
            detail={"code": "ATTACHMENT_FILE_HASH_MISMATCH", "message": "업로드 파일 SHA-256이 클라이언트 값과 다릅니다."},
        )

    file_object = FileObject(
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        extension=stored.extension,
        mime_type=stored.mime_type,
        file_family=stored.file_family,
        size_bytes=stored.size_bytes,
        hash_sha256=stored.hash_sha256,
    )
    session.add(file_object)
    session.flush()

    attachment = FieldCommentAttachment(
        attachment_id=_new_public_id("att"),
        idempotency_key=idempotency_key,
        comment_id=comment_id,
        file_object_id=file_object.id,
        attachment_type=_clean_attachment_type(attachment_type, stored.extension, stored.mime_type),
        caption=_clean_optional(caption),
        captured_at=captured_at,
        created_by=_clean_optional(created_by),
    )
    session.add(attachment)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _delete_stored_file(storage_root, stored.storage_key)
        if idempotency_key is not None:
            existing = session.scalar(
                select(FieldCommentAttachment).where(
                    FieldCommentAttachment.idempotency_key == idempotency_key
                )
            )
            if existing is not None and existing.comment_id == comment_id:
                existing_file = session.get(FileObject, existing.file_object_id)
                if existing_file is not None:
                    return _attachment_response(existing, existing_file)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Field comment attachment could not be saved because of a database constraint.",
        ) from exc
    session.refresh(attachment)
    return _attachment_response(attachment, file_object)


@router.post("/bulk-review", response_model=list[FieldCommentResponse])
def bulk_review_field_comments(
    request: FieldCommentBulkReviewRequest,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[FieldCommentResponse]:
    comment_ids = list(dict.fromkeys(_clean_optional(item) for item in request.comment_ids))
    if any(item is None for item in comment_ids):
        raise HTTPException(status_code=422, detail="commentIds cannot contain blank values.")
    notes = session.scalars(select(FieldComment).where(FieldComment.comment_id.in_(comment_ids))).all()
    by_id = {note.comment_id: note for note in notes}
    missing = [item for item in comment_ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Field comments not found: {', '.join(missing)}")
    ordered = [by_id[item] for item in comment_ids]
    for note in ordered:
        _claim_review_revision(session, note, note.review_revision)
        _apply_review_change(
            session,
            note,
            request,
            current_user.user_id,
            current_user.role,
            app_settings.field_comment_independent_review_required,
        )
    try:
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bulk FieldComment review could not be saved.") from exc
    return [_field_comment_response(note) for note in ordered]


@router.post("/bulk-review/preview", response_model=FieldCommentBulkReviewResponse)
def preview_bulk_review_field_comments(
    request: FieldCommentBulkReviewV2Request,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentBulkReviewResponse:
    results: list[FieldCommentBulkReviewItemResponse] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for item in request.items:
        cleaned_id = item.comment_id.strip()
        review_request = _bulk_item_review_request(request, item)
        failure: tuple[str, str] | None = None
        note = session.scalar(select(FieldComment).where(FieldComment.comment_id == cleaned_id))
        if cleaned_id in seen_ids:
            failure = ("DUPLICATE_COMMENT_ID", "같은 일괄 요청에서 FieldComment를 중복 선택할 수 없습니다.")
        elif item.mutation_key in seen_keys:
            failure = ("DUPLICATE_MUTATION_KEY", "각 항목에는 서로 다른 mutation key가 필요합니다.")
        elif note is None:
            failure = ("FIELD_COMMENT_NOT_FOUND", "FieldComment를 찾을 수 없습니다.")
        else:
            try:
                replay = _review_idempotent_response(
                    session,
                    cleaned_id,
                    item.mutation_key,
                    _review_intent_hash(cleaned_id, review_request),
                )
                if replay is None:
                    _preview_review_change(
                        session,
                        note,
                        review_request,
                        current_user.user_id,
                        current_user.role,
                        app_settings.field_comment_independent_review_required,
                    )
            except HTTPException as exc:
                failure = _bulk_failure(exc)
        seen_ids.add(cleaned_id)
        seen_keys.add(item.mutation_key)
        results.append(FieldCommentBulkReviewItemResponse(
            comment_id=cleaned_id,
            allowed=failure is None,
            from_status=_effective_status(note) if note is not None else None,
            target_status=request.status,
            failure_code=failure[0] if failure else None,
            failure_reason=failure[1] if failure else None,
            review_revision=note.review_revision if note is not None else None,
            receipt=item.mutation_key,
        ))
    failures = sum(not result.allowed for result in results)
    return FieldCommentBulkReviewResponse(
        requested_count=len(results),
        success_count=0,
        failure_count=failures,
        items=results,
    )


@router.post("/bulk-review/execute", response_model=FieldCommentBulkReviewResponse)
def execute_bulk_review_field_comments(
    request: FieldCommentBulkReviewV2Request,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentBulkReviewResponse:
    results: list[FieldCommentBulkReviewItemResponse] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for item in request.items:
        cleaned_id = item.comment_id.strip()
        review_request = _bulk_item_review_request(request, item)
        failure: tuple[str, str] | None = None
        response: FieldCommentResponse | None = None
        from_status: str | None = None
        try:
            if cleaned_id in seen_ids:
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_COMMENT_ID", "message": "같은 일괄 요청에서 FieldComment를 중복 선택할 수 없습니다."})
            if item.mutation_key in seen_keys:
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_MUTATION_KEY", "message": "각 항목에는 서로 다른 mutation key가 필요합니다."})
            intent_hash = _review_intent_hash(cleaned_id, review_request)
            response = _review_idempotent_response(session, cleaned_id, item.mutation_key, intent_hash)
            if response is None:
                note = session.scalar(select(FieldComment).where(FieldComment.comment_id == cleaned_id))
                if note is None:
                    raise HTTPException(status_code=404, detail={"code": "FIELD_COMMENT_NOT_FOUND", "message": "FieldComment를 찾을 수 없습니다."})
                from_status = _effective_status(note)
                _preview_review_change(
                    session,
                    note,
                    review_request,
                    current_user.user_id,
                    current_user.role,
                    app_settings.field_comment_independent_review_required,
                )
                _claim_review_revision(session, note, item.base_review_revision)
                _apply_review_change(
                    session,
                    note,
                    review_request,
                    current_user.user_id,
                    current_user.role,
                    app_settings.field_comment_independent_review_required,
                )
                session.flush()
                response = _field_comment_response(note)
                session.add(FieldCommentReviewMutationReceipt(
                    mutation_key=item.mutation_key,
                    intent_hash_sha256=intent_hash,
                    comment_id=cleaned_id,
                    review_revision=note.review_revision,
                    response_json=response.model_dump_json(),
                ))
                session.commit()
            else:
                from_status = response.status
        except HTTPException as exc:
            session.rollback()
            failure = _bulk_failure(exc)
        except (IntegrityError, ValueError) as exc:
            session.rollback()
            failure = ("FIELD_COMMENT_BULK_ITEM_CONSTRAINT", str(exc))
        seen_ids.add(cleaned_id)
        seen_keys.add(item.mutation_key)
        results.append(FieldCommentBulkReviewItemResponse(
            comment_id=cleaned_id,
            allowed=failure is None,
            success=failure is None,
            from_status=from_status,
            target_status=request.status,
            failure_code=failure[0] if failure else None,
            failure_reason=failure[1] if failure else None,
            review_revision=response.review_revision if response is not None else None,
            receipt=item.mutation_key,
            field_comment=response,
        ))
    success_count = sum(result.success is True for result in results)
    response = FieldCommentBulkReviewResponse(
        requested_count=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        items=results,
    )
    return bulk_review_outcome(response).value or response


@router.patch("/{comment_id}", response_model=FieldCommentResponse)
def review_field_comment(
    http_request: Request,
    comment_id: str,
    request: FieldCommentReviewRequest,
    current_user: FieldCommentAnalyzeUser,
    app_settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> FieldCommentResponse:
    mutation_key = _clean_idempotency_key(request.mutation_key)
    intent_hash = _review_intent_hash(comment_id, request)
    trace = mutation_trace(current_user, http_request)
    reason = sanitize_audit_text(request.transition_reason)
    try:
        return _apply_field_comment_review_mutation(
            comment_id=comment_id,
            request=request,
            current_user=current_user,
            app_settings=app_settings,
            session=session,
            mutation_key=mutation_key,
            intent_hash=intent_hash,
            trace=trace,
            reason=reason,
        )
    except HTTPException as error:
        record_common_mutation_failure(
            session,
            operation_key=mutation_key,
            intent_hash=intent_hash,
            event_type="field_comment.review_changed",
            trace=trace,
            target_type="field_comment",
            target_id=comment_id,
            target_version_id=None,
            target_revision=request.base_review_revision,
            reason=reason,
            error=error,
        )
        raise


field_comment_mutation_router = router
router = APIRouter()
router.include_router(field_comment_mutation_router)
router.include_router(field_comment_query_router)
document_field_comments_router = field_comment_query_document_router
