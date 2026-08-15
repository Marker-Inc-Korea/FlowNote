from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "work-sequence-tests"
PUBLIC_API_OPERATIONS = {
    ("GET", "/"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/db"),
    ("GET", "/api/v1/health/sync-manifest"),
    ("GET", "/api/v1/sync/manifest"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
}
OPENAPI_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


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


def test_app_factory_registers_root_with_its_own_settings() -> None:
    with create_test_client() as client:
        response = client.get("/")

    assert response.status_code == 200, response.text
    assert response.json() == {"service": "FlowNote API", "environment": "test"}


def test_openapi_exposes_only_the_explicit_public_operations_without_bearer_auth() -> None:
    with create_test_client() as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    public_operations = {
        (method.upper(), path)
        for path, path_item in paths.items()
        for method, operation in path_item.items()
        if method in OPENAPI_HTTP_METHODS and not operation.get("security")
    }
    assert public_operations == PUBLIC_API_OPERATIONS


def test_completed_feature_requests_reject_blank_required_text() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)

        tag_response = client.post(
            "/api/v1/tags",
            headers=headers,
            json={"name": "   ", "tagType": "custom"},
        )
        assert tag_response.status_code == 422, tag_response.text

        field_comment_response = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={"rawContent": "   "},
        )
        assert field_comment_response.status_code == 422, field_comment_response.text

        account_response = client.post(
            "/api/v1/server-accounts",
            headers=headers,
            json={
                "username": "   ",
                "display_name": "공백 계정 검증",
                "role": "viewer",
                "temporary_password": "validation-password",
                "reason": "입력 검증",
            },
        )
        assert account_response.status_code == 422, account_response.text

        account_reason_response = client.post(
            "/api/v1/server-accounts",
            headers=headers,
            json={
                "username": f"blank-reason-{suffix}",
                "display_name": "공백 사유 검증",
                "role": "viewer",
                "temporary_password": "validation-password",
                "reason": "   ",
            },
        )
        assert account_reason_response.status_code == 422, account_reason_response.text

        channel_response = client.post(
            "/api/v1/notification-channels",
            headers=headers,
            json={"name": "   ", "channelType": "LINE"},
        )
        assert channel_response.status_code == 422, channel_response.text

        report_response = client.post(
            "/api/v1/reports/drafts",
            headers=headers,
            json={
                "reportType": "PRODUCTION",
                "title": "   ",
                "sources": [{"sourceType": "DOCUMENT", "sourceId": "validation-source"}],
            },
        )
        assert report_response.status_code == 422, report_response.text

        delivery_response = client.post(
            "/api/v1/work-sequence-boards/missing/notification-candidates/missing/deliveries",
            headers=headers,
            json={
                "channelId": "validation-channel",
                "deliveryMode": "CHANNEL",
                "recipientIds": ["validation-user"],
                "title": "   ",
                "body": "검증 본문",
                "reason": "입력 검증",
                "baseBoardRevision": 1,
                "idempotencyKey": f"blank-delivery:{suffix}",
            },
        )
        assert delivery_response.status_code == 422, delivery_response.text

        template_response = client.post(
            "/api/v1/work-sequence-delivery-templates",
            headers=headers,
            json={"name": "   ", "title": "검증 제목", "body": "검증 본문"},
        )
        assert template_response.status_code == 422, template_response.text

        board_response = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": "   ", "idempotencyKey": f"blank-board:{suffix}"},
        )
        assert board_response.status_code == 422, board_response.text

        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": "항목 공백 검증", "idempotencyKey": f"item-board:{suffix}"},
        ).json()
        item_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": "   ",
                "idempotencyKey": f"blank-item:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        )
        assert item_response.status_code == 422, item_response.text

        key_response = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": "공백 키 검증", "idempotencyKey": "   "},
        )
        assert key_response.status_code == 422, key_response.text

        handover_response = client.post(
            "/api/v1/handovers",
            headers=headers,
            json={
                "channelId": "validation-channel",
                "title": "   ",
                "body": "검증 본문",
                "recipientIds": ["user-admin"],
            },
        )
        assert handover_response.status_code == 422, handover_response.text

        correction_response = client.post(
            "/api/v1/reports/missing/corrections",
            headers=headers,
            json={
                "correctionReason": "   ",
                "baseReportRevision": 1,
                "mutationKey": f"blank-correction:{suffix}",
            },
        )
        assert correction_response.status_code == 422, correction_response.text

        approval_response = client.post(
            "/api/v1/document-approvals",
            headers=headers,
            json={
                "documentId": "missing",
                "versionId": "missing",
                "baseDocumentRevision": 1,
                "sourceFileHashSha256": "0" * 64,
                "reviewerRole": "admin",
                "reason": "   ",
                "mutationKey": f"blank-approval:{suffix}",
            },
        )
        assert approval_response.status_code == 422, approval_response.text

        reconciliation_response = client.post(
            "/api/v1/sync/reconciliation-runs",
            headers=headers,
            json={
                "clientId": "   ",
                "triggerReason": "manual",
                "items": [],
            },
        )
        assert reconciliation_response.status_code == 422, reconciliation_response.text


def test_hold_status_requires_auditable_reason_without_advancing_revision() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"보류 사유 검증 {suffix}", "idempotencyKey": f"board:{suffix}"},
        ).json()
        board = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": "검증 항목",
                "idempotencyKey": f"item:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        revision_before = board["board_revision"]
        item_id = board["items"][0]["item_id"]

        response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{item_id}/status",
            headers=headers,
            json={
                "status": "HOLD",
                "idempotencyKey": f"hold:{suffix}",
                "baseBoardRevision": revision_before,
            },
        )
        assert response.status_code == 422, response.text

        latest = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}",
            headers=headers,
        )
        assert latest.status_code == 200, latest.text
        assert latest.json()["board_revision"] == revision_before
        assert latest.json()["items"][0]["status"] == "WAITING"
