from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    AISearchCandidate,
    Document,
    DocumentVersion,
    FieldComment,
    FileObject,
    Report,
    ReportSource,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
)
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
    published_document_id = f"doc-ai-published-{suffix}"
    published_version_id = f"ver-ai-published-{suffix}"
    draft_document_id = f"doc-ai-draft-{suffix}"
    draft_version_id = f"ver-ai-draft-{suffix}"
    analyzed_comment_id = f"comment-ai-analyzed-{suffix}"
    new_comment_id = f"comment-ai-new-{suffix}"
    mes_comment_id = f"comment-ai-mes-{suffix}"
    archived_comment_id = f"comment-ai-archived-{suffix}"
    board_id = f"wseqboard-ai-{suffix}"
    history_id = f"wseqhist-ai-{suffix}"
    report_id = f"report-ai-{suffix}"
    archived_report_id = f"report-ai-archived-{suffix}"
    blank_report_id = f"report-ai-blank-source-{suffix}"

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
                description="Published document version should be indexed as evidence.",
                document_type="work_instruction",
                owner_id="user-admin",
                status="PUBLISHED",
                latest_version_id=published_version_id,
                published_version_id=published_version_id,
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
                raw_content="Analyzed field comment for evidence search.",
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
            WorkSequenceBoard(
                board_id=board_id,
                title=f"AI search work board {suffix[:8]}",
                line_code="line-a",
                status="ACTIVE",
                created_by="user-admin",
            )
        )
        session.add(
            WorkSequenceChangeHistory(
                change_id=history_id,
                board_id=board_id,
                item_id=None,
                change_type="ITEM_REORDERED",
                actor_id="user-admin",
                before_value="step-a, step-b",
                after_value="step-b, step-a",
                change_reason="Priority changed after line review.",
            )
        )
        session.add(
            Report(
                report_id=report_id,
                report_type="field_review",
                title=f"AI search report source {suffix[:8]}",
                summary="Report source should be indexed with trace to report_sources.",
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
        session.commit()

        active_report_source = session.scalar(
            select(ReportSource).where(
                ReportSource.report_id == report_id,
                ReportSource.source_id == analyzed_comment_id,
            )
        )
        assert active_report_source is not None

    return {
        "published_document_id": published_document_id,
        "published_version_id": published_version_id,
        "draft_version_id": draft_version_id,
        "analyzed_comment_id": analyzed_comment_id,
        "new_comment_id": new_comment_id,
        "mes_comment_id": mes_comment_id,
        "archived_comment_id": archived_comment_id,
        "history_id": history_id,
        "report_source_row_id": str(active_report_source.id),
    }


def test_ai_search_rebuild_indexes_traceable_evidence_sources_only() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        seeded = seed_ai_search_sources(client)

        rebuild_response = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild_response.status_code == 200, rebuild_response.text
        rebuild = rebuild_response.json()
        assert rebuild["candidate_count"] >= 4
        assert rebuild["counts_by_source_type"]["PUBLISHED_DOCUMENT_VERSION"] >= 1
        assert rebuild["counts_by_source_type"]["FIELD_COMMENT"] >= 2
        assert rebuild["counts_by_source_type"]["WORK_SEQUENCE_HISTORY"] >= 1
        assert rebuild["counts_by_source_type"]["REPORT_SOURCE"] >= 1
        assert rebuild["excluded_counts_by_reason"]["document_version_not_published"] >= 1
        assert rebuild["excluded_counts_by_reason"]["field_comment_excluded_status"] >= 1
        assert rebuild["excluded_counts_by_reason"]["field_comment_mes_integration"] >= 1
        assert rebuild["excluded_counts_by_reason"]["report_source_archived_report"] >= 1
        assert rebuild["excluded_counts_by_reason"]["report_source_without_trace_id"] >= 1

        published_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={"sourceType": "PUBLISHED_DOCUMENT_VERSION", "limit": 500},
        )
        assert published_response.status_code == 200, published_response.text
        published_candidates = published_response.json()

        field_comment_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={"sourceType": "FIELD_COMMENT", "limit": 500},
        )
        assert field_comment_response.status_code == 200, field_comment_response.text
        field_comment_candidates = field_comment_response.json()

        history_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={"sourceType": "WORK_SEQUENCE_HISTORY", "limit": 500},
        )
        assert history_response.status_code == 200, history_response.text
        history_candidates = history_response.json()

        report_source_response = client.get(
            "/api/v1/ai-search/candidates",
            headers=headers,
            params={"sourceType": "REPORT_SOURCE", "limit": 500},
        )
        assert report_source_response.status_code == 200, report_source_response.text
        report_source_candidates = report_source_response.json()

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
            item["source_type"] == "REPORT_SOURCE" and item["summary"] == "blank-source-id"
            for item in all_checked_candidates
        )

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
        seed_ai_search_sources(client)
        rebuild_response = client.post("/api/v1/ai-search/candidates/rebuild", headers=headers)
        assert rebuild_response.status_code == 200, rebuild_response.text

        quality_response = client.get("/api/v1/ai-search/quality", headers=headers)
        assert quality_response.status_code == 200, quality_response.text
        quality = quality_response.json()

        readiness = quality["field_comment_review_readiness"]
        assert readiness["total_count"] >= 3
        assert readiness["counts_by_status"]["NEW"] >= 1
        assert readiness["counts_by_status"]["ANALYZED"] >= 1
        assert readiness["reviewed_status_count"] >= 1
        assert readiness["required_reviewed_count"] == 100
        assert readiness["missing_reviewed_count"] == max(
            100 - readiness["reviewed_status_count"],
            0,
        )
        assert quality["candidate_count"] >= 4
        assert set(quality["counts_by_source_type"]) <= {
            "PUBLISHED_DOCUMENT_VERSION",
            "FIELD_COMMENT",
            "WORK_SEQUENCE_HISTORY",
            "REPORT_SOURCE",
        }
