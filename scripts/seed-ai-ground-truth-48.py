#!/usr/bin/env python3
"""Create the deterministic, non-sensitive 48-case AI smoke ground-truth matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.db.init_db import hash_password_for_dev  # noqa: E402
from app.db.models import (  # noqa: E402
    ActivityHistory,
    AISearchCandidate,
    AISearchGroundTruthCase,
    AISearchGroundTruthProvenance,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    FileObject,
    NotificationChannel,
    Report,
    ReportSource,
    TagDefinition,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
)
from app.main import create_app  # noqa: E402
from app.services.ai_readiness import QUESTION_CATEGORIES, SCENARIO_TYPES, database_scope  # noqa: E402
from app.services.ai_provider_gate import load_sensitive_filter  # noqa: E402
from app.api.v1.ai_search import rebuild_ai_search_candidates  # noqa: E402


DATASET_VERSION = "smoke48-v1"
FIRST_APPROVER = "user-ai-gt-first"
SECOND_APPROVER = "user-ai-gt-second"
CATEGORY_LABELS = {
    "SAFETY": "안전",
    "QUALITY": "품질",
    "EQUIPMENT_ANOMALY": "설비 이상",
    "WORK_HOLD": "작업 보류",
    "REWORK": "재작업",
    "HANDOVER": "인수인계",
    "LATEST_PUBLISHED_DOCUMENT": "최신 공개 문서",
    "CONFLICTING_RECORDS": "상충 기록",
}
NEGATIVE_KINDS = (
    "SENSITIVE",
    "CUSTOMER_IDENTIFIER",
    "LOCAL_PATH",
    "CHANNEL_DENIED",
    "DELETED_DOCUMENT",
    "PRIVATE_DOCUMENT",
    "EXCLUDED_SOURCE",
    "ARCHIVED_SOURCE",
)
MATRIX_STATUSES = {
    ("NORMAL", 1): "ANALYZED",
    ("NORMAL", 2): "REVIEWED",
    ("CONFLICT", 1): "SELECTED",
    ("CONFLICT", 2): "SELECTED",
    ("EXCLUSION", 1): "EXCLUDED",
    ("EXCLUSION", 2): "EXCLUDED",
}
DOMAIN_TAGS = {
    "equipment": ("press-a", "프레스 A"),
    "item": ("housing-x", "하우징 X"),
    "process": ("alignment", "정렬 공정"),
    "error_type": ("alignment-delay", "정렬 지연"),
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ensure_user(session, user_id: str, username: str) -> None:
    if session.scalar(select(UserAccount.id).where(UserAccount.user_id == user_id)) is None:
        session.add(UserAccount(
            user_id=user_id,
            username=username,
            login_id=username,
            display_name=f"AI 기준자료 독립 승인자 {username[-1].upper()}",
            role="manager",
            password_hash=hash_password_for_dev("1234"),
            is_active=True,
            status="ACTIVE",
        ))


def _ensure_document(session, *, category: str, variant: int) -> tuple[str, str]:
    slug = category.lower()
    document_id = f"doc-{DATASET_VERSION}-{slug}-{variant}"
    version_id = f"ver-{DATASET_VERSION}-{slug}-{variant}"
    if session.scalar(select(Document.id).where(Document.document_id == document_id)) is not None:
        _ensure_document_domain_tags(session, document_id)
        return document_id, version_id
    common = f"{DATASET_VERSION}-{slug}-conflict"
    unique = f"{DATASET_VERSION}-{slug}-normal-{variant}"
    content = f"{CATEGORY_LABELS[category]} 비민감 시험 근거 {unique} {common}"
    file_object = FileObject(
        storage_key=f"ai-ground-truth/{DATASET_VERSION}/{slug}-{variant}.txt",
        original_filename=f"{slug}-{variant}.txt",
        extension=".txt",
        mime_type="text/plain",
        file_family="text",
        size_bytes=len(content.encode("utf-8")),
        hash_sha256=_hash(content),
    )
    session.add(file_object)
    session.flush()
    session.add(Document(
        document_id=document_id,
        title=f"{CATEGORY_LABELS[category]} 시험 공개 문서 {variant}",
        description=content,
        document_type="work_instruction",
        owner_id=FIRST_APPROVER,
        status="PUBLISHED",
        latest_version_id=version_id,
        published_version_id=version_id,
    ))
    session.add(DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        file_object_id=file_object.id,
        version_no=1,
        version_label="v1",
        change_reason=content,
        version_status="PUBLISHED",
        is_latest=True,
        is_published=True,
        created_by=FIRST_APPROVER,
    ))
    session.flush()
    _ensure_document_domain_tags(session, document_id)
    return document_id, version_id


def _ensure_document_domain_tags(session, document_id: str) -> None:
    for tag_type, (code, name) in DOMAIN_TAGS.items():
        tag_id = f"tag-{DATASET_VERSION}-{tag_type}-{code}"
        if session.scalar(select(TagDefinition.id).where(TagDefinition.tag_id == tag_id)) is None:
            session.add(TagDefinition(
                tag_id=tag_id,
                tag_type=tag_type,
                code=code,
                name=name,
                is_active=True,
            ))
            session.flush()
        if session.scalar(select(DocumentTag.id).where(
            DocumentTag.document_id == document_id,
            DocumentTag.tag_id == tag_id,
        )) is None:
            session.add(DocumentTag(document_id=document_id, tag_id=tag_id))
    marker_id = f"tag-{DATASET_VERSION}-readiness-track"
    if session.scalar(select(TagDefinition.id).where(TagDefinition.tag_id == marker_id)) is None:
        session.add(TagDefinition(
            tag_id=marker_id,
            tag_type="custom",
            code="smoke-regression",
            name="SMOKE_REGRESSION",
            is_active=True,
        ))
        session.flush()
    if session.scalar(select(DocumentTag.id).where(
        DocumentTag.document_id == document_id,
        DocumentTag.tag_id == marker_id,
    )) is None:
        session.add(DocumentTag(document_id=document_id, tag_id=marker_id))


def _field_comment_source_hash(comment: FieldComment) -> str:
    payload = {
        "comment_id": comment.comment_id,
        "document_id": comment.document_id,
        "document_version_id": comment.document_version_id,
        "structure_item_id": comment.structure_item_id,
        "work_record_id": comment.work_record_id,
        "comment_type": comment.comment_type,
        "input_mode": comment.input_mode,
        "signal_level": comment.signal_level,
        "template_id": comment.template_id,
        "raw_content": comment.raw_content,
        "author_id": comment.author_id,
        "reported_by": comment.reported_by,
        "operator_id": comment.operator_id,
        "entry_source": comment.entry_source,
        "device_id": comment.device_id,
        "location_code": comment.location_code,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }
    return _hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _ensure_matrix_comment(
    session, *, category: str, scenario: str, variant: int, document_id: str, version_id: str, now: datetime
) -> FieldComment:
    slug = category.lower()
    comment_id = f"comment-{DATASET_VERSION}-{slug}-{scenario.lower()}-{variant}"
    existing = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
    if existing is not None:
        _ensure_matrix_transition_audits(session, existing, scenario=scenario, variant=variant)
        return existing
    status = MATRIX_STATUSES[(scenario, variant)]
    token = f"{DATASET_VERSION}-{slug}-{scenario.lower()}-{variant}"
    conflict_token = f"{DATASET_VERSION}-{slug}-conflict"
    raw = f"{CATEGORY_LABELS[category]} {scenario} 회귀 원천 {token}"
    if scenario == "CONFLICT":
        raw = f"{raw} {conflict_token} 상충 주장 {variant}"
    normalized = f"정제된 {CATEGORY_LABELS[category]} 회귀 근거 {token}"
    analysis = f"{scenario} 정책에 따라 포함·제외·상충 표시를 검증한다. {conflict_token if scenario == 'CONFLICT' else token}"
    comment = FieldComment(
        comment_id=comment_id,
        idempotency_key=f"{DATASET_VERSION}:field-comment:{slug}:{scenario.lower()}:{variant}",
        document_id=document_id,
        document_version_id=version_id,
        comment_type="issue",
        input_mode="free_text",
        signal_level=("green", "yellow", "red")[(variant + list(SCENARIO_TYPES).index(scenario)) % 3],
        raw_content=raw,
        normalized_content=normalized,
        analysis_content=analysis,
        author_id=FIRST_APPROVER,
        reported_by="비민감 스모크 작업자",
        entry_source="field_user",
        location_code="line-a",
        category=category,
        status=status,
        analyzed_by=FIRST_APPROVER if status in {"ANALYZED", "REVIEWED", "SELECTED"} else None,
        reviewed_by=SECOND_APPROVER if status in {"REVIEWED", "SELECTED", "EXCLUDED"} else None,
        assigned_to=SECOND_APPROVER,
        review_due_at=now + timedelta(days=7),
        last_transition_reason=f"{DATASET_VERSION} {scenario} 회귀 계약의 승인 전이",
        analyzed_at=now if status in {"ANALYZED", "REVIEWED", "SELECTED"} else None,
        reviewed_at=now if status in {"REVIEWED", "SELECTED"} else None,
        selected_at=now if status == "SELECTED" else None,
        review_revision={"ANALYZED": 2, "REVIEWED": 3, "SELECTED": 4, "EXCLUDED": 2}[status],
    )
    session.add(comment)
    session.flush()
    _ensure_matrix_transition_audits(session, comment, scenario=scenario, variant=variant)
    return comment


def _ensure_matrix_transition_audits(
    session, comment: FieldComment, *, scenario: str, variant: int
) -> None:
    paths = {
        "ANALYZED": ("NEW", "ANALYZED"),
        "REVIEWED": ("NEW", "ANALYZED", "REVIEWED"),
        "SELECTED": ("NEW", "ANALYZED", "REVIEWED", "SELECTED"),
        "EXCLUDED": ("NEW", "EXCLUDED"),
    }
    path = paths[comment.status]
    source_hash = _field_comment_source_hash(comment)
    slug = (comment.category or "unknown").lower()
    for step, (before_status, after_status) in enumerate(zip(path, path[1:]), 1):
        history_id = f"hist-{DATASET_VERSION}-{slug}-{scenario.lower()}-{variant}-{step}"
        if session.scalar(select(ActivityHistory.id).where(ActivityHistory.history_id == history_id)) is not None:
            continue
        before = {
            "source_hash_sha256": source_hash,
            "status": before_status,
            "assigned_to": SECOND_APPROVER if step > 1 else None,
            "review_due_at": comment.review_due_at.isoformat() if step > 1 and comment.review_due_at else None,
            "review_revision": step,
        }
        after = {
            "source_hash_sha256": source_hash,
            "status": after_status,
            "assigned_to": SECOND_APPROVER,
            "review_due_at": comment.review_due_at.isoformat() if comment.review_due_at else None,
            "review_revision": step + 1,
        }
        session.add(ActivityHistory(
            history_id=history_id,
            event_type="field_comment.review_changed",
            actor_id=FIRST_APPROVER if after_status == "ANALYZED" else SECOND_APPROVER,
            target_type="field_comment",
            target_id=comment.comment_id,
            target_title=comment.comment_id,
            message=f"FieldComment 회귀 전이: {before_status} → {after_status}",
            before_value=json.dumps(before, ensure_ascii=False, sort_keys=True),
            after_value=json.dumps(after, ensure_ascii=False, sort_keys=True),
            change_reason=f"{DATASET_VERSION} 승인 전이 {before_status} → {after_status}",
        ))


def _ensure_work_history(session, *, category: str, variant: int, document_id: str) -> WorkSequenceChangeHistory:
    slug = category.lower()
    board_id = f"board-{DATASET_VERSION}-{slug}"
    item_id = f"item-{DATASET_VERSION}-{slug}-{variant}"
    change_id = f"change-{DATASET_VERSION}-{slug}-{variant}"
    board = session.scalar(select(WorkSequenceBoard).where(WorkSequenceBoard.board_id == board_id))
    if board is None:
        session.add(WorkSequenceBoard(
            board_id=board_id,
            title=f"{CATEGORY_LABELS[category]} 회귀 작업순서",
            description="BOM을 강제하지 않는 라인 작업순서 회귀 자료",
            line_code="line-a",
            board_date=datetime.now(timezone.utc).date(),
            status="ACTIVE",
            board_revision=3,
            created_by=FIRST_APPROVER,
        ))
        session.flush()
    if session.scalar(select(WorkSequenceItem.id).where(WorkSequenceItem.item_id == item_id)) is None:
        session.add(WorkSequenceItem(
            item_id=item_id,
            board_id=board_id,
            title=f"{CATEGORY_LABELS[category]} 확인 {variant}",
            description=f"{DATASET_VERSION}-{slug}-conflict",
            document_id=document_id,
            status="HOLD" if category == "WORK_HOLD" else "IN_PROGRESS",
            hold_reason="검토 근거 확인" if category == "WORK_HOLD" else None,
            sort_order=variant,
            assigned_to="line-a",
            created_by=FIRST_APPROVER,
        ))
        session.flush()
    history = session.scalar(select(WorkSequenceChangeHistory).where(
        WorkSequenceChangeHistory.change_id == change_id
    ))
    if history is None:
        history = WorkSequenceChangeHistory(
            change_id=change_id,
            mutation_key=f"{DATASET_VERSION}:work-sequence:{slug}:{variant}",
            board_revision=variant + 1,
            board_id=board_id,
            item_id=item_id,
            change_type="ITEM_STATUS_CHANGED",
            actor_id=FIRST_APPROVER,
            before_value="WAITING",
            after_value="HOLD" if category == "WORK_HOLD" else "IN_PROGRESS",
            change_reason=f"{DATASET_VERSION}-{slug}-conflict 작업순서 회귀 근거 {variant}",
        )
        session.add(history)
        session.flush()
    return history


def _hash_work_history(history: WorkSequenceChangeHistory) -> str:
    payload = {
        "change_id": history.change_id,
        "board_id": history.board_id,
        "item_id": history.item_id,
        "change_type": history.change_type,
        "actor_id": history.actor_id,
        "before_value": history.before_value,
        "after_value": history.after_value,
        "change_reason": history.change_reason,
        "created_at": history.created_at.isoformat() if history.created_at else None,
    }
    return _hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _ensure_report(
    session, *, category: str, variant: int, document_id: str, version_id: str,
    selected_comment: FieldComment, history: WorkSequenceChangeHistory,
) -> Report:
    slug = category.lower()
    report_id = f"report-{DATASET_VERSION}-{slug}-{variant}"
    report = session.scalar(select(Report).where(Report.report_id == report_id))
    if report is None:
        report = Report(
            idempotency_key=f"{DATASET_VERSION}:report:{slug}:{variant}",
            report_id=report_id,
            report_type="field_review",
            title=f"{CATEGORY_LABELS[category]} 복합 근거 회귀 보고서 {variant}",
            summary=f"{DATASET_VERSION}-{slug}-conflict 문서·FieldComment·작업순서 상충 근거",
            analysis_content="외부 provider 호출 없이 source hash와 역추적만 검증한다.",
            conclusion="상충 원천을 숨기지 않고 함께 표시한다.",
            status="APPROVED",
            ai_draft_used=False,
            created_by=FIRST_APPROVER,
            reviewed_by=SECOND_APPROVER,
            approved_by=SECOND_APPROVER,
        )
        session.add(report)
        session.flush()
    sources = (
        ("DOCUMENT", document_id, version_id, session.scalar(
            select(FileObject.hash_sha256).join(DocumentVersion, DocumentVersion.file_object_id == FileObject.id)
            .where(DocumentVersion.version_id == version_id)
        )),
        ("FIELD_COMMENT", selected_comment.comment_id, version_id, _field_comment_source_hash(selected_comment)),
        ("WORK_SEQUENCE_HISTORY", history.change_id, history.change_id, _hash_work_history(history)),
    )
    for index, (source_type, source_id, source_version_id, source_hash) in enumerate(sources, 1):
        if session.scalar(select(ReportSource.id).where(
            ReportSource.report_id == report_id,
            ReportSource.source_type == source_type,
            ReportSource.source_id == source_id,
            ReportSource.source_version_id == source_version_id,
        )) is None:
            session.add(ReportSource(
                report_id=report_id,
                source_type=source_type,
                source_id=source_id,
                source_version_id=source_version_id,
                trace_id=f"trace-{DATASET_VERSION}-{slug}-{variant}-{index}",
                source_hash_sha256=source_hash,
                relation_type="conflicting_evidence" if source_type != "DOCUMENT" else "published_baseline",
            ))
    session.flush()
    return report


def _negative_content(kind: str, token: str) -> str:
    return {
        "SENSITIVE": f"{token} password: synthetic-secret",
        "CUSTOMER_IDENTIFIER": f"{token} customer_id: synthetic-customer",
        "LOCAL_PATH": f"{token} /Users/example/private/input.txt",
        "CHANNEL_DENIED": f"{token} 권한 밖 채널 시험 근거",
        "EXCLUDED_SOURCE": f"{token} EXCLUDED 원천 시험 근거",
        "ARCHIVED_SOURCE": f"{token} 보관 원천 시험 근거",
    }[kind]


def _ensure_negative_source(
    session, *, category: str, variant: int, target_document_id: str, target_version_id: str
) -> dict[str, str | None]:
    kind = NEGATIVE_KINDS[(list(QUESTION_CATEGORIES).index(category) * 2 + variant - 1) % len(NEGATIVE_KINDS)]
    slug = category.lower()
    token = f"{DATASET_VERSION}-{slug}-exclusion-{variant}"
    if kind in {"DELETED_DOCUMENT", "PRIVATE_DOCUMENT"}:
        document_id = f"doc-{DATASET_VERSION}-negative-{slug}-{variant}"
        version_id = f"ver-{DATASET_VERSION}-negative-{slug}-{variant}"
        if session.scalar(select(Document.id).where(Document.document_id == document_id)) is None:
            content = f"{token} 삭제 또는 비공개 문서 시험 근거"
            file_object = FileObject(
                storage_key=f"ai-ground-truth/{DATASET_VERSION}/negative-{slug}-{variant}.txt",
                original_filename=f"negative-{slug}-{variant}.txt",
                extension=".txt",
                mime_type="text/plain",
                file_family="text",
                size_bytes=len(content.encode("utf-8")),
                hash_sha256=_hash(content),
            )
            session.add(file_object)
            session.flush()
            session.add(Document(
                document_id=document_id,
                title=f"비공개 시험 문서 {slug}-{variant}",
                description=content,
                document_type="work_instruction",
                owner_id=FIRST_APPROVER,
                status="DELETED" if kind == "DELETED_DOCUMENT" else "WORKING",
                latest_version_id=version_id,
            ))
            session.add(DocumentVersion(
                version_id=version_id,
                document_id=document_id,
                file_object_id=file_object.id,
                version_no=1,
                version_label="v1",
                change_reason=content,
                version_status="WORKING",
                is_latest=True,
                is_published=False,
                created_by=FIRST_APPROVER,
            ))
        return {
            "sourceType": "PUBLISHED_DOCUMENT_VERSION",
            "sourceId": document_id,
            "sourceVersionId": version_id,
            "contentHash": _hash(
                f"비공개 시험 문서 {slug}-{variant}\n"
                f"{token} 삭제 또는 비공개 문서 시험 근거\nv1\n"
                f"{token} 삭제 또는 비공개 문서 시험 근거"
            ),
            "exclusionReason": "document_version_not_published",
            "rationale": f"{kind} 원천은 공개 후보에서 제외되어야 함",
        }

    comment_id = f"comment-{DATASET_VERSION}-negative-{slug}-{variant}"
    content = _negative_content(kind, token)
    if session.scalar(select(FieldComment.id).where(FieldComment.comment_id == comment_id)) is None:
        status = "EXCLUDED" if kind == "EXCLUDED_SOURCE" else "ARCHIVED" if kind == "ARCHIVED_SOURCE" else "ANALYZED"
        session.add(FieldComment(
            comment_id=comment_id,
            document_id=target_document_id,
            document_version_id=target_version_id,
            comment_type="issue",
            input_mode="free_text",
            raw_content=content,
            normalized_content=content,
            author_id=FIRST_APPROVER,
            entry_source="field_user",
            status=status,
            analyzed_by=FIRST_APPROVER if status == "ANALYZED" else None,
        ))
        if kind == "CHANNEL_DENIED":
            session.add(NotificationChannel(
                channel_id=f"channel-{DATASET_VERSION}-{slug}-{variant}",
                name=f"권한 격리 시험 채널 {slug}-{variant}",
                channel_type="CUSTOM",
                source_type="FIELD_COMMENT",
                source_id=comment_id,
                status="ACTIVE",
                created_by=FIRST_APPROVER,
            ))
    reason = (
        "CHANNEL_ACCESS_DENIED" if kind == "CHANNEL_DENIED"
        else "field_comment_excluded_status" if kind in {"EXCLUDED_SOURCE", "ARCHIVED_SOURCE"}
        else "SOURCE_NOT_CANDIDATE"
    )
    return {
        "sourceType": "FIELD_COMMENT",
        "sourceId": comment_id,
        "sourceVersionId": None,
        "traceId": comment_id,
        "traceVersionId": None,
        "contentHash": _hash(f"{content}\n{content}"),
        "exclusionReason": reason,
        "rationale": f"{kind} 부정 원천은 후보·권한 정책에 따라 제외되어야 함",
    }


def _candidate_reference(candidate: AISearchCandidate, rationale: str) -> dict[str, str | None]:
    return {
        "candidateId": candidate.candidate_id,
        "sourceType": candidate.source_type,
        "sourceId": candidate.source_id,
        "sourceVersionId": candidate.source_version_id,
        "traceId": candidate.trace_id,
        "traceVersionId": candidate.trace_version_id,
        "contentHash": candidate.content_hash,
        "exclusionReason": None,
        "rationale": rationale,
    }


def _excluded_comment_reference(comment: FieldComment) -> dict[str, str | None]:
    content = "\n".join(filter(None, (
        comment.normalized_content,
        comment.raw_content,
        comment.analysis_content,
        comment.category,
        comment.signal_level,
    )))
    return {
        "candidateId": None,
        "sourceType": "FIELD_COMMENT",
        "sourceId": comment.comment_id,
        "sourceVersionId": comment.document_version_id,
        "traceId": comment.comment_id,
        "traceVersionId": comment.document_version_id,
        "contentHash": _hash(content),
        "exclusionReason": "field_comment_excluded_status",
        "rationale": "승인 전이로 EXCLUDED가 된 원천은 검색·보고서 후보에 노출되지 않아야 함",
    }


def seed(database_url: str) -> dict[str, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        test_database_url=database_url,
        storage_root=str(API_ROOT / "storage" / "ai-ground-truth-48"),
    )
    app = create_app(settings)
    with TestClient(app):
        database = app.state.database
        with database.session() as session:
            _ensure_user(session, FIRST_APPROVER, "ai-gt-first")
            _ensure_user(session, SECOND_APPROVER, "ai-gt-second")
            session.flush()
            now = datetime.now(timezone.utc)
            positives: dict[str, list[tuple[str, str]]] = {}
            negatives: dict[str, list[dict[str, str | None]]] = {}
            matrix_comments: dict[tuple[str, str, int], FieldComment] = {}
            histories: dict[tuple[str, int], WorkSequenceChangeHistory] = {}
            reports: dict[tuple[str, int], Report] = {}
            for category in QUESTION_CATEGORIES:
                positives[category] = [_ensure_document(session, category=category, variant=i) for i in (1, 2)]
                negatives[category] = [
                    _ensure_negative_source(
                        session,
                        category=category,
                        variant=i,
                        target_document_id=positives[category][i - 1][0],
                        target_version_id=positives[category][i - 1][1],
                    )
                    for i in (1, 2)
                ]
                for scenario in SCENARIO_TYPES:
                    for variant in (1, 2):
                        document_id, version_id = positives[category][variant - 1]
                        matrix_comments[(category, scenario, variant)] = _ensure_matrix_comment(
                            session,
                            category=category,
                            scenario=scenario,
                            variant=variant,
                            document_id=document_id,
                            version_id=version_id,
                            now=now,
                        )
                for variant in (1, 2):
                    document_id, version_id = positives[category][variant - 1]
                    histories[(category, variant)] = _ensure_work_history(
                        session, category=category, variant=variant, document_id=document_id
                    )
                    reports[(category, variant)] = _ensure_report(
                        session,
                        category=category,
                        variant=variant,
                        document_id=document_id,
                        version_id=version_id,
                        selected_comment=matrix_comments[(category, "CONFLICT", variant)],
                        history=histories[(category, variant)],
                    )
            session.commit()
            rebuild_ai_search_candidates(session, load_sensitive_filter(session, settings))
            candidate_by_source = {
                (item.source_id, item.source_version_id): item
                for item in session.scalars(select(AISearchCandidate)).all()
            }
            report_candidates = {}
            for item in session.scalars(select(AISearchCandidate).where(
                AISearchCandidate.source_type == "REPORT_SOURCE"
            )).all():
                metadata = json.loads(item.metadata_json or "{}")
                report_candidates.setdefault(metadata.get("report_id"), []).append(item)
            for candidates in report_candidates.values():
                candidates.sort(key=lambda item: item.candidate_id)
            as_of = now + timedelta(minutes=5)
            db_scope = database_scope(database_url)
            created = 0
            positive_reference_index = 0
            expected_source_type_counts = {
                source_type: 0 for source_type in (
                    "PUBLISHED_DOCUMENT_VERSION",
                    "FIELD_COMMENT",
                    "WORK_SEQUENCE_HISTORY",
                    "REPORT_SOURCE",
                )
            }
            for category in QUESTION_CATEGORIES:
                for scenario in SCENARIO_TYPES:
                    for variant in (1, 2):
                        case_key = f"{DATASET_VERSION}-{category.lower()}-{scenario.lower()}-{variant:02d}"
                        comment = matrix_comments[(category, scenario, variant)]
                        report = reports[(category, variant)]
                        source_pool = []
                        if scenario != "EXCLUSION":
                            source_pool = [
                                _candidate_reference(
                                    candidate_by_source[positives[category][variant - 1]],
                                    "현재 공개 문서 version과 content hash를 고정한 문서 근거",
                                ),
                                _candidate_reference(
                                    candidate_by_source[(comment.comment_id, comment.document_version_id)],
                                    "검토 상태와 원천 hash를 고정한 FieldComment 근거",
                                ),
                                _candidate_reference(
                                    candidate_by_source[(histories[(category, variant)].change_id, None)],
                                    "작업순서 상태 전이 시점과 hash를 고정한 이력 근거",
                                ),
                                _candidate_reference(
                                    report_candidates[report.report_id][0],
                                    "승인 보고서에서 원천 ID·version·hash로 역추적되는 보고서 근거",
                                ),
                            ]
                        if scenario == "NORMAL":
                            expected = [source_pool[positive_reference_index % len(source_pool)]]
                            positive_reference_index += 1
                            excluded = []
                            question = (
                                f"{DATASET_VERSION}-{category.lower()}-normal-{variant}"
                                if expected[0]["sourceType"] == "FIELD_COMMENT"
                                else f"{DATASET_VERSION}-{category.lower()}-conflict"
                            )
                            outcome = "SUFFICIENT"
                        elif scenario == "CONFLICT":
                            expected = [
                                source_pool[positive_reference_index % len(source_pool)],
                                source_pool[(positive_reference_index + 1) % len(source_pool)],
                            ]
                            positive_reference_index += 2
                            excluded = []
                            question = f"{DATASET_VERSION}-{category.lower()}-conflict"
                            outcome = "SUFFICIENT"
                        else:
                            expected = []
                            excluded = [
                                negatives[category][variant - 1],
                                _excluded_comment_reference(matrix_comments[(category, scenario, variant)]),
                            ]
                            question = f"{DATASET_VERSION}-{category.lower()}-exclusion-{variant}"
                            outcome = "INSUFFICIENT_EVIDENCE"
                        for reference in expected:
                            expected_source_type_counts[str(reference["sourceType"])] += 1
                        snapshot = {
                            "caseKey": case_key,
                            "customerScope": settings.ai_customer_scope,
                            "siteScope": settings.ai_site_scope,
                            "lineScope": None,
                            "databaseScope": db_scope,
                            "asOf": as_of.isoformat(),
                            "expectedEvidence": expected,
                            "expectedExcluded": excluded,
                        }
                        existing = session.scalar(select(AISearchGroundTruthCase).where(
                            AISearchGroundTruthCase.customer_scope == settings.ai_customer_scope,
                            AISearchGroundTruthCase.site_scope == settings.ai_site_scope,
                            AISearchGroundTruthCase.case_key == case_key,
                        ))
                        if existing is not None:
                            existing.category = category
                            existing.scenario_type = scenario
                            existing.question = question
                            existing.expected_outcome = outcome
                            existing.expected_evidence_json = json.dumps(expected, ensure_ascii=False, sort_keys=True)
                            existing.excluded_evidence_json = json.dumps(excluded, ensure_ascii=False, sort_keys=True)
                            existing.allowed_rank_min = 1
                            existing.allowed_rank_max = 20
                            existing.as_of = as_of
                            provenance = session.scalar(select(AISearchGroundTruthProvenance).where(
                                AISearchGroundTruthProvenance.ground_truth_case_id == existing.ground_truth_case_id
                            ))
                            if provenance is not None:
                                provenance.source_snapshot_hash = _hash(json.dumps(
                                    snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                                ))
                            continue
                        public_id = f"aigt_{_hash(case_key)[:32]}"
                        session.add(AISearchGroundTruthCase(
                            ground_truth_case_id=public_id,
                            case_key=case_key,
                            customer_scope=settings.ai_customer_scope,
                            site_scope=settings.ai_site_scope,
                            line_scope=None,
                            database_scope=db_scope,
                            category=category,
                            scenario_type=scenario,
                            question=question,
                            expected_outcome=outcome,
                            expected_evidence_json=json.dumps(expected, ensure_ascii=False, sort_keys=True),
                            excluded_evidence_json=json.dumps(excluded, ensure_ascii=False, sort_keys=True),
                            allowed_rank_min=1,
                            allowed_rank_max=20,
                            as_of=as_of,
                            approved_by=FIRST_APPROVER,
                            approved_at=now,
                            is_active=True,
                        ))
                        session.add(AISearchGroundTruthProvenance(
                            provenance_id=f"aigtprov_{_hash(case_key)[:28]}",
                            ground_truth_case_id=public_id,
                            data_classification="TEST",
                            readiness_track="SMOKE_REGRESSION",
                            provenance_note="비민감·합성 회귀 자료이며 실제 현장 준비도에는 포함하지 않음",
                            source_snapshot_hash=_hash(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
                            contains_sensitive_data=False,
                            approval_status="APPROVED",
                            first_approved_by=FIRST_APPROVER,
                            first_approved_at=now,
                            second_approved_by=SECOND_APPROVER,
                            second_approved_at=now,
                        ))
                        created += 1
            session.commit()
            cases = session.scalars(select(AISearchGroundTruthCase).where(
                AISearchGroundTruthCase.case_key.like(f"{DATASET_VERSION}-%")
            )).all()
            status_counts = {
                status: sum(comment.status == status for comment in matrix_comments.values())
                for status in ("ANALYZED", "REVIEWED", "SELECTED", "EXCLUDED")
            }
            return {
                "datasetVersion": DATASET_VERSION,
                "readinessTrack": "SMOKE_REGRESSION",
                "created": created,
                "total": len(cases),
                "databaseScope": db_scope,
                "fieldCommentStatusCounts": status_counts,
                "reportCount": len(reports),
                "reportSourceTypes": ["DOCUMENT", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY"],
                "expectedSourceTypeCounts": expected_source_type_counts,
                "domainTagAxes": sorted(DOMAIN_TAGS),
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=f"sqlite:///{(API_ROOT / 'data' / 'flownote.test.sqlite3').as_posix()}",
        help="Target test database. Never point this at a customer or production database.",
    )
    args = parser.parse_args()
    if "test" not in args.database_url.lower():
        parser.error("database URL must visibly identify a test database")
    result = seed(args.database_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["total"] == 48 else 1


if __name__ == "__main__":
    raise SystemExit(main())
