from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import ActivityHistory, AuthSession, TerminalDevice, UserAccount
from app.main import create_app


API_SETTINGS = Settings(
    _env_file=None,
    environment="test",
    database_url="sqlite:///./data/flownote.test.sqlite3",
    test_database_url="sqlite:///./data/flownote.test.sqlite3",
    storage_root="./storage/terminal-device-tests",
)


def create_test_client() -> TestClient:
    return TestClient(create_app(API_SETTINGS))


def create_user_and_headers(client: TestClient, role: str) -> tuple[UserAccount, dict[str, str]]:
    suffix = uuid4().hex
    password = "terminal-test-password"
    account = UserAccount(
        user_id=f"user-terminal-{suffix}",
        username=f"terminal-user-{suffix}",
        login_id=f"terminal-user-{suffix}",
        display_name="단말 관리 테스트 사용자",
        role=role,
        password_hash=hash_password_for_dev(password),
        is_active=True,
        status="ACTIVE",
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)

    response = client.post(
        "/api/v1/auth/login",
        json={"username": account.username, "password": password},
    )
    assert response.status_code == 200, response.text
    return account, {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_can_register_list_read_update_and_inactivate_terminal_device() -> None:
    with create_test_client() as client:
        account, headers = create_user_and_headers(client, "admin")
        device_id = f"managed-terminal-{uuid4().hex}"

        create_response = client.post(
            "/api/v1/terminal-devices",
            headers=headers,
            json={
                "device_id": device_id,
                "device_name": "조립 1라인 단말",
                "device_mode": "viewer",
                "location_code": "LINE-A",
            },
        )
        list_response = client.get("/api/v1/terminal-devices?status=ACTIVE", headers=headers)
        detail_response = client.get(f"/api/v1/terminal-devices/{device_id}", headers=headers)
        android_user, _ = create_user_and_headers(client, "viewer")
        android_login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": device_id,
            },
        )
        android_tokens = android_login_response.json()
        update_response = client.patch(
            f"/api/v1/terminal-devices/{device_id}",
            headers=headers,
            json={"device_name": "조립 1라인 교대 단말", "location_code": "LINE-A-02"},
        )
        status_response = client.patch(
            f"/api/v1/terminal-devices/{device_id}/status",
            headers=headers,
            json={"status": "INACTIVE", "change_reason": "현장 점검"},
        )
        last_seen_response = client.get(
            f"/api/v1/terminal-devices/{device_id}/last-seen",
            headers=headers,
        )
        revoked_access_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {android_tokens['access_token']}"},
        )
        revoked_refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": android_tokens["refresh_token"]},
        )
        inactive_login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": device_id,
            },
        )

        assert create_response.status_code == 201, create_response.text
        assert create_response.json()["registered_by"] == account.user_id
        assert any(item["device_id"] == device_id for item in list_response.json())
        assert detail_response.status_code == 200
        assert android_login_response.status_code == 200
        assert update_response.json()["device_name"] == "조립 1라인 교대 단말"
        assert update_response.json()["updated_by"] == account.user_id
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "INACTIVE"
        assert last_seen_response.json()["device_id"] == device_id
        assert last_seen_response.json()["status"] == "INACTIVE"
        assert last_seen_response.json()["last_seen_at"] is not None
        assert revoked_access_response.status_code == 401
        assert revoked_refresh_response.status_code == 401
        assert inactive_login_response.status_code == 403

        with client.app.state.database.session() as session:
            events = session.scalars(
                select(ActivityHistory).where(ActivityHistory.target_id == device_id)
            ).all()
            assert {event.event_type for event in events} >= {
                "terminal_device.registered",
                "terminal_device.updated",
                "terminal_device.status_changed",
            }
            status_event = next(
                event for event in events if event.event_type == "terminal_device.status_changed"
            )
            assert status_event.actor_id == account.user_id
            assert status_event.change_reason == "현장 점검"
            device_session = session.scalar(
                select(AuthSession).where(AuthSession.device_id == device_id)
            )
            assert device_session is not None
            assert device_session.status == "REVOKED"
            assert device_session.revoked_reason == "terminal_device_inactive"


def test_system_admin_can_replace_device_and_retired_device_cannot_reactivate() -> None:
    with create_test_client() as client:
        account, headers = create_user_and_headers(client, "system-admin")
        old_id = f"old-terminal-{uuid4().hex}"
        new_id = f"new-terminal-{uuid4().hex}"
        client.post(
            "/api/v1/terminal-devices",
            headers=headers,
            json={"device_id": old_id, "device_name": "교체 전 단말"},
        )
        android_user, _ = create_user_and_headers(client, "viewer")
        old_login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": old_id,
            },
        )
        old_tokens = old_login_response.json()

        replace_response = client.post(
            f"/api/v1/terminal-devices/{old_id}/replace",
            headers=headers,
            json={
                "device_id": new_id,
                "device_name": "교체 후 단말",
                "location_code": "PACK-01",
                "change_reason": "단말 파손",
            },
        )
        old_response = client.get(f"/api/v1/terminal-devices/{old_id}", headers=headers)
        reactivate_response = client.patch(
            f"/api/v1/terminal-devices/{old_id}/status",
            headers=headers,
            json={"status": "ACTIVE"},
        )
        retired_login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": old_id,
            },
        )
        old_access_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_tokens['access_token']}"},
        )
        old_refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_tokens["refresh_token"]},
        )
        replacement_login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": new_id,
            },
        )

        assert replace_response.status_code == 201, replace_response.text
        assert replace_response.json()["replaced_device_id"] == old_id
        assert replace_response.json()["registered_by"] == account.user_id
        assert old_response.json()["status"] == "RETIRED"
        assert reactivate_response.status_code == 409
        assert retired_login_response.status_code == 403
        assert old_access_response.status_code == 401
        assert old_refresh_response.status_code == 401
        assert replacement_login_response.status_code == 200
        assert replacement_login_response.json()["device_id"] == new_id

        with client.app.state.database.session() as session:
            old_device = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == old_id)
            )
            new_device = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == new_id)
            )
            assert old_device is not None and old_device.status == "RETIRED"
            assert new_device is not None and new_device.status == "ACTIVE"
            assert old_device.updated_by == account.user_id
            assert new_device.registered_by == account.user_id
            assert new_device.updated_by == account.user_id
            old_session = session.scalar(
                select(AuthSession).where(AuthSession.device_id == old_id)
            )
            new_session = session.scalar(
                select(AuthSession).where(AuthSession.device_id == new_id)
            )
            assert old_session is not None and old_session.status == "REVOKED"
            assert old_session.revoked_at is not None
            assert old_session.revoked_reason == "terminal_device_replaced"
            assert new_session is not None and new_session.status == "ACTIVE"
            event_types = set(
                session.scalars(
                    select(ActivityHistory.event_type).where(
                        ActivityHistory.target_id.in_([old_id, new_id])
                    )
                ).all()
            )
            assert "terminal_device.retired_for_replacement" in event_types
            assert "terminal_device.replacement_registered" in event_types
            replacement_events = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.target_id.in_([old_id, new_id]),
                    ActivityHistory.event_type.in_([
                        "terminal_device.retired_for_replacement",
                        "terminal_device.replacement_registered",
                    ]),
                )
            ).all()
            assert len(replacement_events) == 2
            assert all(event.actor_id == account.user_id for event in replacement_events)
            assert all(event.change_reason == "단말 파손" for event in replacement_events)
            assert all(event.after_value for event in replacement_events)


def test_non_admin_cannot_use_terminal_device_management_api() -> None:
    with create_test_client() as client:
        _, headers = create_user_and_headers(client, "viewer")
        response = client.get("/api/v1/terminal-devices", headers=headers)
        create_response = client.post(
            "/api/v1/terminal-devices",
            headers=headers,
            json={"device_id": f"denied-{uuid4().hex}", "device_name": "거부 단말"},
        )

    assert response.status_code == 403
    assert create_response.status_code == 403


def test_failed_replacement_rolls_back_retirement_session_revocation_and_audit() -> None:
    with create_test_client() as client:
        account, headers = create_user_and_headers(client, "system-admin")
        android_user, _ = create_user_and_headers(client, "viewer")
        old_id = f"rollback-old-terminal-{uuid4().hex}"
        existing_id = f"rollback-existing-terminal-{uuid4().hex}"
        for device_id in (old_id, existing_id):
            response = client.post(
                "/api/v1/terminal-devices",
                headers=headers,
                json={"device_id": device_id, "device_name": f"원자성 검증 {device_id[-8:]}"},
            )
            assert response.status_code == 201, response.text

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": android_user.username,
                "password": "terminal-test-password",
                "deviceId": old_id,
            },
        )
        access_token = login_response.json()["access_token"]
        failed_replace_response = client.post(
            f"/api/v1/terminal-devices/{old_id}/replace",
            headers=headers,
            json={
                "device_id": existing_id,
                "device_name": "중복 교체 단말",
                "change_reason": "중복 ID 원자성 검증",
            },
        )
        still_valid_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert failed_replace_response.status_code == 409
        assert still_valid_response.status_code == 200
        with client.app.state.database.session() as session:
            old_device = session.scalar(
                select(TerminalDevice).where(TerminalDevice.device_id == old_id)
            )
            old_session = session.scalar(
                select(AuthSession).where(AuthSession.device_id == old_id)
            )
            replacement_events = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.target_id.in_([old_id, existing_id]),
                    ActivityHistory.change_reason == "중복 ID 원자성 검증",
                )
            ).all()
            assert old_device is not None and old_device.status == "ACTIVE"
            assert old_device.updated_by == account.user_id
            assert old_session is not None and old_session.status == "ACTIVE"
            assert old_session.revoked_at is None
            assert replacement_events == []
