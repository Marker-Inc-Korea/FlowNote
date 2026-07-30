from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    AISearchCandidate,
    AISearchEvaluationCase,
    AISearchEvaluationRun,
    Document,
    DocumentTag,
    DocumentVersion,
    FieldComment,
    FileObject,
    Report,
    ReportSource,
    TagDefinition,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    NotificationChannel,
    UserAccount,
)
from app.db.init_db import hash_password_for_dev
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "ai-search-tests"


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
    )
    return TestClient(create_app(app_settings))


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_ai_search_sources(client: TestClient) -> dict[str, str]:
    suffix = uuid4().hex
    ground_truth_token = f"groundtruth-{suffix}"
    published_document_id = f"doc-ai-published-{suffix}"
    published_version_id = f"ver-ai-published-{suffix}"
    draft_document_id = f"doc-ai-draft-{suffix}"
    draft_version_id = f"ver-ai-draft-{suffix}"
    analyzed_comment_id = f"comment-ai-analyzed-{suffix}"
    selected_comment_id = f"comment-ai-selected-{suffix}"
    new_comment_id = f"comment-ai-new-{suffix}"
    mes_comment_id = f"comment-ai-mes-{suffix}"
    archived_comment_id = f"comment-ai-archived-{suffix}"
    empty_comment_id = f"comment-ai-empty-{suffix}"
    board_id = f"wseqboard-ai-{suffix}"
    history_id = f"wseqhist-ai-{suffix}"
    empty_history_id = f"wseqhist-ai-empty-{suffix}"
    report_id = f"report-ai-{suffix}"
    archived_report_id = f"report-ai-archived-{suffix}"
    blank_report_id = f"report-ai-blank-source-{suffix}"
    missing_origin_report_id = f"report-ai-missing-source-{suffix}"
    deleted_origin_report_id = f"report-ai-deleted-source-{suffix}"
    excluded_comment_report_id = f"report-ai-excluded-comment-source-{suffix}"
    deleted_document_id = f"doc-ai-deleted-{suffix}"

    with client.app.state.database.session() as session:
        published_file = FileObject(
            storage_key=f"ai-search/{suffix}/published.txt",
            original_filename="published.txt",
            extension=".txt",
            mime_type="text/plain",
            file_family="text",
            size_bytes=31,
            hash_sha256="1" * 64,
        )
        draft_file = FileObject(
            storage_key=f"ai-search/{suffix}/draft.txt",
            original_filename="draft.txt",
            extension=".txt",
            mime_type="text/plain",
            file_family="text",
            size_bytes=17,
            hash_sha256="2" * 64,
        )
        session.add_all([published_file, draft_file])
        session.flush()

        session.add(
            Document(
                document_id=published_document_id,
                title=f"AI search published source {suffix[:8]}",
                description=f"Published document version should be indexed as evidence. {ground_truth_token}",
                document_type="work_instruction",
                owner_id="user-admin",
                status="PUBLISHED",
                latest_version_id=published_version_id,
                published_version_id=published_version_id,
            )
        )
        session.add(
            Document(
                document_id=deleted_document_id,
                title=f"AI search deleted source {suffix[:8]}",
                document_type="work_instruction",
                owner_id="user-admin",
                status="DELETED",
                deleted_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            DocumentVersion(
                version_id=published_version_id,
                document_id=published_document_id,
                file_object_id=published_file.id,
                version_no=1,
                version_label="v1",
                change_reason="Published version approved for field use.",
                version_status="PUBLISHED",
                is_latest=True,
                is_published=True,
                created_by="user-admin",
            )
        )
        session.add(
            Document(
                document_id=draft_document_id,
                title=f"AI search draft excluded {suffix[:8]}",
                document_type="work_instruction",
                owner_id="user-admin",
                status="WORKING",
                latest_version_id=draft_version_id,
            )
        )
        session.add(
            DocumentVersion(
                version_id=draft_version_id,
                document_id=draft_document_id,
                file_object_id=draft_file.id,
                version_no=1,
                version_label="v1",
                change_reason="Working version must not be indexed.",
                version_status="WORKING",
                is_latest=True,
                is_published=False,
                created_by="user-admin",
            )
        )
        session.add(
            FieldComment(
                comment_id=analyzed_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="issue",
                input_mode="free_text",
                raw_content=f"Analyzed field comment for evidence search. {ground_truth_token}",
                normalized_content="Manager normalized the field issue.",
                analysis_content="This is ready to support summary evidence.",
                author_id="user-admin",
                entry_source="field_user",
                status="ANALYZED",
                analyzed_by="user-admin",
            )
        )
        session.add(
            FieldComment(
                comment_id=selected_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="issue",
                input_mode="template_with_text",
                signal_level="red",
                raw_content=f"Selected field comment for report evidence. {ground_truth_token}",
                normalized_content="Manager selected the sensor reset issue.",
                analysis_content="This selected comment should remain traceable as AI evidence.",
                author_id="user-admin",
                entry_source="field_user",
                category="sensor-reset",
                status="SELECTED",
                reviewed_by="user-admin",
                analyzed_by="user-admin",
            )
        )
        session.add(
            FieldComment(
                comment_id=new_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="experience",
                input_mode="free_text",
                raw_content="New field comment remains raw but traceable.",
                author_id="user-admin",
                entry_source="field_user",
                status="NEW",
            )
        )
        session.add(
            FieldComment(
                comment_id=archived_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="issue",
                input_mode="free_text",
                raw_content="Archived field comment should be excluded.",
                author_id="user-admin",
                entry_source="field_user",
                status="ARCHIVED",
            )
        )
        session.add(
            FieldComment(
                comment_id=mes_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="issue",
                input_mode="mes_integration",
                raw_content="MES integration field comment must not seed AI search yet.",
                author_id="user-admin",
                entry_source="mes_integration",
                status="NEW",
            )
        )
        session.add(
            FieldComment(
                comment_id=empty_comment_id,
                document_id=published_document_id,
                document_version_id=published_version_id,
                comment_type="issue",
                input_mode="signal",
                signal_level="yellow",
                raw_content="",
                author_id="user-admin",
                entry_source="field_user",
                category="empty-content-marker",
                status="NEW",
            )
        )
        session.add(
            WorkSequenceBoard(
                board_id=board_id,
                title=f"AI search work board {suffix[:8]}",
                line_code="line-a",
                status="ACTIVE",
                board_revision=1,
                created_by="user-admin",
            )
        )
        session.add(
            WorkSequenceChangeHistory(
                change_id=history_id,
                mutation_key=f"ai-search:{history_id}",
                board_revision=1,
                board_id=board_id,
                item_id=None,
                change_type="ITEM_REORDERED",
                actor_id="user-admin",
                before_value="step-a, step-b",
                after_value="step-b, step-a",
                change_reason=f"Priority changed after line review. {ground_truth_token}",
            )
        )
        session.add(
            WorkSequenceChangeHistory(
                change_id=empty_history_id,
                mutation_key=f"ai-search:{empty_history_id}",
                board_revision=1,
                board_id=board_id,
                item_id=None,
                change_type="STATUS_CHANGED",
                actor_id="user-admin",
                before_value=None,
                after_value=None,
                change_reason=None,
            )
        )
        session.add(
            Report(
                report_id=report_id,
                report_type="field_review",
                title=f"AI search report source {suffix[:8]}",
                summary=f"Report source should be indexed with trace to report_sources. {ground_truth_token}",
                analysis_content="Manual report, not AI decision output.",
                status="APPROVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=report_id,
                source_type="FIELD_COMMENT",
                source_id=analyzed_comment_id,
                source_version_id=None,
                relation_type="primary",
            )
        )
        session.add(
            Report(
                report_id=archived_report_id,
                report_type="field_review",
                title=f"AI search archived report {suffix[:8]}",
                status="ARCHIVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=archived_report_id,
                source_type="DOCUMENT",
                source_id=published_document_id,
                source_version_id=published_version_id,
                relation_type="archived-report-source",
            )
        )
        session.add(
            Report(
                report_id=blank_report_id,
                report_type="field_review",
                title=f"AI search blank source {suffix[:8]}",
                status="APPROVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=blank_report_id,
                source_type="FIELD_COMMENT",
                source_id="",
                source_version_id=None,
                relation_type="blank-source-id",
            )
        )
        session.add(
            Report(
                report_id=missing_origin_report_id,
                report_type="field_review",
                title=f"AI search missing source {suffix[:8]}",
                status="APPROVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=missing_origin_report_id,
                source_type="FIELD_COMMENT",
                source_id=f"comment-ai-missing-origin-{suffix}",
                source_version_id=None,
                relation_type="missing-origin",
            )
        )
        session.add(
            Report(
                report_id=deleted_origin_report_id,
                report_type="field_review",
                title=f"AI search deleted source report {suffix[:8]}",
                status="APPROVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=deleted_origin_report_id,
                source_type="DOCUMENT",
                source_id=deleted_document_id,
                source_version_id=None,
                relation_type="deleted-origin",
            )
        )
        session.add(
            Report(
                report_id=excluded_comment_report_id,
                report_type="field_review",
                title=f"AI search excluded comment source {suffix[:8]}",
                status="APPROVED",
                ai_draft_used=False,
                created_by="user-admin",
            )
        )
        session.add(
            ReportSource(
                report_id=excluded_comment_report_id,
                source_type="FIELD_COMMENT",
                source_id=archived_comment_id,
                source_version_id=None,
                relation_type="archived-field-comment-source",
            )
        )
        session.commit()

        active_report_source = session.scalar(
            select(ReportSource).where(
                ReportSource.report_id == report_id,
                ReportSource.source_id == analyzed_comment_id,
            )
        )
        assert active_report_source is not None
        missing_origin_report_source = session.scalar(
            select(ReportSource).where(ReportSource.report_id == missing_origin_report_id)
        )
        assert missing_origin_report_source is not None

    return {
        "published_document_id": published_document_id,
        "published_version_id": published_version_id,
        "draft_version_id": draft_version_id,
        "analyzed_comment_id": analyzed_comment_id,
        "selected_comment_id": selected_comment_id,
        "new_comment_id": new_comment_id,
        "mes_comment_id": mes_comment_id,
        "archived_comment_id": archived_comment_id,
        "empty_comment_id": empty_comment_id,
        "history_id": history_id,
        "empty_history_id": empty_history_id,
        "report_source_row_id": str(active_report_source.id),
        "ground_truth_token": ground_truth_token,
        "deleted_document_id": deleted_document_id,
        "report_id": report_id,
        "missing_origin_report_source_row_id": str(missing_origin_report_source.id),
    }


def test_ai_search_ground_truth_evaluation_is_reproducible_and_persisted() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)
        suffix = uuid4().hex
        viewer_id = f"user-ai-eval-viewer-{suffix}"
        with client.app.state.database.session() as session:
            session.add(
                UserAccount(
                    user_id=viewer_id,
                    username=f"ai-eval-viewer-{suffix}",
                    login_id=f"ai-eval-viewer-{suffix}",
                    display_name="AI 근거 회귀 조회자",
                    role="viewer",
                    password_hash=hash_password_for_dev("1234"),
                    is_active=True,
                    status="ACTIVE",
                )
            )
            session.add(
                NotificationChannel(
                    channel_id=f"channel-ai-private-{suffix}",
                    name="권한 없는 AI 근거 채널",
                    channel_type="CUSTOM",
                    source_type="FIELD_COMMENT",
                    source_id=seeded["analyzed_comment_id"],
                    status="ACTIVE",
                    created_by="user-admin",
                )
            )
            session.commit()

        payload = {
            "runLabel": f"candidate-5-{suffix}",
            "evaluateAsUserId": viewer_id,
            "cases": [
                {
                    "caseKey": "complex-four-source-ground-truth",
                    "question": f"{seeded['ground_truth_token']} 복합 근거를 찾아주세요",
                    "expectedOutcome": "SUFFICIENT",
                    "expectedEvidence": [
                        {
                            "sourceType": "PUBLISHED_DOCUMENT_VERSION",
                            "sourceId": seeded["published_document_id"],
                            "sourceVersionId": seeded["published_version_id"],
                            "traceId": seeded["published_document_id"],
                            "traceVersionId": seeded["published_version_id"],
                        },
                        {"sourceType": "FIELD_COMMENT", "sourceId": seeded["selected_comment_id"]},
                        {"sourceType": "WORK_SEQUENCE_HISTORY", "sourceId": seeded["history_id"]},
                        {"sourceType": "REPORT_SOURCE", "sourceId": seeded["report_source_row_id"]},
                    ],
                    "expectedExcluded": [
                        {
                            "sourceType": "FIELD_COMMENT",
                            "sourceId": seeded["analyzed_comment_id"],
                            "exclusionReason": "CHANNEL_ACCESS_DENIED",
                        }
                    ],
                    "limit": 4,
                },
                {
                    "caseKey": "insufficient-and-ineligible-sources",
                    "question": f"no-evidence-{uuid4().hex}",
                    "expectedOutcome": "INSUFFICIENT_EVIDENCE",
                    "expectedEvidence": [],
                    "expectedExcluded": [
                        {
                            "sourceType": "FIELD_COMMENT",
                            "sourceId": seeded["archived_comment_id"],
                            "exclusionReason": "field_comment_excluded_status",
                        },
                        {
                            "sourceType": "PUBLISHED_DOCUMENT_VERSION",
                            "sourceId": seeded["deleted_document_id"],
                            "exclusionReason": "document_version_not_published",
                        },
                        {
                            "sourceType": "REPORT_SOURCE",
                            "sourceId": seeded["missing_origin_report_source_row_id"],
                            "exclusionReason": "report_source_missing_origin",
                        },
                    ],
                },
            ],
        }
        response = client.post("/api/v1/ai-search/evaluations", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "PASSED"
        assert result["candidate_identity_stable"] is True
        assert result["ranking_stable"] is True
        assert result["passed_count"] == 2
        assert result["source_coverage_complete"] is True
        assert result["provider_start_ready"] is False
        assert result["field_comment_missing_reviewed_count"] == 0
        complex_case = result["cases"][0]
        assert len(complex_case["actual_evidence"]) == 4
        assert all(item["candidate_id"] and item["content_hash"] for item in complex_case["actual_evidence"])
        assert all(item["internal_source_uri"].startswith("flownote://") for item in complex_case["actual_evidence"])
        assert complex_case["excluded_evidence"][0]["actual_reason"] == "CHANNEL_ACCESS_DENIED"
        insufficient = result["cases"][1]
        assert insufficient["actual_outcome"] == "INSUFFICIENT_EVIDENCE"
        assert insufficient["actual_evidence"] == []

        quality = client.get("/api/v1/ai-search/quality", headers=headers).json()
        assert quality["latest_evaluation"]["run_id"] == result["run_id"]
        assert quality["latest_evaluation"]["provider_start_ready"] is result["provider_start_ready"]
        with client.app.state.database.session() as session:
            run = session.scalar(
                select(AISearchEvaluationRun).where(AISearchEvaluationRun.run_id == result["run_id"])
            )
            cases = session.scalars(
                select(AISearchEvaluationCase).where(AISearchEvaluationCase.run_id == result["run_id"])
            ).all()
            assert run is not None and run.status == "PASSED"
            assert len(cases) == 2 and all(item.passed for item in cases)


def assert_candidate_trace_row_exists(client: TestClient, candidate: dict[str, object]) -> None:
    with client.app.state.database.session() as session:
        source_type = candidate["source_type"]
        trace_table = candidate["trace_table"]
        if source_type == "PUBLISHED_DOCUMENT_VERSION":
            assert trace_table == "document_versions"
            row = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == candidate["trace_id"],
                    DocumentVersion.version_id == candidate["trace_version_id"],
                )
            )
            assert row is not None
            assert row.document_id == candidate["source_id"]
            assert row.version_id == candidate["source_version_id"]
        elif source_type == "FIELD_COMMENT":
            assert trace_table == "field_comments"
            row = session.scalar(
                select(FieldComment).where(FieldComment.comment_id == candidate["trace_id"])
            )
            assert row is not None
            assert row.comment_id == candidate["source_id"]
            assert row.document_version_id == candidate["source_version_id"]
        elif source_type == "WORK_SEQUENCE_HISTORY":
            assert trace_table == "work_sequence_change_history"
            row = session.scalar(
                select(WorkSequenceChangeHistory).where(
                    WorkSequenceChangeHistory.change_id == candidate["trace_id"]
                )
            )
            assert row is not None
            assert row.change_id == candidate["source_id"]
        elif source_type == "REPORT_SOURCE":
            assert trace_table == "report_sources"
            row = session.scalar(select(ReportSource).where(ReportSource.id == int(candidate["trace_id"])))
            assert row is not None
            assert str(row.id) == candidate["source_id"]
            assert row.source_version_id == candidate["source_version_id"]
        else:
            raise AssertionError(f"unexpected source_type: {source_type}")


def test_ai_search_rebuild_indexes_traceable_evidence_sources_only() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)

        rebuild_response = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild_response.status_code == 200, rebuild_response.text
        rebuild = rebuild_response.json()
        assert rebuild["candidate_count"] >= 4
        assert rebuild["counts_by_source_type"]["PUBLISHED_DOCUMENT_VERSION"] >= 1
        assert rebuild["counts_by_source_type"]["FIELD_COMMENT"] >= 3
        assert rebuild["counts_by_source_type"]["WORK_SEQUENCE_HISTORY"] >= 1
        assert rebuild["counts_by_source_type"]["REPORT_SOURCE"] >= 1
        assert rebuild["excluded_counts_by_reason"]["document_version_not_published"] >= 1
        assert rebuild["excluded_counts_by_reason"]["field_comment_excluded_status"] >= 1
        assert rebuild["excluded_counts_by_reason"]["field_comment_mes_integration"] >= 1
        assert rebuild["excluded_counts_by_reason"]["field_comment_without_content"] >= 1
        assert rebuild["excluded_counts_by_reason"]["work_sequence_history_without_trace_text"] >= 1
        assert rebuild["excluded_counts_by_reason"]["report_source_archived_report"] >= 1
        assert rebuild["excluded_counts_by_reason"]["report_source_without_trace_id"] >= 1
        assert rebuild["excluded_counts_by_reason"]["report_source_missing_origin"] >= 2
        assert rebuild["excluded_reason_guidance"]["document_version_not_published"]["label"]
        assert set(rebuild["counts_by_source_type"]) == {
            "PUBLISHED_DOCUMENT_VERSION",
            "FIELD_COMMENT",
            "WORK_SEQUENCE_HISTORY",
            "REPORT_SOURCE",
        }

        published_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "PUBLISHED_DOCUMENT_VERSION",
                "sourceId": seeded["published_document_id"],
                "limit": 500,
            },
        )
        assert published_response.status_code == 200, published_response.text
        published_candidates = published_response.json()

        analyzed_field_comment_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "FIELD_COMMENT",
                "sourceId": seeded["analyzed_comment_id"],
                "limit": 500,
            },
        )
        assert analyzed_field_comment_response.status_code == 200, analyzed_field_comment_response.text
        new_field_comment_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "FIELD_COMMENT",
                "sourceId": seeded["new_comment_id"],
                "limit": 500,
            },
        )
        assert new_field_comment_response.status_code == 200, new_field_comment_response.text
        selected_field_comment_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "FIELD_COMMENT",
                "sourceId": seeded["selected_comment_id"],
                "limit": 500,
            },
        )
        assert selected_field_comment_response.status_code == 200, selected_field_comment_response.text
        field_comment_candidates = (
            analyzed_field_comment_response.json() + new_field_comment_response.json()
            + selected_field_comment_response.json()
        )

        history_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "WORK_SEQUENCE_HISTORY",
                "sourceId": seeded["history_id"],
                "limit": 500,
            },
        )
        assert history_response.status_code == 200, history_response.text
        history_candidates = history_response.json()

        report_source_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={
                "sourceType": "REPORT_SOURCE",
                "sourceId": seeded["report_source_row_id"],
                "limit": 500,
            },
        )
        assert report_source_response.status_code == 200, report_source_response.text
        report_source_candidates = report_source_response.json()
        all_report_source_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={"sourceType": "REPORT_SOURCE", "limit": 500},
        )
        assert all_report_source_response.status_code == 200, all_report_source_response.text
        all_report_source_candidates = all_report_source_response.json()

        published_candidate = next(
            item
            for item in published_candidates
            if item["source_type"] == "PUBLISHED_DOCUMENT_VERSION"
            and item["source_id"] == seeded["published_document_id"]
        )
        assert published_candidate["source_version_id"] == seeded["published_version_id"]
        assert published_candidate["trace_table"] == "document_versions"
        assert published_candidate["trace_id"] == seeded["published_document_id"]
        assert published_candidate["trace_version_id"] == seeded["published_version_id"]

        analyzed_comment_candidate = next(
            item
            for item in field_comment_candidates
            if item["source_type"] == "FIELD_COMMENT"
            and item["source_id"] == seeded["analyzed_comment_id"]
        )
        assert analyzed_comment_candidate["trace_table"] == "field_comments"
        assert analyzed_comment_candidate["review_status"] == "ANALYZED"

        new_comment_candidate = next(
            item
            for item in field_comment_candidates
            if item["source_type"] == "FIELD_COMMENT"
            and item["source_id"] == seeded["new_comment_id"]
        )
        assert new_comment_candidate["review_status"] == "NEW"

        selected_comment_candidate = next(
            item
            for item in field_comment_candidates
            if item["source_type"] == "FIELD_COMMENT"
            and item["source_id"] == seeded["selected_comment_id"]
        )
        assert selected_comment_candidate["trace_table"] == "field_comments"
        assert selected_comment_candidate["review_status"] == "SELECTED"

        history_candidate = next(
            item
            for item in history_candidates
            if item["source_type"] == "WORK_SEQUENCE_HISTORY"
            and item["source_id"] == seeded["history_id"]
        )
        assert history_candidate["trace_table"] == "work_sequence_change_history"

        report_source_candidate = next(
            item
            for item in report_source_candidates
            if item["source_type"] == "REPORT_SOURCE"
            and item["source_id"] == seeded["report_source_row_id"]
        )
        assert report_source_candidate["trace_table"] == "report_sources"
        assert report_source_candidate["parent_type"] == "REPORT"

        all_checked_candidates = (
            published_candidates
            + field_comment_candidates
            + history_candidates
            + report_source_candidates
            + all_report_source_candidates
        )
        assert not any(
            item["source_version_id"] == seeded["draft_version_id"]
            for item in all_checked_candidates
        )
        assert not any(
            item["source_id"] == seeded["archived_comment_id"]
            for item in all_checked_candidates
        )
        assert not any(
            item["source_id"] == seeded["mes_comment_id"]
            for item in all_checked_candidates
        )
        assert not any(
            item["source_id"] == seeded["empty_comment_id"]
            for item in all_checked_candidates
        )
        assert not any(
            item["source_id"] == seeded["empty_history_id"]
            for item in all_checked_candidates
        )
        assert not any(
            item["source_type"] == "REPORT_SOURCE" and item["summary"] == "blank-source-id"
            for item in all_checked_candidates
        )
        assert not any(
            item["source_type"] == "REPORT_SOURCE" and item["summary"] == "missing-origin"
            for item in all_checked_candidates
        )
        assert not any(
            item["source_type"] == "REPORT_SOURCE" and item["summary"] == "deleted-origin"
            for item in all_checked_candidates
        )
        assert not any(
            item["source_type"] == "REPORT_SOURCE" and item["summary"] == "archived-field-comment-source"
            for item in all_checked_candidates
        )
        for candidate in all_checked_candidates:
            assert_candidate_trace_row_exists(client, candidate)

        with client.app.state.database.session() as session:
            source_types = {
                row.source_type
                for row in session.scalars(select(AISearchCandidate)).all()
            }
            assert source_types <= {
                "PUBLISHED_DOCUMENT_VERSION",
                "FIELD_COMMENT",
                "WORK_SEQUENCE_HISTORY",
                "REPORT_SOURCE",
            }


def test_ai_search_quality_reports_field_comment_review_readiness_gap() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)
        rebuild_response = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild_response.status_code == 200, rebuild_response.text

        quality_response = client.get("/api/v1/ai-search/quality", headers=headers)
        assert quality_response.status_code == 200, quality_response.text
        quality = quality_response.json()

        readiness = quality["field_comment_review_readiness"]
        assert readiness["total_count"] >= 3
        assert readiness["counts_by_status"]["NEW"] >= 1
        assert readiness["counts_by_status"]["ANALYZED"] >= 1
        assert readiness["counts_by_status"]["SELECTED"] >= 1
        assert readiness["reviewed_status_count"] >= 2
        assert readiness["required_reviewed_count"] == 100
        assert readiness["missing_reviewed_count"] == max(
            100 - readiness["reviewed_status_count"],
            0,
        )
        assert quality["excluded_reason_guidance"]["field_comment_without_content"]["operator_action"]

        analyze_response = client.patch(
            f"/api/v1/field-comments/{seeded['new_comment_id']}",
            headers=headers,
            json={
                "status": "ANALYZED",
                "normalizedContent": "Reviewed comment now contributes to readiness.",
                "analysisContent": "Manager review should change AI search quality counts.",
                "transitionReason": "AI 준비도 분석 완료",
            },
        )
        assert analyze_response.status_code == 200, analyze_response.text
        review_response = client.patch(
            f"/api/v1/field-comments/{seeded['new_comment_id']}",
            headers=headers,
            json={
                "status": "REVIEWED",
                "normalizedContent": "Reviewed comment now contributes to readiness.",
                "analysisContent": "Manager review should change AI search quality counts.",
                "transitionReason": "AI 준비도 검토 완료",
            },
        )
        assert review_response.status_code == 200, review_response.text

        updated_quality_response = client.get("/api/v1/ai-search/quality", headers=headers)
        assert updated_quality_response.status_code == 200, updated_quality_response.text
        updated_readiness = updated_quality_response.json()["field_comment_review_readiness"]
        assert updated_readiness["reviewed_status_count"] == readiness["reviewed_status_count"] + 1
        assert updated_readiness["counts_by_status"]["REVIEWED"] >= 1
        assert updated_readiness["missing_reviewed_count"] == max(
            100 - updated_readiness["reviewed_status_count"],
            0,
        )
        assert quality["candidate_count"] >= 4
        assert set(quality["counts_by_source_type"]) <= {
            "PUBLISHED_DOCUMENT_VERSION",
            "FIELD_COMMENT",
            "WORK_SEQUENCE_HISTORY",
            "REPORT_SOURCE",
        }


def test_scope_readiness_counts_approved_ground_truth_and_category_gaps() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)
        rebuild = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild.status_code == 200, rebuild.text

        initial = client.get("/api/v1/ai-search/readiness", headers=headers)
        assert initial.status_code == 200, initial.text
        initial_body = initial.json()
        initial_ground_truth_count = initial_body["ground_truth_count"]
        initial_smoke_ground_truth_count = initial_body["smoke_regression_readiness"]["ground_truth_count"]
        assert initial_body["ground_truth_gap"] == max(48 - initial_ground_truth_count, 0)
        assert initial_body["ground_truth_per_category_scenario_minimum"] == 2
        assert initial_body["field_readiness"]["accepted_data_classification"] == "ANONYMOUS_FIELD"
        assert initial_body["smoke_regression_readiness"]["accepted_data_classifications"] == [
            "SYNTHETIC", "TEST"
        ]
        assert initial_body["human_sample_review_ready"] is initial_body["human_sample_review"]["complete"]
        assert initial_body["human_sample_review"]["sample_case_count"] <= 24
        assert initial_body["approval_actor_separation"]["required_actor_count"] == 4
        assert initial_body["approval_actor_separation"]["distinct_actor_count"] <= 4
        assert initial_body["approval_actor_separation"]["complete"] is (
            initial_body["approval_actor_separation"]["distinct_actor_count"] == 4
            and not initial_body["approval_actor_separation"]["missing_roles"]
        )
        assert initial_body["provider_review_ready"] is False
        assert initial_body["provider_start_ready"] is False
        assert initial_body["external_ai_calls_blocked"] is True
        assert initial_body["external_call_configuration"] == {
            "feature_enabled": False,
            "readiness_gate_enabled": True,
            "provider_adapter_mode": "DISABLED",
            "provider_configured": False,
            "model_configured": False,
            "network_test_scope_enabled": False,
        }
        action_codes = {item["code"] for item in initial_body["operator_actions"]}
        assert set(initial_body["readiness_failures"]) <= action_codes
        assert {
            "EXTERNAL_CALL_FEATURE_DISABLED",
            "PROVIDER_ADAPTER_DISABLED",
            "PROVIDER_OR_MODEL_UNCONFIGURED",
        } <= action_codes
        assert all(
            item["title"] and item["detail"] and item["owner"] and item["next_action"]
            for item in initial_body["operator_actions"]
        )
        assert initial_body["scope"]["customer_scope"] == "DEFAULT"
        assert initial_body["scope"]["site_scope"] == "DEFAULT"
        assert initial_body["scope"]["database_scope"].startswith("sqlite:")
        assert set(initial_body["source_gaps"]) == {
            "PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"
        }
        initial_safety_normal = next(
            item["count"] for item in initial_body["category_scenario_counts"]
            if item["category"] == "SAFETY" and item["scenario_type"] == "NORMAL"
        )

        approved = client.post("/api/v1/ai-search/ground-truth-cases", headers=headers, json={
            "caseKey": f"safety-normal-{uuid4().hex}",
            "category": "SAFETY",
            "scenarioType": "NORMAL",
            "question": f"{seeded['ground_truth_token']} 안전 근거는 무엇입니까?",
            "expectedOutcome": "SUFFICIENT",
            "expectedEvidence": [{
                "sourceType": "PUBLISHED_DOCUMENT_VERSION",
                "sourceId": seeded["published_document_id"],
                "sourceVersionId": seeded["published_version_id"],
                "rationale": "현재 공개 버전이 안전 질문의 직접 근거임",
            }],
            "expectedExcluded": [],
            "allowedRankMin": 1,
            "allowedRankMax": 20,
            "asOf": datetime.now(timezone.utc).isoformat(),
            "dataClassification": "TEST",
            "provenanceNote": "비민감 회귀 사례이며 실제 현장 준비도에서 제외",
        })
        assert approved.status_code == 201, approved.text
        assert approved.json()["approved_by"] == "user-admin"
        assert approved.json()["is_active"] is False
        assert approved.json()["provenance"]["approval_status"] == "PENDING_SECOND_APPROVAL"
        same_approver = client.post(
            f"/api/v1/ai-search/ground-truth-cases/{approved.json()['ground_truth_case_id']}/second-approval",
            headers=headers,
        )
        assert same_approver.status_code == 409

        suffix = uuid4().hex
        with client.app.state.database.session() as session:
            session.add(UserAccount(
                user_id=f"user-ground-truth-reviewer-{suffix}",
                username=f"ground-truth-reviewer-{suffix}",
                login_id=f"ground-truth-reviewer-{suffix}",
                display_name="AI ground-truth 독립 검토자",
                role="manager",
                password_hash=hash_password_for_dev("1234"),
                is_active=True,
                status="ACTIVE",
            ))
            session.commit()
        second_login = client.post("/api/v1/auth/login", json={
            "username": f"ground-truth-reviewer-{suffix}", "password": "1234"
        })
        second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}
        second_approval = client.post(
            f"/api/v1/ai-search/ground-truth-cases/{approved.json()['ground_truth_case_id']}/second-approval",
            headers=second_headers,
        )
        assert second_approval.status_code == 200, second_approval.text
        assert second_approval.json()["is_active"] is True
        assert second_approval.json()["provenance"]["approval_status"] == "APPROVED"
        assert second_approval.json()["provenance"]["first_approved_by"] != second_approval.json()["provenance"]["second_approved_by"]

        updated = client.get("/api/v1/ai-search/readiness", headers=headers).json()
        assert updated["ground_truth_count"] == initial_ground_truth_count
        assert updated["smoke_regression_readiness"]["ground_truth_count"] == initial_smoke_ground_truth_count + 1
        assert updated["ground_truth_gap"] == max(48 - updated["ground_truth_count"], 0)
        updated_safety_normal = next(
            item["count"] for item in updated["category_scenario_counts"]
            if item["category"] == "SAFETY" and item["scenario_type"] == "NORMAL"
        )
        assert updated_safety_normal == initial_safety_normal
        listed = client.get("/api/v1/ai-search/ground-truth-cases", headers=headers)
        assert listed.status_code == 200
        assert any(item["ground_truth_case_id"] == approved.json()["ground_truth_case_id"] for item in listed.json())

        evaluation = client.post("/api/v1/ai-search/evaluations", headers=headers, json={
            "runLabel": f"approved-ground-truth-{uuid4().hex}",
            "groundTruthCaseIds": [approved.json()["ground_truth_case_id"]],
        })
        assert evaluation.status_code == 200, evaluation.text
        evaluation_body = evaluation.json()
        assert evaluation_body["case_count"] == 1
        assert evaluation_body["precision_at_k"] >= 0
        assert evaluation_body["recall_at_k"] == 1
        assert evaluation_body["excluded_source_violation"] == 0
        assert evaluation_body["permission_leak_violation"] == 0
        assert evaluation_body["nonexistent_citation_violation"] == 0
        assert evaluation_body["citation_trace_success_rate"] == 1
        assert evaluation_body["citation_semantic_match_rate"] == 1
        assert evaluation_body["conflict_disclosure_rate"] == 1
        assert evaluation_body["readiness_track"] == "SMOKE_REGRESSION"
        assert evaluation_body["provider_start_ready"] is False

        repeated = client.post("/api/v1/ai-search/evaluations", headers=headers, json={
            "runLabel": f"approved-ground-truth-repeat-{uuid4().hex}",
            "groundTruthCaseIds": [approved.json()["ground_truth_case_id"]],
        })
        assert repeated.status_code == 200, repeated.text
        delta = repeated.json()["cases"][0]["previous_run_delta"]
        assert delta["candidate_ids_added"] == []
        assert delta["candidate_ids_removed"] == []
        assert delta["content_hash_changed"] == []
        assert delta["ranking_changed"] is False


def test_scope_readiness_excludes_smoke_regression_candidates_from_field_source_counts() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)
        with client.app.state.database.session() as session:
            marker = session.scalar(select(TagDefinition).where(
                TagDefinition.tag_type == "custom",
                TagDefinition.code == "smoke-regression",
            ))
            if marker is None:
                marker = TagDefinition(
                    tag_id=f"tag-smoke-regression-{uuid4().hex}",
                    tag_type="custom",
                    code="smoke-regression",
                    name="SMOKE_REGRESSION",
                    is_active=True,
                )
                session.add(marker)
                session.flush()
            session.add(DocumentTag(
                document_id=seeded["published_document_id"],
                tag_id=marker.tag_id,
            ))
            session.commit()

        rebuild = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild.status_code == 200, rebuild.text
        readiness_response = client.get("/api/v1/ai-search/readiness", headers=headers)
        assert readiness_response.status_code == 200, readiness_response.text
        readiness = readiness_response.json()

        with client.app.state.database.session() as session:
            candidates = session.scalars(select(AISearchCandidate)).all()
            smoke_candidates = [
                candidate for candidate in candidates
                if json.loads(candidate.metadata_json or "{}").get("readiness_track") == "SMOKE_REGRESSION"
            ]
            field_counts = Counter(
                candidate.source_type for candidate in candidates
                if json.loads(candidate.metadata_json or "{}").get("readiness_track") == "FIELD_READINESS"
                and (candidate.source_type != "FIELD_COMMENT" or candidate.review_status in {"ANALYZED", "REVIEWED", "SELECTED"})
            )

        assert smoke_candidates
        assert readiness["source_counts"] == {
            source_type: field_counts[source_type]
            for source_type in readiness["source_minimums"]
        }
        assert readiness["provider_start_ready"] is False
