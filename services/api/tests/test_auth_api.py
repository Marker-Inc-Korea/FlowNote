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


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
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


def test_login_returns_mvp_user_payload() -> None:
    with create_test_client() as client:
        account = create_login_user(client)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "user_id": account.user_id,
        "username": account.username,
        "role": "viewer",
        "display_name": "Login Test User",
    }


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
