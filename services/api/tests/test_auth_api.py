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
TEST_STORAGE_ROOT = API_ROOT / "storage" / "auth-tests"


def create_test_client(*, access_token_expires_minutes: int = 480) -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
        access_token_expires_minutes=access_token_expires_minutes,
    )
    return TestClient(create_app(app_settings))


def create_login_user(
    client: TestClient,
    *,
    password: str = "correct-password",
    is_active: bool = True,
    account_status: str = "ACTIVE",
) -> UserAccount:
    suffix = uuid4().hex
    account = UserAccount(
        user_id=f"user-login-{suffix}",
        username=f"login-user-{suffix}",
        login_id=f"login-user-{suffix}",
        display_name="Login Test User",
        role="viewer",
        password_hash=hash_password_for_dev(password),
        is_active=is_active,
        status=account_status,
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def test_login_returns_mvp_user_payload_with_access_token() -> None:
    with create_test_client() as client:
        account = create_login_user(client)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["user_id"] == account.user_id
    assert payload["username"] == account.username
    assert payload["role"] == "viewer"
    assert payload["display_name"] == "Login Test User"
    assert payload["token_type"] == "Bearer"
    assert payload["access_token"]
    assert payload["expires_at"]
    assert payload["refresh_token"]
    assert payload["refresh_expires_at"]


def test_me_returns_current_user_for_bearer_token() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )
        token = login_response.json()["access_token"]

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "user_id": account.user_id,
        "username": account.username,
        "role": "viewer",
        "display_name": "Login Test User",
    }


def test_me_rejects_missing_token() -> None:
    with create_test_client() as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_rejects_expired_access_token() -> None:
    with create_test_client(access_token_expires_minutes=-1) as client:
        account = create_login_user(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )
        token = login_response.json()["access_token"]

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication token has expired."


def test_logout_revokes_current_access_token() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        logout_response = client.post("/api/v1/auth/logout", headers=headers)
        me_response = client.get("/api/v1/auth/me", headers=headers)

    assert logout_response.status_code == 200, logout_response.text
    assert logout_response.json() == {"revoked": True}
    assert me_response.status_code == 401
    assert me_response.json()["detail"] == "Authentication session has been revoked."


def test_refresh_rotates_tokens_and_rejects_reused_refresh_token() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )
        login_payload = login_response.json()
        old_access_token = login_payload["access_token"]
        old_refresh_token = login_payload["refresh_token"]

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        refreshed_payload = refresh_response.json()
        old_access_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_access_token}"},
        )
        new_access_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed_payload['access_token']}"},
        )
        reused_refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )

    assert refresh_response.status_code == 200, refresh_response.text
    assert refreshed_payload["access_token"] != old_access_token
    assert refreshed_payload["refresh_token"] != old_refresh_token
    assert old_access_response.status_code == 401
    assert old_access_response.json()["detail"] == "Authentication token has been replaced."
    assert new_access_response.status_code == 200, new_access_response.text
    assert reused_refresh_response.status_code == 401
    assert reused_refresh_response.json()["detail"] == "Refresh token is invalid or expired."


def test_refresh_rejects_invalid_refresh_token() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": f"invalid-{uuid4().hex}"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token is invalid or expired."


def test_login_rejects_wrong_password() -> None:
    with create_test_client() as client:
        account = create_login_user(client)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_login_rejects_inactive_account() -> None:
    with create_test_client() as client:
        account = create_login_user(client, is_active=False, account_status="DISABLED")

        response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is not active."


def test_login_rejects_unknown_account() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": f"missing-{uuid4().hex}", "password": "any-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."
