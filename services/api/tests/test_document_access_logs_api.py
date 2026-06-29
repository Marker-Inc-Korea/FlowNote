from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import DocumentAccessLog, UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "document-access-log-tests"


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


def create_user(client: TestClient) -> UserAccount:
    suffix = uuid4().hex
    account = UserAccount(
        user_id=f"user-access-log-{suffix}",
        username=f"access-log-user-{suffix}",
        login_id=f"access-log-user-{suffix}",
        display_name="Access Log Test User",
        role="viewer",
        password_hash=hash_password_for_dev("correct-password"),
        is_active=True,
        status="ACTIVE",
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def create_document(client: TestClient) -> dict:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/documents",
        headers=auth_headers(client),
        data={
            "title": f"Access log target {suffix}",
            "documentType": "work_instruction",
            "changeReason": "Create a document for access log API testing.",
        },
        files={"file": (f"access-log-target-{suffix}.txt", b"access log target", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_document_access_logs() -> None:
    with create_test_client() as client:
        account = create_user(client)
        document = create_document(client)
        headers = auth_headers(client)
        version_id = document["latest_version"]["version_id"]

        started_response = client.post(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=headers,
            json={
                "documentVersionId": version_id,
                "action": "view_started",
                "actorId": account.user_id,
                "clientIp": "127.0.0.1",
                "userAgent": "FlowNote.Windows.SmokeTests",
            },
        )
        assert started_response.status_code == 201, started_response.text
        started = started_response.json()
        assert started["document_id"] == document["document_id"]
        assert started["document_version_id"] == version_id
        assert started["action"] == "view_started"
        assert started["actor_id"] == account.user_id

        closed_response = client.post(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=headers,
            json={
                "documentVersionId": version_id,
                "action": "view_closed",
                "actorId": account.user_id,
            },
        )
        assert closed_response.status_code == 201, closed_response.text
        closed = closed_response.json()
        assert closed["action"] == "view_closed"

        list_response = client.get(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=headers,
        )
        assert list_response.status_code == 200
        logs = list_response.json()
        assert {log["log_id"] for log in logs} >= {started["log_id"], closed["log_id"]}

        with client.app.state.database.session() as session:
            saved = session.scalars(
                select(DocumentAccessLog).where(
                    DocumentAccessLog.document_id == document["document_id"]
                )
            ).all()
            assert len(saved) == 2


def test_document_access_log_rejects_version_from_another_document() -> None:
    with create_test_client() as client:
        first = create_document(client)
        second = create_document(client)

        response = client.post(
            f"/api/v1/documents/{first['document_id']}/access-logs",
            headers=auth_headers(client),
            json={
                "documentVersionId": second["latest_version"]["version_id"],
                "action": "view_started",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "documentVersionId must belong to documentId."


def test_document_access_log_requires_authentication() -> None:
    with create_test_client() as client:
        response = client.get("/api/v1/documents/doc-does-not-exist/access-logs")

    assert response.status_code == 401
