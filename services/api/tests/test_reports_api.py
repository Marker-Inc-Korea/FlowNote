from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import Document, DocumentVersion, FieldComment, Report, ReportSource, UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "report-tests"
TEST_PASSWORD = "correct-password"


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
    )
    return TestClient(create_app(app_settings))


def auth_headers(client: TestClient, username: str = "admin", password: str = "1234") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_role_user(client: TestClient, role: str) -> UserAccount:
    suffix = uuid4().hex
    username = f"report-{role.replace('-', '_')}-{suffix}"
    account = UserAccount(
        user_id=f"user-{username}",
        username=username,
        login_id=username,
        display_name=f"Report Test {role}",
        role=role,
        password_hash=hash_password_for_dev(TEST_PASSWORD),
        is_active=True,
        status="ACTIVE",
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def create_document(client: TestClient, headers: dict[str, str]) -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        data={
            "title": f"Report source document {suffix}",
            "documentType": "work_instruction",
            "changeReason": "Create report source document.",
        },
        files={"file": (f"report-source-{suffix}.txt", b"report source document", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_field_comment(client: TestClient, headers: dict[str, str], document: dict) -> dict:
    response = client.post(
        "/api/v1/field-comments",
        headers=headers,
        json={
            "documentId": document["document_id"],
            "documentVersionId": document["latest_version"]["version_id"],
            "commentType": "issue",
            "inputMode": "free_text",
            "rawContent": f"Report source FieldComment {uuid4().hex[:8]}",
            "entrySource": "field_user",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_work_sequence_sources(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    board_response = client.post(
        "/api/v1/work-sequence-boards",
        headers=headers,
        json={"title": f"Report source board {suffix}", "lineCode": "line-a"},
    )
    assert board_response.status_code == 201, board_response.text
    board = board_response.json()
    item_response = client.post(
        f"/api/v1/work-sequence-boards/{board['board_id']}/items",
        headers=headers,
        json={"title": f"Report source sequence item {suffix}"},
    )
    assert item_response.status_code == 201, item_response.text
    item = item_response.json()["items"][0]
    history_response = client.get(
        f"/api/v1/work-sequence-boards/{board['board_id']}/history",
        headers=headers,
    )
    assert history_response.status_code == 200, history_response.text
    return item["item_id"], history_response.json()[0]["change_id"]


def test_report_draft_final_document_and_source_traceability() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        item_id, history_id = create_work_sequence_sources(client, headers)

        draft_response = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "Manual field review draft",
                "summary": "Manager grouped field comment and related document.",
                "analysisContent": "Check source comment against the published work instruction.",
                "sources": [
                    {
                        "sourceType": "FIELD_COMMENT",
                        "sourceId": field_comment["comment_id"],
                        "relationType": "primary",
                    },
                    {
                        "sourceType": "DOCUMENT",
                        "sourceId": document["document_id"],
                        "sourceVersionId": document["latest_version"]["version_id"],
                        "relationType": "related_document",
                    },
                    {
                        "sourceType": "WORK_SEQUENCE_ITEM",
                        "sourceId": item_id,
                        "relationType": "work_sequence",
                    },
                    {
                        "sourceType": "WORK_SEQUENCE_HISTORY",
                        "sourceId": history_id,
                        "relationType": "work_sequence_history",
                    },
                ],
            },
        )
        assert draft_response.status_code == 201, draft_response.text
        draft = draft_response.json()
        assert draft["report_id"].startswith("report_")
        assert draft["status"] == "DRAFT"
        assert any(source["source_id"] == field_comment["comment_id"] for source in draft["sources"])
        assert any(source["source_id"] == document["document_id"] for source in draft["sources"])

        save_response = client.post(
            "/api/v1/reports",
            headers=headers,
            json={
                "draftReportId": draft["report_id"],
                "conclusion": "Use the source document and update the field instruction.",
                "actionPlan": "Manager will review the work standard before the next shift.",
                "saveAsDocument": True,
                "documentTitle": "Manual field review report",
                "documentStatus": "IN_REVIEW",
            },
        )
        assert save_response.status_code == 201, save_response.text
        saved = save_response.json()
        assert saved["status"] == "APPROVED"
        assert saved["generated_document_id"].startswith("doc_")
        assert saved["generated_document"]["status"] == "IN_REVIEW"

        document_list_response = client.get("/api/v1/documents", headers=headers)
        assert document_list_response.status_code == 200, document_list_response.text
        generated_document_item = next(
            item for item in document_list_response.json() if item["document_id"] == saved["generated_document_id"]
        )
        assert generated_document_item["document_type"] == "report"
        assert set(generated_document_item["tags"]) >= {"Report", "FieldComment", "Document", "WorkSequence"}

        detail_response = client.get(f"/api/v1/reports/{draft['report_id']}", headers=headers)
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["generated_document_id"] == saved["generated_document_id"]
        assert any(
            source["source_type"] == "FIELD_COMMENT" and source["summary"] == field_comment["raw_content"]
            for source in detail["sources"]
        )
        assert any(
            source["source_type"] == "DOCUMENT" and source["source_version_id"] == document["latest_version"]["version_id"]
            for source in detail["sources"]
        )

        with client.app.state.database.session() as session:
            report = session.scalar(select(Report).where(Report.report_id == draft["report_id"]))
            assert report is not None
            assert report.generated_document_id == saved["generated_document_id"]
            source_rows = session.scalars(
                select(ReportSource).where(ReportSource.report_id == draft["report_id"])
            ).all()
            assert {source.source_type for source in source_rows} >= {
                "FIELD_COMMENT",
                "DOCUMENT",
                "WORK_SEQUENCE_ITEM",
                "WORK_SEQUENCE_HISTORY",
            }
            saved_document = session.scalar(
                select(Document).where(Document.document_id == saved["generated_document_id"])
            )
            assert saved_document is not None
            assert saved_document.status == "IN_REVIEW"
            saved_version = session.scalar(
                select(DocumentVersion).where(DocumentVersion.document_id == saved_document.document_id)
            )
            assert saved_version is not None
            assert saved_version.version_no == 1
            assert saved_version.version_status == "APPROVED"
            assert saved_version.created_by == "user-admin"


def test_report_draft_requires_manager_role() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        member = create_role_user(client, "team-member")

        response = client.post(
            "/api/v1/reports/drafts",
            headers=auth_headers(client, member.username, TEST_PASSWORD),
            json={
                "reportType": "field_review",
                "title": "Denied report draft",
                "sources": [{"sourceType": "FIELD_COMMENT", "sourceId": field_comment["comment_id"]}],
            },
        )

    assert response.status_code == 403, response.text


def test_report_rejects_unknown_source() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/reports/drafts",
            headers=auth_headers(client),
            json={
                "reportType": "field_review",
                "title": "Unknown source report draft",
                "sources": [{"sourceType": "FIELD_COMMENT", "sourceId": "comment-does-not-exist"}],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "FIELD_COMMENT source is unknown."
