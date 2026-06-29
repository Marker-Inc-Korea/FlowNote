from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import FieldNoteAttachment, FileObject
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "field-note-tests"


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


def create_document(client: TestClient) -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/documents",
        headers=auth_headers(client),
        data={
            "title": f"Field note target {suffix}",
            "documentType": "work_instruction",
            "changeReason": "Create a document for field note API testing.",
        },
        files={"file": (f"field-note-target-{suffix}.txt", b"field note target", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_list_and_review_field_note() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        content = f"Field note API raw content {uuid4().hex}"

        response = client.post(
            "/api/v1/field-notes",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": content,
                "entrySource": "field_user",
                "locationCode": "line-a",
            },
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["note_id"].startswith("note_")
        assert created["document_id"] == document["document_id"]
        assert created["document_version_id"] == document["latest_version"]["version_id"]
        assert created["raw_content"] == content
        assert created["status"] == "NEW"

        document_notes_response = client.get(
            f"/api/v1/documents/{document['document_id']}/field-notes",
            headers=headers,
        )
        assert document_notes_response.status_code == 200
        assert any(note["note_id"] == created["note_id"] for note in document_notes_response.json())

        filtered_response = client.get(
            "/api/v1/field-notes",
            headers=headers,
            params={"documentId": document["document_id"], "status": "NEW"},
        )
        assert filtered_response.status_code == 200
        assert any(note["note_id"] == created["note_id"] for note in filtered_response.json())

        review_response = client.patch(
            f"/api/v1/field-notes/{created['note_id']}",
            headers=headers,
            json={
                "status": "ANALYZED",
                "normalizedContent": "Field issue normalized for manager review.",
                "analysisContent": "Repeated field note should be checked against the work standard.",
            },
        )
        assert review_response.status_code == 200, review_response.text
        reviewed = review_response.json()
        assert reviewed["status"] == "ANALYZED"
        assert reviewed["normalized_content"] == "Field issue normalized for manager review."
        assert reviewed["analysis_content"] == (
            "Repeated field note should be checked against the work standard."
        )


def test_field_note_attachment_registration_and_list() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        note_response = client.post(
            "/api/v1/field-notes",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": f"Field note with attachment {uuid4().hex}",
            },
        )
        assert note_response.status_code == 201, note_response.text
        note = note_response.json()
        file_bytes = b"field note attachment text"

        response = client.post(
            f"/api/v1/field-notes/{note['note_id']}/attachments",
            headers=headers,
            data={
                "caption": "현장 확인용 텍스트 첨부",
                "createdBy": "user-admin",
            },
            files={"file": ("field-note-attachment.txt", file_bytes, "text/plain")},
        )

        assert response.status_code == 201, response.text
        attachment = response.json()
        assert attachment["attachment_id"].startswith("att_")
        assert attachment["note_id"] == note["note_id"]
        assert attachment["attachment_type"] == "document"
        assert attachment["caption"] == "현장 확인용 텍스트 첨부"
        assert attachment["created_by"] == "user-admin"
        assert attachment["file"]["original_filename"] == "field-note-attachment.txt"
        assert attachment["file"]["extension"] == ".txt"
        assert attachment["file"]["file_family"] == "text"
        assert attachment["file"]["size_bytes"] == len(file_bytes)
        assert attachment["file"]["hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
        assert attachment["file"]["storage_key"].startswith(
            f"field-notes/{note['note_id']}/attachments/"
        )

        list_response = client.get(
            f"/api/v1/field-notes/{note['note_id']}/attachments",
            headers=headers,
        )
        assert list_response.status_code == 200, list_response.text
        assert any(item["attachment_id"] == attachment["attachment_id"] for item in list_response.json())

        with client.app.state.database.session() as session:
            row = session.execute(
                select(FieldNoteAttachment, FileObject)
                .join(FileObject, FieldNoteAttachment.file_object_id == FileObject.id)
                .where(FieldNoteAttachment.attachment_id == attachment["attachment_id"])
            ).first()
            assert row is not None
            saved_attachment, saved_file = row
            assert saved_attachment.note_id == note["note_id"]
            assert saved_file.original_filename == "field-note-attachment.txt"
            assert saved_file.size_bytes == len(file_bytes)
            assert saved_file.hash_sha256 == hashlib.sha256(file_bytes).hexdigest()


def test_field_note_attachment_rejects_unknown_note_id() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes/note-does-not-exist/attachments",
            headers=auth_headers(client),
            files={"file": ("field-note-attachment.txt", b"attachment", "text/plain")},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Field note not found."


def test_field_note_attachment_rejects_unsupported_file_type() -> None:
    with create_test_client() as client:
        document = create_document(client)
        headers = auth_headers(client)
        note_response = client.post(
            "/api/v1/field-notes",
            headers=headers,
            json={
                "documentId": document["document_id"],
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": f"Field note with invalid attachment {uuid4().hex}",
            },
        )
        assert note_response.status_code == 201, note_response.text
        note = note_response.json()

        response = client.post(
            f"/api/v1/field-notes/{note['note_id']}/attachments",
            headers=headers,
            files={"file": ("field-note-attachment.exe", b"attachment", "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Attachment file type is not allowed."


def test_field_note_requires_a_target() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes",
            headers=auth_headers(client),
            json={
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": "This note has no target.",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A field note must reference documentId, structureItemId, or workRecordId."
    )


def test_field_note_requires_authentication() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes",
            json={
                "documentId": "doc-does-not-exist",
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": "This unauthenticated note should be rejected.",
            },
        )

    assert response.status_code == 401


def test_field_note_rejects_unknown_document() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes",
            headers=auth_headers(client),
            json={
                "documentId": "doc-does-not-exist",
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": "This note references an unknown document.",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
