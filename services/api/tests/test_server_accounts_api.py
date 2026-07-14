from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.api.v1.server_accounts import _protect_last_system_admin
from app.db.init_db import ALLOWED_USER_ROLES, hash_password_for_dev
from app.db.models import ActivityHistory, AuthSession, UserAccount
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "server-account-tests"
PASSWORD = "Account-test-password-1"


def create_test_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
    )
    return TestClient(create_app(settings))


def create_user(client: TestClient, role: str, *, must_change_password: bool = False) -> UserAccount:
    suffix = uuid4().hex
    account = UserAccount(
        user_id=f"user-account-api-{suffix}",
        username=f"account-api-{role}-{suffix}",
        login_id=f"account-api-{role}-{suffix}",
        display_name=f"계정 API {role}",
        role=role,
        password_hash=hash_password_for_dev(PASSWORD),
        is_active=True,
        status="ACTIVE",
        must_change_password=must_change_password,
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def login(client: TestClient, account: UserAccount, password: str = PASSWORD) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": account.username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def headers(tokens: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_account_creation_forces_password_change_without_reexposing_temporary_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    temporary_password = f"Temporary-{uuid4().hex}"
    changed_password = f"Changed-{uuid4().hex}"
    with create_test_client() as client:
        actor = create_user(client, "system-admin")
        actor_headers = headers(login(client, actor))
        username = f"new-server-user-{uuid4().hex}"
        with caplog.at_level(logging.DEBUG):
            create_response = client.post(
                "/api/v1/server-accounts",
                headers=actor_headers,
                json={
                    "username": username,
                    "display_name": "신규 서버 사용자",
                    "role": "viewer",
                    "temporary_password": temporary_password,
                    "reason": "신규 현장 사용자 발급",
                },
            )
        assert create_response.status_code == 201, create_response.text
        created_payload = create_response.json()
        assert created_payload["account"]["must_change_password"] is True
        assert "temporary_password" not in created_payload
        assert "password_hash" not in created_payload["account"]
        assert temporary_password not in create_response.text
        assert temporary_password not in caplog.text

        first_login = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": temporary_password},
        )
        assert first_login.status_code == 200, first_login.text
        first_tokens = first_login.json()
        assert first_tokens["must_change_password"] is True
        blocked_me = client.get("/api/v1/auth/me", headers=headers(first_tokens))
        blocked_refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_tokens["refresh_token"]},
        )
        assert blocked_me.status_code == 403
        assert blocked_refresh.status_code == 403

        change_response = client.post(
            "/api/v1/auth/change-password",
            headers=headers(first_tokens),
            json={"current_password": temporary_password, "new_password": changed_password},
        )
        assert change_response.status_code == 200, change_response.text
        assert change_response.json()["sessions_revoked"] == 1
        assert client.get("/api/v1/auth/me", headers=headers(first_tokens)).status_code == 401

        second_login = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": changed_password},
        )
        assert second_login.status_code == 200, second_login.text
        assert second_login.json()["must_change_password"] is False
        assert client.get("/api/v1/auth/me", headers=headers(second_login.json())).status_code == 200

        with client.app.state.database.session() as session:
            created = session.scalar(select(UserAccount).where(UserAccount.username == username))
            assert created is not None
            history = session.scalars(
                select(ActivityHistory)
                .where(ActivityHistory.target_id == created.user_id)
                .order_by(ActivityHistory.id)
            ).all()
            assert [row.event_type for row in history] == ["user.created", "user.password_changed"]
            assert all(row.actor_id for row in history)
            assert all(row.change_reason for row in history)
            serialized_history = " ".join(
                filter(
                    None,
                    (
                        value
                        for row in history
                        for value in (row.before_value, row.after_value, row.message, row.change_reason)
                    ),
                )
            )
            assert temporary_password not in serialized_history
            assert changed_password not in serialized_history


@pytest.mark.parametrize("role", ALLOWED_USER_ROLES)
def test_every_account_operation_endpoint_uses_admin_system_admin_permission_boundary(role: str) -> None:
    with create_test_client() as client:
        actor = create_user(client, role)
        actor_headers = headers(login(client, actor))
        target = create_user(client, "viewer")
        expected = 200 if role in {"admin", "system-admin"} else 403
        responses = [
            client.get("/api/v1/server-accounts", headers=actor_headers),
            client.patch(
                f"/api/v1/server-accounts/{target.user_id}",
                headers=actor_headers,
                json={"display_name": "권한 행렬 대상", "reason": "권한 행렬 검증"},
            ),
            client.post(
                f"/api/v1/server-accounts/{target.user_id}/password-reset",
                headers=actor_headers,
                json={"temporary_password": f"Reset-{uuid4().hex}", "reason": "권한 행렬 검증"},
            ),
            client.get(
                f"/api/v1/server-accounts/{target.user_id}/sessions",
                headers=actor_headers,
            ),
            client.post(
                f"/api/v1/server-accounts/{target.user_id}/sessions/revoke",
                headers=actor_headers,
                json={"reason": "권한 행렬 검증"},
            ),
        ]
        assert all(response.status_code == expected for response in responses), [
            (response.status_code, response.text) for response in responses
        ]


def test_disable_and_forced_revoke_immediately_reject_access_and_refresh() -> None:
    with create_test_client() as client:
        actor = create_user(client, "system-admin")
        actor_headers = headers(login(client, actor))
        disabled_target = create_user(client, "viewer")
        disabled_tokens = login(client, disabled_target)

        disable_response = client.patch(
            f"/api/v1/server-accounts/{disabled_target.user_id}",
            headers=actor_headers,
            json={"status": "DISABLED", "reason": "퇴사자 계정 비활성화"},
        )
        assert disable_response.status_code == 200, disable_response.text
        assert disable_response.json()["sessions_revoked"] == 1
        assert client.get("/api/v1/auth/me", headers=headers(disabled_tokens)).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": disabled_tokens["refresh_token"]},
        ).status_code == 401

        revoke_target = create_user(client, "viewer")
        revoke_tokens = login(client, revoke_target)
        revoke_response = client.post(
            f"/api/v1/server-accounts/{revoke_target.user_id}/sessions/revoke",
            headers=actor_headers,
            json={"reason": "분실 단말 세션 폐기"},
        )
        assert revoke_response.status_code == 200, revoke_response.text
        assert revoke_response.json() == {"sessions_revoked": 1}
        assert client.get("/api/v1/auth/me", headers=headers(revoke_tokens)).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": revoke_tokens["refresh_token"]},
        ).status_code == 401


def test_admin_cannot_manage_system_admin_and_self_disable_is_protected() -> None:
    with create_test_client() as client:
        system_admin = create_user(client, "system-admin")
        system_headers = headers(login(client, system_admin))
        admin = create_user(client, "admin")
        admin_headers = headers(login(client, admin))

        assert client.patch(
            f"/api/v1/server-accounts/{system_admin.user_id}",
            headers=admin_headers,
            json={"status": "DISABLED", "reason": "허용되지 않는 변경"},
        ).status_code == 403
        assert client.post(
            "/api/v1/server-accounts",
            headers=admin_headers,
            json={
                "username": f"forbidden-system-admin-{uuid4().hex}",
                "display_name": "금지된 시스템 관리자",
                "role": "system-admin",
                "temporary_password": f"Temporary-{uuid4().hex}",
                "reason": "허용되지 않는 생성",
            },
        ).status_code == 403
        assert client.patch(
            f"/api/v1/server-accounts/{system_admin.user_id}",
            headers=system_headers,
            json={"status": "DISABLED", "reason": "자기 자신 비활성화"},
        ).status_code == 409

        second_system_admin = create_user(client, "system-admin")
        demote_response = client.patch(
            f"/api/v1/server-accounts/{second_system_admin.user_id}",
            headers=system_headers,
            json={"role": "admin", "reason": "시스템 관리자 역할 정리"},
        )
        assert demote_response.status_code == 200, demote_response.text


def test_last_active_system_admin_removal_is_rejected() -> None:
    target = UserAccount(
        user_id=f"last-system-admin-{uuid4().hex}",
        username=f"last-system-admin-{uuid4().hex}",
        login_id=f"last-system-admin-{uuid4().hex}",
        display_name="마지막 시스템 관리자",
        role="system-admin",
        password_hash="not-used",
        is_active=True,
        status="ACTIVE",
    )

    class EmptySystemAdminSession:
        @staticmethod
        def scalar(statement: object) -> int:
            return 0

    with pytest.raises(HTTPException) as error:
        _protect_last_system_admin(
            EmptySystemAdminSession(),  # type: ignore[arg-type]
            target,
            requested_role="admin",
            requested_status="ACTIVE",
        )
    assert getattr(error.value, "status_code", None) == 409


def test_role_change_revokes_existing_session_immediately() -> None:
    with create_test_client() as client:
        actor = create_user(client, "system-admin")
        actor_headers = headers(login(client, actor))
        target = create_user(client, "viewer")
        target_tokens = login(client, target)

        response = client.patch(
            f"/api/v1/server-accounts/{target.user_id}",
            headers=actor_headers,
            json={"role": "team-member", "reason": "현장 업무 역할 배정"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["sessions_revoked"] == 1
        assert client.get("/api/v1/auth/me", headers=headers(target_tokens)).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": target_tokens["refresh_token"]},
        ).status_code == 401


def test_password_reset_revokes_sessions_and_records_redacted_audit_state() -> None:
    temporary_password = f"Reset-{uuid4().hex}"
    with create_test_client() as client:
        actor = create_user(client, "system-admin")
        actor_headers = headers(login(client, actor))
        target = create_user(client, "viewer")
        target_tokens = login(client, target)

        response = client.post(
            f"/api/v1/server-accounts/{target.user_id}/password-reset",
            headers=actor_headers,
            json={"temporary_password": temporary_password, "reason": "비밀번호 분실 신고"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["sessions_revoked"] == 1
        assert response.json()["account"]["must_change_password"] is True
        assert temporary_password not in response.text
        assert client.get("/api/v1/auth/me", headers=headers(target_tokens)).status_code == 401
        assert client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": target_tokens["refresh_token"]},
        ).status_code == 401

        with client.app.state.database.session() as session:
            history = session.scalar(
                select(ActivityHistory)
                .where(
                    ActivityHistory.target_id == target.user_id,
                    ActivityHistory.event_type == "user.password_reset",
                )
                .order_by(ActivityHistory.id.desc())
            )
            assert history is not None
            assert history.actor_id == actor.user_id
            assert history.change_reason == "비밀번호 분실 신고"
            assert temporary_password not in (history.before_value or "")
            assert temporary_password not in (history.after_value or "")
            active_sessions = session.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == target.user_id,
                    AuthSession.status == "ACTIVE",
                )
            ).all()
            assert active_sessions == []


def test_password_policy_rejects_short_and_reused_passwords_and_uses_unique_salts() -> None:
    shared_password = f"Shared-{uuid4().hex}"
    with create_test_client() as client:
        actor = create_user(client, "system-admin")
        actor_headers = headers(login(client, actor))
        short_response = client.post(
            "/api/v1/server-accounts",
            headers=actor_headers,
            json={
                "username": f"short-password-{uuid4().hex}",
                "display_name": "짧은 비밀번호",
                "role": "viewer",
                "temporary_password": "short",
                "reason": "비밀번호 정책 검증",
            },
        )
        assert short_response.status_code == 422

        created_ids: list[str] = []
        for index in range(2):
            response = client.post(
                "/api/v1/server-accounts",
                headers=actor_headers,
                json={
                    "username": f"salt-account-{index}-{uuid4().hex}",
                    "display_name": f"salt 계정 {index}",
                    "role": "viewer",
                    "temporary_password": shared_password,
                    "reason": "계정별 salt 검증",
                },
            )
            assert response.status_code == 201, response.text
            created_ids.append(response.json()["account"]["user_id"])

        with client.app.state.database.session() as session:
            accounts = session.scalars(
                select(UserAccount).where(UserAccount.user_id.in_(created_ids))
            ).all()
            assert len(accounts) == 2
            assert accounts[0].password_hash != accounts[1].password_hash

        with client.app.state.database.session() as session:
            account = session.scalar(select(UserAccount).where(UserAccount.user_id == created_ids[0]))
            assert account is not None
            account_username = account.username
        first_login = client.post(
            "/api/v1/auth/login",
            json={"username": account_username, "password": shared_password},
        )
        reused_response = client.post(
            "/api/v1/auth/change-password",
            headers=headers(first_login.json()),
            json={"current_password": shared_password, "new_password": shared_password},
        )
        assert reused_response.status_code == 400
