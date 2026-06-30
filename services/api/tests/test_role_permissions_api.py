from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "role-permission-tests"
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


def create_role_user(client: TestClient, role: str) -> UserAccount:
    suffix = uuid4().hex
    username = f"{role.replace('-', '_')}-{suffix}"
    account = UserAccount(
        user_id=f"user-{username}",
        username=username,
        login_id=username,
        display_name=f"Permission Test {role}",
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


def auth_headers(client: TestClient, account: UserAccount) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": account.username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def post_document(client: TestClient, headers: dict[str, str], title: str):
    suffix = uuid4().hex[:8]
    return client.post(
        "/api/v1/documents",
        headers=headers,
        data={
            "title": title,
            "documentType": "work_instruction",
            "changeReason": "Role permission test document registration.",
            "tags": ["role-permission", suffix],
        },
        files={"file": (f"role-permission-{suffix}.txt", b"role permission", "text/plain")},
    )


def test_document_registration_allows_admin_foreman_and_team_lead_roles() -> None:
    with create_test_client() as client:
        for role in ["document-admin", "line-foreman", "team-lead"]:
            account = create_role_user(client, role)
            response = post_document(
                client,
                auth_headers(client, account),
                f"Allowed document registration for {role}",
            )

            assert response.status_code == 201, response.text
            assert response.json()["document_id"].startswith("doc_")


def test_team_member_can_create_field_comment_but_cannot_register_document() -> None:
    with create_test_client() as client:
        lead = create_role_user(client, "team-lead")
        member = create_role_user(client, "team-member")

        document_response = post_document(
            client,
            auth_headers(client, lead),
            "Team member field comment target",
        )
        assert document_response.status_code == 201, document_response.text
        document = document_response.json()

        denied_document_response = post_document(
            client,
            auth_headers(client, member),
            "Team member rejected document registration",
        )
        assert denied_document_response.status_code == 403, denied_document_response.text

        field_comment_response = client.post(
            "/api/v1/field-comments",
            headers=auth_headers(client, member),
            json={
                "documentId": document["document_id"],
                "documentVersionId": document["latest_version"]["version_id"],
                "commentType": "issue",
                "inputMode": "free_text",
                "rawContent": "Team member can leave a field comment.",
                "authorId": member.user_id,
            },
        )
        assert field_comment_response.status_code == 201, field_comment_response.text
        assert field_comment_response.json()["raw_content"] == "Team member can leave a field comment."


def test_team_member_cannot_register_document_version_or_change_tags() -> None:
    with create_test_client() as client:
        lead = create_role_user(client, "team-lead")
        member = create_role_user(client, "team-member")
        document_response = post_document(
            client,
            auth_headers(client, lead),
            "Document write boundary target",
        )
        assert document_response.status_code == 201, document_response.text
        document_id = document_response.json()["document_id"]

        version_response = client.post(
            f"/api/v1/documents/{document_id}/versions",
            headers=auth_headers(client, member),
            data={"changeReason": "Team member should not add a document version."},
            files={"file": ("member-version.txt", b"member version", "text/plain")},
        )
        assert version_response.status_code == 403, version_response.text

        tag_response = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=auth_headers(client, member),
            json=["member-denied"],
        )
        assert tag_response.status_code == 403, tag_response.text


def test_document_access_log_read_is_admin_only() -> None:
    with create_test_client() as client:
        admin = create_role_user(client, "admin")
        member = create_role_user(client, "team-member")
        document_response = post_document(
            client,
            auth_headers(client, admin),
            "Access log permission target",
        )
        assert document_response.status_code == 201, document_response.text
        document = document_response.json()

        create_log_response = client.post(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=auth_headers(client, member),
            json={
                "documentVersionId": document["latest_version"]["version_id"],
                "action": "view_started",
                "actorId": member.user_id,
            },
        )
        assert create_log_response.status_code == 201, create_log_response.text

        denied_list_response = client.get(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=auth_headers(client, member),
        )
        assert denied_list_response.status_code == 403, denied_list_response.text

        allowed_list_response = client.get(
            f"/api/v1/documents/{document['document_id']}/access-logs",
            headers=auth_headers(client, admin),
        )
        assert allowed_list_response.status_code == 200, allowed_list_response.text
        assert any(
            item["log_id"] == create_log_response.json()["log_id"]
            for item in allowed_list_response.json()
        )


def test_tag_creation_requires_document_write_role() -> None:
    with create_test_client() as client:
        lead = create_role_user(client, "team-lead")
        member = create_role_user(client, "team-member")

        denied_response = client.post(
            "/api/v1/tags",
            headers=auth_headers(client, member),
            json={"name": f"member-denied-{uuid4().hex[:8]}", "tagType": "custom"},
        )
        assert denied_response.status_code == 403, denied_response.text

        tag_name = f"lead-allowed-{uuid4().hex[:8]}"
        allowed_response = client.post(
            "/api/v1/tags",
            headers=auth_headers(client, lead),
            json={"name": tag_name, "tagType": "custom"},
        )
        assert allowed_response.status_code == 201, allowed_response.text
        assert allowed_response.json()["name"] == tag_name
