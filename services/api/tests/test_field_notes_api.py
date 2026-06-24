from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
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


def create_document(client: TestClient) -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/documents",
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
        content = f"Field note API raw content {uuid4().hex}"

        response = client.post(
            "/api/v1/field-notes",
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
            f"/api/v1/documents/{document['document_id']}/field-notes"
        )
        assert document_notes_response.status_code == 200
        assert any(note["note_id"] == created["note_id"] for note in document_notes_response.json())

        filtered_response = client.get(
            "/api/v1/field-notes",
            params={"documentId": document["document_id"], "status": "NEW"},
        )
        assert filtered_response.status_code == 200
        assert any(note["note_id"] == created["note_id"] for note in filtered_response.json())

        review_response = client.patch(
            f"/api/v1/field-notes/{created['note_id']}",
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


def test_field_note_requires_a_target() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes",
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


def test_field_note_rejects_unknown_document() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/field-notes",
            json={
                "documentId": "doc-does-not-exist",
                "noteType": "issue",
                "inputMode": "free_text",
                "rawContent": "This note references an unknown document.",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
