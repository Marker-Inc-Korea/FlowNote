from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Handover,
    HandoverReceipt,
    NotificationChannel,
    NotificationChannelMember,
    UserAccount,
)
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "channel-tests"
TEST_PASSWORD = "correct-password"


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
    )
    return TestClient(create_app(app_settings))


def create_user(client: TestClient, role: str, label: str) -> UserAccount:
    suffix = uuid4().hex
    username = f"channel-{label}-{role.replace('-', '_')}-{suffix}"
    account = UserAccount(
        user_id=f"user-{username}",
        username=username,
        login_id=username,
        display_name=f"Channel Test {label}",
        role=role,
        password_hash=hash_password_for_dev(TEST_PASSWORD),
        is_active=True,
        status="ACTIVE",
    )
    with client.app.state.database.session() as session:
        session.add(account)
        session.commit()
        session.refresh(account)
    return account


def auth_headers(client: TestClient, account: UserAccount) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": account.username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_channel(client: TestClient, headers: dict[str, str], suffix: str) -> dict:
    response = client.post(
        "/api/v1/notification-channels",
        headers=headers,
        json={
            "name": f"라인 A 업무 채널 {suffix}",
            "description": "공통 알림과 인수인계 테스트 채널",
            "channelType": "LINE",
            "sourceType": "WORK_RECORD",
            "sourceId": f"work-record-{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_member(
    client: TestClient,
    headers: dict[str, str],
    channel_id: str,
    account: UserAccount,
    member_role: str = "MEMBER",
) -> dict:
    response = client.post(
        f"/api/v1/notification-channels/{channel_id}/members",
        headers=headers,
        json={"userId": account.user_id, "memberRole": member_role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def receipt_for(payload: dict, user_id: str) -> dict:
    return next(receipt for receipt in payload["receipts"] if receipt["recipient_id"] == user_id)


def test_channel_members_messages_notifications_and_read_status() -> None:
    suffix = uuid4().hex[:8]
    with create_test_client() as client:
        admin = create_user(client, "admin", f"admin-{suffix}")
        lead = create_user(client, "team-lead", f"lead-{suffix}")
        outsider = create_user(client, "team-member", f"outsider-{suffix}")
        admin_headers = auth_headers(client, admin)
        lead_headers = auth_headers(client, lead)
        outsider_headers = auth_headers(client, outsider)

        channel = create_channel(client, admin_headers, suffix)
        channel_id = channel["channel_id"]
        assert channel["channel_type"] == "LINE"
        assert channel["source_type"] == "WORK_RECORD"

        lead_member = add_member(client, admin_headers, channel_id, lead, "MANAGER")
        assert lead_member["member_role"] == "MANAGER"

        message_response = client.post(
            f"/api/v1/notification-channels/{channel_id}/messages",
            headers=lead_headers,
            json={
                "messageType": "FIELD_COMMENT_EVENT",
                "sourceType": "FIELD_COMMENT",
                "sourceId": f"comment-{suffix}",
                "title": "현장 코멘트 검토 필요",
                "body": "라인 A 점검 중 남긴 코멘트입니다.",
            },
        )
        assert message_response.status_code == 201, message_response.text
        message = message_response.json()
        assert message["message_type"] == "FIELD_COMMENT_EVENT"
        assert message["source_type"] == "FIELD_COMMENT"

        list_response = client.get(
            f"/api/v1/notification-channels/{channel_id}/messages",
            headers=lead_headers,
        )
        assert list_response.status_code == 200, list_response.text
        assert any(item["message_id"] == message["message_id"] for item in list_response.json())

        denied_messages = client.get(
            f"/api/v1/notification-channels/{channel_id}/messages",
            headers=outsider_headers,
        )
        assert denied_messages.status_code == 403, denied_messages.text

        notification_response = client.get("/api/v1/notifications", headers=lead_headers)
        assert notification_response.status_code == 200, notification_response.text
        notification = next(
            item for item in notification_response.json() if item["message_id"] == message["message_id"]
        )
        assert notification["read"] is False

        read_response = client.patch(
            f"/api/v1/notifications/{message['message_id']}/read",
            headers=lead_headers,
        )
        assert read_response.status_code == 200, read_response.text
        assert read_response.json()["read"] is True
        assert read_response.json()["read_at"] is not None

        denied_read = client.patch(
            f"/api/v1/notifications/{message['message_id']}/read",
            headers=outsider_headers,
        )
        assert denied_read.status_code == 404, denied_read.text

        with client.app.state.database.session() as session:
            saved_channel = session.scalar(
                select(NotificationChannel).where(NotificationChannel.channel_id == channel_id)
            )
            saved_message = session.scalar(select(ChannelMessage).where(ChannelMessage.message_id == message["message_id"]))
            saved_member = session.scalar(
                select(NotificationChannelMember).where(NotificationChannelMember.member_id == lead_member["member_id"])
            )
            assert saved_channel is not None
            assert saved_message is not None
            assert saved_message.source_id == f"comment-{suffix}"
            assert saved_member is not None
            assert saved_member.last_read_message_id == message["message_id"]


def test_notification_polling_cursor_is_stable_scoped_and_idempotent() -> None:
    suffix = uuid4().hex[:8]
    with create_test_client() as client:
        admin = create_user(client, "admin", f"poll-admin-{suffix}")
        member = create_user(client, "team-member", f"poll-member-{suffix}")
        outsider = create_user(client, "team-member", f"poll-outsider-{suffix}")
        admin_headers = auth_headers(client, admin)
        member_headers = auth_headers(client, member)
        outsider_headers = auth_headers(client, outsider)
        channel = create_channel(client, admin_headers, suffix)
        add_member(client, admin_headers, channel["channel_id"], member)

        message_ids = []
        for index in range(3):
            response = client.post(
                f"/api/v1/notification-channels/{channel['channel_id']}/messages",
                headers=admin_headers,
                json={
                    "messageType": "NOTICE",
                    "sourceType": "SYSTEM",
                    "sourceId": f"poll-{suffix}-{index}",
                    "title": f"연속 알림 {index}",
                },
            )
            assert response.status_code == 201, response.text
            message_ids.append(response.json()["message_id"])

        first_page = client.get(
            "/api/v1/notifications?afterId=0&limit=2",
            headers=member_headers,
        )
        assert first_page.status_code == 200, first_page.text
        first_items = first_page.json()
        assert [item["message_id"] for item in first_items] == message_ids[:2]
        assert first_items[0]["cursor"] < first_items[1]["cursor"]
        server_cursor = int(first_page.headers["X-FlowNote-Notification-Cursor"])
        assert server_cursor >= first_items[-1]["cursor"]

        second_page = client.get(
            f"/api/v1/notifications?afterId={first_items[-1]['cursor']}&limit=2",
            headers=member_headers,
        )
        assert [item["message_id"] for item in second_page.json()] == message_ids[2:]
        assert int(second_page.headers["X-FlowNote-Notification-Cursor"]) == server_cursor
        assert client.get(
            f"/api/v1/notifications?afterId={second_page.json()[-1]['cursor']}",
            headers=member_headers,
        ).json() == []
        assert client.get("/api/v1/notifications?afterId=0", headers=outsider_headers).json() == []

        for _ in range(2):
            read = client.patch(f"/api/v1/notifications/{message_ids[0]}/read", headers=member_headers)
            assert read.status_code == 200, read.text
        with client.app.state.database.session() as session:
            read_events = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.event_type == "channel_message.read",
                    ActivityHistory.target_id == message_ids[0],
                    ActivityHistory.actor_id == member.user_id,
                )
            ).all()
            assert len(read_events) == 1


def test_handover_receipts_record_read_acknowledged_and_follow_up_required() -> None:
    suffix = uuid4().hex[:8]
    with create_test_client() as client:
        admin = create_user(client, "admin", f"handover-admin-{suffix}")
        read_user = create_user(client, "team-member", f"read-{suffix}")
        ack_user = create_user(client, "team-member", f"ack-{suffix}")
        follow_user = create_user(client, "team-member", f"follow-{suffix}")
        outsider = create_user(client, "team-member", f"handover-outsider-{suffix}")
        admin_headers = auth_headers(client, admin)
        read_headers = auth_headers(client, read_user)
        ack_headers = auth_headers(client, ack_user)
        follow_headers = auth_headers(client, follow_user)
        outsider_headers = auth_headers(client, outsider)

        channel = create_channel(client, admin_headers, suffix)
        channel_id = channel["channel_id"]
        for account in [read_user, ack_user, follow_user]:
            add_member(client, admin_headers, channel_id, account)

        create_response = client.post(
            "/api/v1/handovers",
            headers=admin_headers,
            json={
                "channelId": channel_id,
                "title": "야간조 인수인계",
                "body": "라인 A 압력 변동을 다음 조에서 확인하세요.",
                "sourceType": "WORK_SEQUENCE_ITEM",
                "sourceId": f"wseqitem-{suffix}",
                "recipientIds": [read_user.user_id, ack_user.user_id, follow_user.user_id],
            },
        )
        assert create_response.status_code == 201, create_response.text
        handover = create_response.json()
        assert handover["status"] == "SENT"
        assert all(receipt["receipt_status"] == "UNREAD" for receipt in handover["receipts"])

        read_receipt = receipt_for(handover, read_user.user_id)
        ack_receipt = receipt_for(handover, ack_user.user_id)
        follow_receipt = receipt_for(handover, follow_user.user_id)

        denied_get = client.get(f"/api/v1/handovers/{handover['handover_id']}", headers=outsider_headers)
        assert denied_get.status_code == 403, denied_get.text

        read_update = client.patch(
            f"/api/v1/handovers/{handover['handover_id']}/receipts/{read_receipt['receipt_id']}",
            headers=read_headers,
            json={"receiptStatus": "READ"},
        )
        assert read_update.status_code == 200, read_update.text
        assert receipt_for(read_update.json(), read_user.user_id)["receipt_status"] == "READ"

        ack_update = client.patch(
            f"/api/v1/handovers/{handover['handover_id']}/receipts/{ack_receipt['receipt_id']}",
            headers=ack_headers,
            json={"receiptStatus": "ACKNOWLEDGED", "note": "확인했습니다."},
        )
        assert ack_update.status_code == 200, ack_update.text
        assert receipt_for(ack_update.json(), ack_user.user_id)["receipt_status"] == "ACKNOWLEDGED"

        follow_update = client.patch(
            f"/api/v1/handovers/{handover['handover_id']}/receipts/{follow_receipt['receipt_id']}",
            headers=follow_headers,
            json={"receiptStatus": "FOLLOW_UP_REQUIRED", "note": "현장 확인 후 조치가 필요합니다."},
        )
        assert follow_update.status_code == 200, follow_update.text
        updated_handover = follow_update.json()
        assert updated_handover["status"] == "FOLLOW_UP_REQUIRED"
        assert receipt_for(updated_handover, follow_user.user_id)["receipt_status"] == "FOLLOW_UP_REQUIRED"

        denied_update = client.patch(
            f"/api/v1/handovers/{handover['handover_id']}/receipts/{ack_receipt['receipt_id']}",
            headers=follow_headers,
            json={"receiptStatus": "READ"},
        )
        assert denied_update.status_code == 403, denied_update.text

        with client.app.state.database.session() as session:
            saved_handover = session.scalar(select(Handover).where(Handover.handover_id == handover["handover_id"]))
            receipt_statuses = {
                receipt.recipient_id: receipt.receipt_status
                for receipt in session.scalars(
                    select(HandoverReceipt).where(HandoverReceipt.handover_id == handover["handover_id"])
                ).all()
            }
            handover_message = session.scalar(
                select(ChannelMessage).where(
                    ChannelMessage.source_type == "HANDOVER",
                    ChannelMessage.source_id == handover["handover_id"],
                )
            )
            assert saved_handover is not None
            assert saved_handover.source_type == "WORK_SEQUENCE_ITEM"
            assert receipt_statuses[read_user.user_id] == "READ"
            assert receipt_statuses[ack_user.user_id] == "ACKNOWLEDGED"
            assert receipt_statuses[follow_user.user_id] == "FOLLOW_UP_REQUIRED"
            assert handover_message is not None
            assert handover_message.message_type == "HANDOVER"
