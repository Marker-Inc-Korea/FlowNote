from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"


def create_test_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        storage_root=str(API_ROOT / "storage" / "field-comment-dashboard-tests"),
    )
    return TestClient(create_app(settings))


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_review_dashboard_exposes_counts_owners_and_next_actions() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        marker = uuid4().hex
        document = client.post(
            "/api/v1/documents",
            headers=headers,
            data={
                "title": f"FieldComment 대시보드 검증 {marker}",
                "documentType": "work_instruction",
                "changeReason": "FieldComment 대시보드 API 검증",
            },
            files={"file": (f"dashboard-{marker}.txt", b"dashboard test", "text/plain")},
        )
        assert document.status_code == 201, document.text
        created = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "rawContent": f"안전·품질 위험 대시보드 검증 {marker}",
                "documentId": document.json()["document_id"],
                "documentVersionId": document.json()["latest_version"]["version_id"],
                "authorId": "user-admin",
                "signalLevel": "red",
                "category": "quality",
            },
        )
        assert created.status_code == 201, created.text
        due = client.patch(
            f"/api/v1/field-comments/{created.json()['comment_id']}",
            headers=headers,
            json={"reviewDueAt": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
        )
        assert due.status_code == 200, due.text

        response = client.get("/api/v1/field-comments/review-dashboard", headers=headers)
        assert response.status_code == 200, response.text
        dashboard = response.json()

        assert dashboard["total_count"] >= 1
        assert dashboard["unreviewed_count"] >= 1
        assert dashboard["safety_quality_risk_count"] >= 1
        assert dashboard["report_unlinked_count"] >= 1
        assert dashboard["unassigned_count"] >= 1
        assert dashboard["overdue_count"] >= 1
        assert dashboard["counts_by_status"]["NEW"] >= 1
        actions = {item["code"]: item for item in dashboard["actions"]}
        assert actions["SAFETY_QUALITY_RISK"]["owner"]
        assert actions["SAFETY_QUALITY_RISK"]["next_action"]
        assert actions["SAFETY_QUALITY_RISK"]["workbench_filter"] == "HIGH_RISK"
        assert actions["OVERDUE"]["workbench_filter"] == "OVERDUE"


def test_review_dashboard_rejects_viewer_without_analysis_role() -> None:
    with create_test_client() as client:
        suffix = uuid4().hex[:10]
        username = f"dashboard-field-user-{suffix}"
        with client.app.state.database.session() as session:
            session.add(UserAccount(
                user_id=f"user-{suffix}",
                username=username,
                login_id=username,
                display_name="대시보드 권한 검증 현장 사용자",
                role="viewer",
                password_hash=hash_password_for_dev("1234"),
                is_active=True,
                status="ACTIVE",
            ))
            session.commit()
        login = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "1234"},
        )
        assert login.status_code == 200, login.text

        response = client.get(
            "/api/v1/field-comments/review-dashboard",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "PERMISSION_DENIED"
