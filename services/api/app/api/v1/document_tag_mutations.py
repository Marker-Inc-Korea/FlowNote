from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.document_support import (
    DocumentResponse,
    DocumentTagMutationRequest,
    claim_revision,
    clean_idempotency_key,
    clean_tags,
    conflict,
    document_mutation_intent_hash,
    document_authority_hash,
    document_mutation_replay,
    document_response,
    document_tag_intent_hash,
    document_tags_at_revision,
    record_activity,
    record_document_tag_revision,
    replace_document_tags,
    require_live_document,
    store_document_mutation_receipt,
    tag_response,
)
from app.core.auth import AuthenticatedUser
from app.db.models import Document, TagDefinition
from app.services.mutation_receipts import MutationTrace


def apply_document_tag_mutation(
    session: Session,
    *,
    document_id: str,
    payload: DocumentTagMutationRequest | list[str],
    current_user: AuthenticatedUser,
    trace: MutationTrace,
    legacy_base_revision: int | None,
    legacy_mutation_key: str | None,
) -> DocumentResponse:
    _lock_document_tag_mutation(session, document_id)
    if isinstance(payload, list):
        return _replace_tags_for_legacy_client(
            session,
            document_id=document_id,
            tags=payload,
            current_user=current_user,
            trace=trace,
            base_revision=legacy_base_revision,
            mutation_key=legacy_mutation_key,
        )

    added_tags = clean_tags(payload.added_tags)
    removed_tags = clean_tags(payload.removed_tags)
    mutation_key = clean_idempotency_key(payload.mutation_key)
    base_revision = payload.base_revision
    intent_hash = document_tag_intent_hash(
        document_id, base_revision, added_tags, removed_tags
    )
    if payload.intent_hash.lower() != intent_hash:
        raise conflict(
            "TAG_INTENT_HASH_MISMATCH",
            "The document tag mutation intentHash does not match its canonical intent.",
            expected_revision=base_revision,
            extra={"expectedIntentHash": intent_hash, "requestIntentHash": payload.intent_hash},
        )
    replay = document_mutation_replay(
        session, mutation_key, "MERGE_TAGS", document_id, intent_hash
    )
    if replay is not None:
        session.commit()
        return replay
    document = require_live_document(session, document_id)
    before_hash = document_authority_hash(session, document)
    if base_revision > document.revision:
        raise conflict(
            "FUTURE_REVISION",
            "baseRevision is newer than the authoritative server revision.",
            document=document,
            expected_revision=base_revision,
        )

    added_by_code = {_normalize(tag): tag for tag in added_tags}
    removed_by_code = {_normalize(tag): tag for tag in removed_tags}
    invalid_overlap = sorted(set(added_by_code) & set(removed_by_code))
    if invalid_overlap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "TAG_INTENT_INVALID",
                "message": "The same tag cannot be added and removed in one mutation.",
                "tags": invalid_overlap,
            },
        )

    current_tags = tag_response(session, document_id)
    current_by_code = {_normalize(tag): tag for tag in current_tags}
    base_tags = document_tags_at_revision(session, document_id, base_revision)
    if base_tags is None and base_revision == document.revision:
        base_tags = current_tags
    if base_tags is None:
        raise conflict(
            "TAG_BASE_UNAVAILABLE",
            "The server has no tag snapshot for baseRevision; automatic merge is unsafe.",
            document=document,
            expected_revision=base_revision,
            extra={
                "serverValue": {"revision": document.revision, "tags": current_tags},
                "localRequest": payload.model_dump(by_alias=True),
                "autoMerge": {"addedTags": [], "removedTags": []},
                "userChoice": [{"field": "tags", "reason": "BASE_SNAPSHOT_MISSING"}],
            },
        )
    base_by_code = {_normalize(tag): tag for tag in base_tags}

    requested_codes = set(added_by_code) | set(removed_by_code)
    definitions = (
        session.scalars(
            select(TagDefinition).where(
                TagDefinition.tag_type == "custom",
                TagDefinition.code.in_(requested_codes),
            )
        ).all()
        if requested_codes
        else []
    )
    definitions_by_code = {definition.code: definition for definition in definitions}
    unavailable: list[dict[str, str]] = []
    for code in sorted(requested_codes):
        definition = definitions_by_code.get(code)
        if definition is not None and not definition.is_active:
            unavailable.append({"tag": definition.name, "reason": "INACTIVE"})
        elif definition is None and code in base_by_code:
            unavailable.append({"tag": base_by_code[code], "reason": "DELETED"})

    server_added = set(current_by_code) - set(base_by_code)
    server_removed = set(base_by_code) - set(current_by_code)
    conflicting_codes = sorted(
        (set(added_by_code) & server_removed) | (set(removed_by_code) & server_added)
    )
    safe_added = sorted(set(added_by_code) - set(conflicting_codes))
    safe_removed = sorted(set(removed_by_code) - set(conflicting_codes))
    if conflicting_codes or unavailable:
        server_response = document_response(session, document)
        latest_hash = (
            server_response.latest_version.file.hash_sha256
            if server_response.latest_version is not None
            else None
        )
        choices = [
            {"field": "tags", "tag": code, "reason": "OPPOSING_TAG_CHANGE"}
            for code in conflicting_codes
        ] + [{"field": "tags", **item} for item in unavailable]
        raise conflict(
            "TAG_MERGE_CONFLICT" if conflicting_codes else "TAG_UNAVAILABLE",
            "The tag mutation contains changes that require administrator resolution.",
            document=document,
            expected_revision=base_revision,
            extra={
                "serverValue": {
                    "revision": document.revision,
                    "tags": current_tags,
                    "status": document.status,
                    "latestVersionId": document.latest_version_id,
                    "publishedVersionId": document.published_version_id,
                    "latestVersionHash": latest_hash,
                },
                "localRequest": payload.model_dump(by_alias=True),
                "autoMerge": {
                    "addedTags": [added_by_code[code] for code in safe_added],
                    "removedTags": [removed_by_code[code] for code in safe_removed],
                },
                "userChoice": choices,
            },
        )

    merged_by_code = dict(current_by_code)
    merged_by_code.update(added_by_code)
    for code in removed_by_code:
        merged_by_code.pop(code, None)
    merged_tags = [merged_by_code[code] for code in sorted(merged_by_code)]
    if set(merged_by_code) == set(current_by_code):
        response = document_response(session, document)
        store_document_mutation_receipt(
            session,
            mutation_key=mutation_key,
            mutation_type="MERGE_TAGS",
            intent_hash=intent_hash,
            document=document,
            response=response,
            actor_id=current_user.user_id,
            trace=trace,
            before_hash=before_hash,
        )
        session.commit()
        return response

    claim_revision(session, document, document.revision)
    replace_document_tags(session, document_id, merged_tags)
    record_document_tag_revision(
        session, document_id, document.revision, merged_tags, mutation_key
    )
    record_activity(
        session,
        event_type="document.tags_merged",
        actor_id=current_user.user_id,
        target_type="document",
        target_id=document.document_id,
        target_title=document.title,
        message="Document tag additions and removals were merged against the server authority.",
        before_value=",".join(current_tags),
        after_value=",".join(merged_tags),
    )
    session.flush()
    response = document_response(session, document)
    store_document_mutation_receipt(
        session,
        mutation_key=mutation_key,
        mutation_type="MERGE_TAGS",
        intent_hash=intent_hash,
        document=document,
        response=response,
        actor_id=current_user.user_id,
        trace=trace,
        before_hash=before_hash,
    )
    session.commit()
    return response


def _replace_tags_for_legacy_client(
    session: Session,
    *,
    document_id: str,
    tags: list[str],
    current_user: AuthenticatedUser,
    trace: MutationTrace,
    base_revision: int | None,
    mutation_key: str | None,
) -> DocumentResponse:
    if base_revision is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="baseRevision is required for the legacy tag replacement request.",
        )
    cleaned_tags = clean_tags(tags)
    mutation_key = clean_idempotency_key(mutation_key)
    intent_hash = document_mutation_intent_hash(
        "REPLACE_TAGS",
        document_id,
        {"baseRevision": base_revision, "tags": cleaned_tags},
    )
    replay = document_mutation_replay(
        session, mutation_key, "REPLACE_TAGS", document_id, intent_hash
    )
    if replay is not None:
        session.commit()
        return replay
    document = require_live_document(session, document_id)
    before_hash = document_authority_hash(session, document)
    claim_revision(session, document, base_revision)
    before_tags = tag_response(session, document_id)
    replace_document_tags(session, document_id, cleaned_tags)
    record_document_tag_revision(
        session, document_id, document.revision, cleaned_tags, mutation_key
    )
    record_activity(
        session,
        event_type="document.tags_changed",
        actor_id=current_user.user_id,
        target_type="document",
        target_id=document.document_id,
        target_title=document.title,
        message="Document tags were replaced by a legacy client.",
        before_value=",".join(before_tags),
        after_value=",".join(cleaned_tags),
    )
    session.flush()
    response = document_response(session, document)
    store_document_mutation_receipt(
        session,
        mutation_key=mutation_key,
        mutation_type="REPLACE_TAGS",
        intent_hash=intent_hash,
        document=document,
        response=response,
        actor_id=current_user.user_id,
        trace=trace,
        before_hash=before_hash,
    )
    session.commit()
    return response


def _normalize(value: str) -> str:
    return "-".join(value.strip().lower().split())


def _lock_document_tag_mutation(session: Session, document_id: str) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        if session.in_transaction():
            session.rollback()
        session.execute(text("BEGIN IMMEDIATE"))
        return
    session.execute(
        select(Document.id)
        .where(Document.document_id == document_id)
        .with_for_update()
    )
