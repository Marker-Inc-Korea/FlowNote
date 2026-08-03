from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import (
    Document,
    DocumentVersion,
    ActivityHistory,
    NotificationChannel,
    NotificationChannelMember,
    Report,
    ReportMutationReceipt,
    ReportSource,
    UserAccount,
)
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
    document = response.json()
    publish_response = client.post(
        f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version']['version_id']}/publish",
        headers=headers,
        json={"changeReason": "보고서 근거 적격성 검증용 공개"},
    )
    assert publish_response.status_code == 200, publish_response.text
    return publish_response.json()


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
    comment = response.json()
    transitions = (
        ("ANALYZED", "보고서 근거 분석 완료"),
        ("REVIEWED", "보고서 근거 검토 완료"),
        ("SELECTED", "보고서 근거 선정 완료"),
    )
    for target, reason in transitions:
        transition = client.patch(
            f"/api/v1/field-comments/{comment['comment_id']}",
            headers=headers,
            json={
                "status": target,
                "normalizedContent": "보고서용 정리 내용",
                "analysisContent": "공개 문서와 대조한 관리자 분석 내용",
                "transitionReason": reason,
            },
        )
        assert transition.status_code == 200, transition.text
        comment = transition.json()
    return comment


def create_work_sequence_sources(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    board_response = client.post(
        "/api/v1/work-sequence-boards",
        headers=headers,
        json={
            "title": f"Report source board {suffix}",
            "lineCode": "line-a",
            "idempotencyKey": f"report-board:{suffix}",
        },
    )
    assert board_response.status_code == 201, board_response.text
    board = board_response.json()
    item_response = client.post(
        f"/api/v1/work-sequence-boards/{board['board_id']}/items",
        headers=headers,
        json={
            "title": f"Report source sequence item {suffix}",
            "idempotencyKey": f"report-item:{suffix}",
            "baseBoardRevision": board["board_revision"],
        },
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
        field_comment_source = next(
            source for source in detail["sources"] if source["source_type"] == "FIELD_COMMENT"
        )
        assert field_comment_source["source_version_id"] == field_comment["document_version_id"]
        assert field_comment_source["trace_id"].startswith("trace_")
        assert field_comment_source["source_hash_sha256"] == field_comment["source_hash_sha256"]
        assert len({source["trace_id"] for source in detail["sources"]}) == len(detail["sources"])
        assert all(source["source_version_id"] for source in detail["sources"])
        assert all(len(source["source_hash_sha256"]) == 64 for source in detail["sources"])
        assert saved["report_revision"] == draft["report_revision"] + 1
        assert len(saved["content_hash_sha256"]) == 64
        assert len(saved["source_set_hash_sha256"]) == 64
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

        trace_response = client.get(
            f"/api/v1/field-comments/{field_comment['comment_id']}/traceability",
            headers=headers,
        )
        assert trace_response.status_code == 200, trace_response.text
        trace = trace_response.json()
        assert trace["field_comment"]["raw_content"] == field_comment["raw_content"]
        assert trace["field_comment"]["source_hash_sha256"] == field_comment["source_hash_sha256"]
        assert len(trace["audit"]) >= 3
        assert all(
            item["after_snapshot"]["source_hash_sha256"] == field_comment["source_hash_sha256"]
            for item in trace["audit"]
        )
        linked_report = next(item for item in trace["reports"] if item["report_id"] == saved["report_id"])
        assert linked_report["source_version_id"] == field_comment["document_version_id"]
        assert linked_report["source_revision"] == trace["field_comment"]["review_revision"]
        assert linked_report["source_hash_sha256"] == trace["field_comment"]["source_hash_sha256"]
        assert linked_report["trace_id"]
        assert linked_report["generated_document"]["document_id"] == saved["generated_document_id"]
        assert linked_report["generated_document"]["generated_version_ids"]


def test_report_save_rejects_source_changed_after_selection_with_409() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        draft = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "오래된 원천 차단 보고서",
                "sources": [
                    {"sourceType": "FIELD_COMMENT", "sourceId": field_comment["comment_id"]},
                    {
                        "sourceType": "DOCUMENT",
                        "sourceId": document["document_id"],
                        "sourceVersionId": document["latest_version"]["version_id"],
                    },
                ],
            },
        ).json()
        changed = client.patch(
            f"/api/v1/field-comments/{field_comment['comment_id']}",
            headers=headers,
            json={
                "status": "REVIEWED",
                "normalizedContent": "재검토 정리",
                "analysisContent": "선정 후 원천 재검토",
                "transitionReason": "보고서 선정 후 원천 변경",
                "baseReviewRevision": field_comment["review_revision"],
                "mutationKey": f"reopen-{uuid4().hex}",
            },
        )
        assert changed.status_code == 200, changed.text

        saved = client.post(
            "/api/v1/reports",
            headers=headers,
            json={
                "draftReportId": draft["report_id"],
                "baseReportRevision": draft["report_revision"],
                "mutationKey": f"stale-report-{uuid4().hex}",
                "saveAsDocument": True,
            },
        )
        assert saved.status_code == 404, saved.text
        assert saved.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"
        with client.app.state.database.session() as session:
            report = session.scalar(select(Report).where(Report.report_id == draft["report_id"]))
            assert report.status == "DRAFT"
            assert report.generated_document_id is None
            assert session.scalar(
                select(ReportMutationReceipt.id).where(ReportMutationReceipt.report_id == draft["report_id"])
            ) is None


def test_report_save_idempotency_key_returns_existing_report() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        report_suffix = uuid4().hex
        idempotency_key = f"pytest:report:{report_suffix}"
        document_title = f"Idempotent report document {report_suffix}"
        payload = {
            "idempotencyKey": idempotency_key,
            "reportType": "field_review",
            "title": "Idempotent report save",
            "summary": "Report should be created once for the same key.",
            "analysisContent": "Retry should return the first saved report.",
            "sources": [
                {
                    "sourceType": "DOCUMENT",
                    "sourceId": document["document_id"],
                    "sourceVersionId": document["latest_version"]["version_id"],
                    "relationType": "related_document",
                },
                {
                    "sourceType": "FIELD_COMMENT",
                    "sourceId": field_comment["comment_id"],
                    "relationType": "primary",
                },
            ],
            "saveAsDocument": True,
            "documentTitle": document_title,
            "documentStatus": "IN_REVIEW",
        }

        first_response = client.post("/api/v1/reports", headers=headers, json=payload)
        assert first_response.status_code == 201, first_response.text
        first = first_response.json()
        second_response = client.post("/api/v1/reports", headers=headers, json=payload)
        assert second_response.status_code == 201, second_response.text
        second = second_response.json()

        assert second["report_id"] == first["report_id"]
        assert second["generated_document_id"] == first["generated_document_id"]
        with client.app.state.database.session() as session:
            reports = session.scalars(
                select(Report).where(Report.idempotency_key == idempotency_key)
            ).all()
            assert len(reports) == 1
            generated_documents = session.scalars(
                select(Document).where(Document.title == document_title)
            ).all()
            assert len(generated_documents) == 1
            sources = session.scalars(
                select(ReportSource).where(ReportSource.report_id == first["report_id"])
            ).all()
            assert len(sources) == 2
            assert len({source.trace_id for source in sources}) == 2


def test_report_requires_two_distinct_source_types() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        response = client.post(
            "/api/v1/reports",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "단일 근거 유형 차단",
                "sources": [{
                    "sourceType": "DOCUMENT",
                    "sourceId": document["document_id"],
                    "sourceVersionId": document["latest_version"]["version_id"],
                }],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "A report requires at least two distinct source types."


def test_report_approval_rejects_field_comment_source_hash_mismatch() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        draft_response = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "원천 hash 불일치 차단",
                "sources": [
                    {"sourceType": "FIELD_COMMENT", "sourceId": field_comment["comment_id"]},
                    {
                        "sourceType": "DOCUMENT",
                        "sourceId": document["document_id"],
                        "sourceVersionId": document["latest_version"]["version_id"],
                    },
                ],
            },
        )
        assert draft_response.status_code == 201, draft_response.text
        draft = draft_response.json()

        with client.app.state.database.engine.begin() as connection:
            connection.execute(
                text("UPDATE field_comments SET raw_content = :content WHERE comment_id = :comment_id"),
                {"content": "DB 우회 변조 원문", "comment_id": field_comment["comment_id"]},
            )

        save_response = client.post(
            "/api/v1/reports",
            headers=headers,
            json={"draftReportId": draft["report_id"], "saveAsDocument": True},
        )

    assert save_response.status_code == 409
    assert save_response.json()["detail"].startswith("Report source hash mismatch: trace_")


def test_report_approval_rejects_selected_source_revision_change_until_redrafted() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)
        draft_response = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "선정 원천 revision 고정",
                "sources": [
                    {
                        "sourceType": "FIELD_COMMENT",
                        "sourceId": field_comment["comment_id"],
                        "sourceRevision": field_comment["review_revision"],
                        "sourceHashSha256": field_comment["source_hash_sha256"],
                    },
                    {"sourceType": "DOCUMENT", "sourceId": document["document_id"]},
                ],
            },
        )
        assert draft_response.status_code == 201, draft_response.text
        draft = draft_response.json()
        frozen = next(source for source in draft["sources"] if source["source_type"] == "FIELD_COMMENT")
        assert frozen["source_revision"] == field_comment["review_revision"]

        changed = client.patch(
            f"/api/v1/field-comments/{field_comment['comment_id']}",
            headers=headers,
            json={
                "status": "REVIEWED",
                "analysisContent": "선정 후 재분석되어 재검토가 필요한 내용",
                "transitionReason": "선정 원천 재검토 전환",
                "baseReviewRevision": field_comment["review_revision"],
            },
        )
        assert changed.status_code == 200, changed.text
        reselected = client.patch(
            f"/api/v1/field-comments/{field_comment['comment_id']}",
            headers=headers,
            json={
                "status": "SELECTED",
                "transitionReason": "재검토 뒤 보고서 근거 재선정",
                "baseReviewRevision": changed.json()["review_revision"],
            },
        )
        assert reselected.status_code == 200, reselected.text
        assert changed.json()["source_hash_sha256"] == field_comment["source_hash_sha256"]
        assert reselected.json()["review_revision"] == field_comment["review_revision"] + 2

        save_response = client.post(
            "/api/v1/reports",
            headers=headers,
            json={"draftReportId": draft["report_id"], "saveAsDocument": True},
        )
        assert save_response.status_code == 409, save_response.text
        assert save_response.json()["detail"].startswith("Report source revision changed: trace_")

        current_source = client.get(
            f"/api/v1/field-comments/{field_comment['comment_id']}",
            headers=headers,
        )
        assert current_source.status_code == 200, current_source.text
        assert current_source.json()["review_revision"] == reselected.json()["review_revision"]
        assert current_source.json()["source_hash_sha256"] == field_comment["source_hash_sha256"]


def test_report_rejects_excluded_field_comment_source() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        document = create_document(client, headers)
        field_comment = create_field_comment(client, headers, document)

        review_response = client.patch(
            f"/api/v1/field-comments/{field_comment['comment_id']}",
            headers=headers,
            json={
                "status": "EXCLUDED",
                "normalizedContent": "Excluded from report source candidates.",
                "analysisContent": "Manager decided this source should not be reused.",
                "reviewedBy": "user-admin",
                "transitionReason": "보고서 근거 제외 결정",
            },
        )
        assert review_response.status_code == 200, review_response.text

        response = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": "Excluded field comment source report",
                "sources": [
                    {
                        "sourceType": "FIELD_COMMENT",
                        "sourceId": field_comment["comment_id"],
                        "relationType": "primary",
                    }
                ],
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"


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

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"


def test_report_source_eligibility_rejects_unselected_private_stale_and_out_of_channel_evidence() -> None:
    with create_test_client() as client:
        admin_headers = auth_headers(client)
        published = create_document(client, admin_headers)

        unselected_response = client.post(
            "/api/v1/field-comments",
            headers=admin_headers,
            json={
                "documentId": published["document_id"],
                "documentVersionId": published["published_version_id"],
                "rawContent": f"미선정 근거 {uuid4().hex}",
                "authorId": "user-admin",
            },
        )
        assert unselected_response.status_code == 201
        unselected = unselected_response.json()
        rejected_unselected = client.post(
            "/api/v1/reports/drafts",
            headers=admin_headers,
            json={
                "reportType": "eligibility",
                "title": "미선정 근거 거부",
                "sources": [{"sourceType": "FIELD_COMMENT", "sourceId": unselected["comment_id"]}],
            },
        )
        assert rejected_unselected.status_code == 404
        assert rejected_unselected.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"

        private_response = client.post(
            "/api/v1/documents",
            headers=admin_headers,
            data={
                "title": f"비공개 근거 {uuid4().hex[:8]}",
                "documentType": "work_instruction",
                "changeReason": "비공개 근거 제외 검증",
            },
            files={"file": ("private-evidence.txt", b"private evidence", "text/plain")},
        )
        assert private_response.status_code == 201
        private = private_response.json()
        rejected_private = client.post(
            "/api/v1/reports/drafts",
            headers=admin_headers,
            json={
                "reportType": "eligibility",
                "title": "비공개 근거 거부",
                "sources": [{"sourceType": "DOCUMENT", "sourceId": private["document_id"]}],
            },
        )
        assert rejected_private.status_code == 404
        assert rejected_private.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"

        v2_response = client.post(
            f"/api/v1/documents/{published['document_id']}/versions",
            headers=admin_headers,
            data={"versionLabel": "v2", "changeReason": "비공개 최신 버전으로 오래된 근거 구분"},
            files={"file": ("stale-evidence-v2.txt", b"stale evidence v2", "text/plain")},
        )
        assert v2_response.status_code == 201, v2_response.text
        rejected_stale = client.post(
            "/api/v1/reports/drafts",
            headers=admin_headers,
            json={
                "reportType": "eligibility",
                "title": "현재 공개본이 아닌 버전 거부",
                "sources": [{
                    "sourceType": "DOCUMENT",
                    "sourceId": published["document_id"],
                    "sourceVersionId": v2_response.json()["version_id"],
                }],
            },
        )
        assert rejected_stale.status_code == 404
        assert rejected_stale.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"

        selected = create_field_comment(client, admin_headers, published)
        manager = create_role_user(client, "manager")
        with client.app.state.database.session() as session:
            session.add(NotificationChannel(
                channel_id=f"channel-{uuid4().hex}",
                name="권한 밖 근거 채널",
                channel_type="LINE",
                source_type="FIELD_COMMENT",
                source_id=selected["comment_id"],
                status="ACTIVE",
                created_by="user-admin",
            ))
            session.commit()
        rejected_channel = client.post(
            "/api/v1/reports/drafts",
            headers=auth_headers(client, manager.username, TEST_PASSWORD),
            json={
                "reportType": "eligibility",
                "title": "권한 밖 채널 근거 거부",
                "sources": [{"sourceType": "FIELD_COMMENT", "sourceId": selected["comment_id"]}],
            },
        )
        assert rejected_channel.status_code == 404
        assert rejected_channel.json()["detail"]["code"] == "SOURCE_NOT_VISIBLE"


def test_report_reads_hide_any_out_of_channel_source_and_write_audit() -> None:
    with create_test_client() as client:
        admin_headers = auth_headers(client)
        document = create_document(client, admin_headers)
        field_comment = create_field_comment(client, admin_headers, document)
        report_response = client.post(
            "/api/v1/reports/drafts",
            headers=admin_headers,
            json={
                "reportType": "scope_recheck",
                "title": f"원천 권한 재검사 {uuid4().hex[:8]}",
                "sources": [
                    {
                        "sourceType": "FIELD_COMMENT",
                        "sourceId": field_comment["comment_id"],
                    },
                    {
                        "sourceType": "DOCUMENT",
                        "sourceId": document["document_id"],
                    },
                ],
            },
        )
        assert report_response.status_code == 201, report_response.text
        report = report_response.json()
        manager = create_role_user(client, "manager")
        manager_headers = auth_headers(client, manager.username, TEST_PASSWORD)
        channel_id = f"channel-{uuid4().hex}"
        with client.app.state.database.session() as session:
            session.add(
                NotificationChannel(
                    channel_id=channel_id,
                    name="보고서 원천 제한 채널",
                    channel_type="LINE",
                    source_type="FIELD_COMMENT",
                    source_id=field_comment["comment_id"],
                    status="ACTIVE",
                    created_by="user-admin",
                )
            )
            session.commit()

        listed = client.get("/api/v1/reports", headers=manager_headers)
        detail = client.get(
            f"/api/v1/reports/{report['report_id']}",
            headers=manager_headers,
        )
        sources = client.get(
            f"/api/v1/reports/{report['report_id']}/sources",
            headers=manager_headers,
        )

        assert listed.status_code == 200
        assert report["report_id"] not in {item["report_id"] for item in listed.json()}
        assert detail.status_code == 404
        assert sources.status_code == 404
        assert detail.json() == sources.json()
        assert detail.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"
        with client.app.state.database.session() as session:
            denied_events = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.actor_id == manager.user_id,
                    ActivityHistory.target_id == report["report_id"],
                    ActivityHistory.event_type.in_(
                        {"report.read_denied", "report.source_read_denied"}
                    ),
                )
            ).all()
            assert {event.event_type for event in denied_events} == {
                "report.read_denied",
                "report.source_read_denied",
            }
            session.add(
                NotificationChannelMember(
                    member_id=f"member-{uuid4().hex}",
                    channel_id=channel_id,
                    user_id=manager.user_id,
                    member_role="MEMBER",
                    status="ACTIVE",
                    added_by="user-admin",
                )
            )
            session.commit()

        allowed_detail = client.get(
            f"/api/v1/reports/{report['report_id']}",
            headers=manager_headers,
        )
        allowed_sources = client.get(
            f"/api/v1/reports/{report['report_id']}/sources",
            headers=manager_headers,
        )
        assert allowed_detail.status_code == 200, allowed_detail.text
        assert allowed_sources.status_code == 200, allowed_sources.text
        assert len(allowed_sources.json()) == 2
