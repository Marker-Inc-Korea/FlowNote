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
    AndroidDocumentViewGrant,
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
TEST_STORAGE_ROOT = API_ROOT / "storage" / "android-view-tests"
PASSWORD = "android-view-test-password"


def create_client(*, expires_seconds: int = 60, max_bytes: int = 1024 * 1024) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        storage_root=str(TEST_STORAGE_ROOT),
        android_view_grant_expires_seconds=expires_seconds,
        android_view_max_bytes=max_bytes,
        android_view_max_pdf_pages=2,
        android_view_auto_close_seconds=30,
    )
    return TestClient(create_app(settings))


def login(client: TestClient, role: str = "viewer", *, device_status: str = "ACTIVE"):
    suffix = uuid4().hex
    user_id = f"user-aview-{suffix}"
    username = f"aview-{suffix}"
    device_id = f"android-{suffix}"
    with client.app.state.database.session() as session:
        session.add(UserAccount(
            user_id=user_id, username=username, login_id=username,
            display_name="Android View Test", role=role,
            password_hash=hash_password_for_dev(PASSWORD), is_active=True, status="ACTIVE"))
        session.add(TerminalDevice(
            device_id=device_id, device_name="Android View Test Device",
            device_mode="viewer", status=device_status))
        session.commit()
    response = client.post("/api/v1/auth/login", json={
        "username": username, "password": PASSWORD, "deviceId": device_id})
    return user_id, device_id, response


def document(client: TestClient, content: bytes = b"FlowNote secure text\n", *,
             extension: str = ".txt", mime_type: str = "text/plain"):
    suffix = uuid4().hex
    document_id = f"doc_aview_{suffix}"
    version_id = f"ver_aview_{suffix}"
    key = f"documents/{document_id}/v1/body{extension}"
    path = TEST_STORAGE_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    with client.app.state.database.session() as session:
        file_object = FileObject(
            storage_type="local", storage_key=key, original_filename=f"sensitive-name{extension}",
            extension=extension, mime_type=mime_type, size_bytes=len(content),
            hash_sha256=hashlib.sha256(content).hexdigest())
        session.add(file_object)
        session.flush()
        session.add(Document(
            document_id=document_id, title="Android secure view", document_type="work_instruction",
            status="PUBLISHED", latest_version_id=version_id, published_version_id=version_id))
        session.add(DocumentVersion(
            version_id=version_id, document_id=document_id, file_object_id=file_object.id,
            version_no=1, change_reason="Android view test", version_status="PUBLISHED",
            is_latest=True, is_published=True, published_at=datetime.now(timezone.utc)))
        session.commit()
    return document_id, version_id, path


def headers(login_response):
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def grant(client, auth_headers, document_id, version_id):
    return client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/android-view-grants",
        headers=auth_headers)


def test_android_view_txt_stream_is_one_time_integrity_checked_and_audited():
    with create_client() as client:
        user_id, device_id, signed_in = login(client)
        auth = headers(signed_in)
        document_id, version_id, _ = document(client)
        issued = grant(client, auth, document_id, version_id)
        assert issued.status_code == 201, issued.text
        contract = issued.json()
        assert "filename" not in contract
        assert contract["media_kind"] == "TEXT"
        streamed = client.get(contract["stream_url"], headers=auth)
        assert streamed.status_code == 200
        assert streamed.content == b"FlowNote secure text\n"
        assert streamed.headers["content-disposition"] == "inline"
        assert streamed.headers["cache-control"].startswith("no-store")
        assert streamed.headers["x-content-sha256"] == hashlib.sha256(streamed.content).hexdigest()
        assert client.get(contract["stream_url"], headers=auth).status_code == 410
        with client.app.state.database.session() as session:
            rows = session.scalars(select(DocumentAccessLog).where(
                DocumentAccessLog.document_id == document_id,
                DocumentAccessLog.actor_id == user_id)).all()
        assert {"android_view_granted", "android_view_stream_started", "android_view_completed",
                "android_view_expired"} <= {
            row.action for row in rows}
        assert {row.device_id for row in rows} == {device_id}
        assert all(row.document_version_id == version_id for row in rows)


def test_android_view_requires_allowed_role_and_active_approved_device():
    with create_client() as client:
        document_id, version_id, _ = document(client)
        _, _, denied = login(client, role="system-admin")
        assert denied.status_code == 200
        assert grant(client, headers(denied), document_id, version_id).status_code == 403

        _, _, inactive = login(client, device_status="INACTIVE")
        assert inactive.status_code == 403

        # Login without a device is valid for non-terminal clients, but Android viewing is not.
        username_suffix = uuid4().hex
        with client.app.state.database.session() as session:
            session.add(UserAccount(
                user_id=f"no-device-{username_suffix}", username=f"no-device-{username_suffix}",
                login_id=f"no-device-{username_suffix}", display_name="No Device", role="viewer",
                password_hash=hash_password_for_dev(PASSWORD), is_active=True, status="ACTIVE"))
            session.commit()
        plain_login = client.post("/api/v1/auth/login", json={
            "username": f"no-device-{username_suffix}", "password": PASSWORD})
        assert grant(client, headers(plain_login), document_id, version_id).status_code == 403


def test_android_view_rechecks_expiry_device_publication_and_file_integrity():
    with create_client() as client:
        _, device_id, signed_in = login(client)
        auth = headers(signed_in)
        document_id, version_id, path = document(client)

        expired = grant(client, auth, document_id, version_id).json()
        with client.app.state.database.session() as session:
            row = session.scalar(select(AndroidDocumentViewGrant).where(
                AndroidDocumentViewGrant.grant_id == expired["grant_id"]))
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        assert client.get(expired["stream_url"], headers=auth).status_code == 410

        inactive = grant(client, auth, document_id, version_id).json()
        with client.app.state.database.session() as session:
            device_row = session.scalar(select(TerminalDevice).where(TerminalDevice.device_id == device_id))
            device_row.status = "INACTIVE"
            session.commit()
        assert client.get(inactive["stream_url"], headers=auth).status_code == 403
        with client.app.state.database.session() as session:
            device_row = session.scalar(select(TerminalDevice).where(TerminalDevice.device_id == device_id))
            device_row.status = "ACTIVE"
            session.commit()

        unpublished = grant(client, auth, document_id, version_id).json()
        with client.app.state.database.session() as session:
            doc = session.scalar(select(Document).where(Document.document_id == document_id))
            doc.status = "WORKING"
            doc.published_version_id = None
            session.commit()
        assert client.get(unpublished["stream_url"], headers=auth).status_code == 409

        with client.app.state.database.session() as session:
            doc = session.scalar(select(Document).where(Document.document_id == document_id))
            doc.status = "PUBLISHED"
            doc.published_version_id = version_id
            session.commit()
        changed = grant(client, auth, document_id, version_id).json()
        path.write_bytes(path.read_bytes() + b"tampered")
        assert client.get(changed["stream_url"], headers=auth).status_code == 409


def test_android_view_supports_pdf_image_text_and_rejects_damage_size_and_format():
    png = b"\x89PNG\r\n\x1a\n" + b"valid-enough-for-server-contract"
    pdf = b"%PDF-1.4\n1 0 obj <</Type /Page>> endobj\n%%EOF\n"
    with create_client(max_bytes=64) as client:
        _, _, signed_in = login(client)
        auth = headers(signed_in)
        for content, extension, mime, expected_kind in (
            (b"valid utf-8", ".txt", "text/plain", "TEXT"),
            (png, ".png", "image/png", "IMAGE"),
            (pdf, ".pdf", "application/pdf", "PDF"),
        ):
            document_id, version_id, _ = document(
                client, content, extension=extension, mime_type=mime)
            response = grant(client, auth, document_id, version_id)
            assert response.status_code == 201, response.text
            assert response.json()["media_kind"] == expected_kind

        damaged_id, damaged_version, _ = document(
            client, b"not-a-pdf", extension=".pdf", mime_type="application/pdf")
        assert grant(client, auth, damaged_id, damaged_version).status_code == 415
        large_id, large_version, _ = document(client, b"x" * 65)
        assert grant(client, auth, large_id, large_version).status_code == 413
        unsupported_id, unsupported_version, _ = document(
            client, b"office", extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert grant(client, auth, unsupported_id, unsupported_version).status_code == 415
