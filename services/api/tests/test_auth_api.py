from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import AuthSession, TerminalDevice, UserAccount
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


def create_terminal_device(
    client: TestClient,
    *,
    status: str = "ACTIVE",
    device_id: str | None = None,
) -> TerminalDevice:
    suffix = uuid4().hex
    terminal = TerminalDevice(
        device_id=device_id or f"android-terminal-{suffix}",
        device_name=f"현장 단말 {suffix[:8]}",
        device_mode="viewer",
        location_code="line-a",
        status=status,
    )
    with client.app.state.database.session() as session:
        session.add(terminal)
        session.commit()
        session.refresh(terminal)
    return terminal


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
    assert payload["device_id"] is None
    assert payload["token_type"] == "Bearer"
    assert payload["access_token"]
    assert payload["expires_at"]
    assert payload["refresh_token"]
    assert payload["refresh_expires_at"]


def test_login_accepts_approved_android_terminal_device_and_stores_session_device() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        terminal = create_terminal_device(client)
        original_last_seen = datetime(2000, 1, 1, tzinfo=timezone.utc)
        with client.app.state.database.session() as session:
            terminal_row = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == terminal.device_id)
            )
            assert terminal_row is not None
            terminal_row.last_seen_at = original_last_seen
            session.add(terminal_row)
            session.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": terminal.device_id,
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["device_id"] == terminal.device_id
        with client.app.state.database.session() as session:
            terminal_row = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == terminal.device_id)
            )
            assert terminal_row is not None
            assert terminal_row.last_seen_at is not None
            assert terminal_row.last_seen_at.year > original_last_seen.year
            first_last_seen = terminal_row.last_seen_at

        second_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": terminal.device_id,
            },
        )
        assert second_response.status_code == 200, second_response.text
        with client.app.state.database.session() as session:
            terminal_row = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == terminal.device_id)
            )
            device_sessions = session.scalars(
                select(AuthSession).where(AuthSession.device_id == terminal.device_id)
            ).all()
            assert terminal_row is not None
            assert terminal_row.last_seen_at is not None
            assert terminal_row.last_seen_at >= first_last_seen
            assert len(device_sessions) == 2


def test_login_rejects_unknown_or_inactive_android_terminal_device() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        inactive_terminal = create_terminal_device(client, status="INACTIVE")
        retired_terminal = create_terminal_device(client, status="RETIRED")

        unknown_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": f"missing-{uuid4().hex}",
            },
        )
        inactive_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": inactive_terminal.device_id,
            },
        )
        retired_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": retired_terminal.device_id,
            },
        )

    assert unknown_response.status_code == 403
    assert unknown_response.json()["detail"]["code"] == "DEVICE_NOT_APPROVED"
    assert inactive_response.status_code == 403
    assert inactive_response.json()["detail"]["code"] == "DEVICE_NOT_APPROVED"
    assert retired_response.status_code == 403
    assert retired_response.json()["detail"]["code"] == "DEVICE_NOT_APPROVED"


def test_direct_device_deactivation_blocks_access_refresh_and_relogin() -> None:
    with create_test_client() as client:
        account = create_login_user(client)
        terminal = create_terminal_device(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": terminal.device_id,
            },
        )
        tokens = login_response.json()

        with client.app.state.database.session() as session:
            terminal_row = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == terminal.device_id)
            )
            assert terminal_row is not None
            terminal_row.status = "INACTIVE"
            session.commit()

        access_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        relogin_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": account.username,
                "password": "correct-password",
                "deviceId": terminal.device_id,
            },
        )

    assert access_response.status_code == 401
    assert refresh_response.status_code == 401
    assert relogin_response.status_code == 403


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
            "must_change_password": False,
            "customer_scope": "DEFAULT",
            "site_scope": "DEFAULT",
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


def test_authentication_inputs_reject_values_over_the_account_contract_limit() -> None:
    overlong_password = "p" * 201
    with create_test_client() as client:
        account = create_login_user(client)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": "correct-password"},
        )
        token = login_response.json()["access_token"]

        overlong_username = client.post(
            "/api/v1/auth/login",
            json={"username": "u" * 101, "password": "correct-password"},
        )
        overlong_login_password = client.post(
            "/api/v1/auth/login",
            json={"username": account.username, "password": overlong_password},
        )
        overlong_refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "r" * 513},
        )
        overlong_change = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "correct-password",
                "new_password": overlong_password,
            },
        )

    assert overlong_username.status_code == 422
    assert overlong_login_password.status_code == 422
    assert overlong_refresh.status_code == 422
    assert overlong_change.status_code == 422


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
    assert response.json()["detail"]["code"] == "ACCOUNT_NOT_ACTIVE"


def test_login_rejects_unknown_account() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": f"missing-{uuid4().hex}", "password": "any-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."
