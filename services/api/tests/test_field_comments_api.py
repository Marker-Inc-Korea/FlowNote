from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import FieldComment, FieldCommentAttachment, FileObject, UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "field-comment-tests"


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
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_role_headers(client: TestClient, role: str) -> dict[str, str]:
    suffix = uuid4().hex[:10]
    username = f"field-comment-{role}-{suffix}"
    with client.app.state.database.session() as session:
        session.add(UserAccount(
            user_id=f"user-{suffix}",
            username=username,
            login_id=username,
            display_name=f"FieldComment {role}",
            role=role,
            password_hash=hash_password_for_dev("1234"),
            is_active=True,
            status="ACTIVE",
        ))
        session.commit()
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_document(client: TestClient) -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/documents",
        headers=auth_headers(client),
        data={
            "title": f"Field comment target {suffix}",
            "documentType": "work_instruction",
            "changeReason": "Create a document for field comment API testing.",
        },
        files={"file": (f"field-comment-target-{suffix}.txt", b"field comment target", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_list_and_review_field_comment() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        content = f"Field comment API raw content {uuid4().hex}"

        response = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": content,
                "authorId": "user-admin",
                "reportedBy": "관리자",
                "entrySource": "field_user",
                "locationCode": "line-a",
            },
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["comment_id"].startswith("comment_")
        assert created["document_id"] == document["document_id"]
        assert created["document_version_id"] == document["latest_version"]["version_id"]
        assert created["raw_content"] == content
        assert created["status"] == "NEW"

        document_comments_response = client.get(
            f"/api/v1/documents/{document['document_id']}/field-comments",
            headers=headers,
        )
        assert document_comments_response.status_code == 200
        assert any(note["comment_id"] == created["comment_id"] for note in document_comments_response.json())

        filtered_response = client.get(
            "/api/v1/field-comments",
            headers=headers,
            params={"documentId": document["document_id"], "status": "NEW"},
        )
        assert filtered_response.status_code == 200
        assert any(note["comment_id"] == created["comment_id"] for note in filtered_response.json())

        author_filtered_response = client.get(
            "/api/v1/field-comments",
            headers=headers,
            params={"author": "user-admin", "createdFrom": "2000-01-01T00:00:00"},
        )
        assert author_filtered_response.status_code == 200
        assert any(note["comment_id"] == created["comment_id"] for note in author_filtered_response.json())

        review_response = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=headers,
            json={
                "status": "ANALYZED",
                "normalizedContent": "Field issue normalized for manager review.",
                "analysisContent": "Repeated field comment should be checked against the work standard.",
                "analyzedBy": "user-admin",
                "transitionReason": "관리자 분석 완료",
            },
        )
        assert review_response.status_code == 200, review_response.text
        reviewed = review_response.json()
        assert reviewed["status"] == "ANALYZED"
        assert reviewed["normalized_content"] == "Field issue normalized for manager review."
        assert reviewed["analysis_content"] == (
            "Repeated field comment should be checked against the work standard."
        )
        assert reviewed["analyzed_by"] == "user-admin"
        assert reviewed["analyzed_at"] is not None

        audit_response = client.get(
            f"/api/v1/field-comments/{created['comment_id']}/audit",
            headers=headers,
        )
        assert audit_response.status_code == 200, audit_response.text
        audit = audit_response.json()[-1]
        assert audit["before_snapshot"]["status"] == "NEW"
        assert audit["after_snapshot"]["status"] == "ANALYZED"
        assert audit["before_snapshot"]["source_hash_sha256"] == created["source_hash_sha256"]
        assert audit["after_snapshot"]["source_hash_sha256"] == created["source_hash_sha256"]


def test_field_comment_transition_policy_rejects_skip_and_requires_reason() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        created = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "rawContent": "상태 전이 정책 검증",
                "authorId": "user-admin",
            },
        ).json()

        skipped = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=headers,
            json={
                "status": "SELECTED",
                "normalizedContent": "정리",
                "analysisContent": "분석",
                "transitionReason": "바로 선정 시도",
            },
        )
        assert skipped.status_code == 409

        no_reason = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=headers,
            json={"status": "ANALYZED", "analysisContent": "분석"},
        )
        assert no_reason.status_code == 422


def test_bulk_review_preserves_source_and_quality_metrics_are_available() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        comments = []
        for index in range(2):
            response = client.post(
                "/api/v1/field-comments",
                headers=headers,
                json={
                    "documentId": document["document_id"],
                    "documentVersionId": document["latest_version"]["version_id"],
                    "rawContent": f"일괄 분석 원문 {index}",
                    "authorId": "user-admin",
                    "signalLevel": "YELLOW",
                    "locationCode": "line-b",
                    "category": "quality",
                },
            )
            assert response.status_code == 201
            comments.append(response.json())

        for item in comments:
            prepared = client.patch(
                f"/api/v1/field-comments/{item['comment_id']}",
                headers=headers,
                json={"analysisContent": "공통 분석 내용"},
            )
            assert prepared.status_code == 200

        bulk = client.post(
            "/api/v1/field-comments/bulk-review",
            headers=headers,
            json={
                "commentIds": [item["comment_id"] for item in comments],
                "status": "ANALYZED",
                "assignedTo": "user-admin",
                "transitionReason": "일괄 분석 처리",
            },
        )
        assert bulk.status_code == 200, bulk.text
        for before, after in zip(comments, bulk.json(), strict=True):
            assert after["status"] == "ANALYZED"
            assert after["raw_content"] == before["raw_content"]
            assert after["source_hash_sha256"] == before["source_hash_sha256"]

        filtered = client.get(
            "/api/v1/field-comments",
            headers=headers,
            params={"assignedTo": "user-admin", "hasAttachments": False, "reportLinked": False},
        )
        assert filtered.status_code == 200
        assert all(item["assigned_to"] == "user-admin" for item in filtered.json())

        metrics = client.get("/api/v1/field-comments/quality-metrics", headers=headers)
        assert metrics.status_code == 200, metrics.text
        assert metrics.json()["status_distribution"]["ANALYZED"] >= 2
        assert metrics.json()["line_distribution"]["line-b"] >= 2

        workbench = client.get("/api/v1/field-comments/quality-workbench", headers=headers)
        assert workbench.status_code == 200, workbench.text


def test_review_workbench_filters_and_priority_flags_are_explicit() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        raw_content = f"중복 의심 작업함 검증 {uuid4().hex}"
        created = []
        for _ in range(2):
            response = client.post(
                "/api/v1/field-comments",
                headers=headers,
                json={
                    "documentId": document["document_id"],
                    "documentVersionId": document["latest_version"]["version_id"],
                    "rawContent": raw_content,
                    "authorId": "user-admin",
                },
            )
            assert response.status_code == 201, response.text
            created.append(response.json())

        overdue = client.patch(
            f"/api/v1/field-comments/{created[0]['comment_id']}",
            headers=headers,
            json={"reviewDueAt": "2000-01-01T00:00:00Z"},
        )
        assert overdue.status_code == 200, overdue.text

        response = client.get(
            "/api/v1/field-comments",
            headers=headers,
            params={
                "documentId": document["document_id"],
                "unreviewed": True,
                "unassigned": True,
                "missingEvidence": True,
                "duplicateSuspected": True,
                "reportLinked": False,
                "priorityOrder": True,
            },
        )
        assert response.status_code == 200, response.text
        rows = response.json()
        assert {item["comment_id"] for item in rows} >= {item["comment_id"] for item in created}
        assert rows[0]["comment_id"] == created[0]["comment_id"]
        assert set(rows[0]["workbench_flags"]) >= {
            "UNREVIEWED",
            "OVERDUE",
            "UNASSIGNED",
            "MISSING_EVIDENCE",
            "DUPLICATE_SUSPECTED",
            "REPORT_UNLINKED",
        }

        overdue_only = client.get(
            "/api/v1/field-comments",
            headers=headers,
            params={"documentId": document["document_id"], "overdue": True},
        )
        assert overdue_only.status_code == 200
        assert [item["comment_id"] for item in overdue_only.json()] == [created[0]["comment_id"]]

        metrics = client.get("/api/v1/field-comments/quality-metrics", headers=headers)
        assert metrics.status_code == 200, metrics.text
        quality = metrics.json()
        assert "connection_quality" in quality
        assert "tag_axis_coverage" in quality
        assert quality["connection_quality"]["report_source_type_count"] >= 0
        assert quality["connection_quality"]["orphan_report_source_rate"] >= 0


def test_field_comment_source_fields_are_immutable_in_database() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        created = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={"documentId": document["document_id"], "rawContent": "불변 원문"},
        ).json()

        with client.app.state.database.session() as session:
            note = session.scalar(select(FieldComment).where(FieldComment.comment_id == created["comment_id"]))
            assert note is not None
            note.raw_content = "변경 시도"
            try:
                session.commit()
            except ValueError as exc:
                assert "immutable" in str(exc)
                session.rollback()
            else:
                raise AssertionError("FieldComment source update must be rejected")

        with client.app.state.database.session() as session:
            note = session.scalar(select(FieldComment).where(FieldComment.comment_id == created["comment_id"]))
            assert note is not None
            session.delete(note)
            try:
                session.commit()
            except ValueError as exc:
                assert "cannot be deleted" in str(exc)
                session.rollback()
            else:
                raise AssertionError("FieldComment source deletion must be rejected")

        unchanged = client.get(
            f"/api/v1/field-comments/{created['comment_id']}", headers=headers
        ).json()
        assert unchanged["raw_content"] == "불변 원문"
        assert unchanged["source_hash_sha256"] == created["source_hash_sha256"]


def test_field_comment_review_roles_separate_analysis_and_decision() -> None:
    with create_test_client() as client:
        document = create_document(client)
        admin_headers = auth_headers(client)
        viewer_headers = create_role_headers(client, "viewer")
        foreman_headers = create_role_headers(client, "line-foreman")
        created = client.post(
            "/api/v1/field-comments",
            headers=admin_headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "rawContent": "권한 분리 원문",
            },
        ).json()

        denied_viewer = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=viewer_headers,
            json={"status": "ANALYZED", "analysisContent": "분석", "transitionReason": "viewer 분석"},
        )
        assert denied_viewer.status_code == 403

        analyzed = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=foreman_headers,
            json={
                "status": "ANALYZED",
                "normalizedContent": "정리 내용",
                "analysisContent": "반장 분석 내용",
                "transitionReason": "반장 분석 완료",
            },
        )
        assert analyzed.status_code == 200, analyzed.text

        denied_decision = client.patch(
            f"/api/v1/field-comments/{created['comment_id']}",
            headers=foreman_headers,
            json={
                "status": "REVIEWED",
                "normalizedContent": "정리 내용",
                "analysisContent": "반장 분석 내용",
                "transitionReason": "반장 검토 시도",
            },
        )
        assert denied_decision.status_code == 403


def test_field_comment_idempotency_key_returns_existing_note() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        idempotency_key = f"pytest:field-comment:{uuid4().hex}"

        payload = {
            "documentId": document["document_id"],
            "documentVersionId": document["latest_version"]["version_id"],
            "commentType": "issue",
            "inputMode": "free_text",
            "rawContent": f"Idempotent field comment {uuid4().hex}",
            "idempotencyKey": idempotency_key,
        }
        first_response = client.post("/api/v1/field-comments", headers=headers, json=payload)
        assert first_response.status_code == 201, first_response.text
        first = first_response.json()

        duplicate_payload = dict(payload)
        duplicate_payload["rawContent"] = "Changed duplicate content should not be saved."
        second_response = client.post("/api/v1/field-comments", headers=headers, json=duplicate_payload)
        assert second_response.status_code == 201, second_response.text
        second = second_response.json()
        assert second["comment_id"] == first["comment_id"]
        assert second["raw_content"] == first["raw_content"]

        with client.app.state.database.session() as session:
            saved_count = session.scalar(
                select(func.count()).select_from(FieldComment).where(
                    FieldComment.idempotency_key == idempotency_key
                )
            )
            assert saved_count == 1


def test_field_comment_attachment_registration_and_list() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        comment_response = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": f"Field comment with attachment {uuid4().hex}",
            },
        )
        assert comment_response.status_code == 201, comment_response.text
        note = comment_response.json()
        file_bytes = b"field comment attachment text"

        response = client.post(
            f"/api/v1/field-comments/{note['comment_id']}/attachments",
            headers=headers,
            data={
                "caption": "현장 확인용 텍스트 첨부",
                "createdBy": "user-admin",
            },
            files={"file": ("field-comment-attachment.txt", file_bytes, "text/plain")},
        )

        assert response.status_code == 201, response.text
        attachment = response.json()
        assert attachment["attachment_id"].startswith("att_")
        assert attachment["comment_id"] == note["comment_id"]
        assert attachment["attachment_type"] == "document"
        assert attachment["caption"] == "현장 확인용 텍스트 첨부"
        assert attachment["created_by"] == "user-admin"
        assert attachment["file"]["original_filename"] == "field-comment-attachment.txt"
        assert attachment["file"]["extension"] == ".txt"
        assert attachment["file"]["file_family"] == "text"
        assert attachment["file"]["size_bytes"] == len(file_bytes)
        assert attachment["file"]["hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
        assert attachment["file"]["storage_key"].startswith(
            f"field-comments/{note['comment_id']}/attachments/"
        )

        list_response = client.get(
            f"/api/v1/field-comments/{note['comment_id']}/attachments",
            headers=headers,
        )
        assert list_response.status_code == 200, list_response.text
        assert any(item["attachment_id"] == attachment["attachment_id"] for item in list_response.json())

        with client.app.state.database.session() as session:
            row = session.execute(
                select(FieldCommentAttachment, FileObject)
                .join(FileObject, FieldCommentAttachment.file_object_id == FileObject.id)
                .where(FieldCommentAttachment.attachment_id == attachment["attachment_id"])
            ).first()
            assert row is not None
            saved_attachment, saved_file = row
            assert saved_attachment.comment_id == note["comment_id"]
            assert saved_file.original_filename == "field-comment-attachment.txt"
            assert saved_file.size_bytes == len(file_bytes)
            assert saved_file.hash_sha256 == hashlib.sha256(file_bytes).hexdigest()


def test_field_comment_attachment_rejects_unknown_comment_id() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-comments/comment-does-not-exist/attachments",
            headers=auth_headers(client),
            files={"file": ("field-comment-attachment.txt", b"attachment", "text/plain")},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Field comment not found."


def test_field_comment_attachment_idempotency_key_returns_existing_attachment() -> None:
    idempotency_key = f"pytest:field-comment-attachment:{uuid4().hex}"
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        comment_response = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "rawContent": "Idempotent attachment target",
            },
        )
        assert comment_response.status_code == 201, comment_response.text
        comment_id = comment_response.json()["comment_id"]

        responses = []
        for caption in ("First upload", "Duplicate upload"):
            response = client.post(
                f"/api/v1/field-comments/{comment_id}/attachments",
                headers=headers,
                data={"caption": caption, "idempotencyKey": idempotency_key},
                files={"file": ("evidence.txt", b"same evidence", "text/plain")},
            )
            assert response.status_code == 201, response.text
            responses.append(response.json())

        assert responses[0]["attachment_id"] == responses[1]["attachment_id"]
        assert responses[1]["caption"] == "First upload"
        with client.app.state.database.session() as session:
            count = session.scalar(
                select(func.count()).select_from(FieldCommentAttachment).where(
                    FieldCommentAttachment.idempotency_key == idempotency_key
                )
            )
            assert count == 1


def test_field_comment_attachment_rejects_unsupported_file_type() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        comment_response = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": f"Field comment with invalid attachment {uuid4().hex}",
            },
        )
        assert comment_response.status_code == 201, comment_response.text
        note = comment_response.json()

        response = client.post(
            f"/api/v1/field-comments/{note['comment_id']}/attachments",
            headers=headers,
            files={"file": ("field-comment-attachment.exe", b"attachment", "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Attachment file type is not allowed."


def test_field_comment_requires_a_target() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-comments",
            headers=auth_headers(client),
            json={
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": "This note has no target.",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A field comment must reference documentId, structureItemId, or workRecordId."
    )


def test_field_comment_requires_authentication() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-comments",
            json={
                "documentId": "doc-does-not-exist",
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": "This unauthenticated note should be rejected.",
            },
        )

    assert response.status_code == 401


def test_field_comment_rejects_unknown_document() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-comments",
            headers=auth_headers(client),
            json={
                "documentId": "doc-does-not-exist",
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": "This note references an unknown document.",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
