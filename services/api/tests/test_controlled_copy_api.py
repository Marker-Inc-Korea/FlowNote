from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import (
    ActivityHistory,
    ControlledCopyGrant,
    Document,
    DocumentAccessLog,
    DocumentVersion,
    FileObject,
    TerminalDevice,
    UserAccount,
)
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "controlled-copy-tests"
PASSWORD = "controlled-copy-test-password"
ALLOWED_ROLES = {
    "admin",
    "manager",
    "system-admin",
    "document-admin",
    "assistant-manager",
    "department-manager",
}
DENIED_ROLES = {"viewer", "line-foreman", "team-lead", "team-member"}


def create_client(*, expires_seconds: int = 60, max_bytes: int = 1024 * 1024) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        storage_root=str(TEST_STORAGE_ROOT),
        controlled_copy_ticket_expires_seconds=expires_seconds,
        controlled_copy_max_bytes=max_bytes,
    )
    return TestClient(create_app(settings))


def ensure_user(
    client: TestClient,
    role: str,
    *,
    suffix: str | None = None,
    device_id: str | None = None,
) -> tuple[str, dict[str, str]]:
    suffix = suffix or uuid4().hex[:10]
    user_id = f"user-copy-{role}-{suffix}"
    username = f"copy-{role}-{suffix}"
    with client.app.state.database.session() as session:
        session.add(
            UserAccount(
                user_id=user_id,
                username=username,
                login_id=username,
                display_name=f"Controlled Copy {role}",
                role=role,
                password_hash=hash_password_for_dev(PASSWORD),
                is_active=True,
                status="ACTIVE",
            )
        )
        if device_id:
            session.add(
                TerminalDevice(
                    device_id=device_id,
                    device_name="Controlled Copy Test Device",
                    device_mode="admin_support",
                    status="ACTIVE",
                )
            )
        session.commit()
    login_payload = {"username": username, "password": PASSWORD}
    if device_id:
        login_payload["deviceId"] = device_id
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200, response.text
    return user_id, {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_published_document(
    client: TestClient,
    *,
    content: bytes = b"FlowNote controlled copy integrity sample\n",
    storage_key: str | None = None,
    published: bool = True,
    deleted: bool = False,
) -> tuple[str, str, bytes]:
    suffix = uuid4().hex
    document_id = f"doc_copy_{suffix}"
    version_id = f"ver_copy_{suffix}"
    filename = f"controlled-copy-{suffix}.txt"
    key = storage_key or f"documents/{document_id}/v1/{filename}"
    if storage_key is None:
        path = TEST_STORAGE_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with client.app.state.database.session() as session:
        file_object = FileObject(
            storage_type="local",
            storage_key=key,
            original_filename=filename,
            extension=".txt",
            mime_type="text/plain",
            file_family="text",
            size_bytes=len(content),
            hash_sha256=hashlib.sha256(content).hexdigest(),
        )
        session.add(file_object)
        session.flush()
        document = Document(
            document_id=document_id,
            title=f"Controlled copy {suffix}",
            document_type="work_instruction",
            status="PUBLISHED" if published else "WORKING",
            latest_version_id=version_id,
            published_version_id=version_id if published else None,
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )
        session.add(document)
        session.add(
            DocumentVersion(
                version_id=version_id,
                document_id=document_id,
                file_object_id=file_object.id,
                version_no=1,
                version_label="v1",
                change_reason="Controlled copy API test.",
                version_status="PUBLISHED" if published else "WORKING",
                is_latest=True,
                is_published=published,
                published_at=datetime.now(timezone.utc) if published else None,
            )
        )
        session.commit()
    return document_id, version_id, content


def request_grant(client: TestClient, headers: dict[str, str], document_id: str, version_id: str):
    return client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/controlled-copy",
        headers=headers,
    )


def test_controlled_copy_role_policy_matches_server_policy() -> None:
    with create_client() as client:
        document_id, version_id, _ = create_published_document(client)
        for role in sorted(ALLOWED_ROLES | DENIED_ROLES):
            _, headers = ensure_user(client, role)
            response = request_grant(client, headers, document_id, version_id)
            expected = 201 if role in ALLOWED_ROLES else 403
            assert response.status_code == expected, (role, response.text)
            if response.status_code == 201:
                assert "storage" not in response.text.lower()
                assert response.json()["document_version_id"] == version_id


def test_controlled_copy_download_is_one_time_hash_verified_and_audited() -> None:
    with create_client() as client:
        device_id = f"device-copy-{uuid4().hex}"
        user_id, headers = ensure_user(client, "admin", device_id=device_id)
        document_id, version_id, content = create_published_document(client)
        grant_response = request_grant(client, headers, document_id, version_id)
        assert grant_response.status_code == 201, grant_response.text
        grant = grant_response.json()

        download = client.get(grant["download_url"], headers=headers)
        assert download.status_code == 200, download.text
        assert download.content == content
        assert download.headers["x-content-sha256"] == hashlib.sha256(content).hexdigest()
        assert download.headers["accept-ranges"] == "none"
        assert "attachment;" in download.headers["content-disposition"]
        assert str(TEST_STORAGE_ROOT) not in download.text

        reused = client.get(grant["download_url"], headers=headers)
        assert reused.status_code == 410

        with client.app.state.database.session() as session:
            access_actions = set(
                session.scalars(
                    select(DocumentAccessLog.action).where(
                        DocumentAccessLog.document_id == document_id,
                        DocumentAccessLog.actor_id == user_id,
                    )
                ).all()
            )
            activity_actions = set(
                session.scalars(
                    select(ActivityHistory.event_type).where(
                        ActivityHistory.actor_id == user_id,
                        ActivityHistory.target_id.in_([document_id, version_id]),
                    )
                ).all()
            )
            device_ids = set(
                session.scalars(
                    select(DocumentAccessLog.device_id).where(
                        DocumentAccessLog.document_id == document_id,
                        DocumentAccessLog.actor_id == user_id,
                    )
                ).all()
            )
            reasons = session.scalars(
                select(DocumentAccessLog.reason).where(
                    DocumentAccessLog.document_id == document_id,
                    DocumentAccessLog.actor_id == user_id,
                )
            ).all()
            activity_messages = session.scalars(
                select(ActivityHistory.message).where(
                    ActivityHistory.actor_id == user_id,
                    ActivityHistory.target_id.in_([document_id, version_id]),
                )
            ).all()
        assert {
            "controlled_copy_requested",
            "controlled_copy_allowed",
            "controlled_copy_completed",
            "controlled_copy_blocked",
        } <= access_actions
        assert access_actions <= activity_actions
        assert device_ids == {device_id}
        assert all(reasons)
        assert all(device_id in message for message in activity_messages)


def test_controlled_copy_rejects_other_user_session_range_and_expiry() -> None:
    with create_client() as client:
        _, owner_headers = ensure_user(client, "manager")
        _, other_headers = ensure_user(client, "manager")
        document_id, version_id, _ = create_published_document(client)

        other_user_grant = request_grant(client, owner_headers, document_id, version_id).json()
        assert client.get(other_user_grant["download_url"], headers=other_headers).status_code == 403
        assert client.get(other_user_grant["download_url"], headers=owner_headers).status_code == 200

        range_grant = request_grant(client, owner_headers, document_id, version_id).json()
        ranged = client.get(range_grant["download_url"], headers={**owner_headers, "Range": "bytes=0-4"})
        assert ranged.status_code == 416
        assert client.get(range_grant["download_url"], headers=owner_headers).status_code == 410

        expired_grant = request_grant(client, owner_headers, document_id, version_id).json()
        with client.app.state.database.session() as session:
            row = session.scalar(
                select(ControlledCopyGrant).where(
                    ControlledCopyGrant.grant_id == expired_grant["grant_id"]
                )
            )
            assert row is not None
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(row)
            session.commit()
        assert client.get(expired_grant["download_url"], headers=owner_headers).status_code == 410


def test_controlled_copy_rejects_unpublished_missing_mismatched_and_unsafe_paths() -> None:
    with create_client() as client:
        _, headers = ensure_user(client, "document-admin")
        published_id, published_version_id, _ = create_published_document(client)
        other_id, other_version_id, _ = create_published_document(client)
        unpublished_id, unpublished_version_id, _ = create_published_document(client, published=False)
        deleted_id, deleted_version_id, _ = create_published_document(client, deleted=True)
        unsafe_id, unsafe_version_id, _ = create_published_document(
            client,
            storage_key=f"../outside-controlled-copy-{uuid4().hex}.txt",
        )

        assert request_grant(client, headers, published_id, other_version_id).status_code == 404
        assert request_grant(client, headers, other_id, published_version_id).status_code == 404
        assert request_grant(client, headers, unpublished_id, unpublished_version_id).status_code == 403
        assert request_grant(client, headers, deleted_id, deleted_version_id).status_code == 404
        assert request_grant(client, headers, unsafe_id, unsafe_version_id).status_code == 409
        assert request_grant(client, headers, "doc_missing", "ver_missing").status_code == 404


def test_controlled_copy_rejects_file_changed_after_grant() -> None:
    with create_client() as client:
        _, headers = ensure_user(client, "system-admin")
        document_id, version_id, content = create_published_document(client)
        grant = request_grant(client, headers, document_id, version_id).json()
        with client.app.state.database.session() as session:
            version = session.scalar(select(DocumentVersion).where(DocumentVersion.version_id == version_id))
            file_object = session.get(FileObject, version.file_object_id)
            path = TEST_STORAGE_ROOT / file_object.storage_key
        path.write_bytes(content + b"tampered")
        assert client.get(grant["download_url"], headers=headers).status_code == 409
        with client.app.state.database.session() as session:
            access_failed = session.scalar(
                select(DocumentAccessLog.id).where(
                    DocumentAccessLog.document_id == document_id,
                    DocumentAccessLog.document_version_id == version_id,
                    DocumentAccessLog.action == "controlled_copy_failed",
                )
            )
            activity_failed = session.scalar(
                select(ActivityHistory.id).where(
                    ActivityHistory.target_id == version_id,
                    ActivityHistory.event_type == "controlled_copy_failed",
                )
            )
        assert access_failed is not None
        assert activity_failed is not None


def test_controlled_copy_enforces_configured_size_limit() -> None:
    with create_client(max_bytes=16) as client:
        _, headers = ensure_user(client, "department-manager")
        document_id, version_id, _ = create_published_document(client, content=b"x" * 17)
        response = request_grant(client, headers, document_id, version_id)
        assert response.status_code == 413
