from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import AuthSession, UserAccount
from app.main import create_app
from app.ops.server_accounts import create_account, reset_password, set_role, set_status


def create_isolated_client(tmp_path: Path) -> tuple[TestClient, str]:
    database_path = tmp_path / "flownote.ops.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        test_database_url=database_url,
        storage_root=str(tmp_path / "storage"),
    )
    return TestClient(create_app(app_settings)), database_url


def password_provider(password: str) -> Iterator[str]:
    yield password
    yield password


def test_reset_password_revokes_active_sessions_and_rejects_old_admin_password(
    tmp_path: Path,
) -> None:
    client, database_url = create_isolated_client(tmp_path)
    new_password = "changed-admin-password"
    provider = password_provider(new_password)

    with client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "1234"},
        )
        assert login_response.status_code == 200, login_response.text

        result = reset_password(
            database_url,
            username="admin",
            password_provider=lambda _: next(provider),
        )

        old_password_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "1234"},
        )
        new_password_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": new_password},
        )

        with client.app.state.database.session() as session:
            sessions = session.scalars(
                select(AuthSession).where(AuthSession.user_id == "user-admin")
            ).all()

    assert result.revoked_sessions == 1
    assert old_password_response.status_code == 401
    assert new_password_response.status_code == 200, new_password_response.text
    assert any(
        auth_session.status == "REVOKED"
        and auth_session.revoked_reason == "password_reset"
        and auth_session.revoked_at is not None
        for auth_session in sessions
    )


def test_set_status_locks_and_disables_account_login_with_403(tmp_path: Path) -> None:
    client, database_url = create_isolated_client(tmp_path)

    with client:
        locked_result = set_status(database_url, username="admin", status="LOCKED")
        locked_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "1234"},
        )

        active_result = set_status(database_url, username="admin", status="ACTIVE")
        active_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "1234"},
        )

        disabled_result = set_status(database_url, username="admin", status="DISABLED")
        disabled_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "1234"},
        )

    assert locked_result.action == "status_locked"
    assert locked_login.status_code == 403
    assert active_result.action == "status_active"
    assert active_login.status_code == 200, active_login.text
    assert disabled_result.action == "status_disabled"
    assert disabled_login.status_code == 403


def test_create_account_and_set_role_use_documented_role_values(tmp_path: Path) -> None:
    client, database_url = create_isolated_client(tmp_path)
    provider = password_provider("created-user-password")

    with client:
        created = create_account(
            database_url,
            username="line-admin",
            display_name="Line Admin",
            role="line-foreman",
            password_provider=lambda _: next(provider),
        )
        role_changed = set_role(database_url, username="line-admin", role="document-admin")
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "line-admin", "password": "created-user-password"},
        )

        with client.app.state.database.session() as session:
            account = session.scalar(
                select(UserAccount).where(UserAccount.username == "line-admin")
            )

    assert created.action == "created"
    assert created.revoked_sessions == 0
    assert role_changed.action == "role_changed"
    assert role_changed.revoked_sessions == 0
    assert account is not None
    assert account.role == "document-admin"
    assert login_response.status_code == 200, login_response.text
    assert login_response.json()["role"] == "document-admin"
