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
    AISearchCandidate,
    AISearchGroundTruthCase,
    AISearchGroundTruthProvenance,
    Document,
    DocumentVersion,
    FieldComment,
    FileObject,
    NotificationChannel,
    UserAccount,
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
    return document_id, version_id


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
            positives: dict[str, list[tuple[str, str]]] = {}
            negatives: dict[str, list[dict[str, str | None]]] = {}
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
            session.commit()
            rebuild_ai_search_candidates(session, load_sensitive_filter(session, settings))
            candidate_by_source = {
                (item.source_id, item.source_version_id): item
                for item in session.scalars(select(AISearchCandidate)).all()
            }
            now = datetime.now(timezone.utc)
            as_of = now + timedelta(minutes=5)
            db_scope = database_scope(database_url)
            created = 0
            for category in QUESTION_CATEGORIES:
                refs = [
                    _candidate_reference(candidate_by_source[source], "질문의 직접 공개 근거이며 hash와 version을 고정함")
                    for source in positives[category]
                ]
                for scenario in SCENARIO_TYPES:
                    for variant in (1, 2):
                        case_key = f"{DATASET_VERSION}-{category.lower()}-{scenario.lower()}-{variant:02d}"
                        if scenario == "NORMAL":
                            expected, excluded = [refs[variant - 1]], []
                            question = f"{DATASET_VERSION}-{category.lower()}-normal-{variant}"
                            outcome = "SUFFICIENT"
                        elif scenario == "CONFLICT":
                            expected, excluded = refs, []
                            question = f"{DATASET_VERSION}-{category.lower()}-conflict"
                            outcome = "SUFFICIENT"
                        else:
                            expected, excluded = [], [negatives[category][variant - 1]]
                            question = f"{DATASET_VERSION}-{category.lower()}-exclusion-{variant}"
                            outcome = "INSUFFICIENT_EVIDENCE"
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
                            existing.question = question
                            existing.expected_evidence_json = json.dumps(expected, ensure_ascii=False, sort_keys=True)
                            existing.excluded_evidence_json = json.dumps(excluded, ensure_ascii=False, sort_keys=True)
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
            return {"datasetVersion": DATASET_VERSION, "created": created, "total": len(cases), "databaseScope": db_scope}


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
