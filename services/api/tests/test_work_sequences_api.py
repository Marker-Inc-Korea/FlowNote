from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import (
    ActivityHistory,
    ChannelMessage,
    Document,
    DocumentVersion,
    FileObject,
    Handover,
    HandoverReceipt,
    NotificationChannel,
    NotificationChannelMember,
    SyncMutationReceipt,
    TerminalDevice,
    UserAccount,
    WorkSequenceBoard,
    WorkSequenceCandidateDelivery,
    WorkSequenceChangeHistory,
    WorkSequenceDeliveryRecipient,
    WorkSequenceItem,
    WorkSequenceMutationReceipt,
    WorkSequenceNotificationCandidate,
)
from app.db.init_db import hash_password_for_dev
from app.main import create_app
from app.services.mutation_receipts import canonical_hash


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "work-sequence-tests"


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


def test_android_field_work_sequence_paging_scope_source_and_document_recheck() -> None:
    suffix = uuid4().hex[:10]
    username = f"field-wseq-{suffix}"
    password = "field-work-sequence-password"
    user_id = f"user-field-wseq-{suffix}"
    recipient_id = f"user-field-recipient-{suffix}"
    device_id = f"device-field-wseq-{suffix}"
    line_code = f"line-field-{suffix}"
    today = date.today()
    with create_test_client() as client:
        with client.app.state.database.session() as session:
            session.add_all([
                UserAccount(
                    user_id=user_id,
                    username=username,
                    login_id=username,
                    display_name="현장 작업자",
                    role="team-member",
                    password_hash=hash_password_for_dev(password),
                    is_active=True,
                    status="ACTIVE",
                ),
                UserAccount(
                    user_id=recipient_id,
                    username=f"field-recipient-{suffix}",
                    login_id=f"field-recipient-{suffix}",
                    display_name="다음 작업자",
                    role="team-member",
                    password_hash=hash_password_for_dev(password),
                    is_active=True,
                    status="ACTIVE",
                ),
                TerminalDevice(
                    device_id=device_id,
                    device_name="현장 작업순서 단말",
                    device_mode="viewer",
                    status="ACTIVE",
                ),
            ])
            file_object = FileObject(
                storage_key=f"work-sequence-field/{suffix}.pdf",
                original_filename=f"{suffix}.pdf",
                extension="pdf",
                mime_type="application/pdf",
                file_family="pdf",
                size_bytes=10,
                hash_sha256="b" * 64,
            )
            session.add(file_object)
            session.flush()
            document_id = f"document-field-{suffix}"
            version_id = f"version-field-{suffix}"
            session.add(Document(
                document_id=document_id,
                title="현장 공개 작업 표준",
                document_type="work_instruction",
                status="PUBLISHED",
                latest_version_id=version_id,
                published_version_id=version_id,
                revision=3,
                owner_id="user-admin",
            ))
            session.add(DocumentVersion(
                version_id=version_id,
                document_id=document_id,
                file_object_id=file_object.id,
                version_no=1,
                change_reason="Android 작업순서 공개 문서 검증",
                version_status="PUBLISHED",
                is_latest=True,
                is_published=True,
                created_by="user-admin",
            ))
            first_board_id = f"wseqboard-field-{suffix}-000"
            first_item_id = f"wseqitem-field-{suffix}-000"
            for index in range(101):
                board_id = f"wseqboard-field-{suffix}-{index:03d}"
                item_id = f"wseqitem-field-{suffix}-{index:03d}"
                session.add(WorkSequenceBoard(
                    board_id=board_id,
                    title=f"현장 작업판 {index:03d}",
                    line_code=line_code,
                    board_date=today,
                    status="ACTIVE",
                    board_revision=7,
                    created_by="user-admin",
                ))
                session.add(WorkSequenceItem(
                    item_id=item_id,
                    board_id=board_id,
                    title=f"현장 작업 {index:03d}",
                    document_id=document_id if index == 0 else None,
                    status="WAITING",
                    sort_order=1,
                    assigned_to=None if index == 0 else user_id,
                    created_by="user-admin",
                ))
            channel_id = f"channel-field-wseq-{suffix}"
            session.add(NotificationChannel(
                channel_id=channel_id,
                name="작업순서 현장 채널",
                channel_type="LINE",
                source_type="WORK_SEQUENCE_ITEM",
                source_id=first_item_id,
                status="ACTIVE",
                created_by="user-admin",
            ))
            session.flush()
            session.add_all([
                NotificationChannelMember(
                    member_id=f"member-field-{suffix}",
                    channel_id=channel_id,
                    user_id=user_id,
                    member_role="MEMBER",
                    status="ACTIVE",
                    added_by="user-admin",
                ),
                NotificationChannelMember(
                    member_id=f"member-field-recipient-{suffix}",
                    channel_id=channel_id,
                    user_id=recipient_id,
                    member_role="MEMBER",
                    status="ACTIVE",
                    added_by="user-admin",
                ),
                ChannelMessage(
                    message_id=f"chmsg-field-{suffix}",
                    channel_id=channel_id,
                    message_type="WORK_SEQUENCE_EVENT",
                    source_type="WORK_SEQUENCE_ITEM",
                    source_id=first_item_id,
                    title="작업순서 확인",
                    created_by="user-admin",
                ),
            ])
            session.commit()

        login = client.post("/api/v1/auth/login", json={
            "username": username,
            "password": password,
            "deviceId": device_id,
        })
        assert login.status_code == 200, login.text
        login_payload = login.json()
        headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        first_page = client.get(
            "/api/v1/work-sequence-field-boards",
            headers=headers,
            params={"boardDate": today.isoformat(), "lineCode": line_code, "limit": 100},
        )
        assert first_page.status_code == 200, first_page.text
        assert len(first_page.json()["items"]) == 100
        assert first_page.json()["total"] == 101
        assert first_page.json()["has_more"] is True
        second_page = client.get(
            "/api/v1/work-sequence-field-boards",
            headers=headers,
            params={
                "boardDate": today.isoformat(),
                "lineCode": line_code,
                "offset": 100,
                "limit": 100,
            },
        )
        assert second_page.status_code == 200, second_page.text
        assert len(second_page.json()["items"]) == 1
        assert second_page.json()["has_more"] is False

        detail = client.get(
            f"/api/v1/work-sequence-field-boards/by-item/{first_item_id}",
            headers=headers,
            params={"expectedRevision": 7},
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["customer_scope"] == login_payload["customer_scope"]
        assert detail.json()["site_scope"] == login_payload["site_scope"]
        assert detail.json()["user_id"] == user_id
        assert detail.json()["device_id"] == device_id
        source_item = detail.json()["items"][0]
        assert detail.json()["board_id"] == first_board_id
        assert source_item["source_id"] == first_item_id
        assert source_item["source_revision"] == 7
        assert source_item["published_document"]["version_id"] == version_id
        assert source_item["allowed_channel_ids"] == [channel_id]

        server_scope = "http://field-server.local"
        raw_content = "압력 상승을 확인했습니다."
        field_intent = canonical_hash({
            "serverScope": server_scope,
            "customerScope": login_payload["customer_scope"],
            "siteScope": login_payload["site_scope"],
            "userId": user_id,
            "deviceId": device_id,
            "sourceType": "WORK_SEQUENCE_ITEM",
            "sourceId": first_item_id,
            "sourceRevision": 7,
            "documentId": document_id,
            "documentVersionId": version_id,
            "workRecordId": None,
            "rawContent": raw_content,
            "inputMode": "free_text",
            "signalLevel": None,
        })
        comment_key = f"android:wseq:field-comment:{suffix}"
        comment_request = {
            "documentId": document_id,
            "documentVersionId": version_id,
            "sourceType": "WORK_SEQUENCE_ITEM",
            "sourceId": first_item_id,
            "sourceRevision": 7,
            "serverScope": server_scope,
            "intentHashSha256": field_intent,
            "rawContent": raw_content,
            "inputMode": "free_text",
            "entrySource": "android_field_terminal",
            "deviceId": device_id,
            "idempotencyKey": comment_key,
        }
        comment = client.post("/api/v1/field-comments", headers=headers, json=comment_request)
        assert comment.status_code == 201, comment.text
        assert comment.json()["source_id"] == first_item_id
        assert comment.json()["intent_hash_sha256"] == field_intent
        replay = client.post("/api/v1/field-comments", headers=headers, json=comment_request)
        assert replay.status_code == 201
        assert replay.json()["comment_id"] == comment.json()["comment_id"]

        handover_title = "다음 교대 확인"
        handover_body = "압력 상태를 다시 확인하세요."
        handover_intent = canonical_hash({
            "serverScope": server_scope,
            "customerScope": login_payload["customer_scope"],
            "siteScope": login_payload["site_scope"],
            "userId": user_id,
            "deviceId": device_id,
            "sourceType": "WORK_SEQUENCE_ITEM",
            "sourceId": first_item_id,
            "sourceRevision": 7,
            "relatedDocumentId": document_id,
            "relatedDocumentVersionId": version_id,
            "channelId": channel_id,
            "recipientIds": [recipient_id],
            "title": handover_title,
            "body": handover_body,
        })
        handover = client.post("/api/v1/handovers", headers=headers, json={
            "channelId": channel_id,
            "title": handover_title,
            "body": handover_body,
            "sourceType": "WORK_SEQUENCE_ITEM",
            "sourceId": first_item_id,
            "sourceRevision": 7,
            "relatedDocumentId": document_id,
            "relatedDocumentVersionId": version_id,
            "serverScope": server_scope,
            "intentHashSha256": handover_intent,
            "recipientIds": [recipient_id],
            "entrySource": "android_field_terminal",
            "deviceId": device_id,
            "idempotencyKey": f"android:wseq:handover:{suffix}",
        })
        assert handover.status_code == 201, handover.text
        assert handover.json()["source_revision"] == 7
        assert handover.json()["related_document_version_id"] == version_id

        with client.app.state.database.session() as session:
            document = session.scalar(select(Document).where(Document.document_id == document_id))
            document.status = "IN_REVIEW"
            session.commit()
        replay_after_document_change = client.post(
            "/api/v1/field-comments", headers=headers, json=comment_request
        )
        assert replay_after_document_change.status_code == 201
        assert replay_after_document_change.json()["comment_id"] == comment.json()["comment_id"]

        with client.app.state.database.session() as session:
            membership = session.scalar(select(NotificationChannelMember).where(
                NotificationChannelMember.channel_id == channel_id,
                NotificationChannelMember.user_id == user_id,
            ))
            membership.status = "REMOVED"
            session.commit()
        hidden = client.get(
            f"/api/v1/work-sequence-field-boards/{first_board_id}", headers=headers
        )
        assert hidden.status_code == 404

        with client.app.state.database.session() as session:
            terminal = session.scalar(select(TerminalDevice).where(TerminalDevice.device_id == device_id))
            terminal.status = "INACTIVE"
            session.commit()
        inactive = client.get(
            "/api/v1/work-sequence-field-boards",
            headers=headers,
            params={"boardDate": today.isoformat(), "lineCode": line_code},
        )
        assert inactive.status_code == 401

        with client.app.state.database.session() as session:
            assert session.scalar(select(func.count()).select_from(ActivityHistory).where(
                ActivityHistory.event_type == "work_sequence.android_read",
                ActivityHistory.actor_id == user_id,
            )) >= 3
            assert session.scalar(select(func.count()).select_from(ActivityHistory).where(
                ActivityHistory.event_type == "field_comment.work_sequence_source_linked",
                ActivityHistory.target_id == comment.json()["comment_id"],
            )) == 1


def test_work_sequence_board_item_reorder_status_and_history() -> None:
    suffix = uuid4().hex[:8]
    with create_test_client() as client:
        headers = auth_headers(client)

        board_response = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={
                "title": f"Line A work sequence {suffix}",
                "description": "Admin-entered work sequence for field TV view.",
                "lineCode": "line-a",
                "boardDate": "2026-06-29",
                "idempotencyKey": f"board:{suffix}",
            },
        )
        assert board_response.status_code == 201, board_response.text
        board = board_response.json()
        assert board["board_id"].startswith("wseqboard_")
        assert board["items"] == []

        first_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": f"Prepare material {suffix}",
                "assignedTo": "line-a",
                "idempotencyKey": f"item-1:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        )
        assert first_response.status_code == 201, first_response.text
        first_item = first_response.json()["items"][0]

        second_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": f"Start press run {suffix}",
                "workOrderNo": f"WO-{suffix}",
                "idempotencyKey": f"item-2:{suffix}",
                "baseBoardRevision": first_response.json()["board_revision"],
            },
        )
        assert second_response.status_code == 201, second_response.text
        items = second_response.json()["items"]
        assert [item["sort_order"] for item in items] == [1, 2]
        second_item = items[1]

        reorder_response = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json={
                "itemIds": [second_item["item_id"], first_item["item_id"]],
                "changeReason": "Manager changed current priority.",
                "idempotencyKey": f"reorder:{suffix}",
                "baseBoardRevision": second_response.json()["board_revision"],
            },
        )
        assert reorder_response.status_code == 200, reorder_response.text
        reordered = reorder_response.json()["items"]
        assert [item["item_id"] for item in reordered] == [second_item["item_id"], first_item["item_id"]]
        assert [item["sort_order"] for item in reordered] == [1, 2]

        status_response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{second_item['item_id']}/status",
            headers=headers,
            json={
                "status": "HOLD",
                "changeReason": "Material is delayed.",
                "holdReason": "Material is delayed.",
                "idempotencyKey": f"status-1:{suffix}",
                "baseBoardRevision": reorder_response.json()["board_revision"],
            },
        )
        assert status_response.status_code == 200, status_response.text
        status_items = status_response.json()["items"]
        assert status_items[0]["status"] == "HOLD"
        assert status_items[0]["hold_reason"] == "Material is delayed."

        hold_reason_response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{second_item['item_id']}/status",
            headers=headers,
            json={
                "status": "HOLD",
                "changeReason": "Material delay detail changed.",
                "holdReason": "Supplier delivery moved to 15:00.",
                "idempotencyKey": f"status-2:{suffix}",
                "baseBoardRevision": status_response.json()["board_revision"],
            },
        )
        assert hold_reason_response.status_code == 200, hold_reason_response.text
        hold_reason_items = hold_reason_response.json()["items"]
        assert hold_reason_items[0]["hold_reason"] == "Supplier delivery moved to 15:00."

        history_response = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/history",
            headers=headers,
        )
        assert history_response.status_code == 200
        history_types = [item["change_type"] for item in history_response.json()]
        assert "BOARD_CREATED" in history_types
        assert "ITEM_ADDED" in history_types
        assert "ITEM_REORDERED" in history_types
        assert history_types.count("ITEM_STATUS_CHANGED") == 2

        candidate_response = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates",
            headers=headers,
        )
        assert candidate_response.status_code == 200, candidate_response.text
        candidates_json = candidate_response.json()
        status_candidate = next(
            item for item in candidates_json if item["event_type"] == "work_sequence.status_changed"
        )
        assert status_candidate["status"] == "CANDIDATE"
        direct_sent = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/{status_candidate['candidate_id']}",
            headers=headers,
            json={"status": "SENT"},
        )
        assert direct_sent.status_code == 409, direct_sent.text
        assert direct_sent.json()["detail"]["code"] == "CANDIDATE_DELIVERY_REQUIRED"
        sent_response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/{status_candidate['candidate_id']}",
            headers=headers,
            json={"status": "DISMISSED"},
        )
        assert sent_response.status_code == 200, sent_response.text
        assert sent_response.json()["status"] == "DISMISSED"

        list_response = client.get("/api/v1/work-sequence-boards", headers=headers)
        assert list_response.status_code == 200
        assert any(item["board_id"] == board["board_id"] and item["item_count"] == 2 for item in list_response.json())

        with client.app.state.database.session() as session:
            saved_items = session.scalars(
                select(WorkSequenceItem)
                .where(WorkSequenceItem.board_id == board["board_id"])
                .order_by(WorkSequenceItem.sort_order)
            ).all()
            assert [item.item_id for item in saved_items] == [second_item["item_id"], first_item["item_id"]]
            assert saved_items[0].status == "HOLD"
            assert saved_items[0].hold_reason == "Supplier delivery moved to 15:00."
            history = session.scalars(
                select(WorkSequenceChangeHistory).where(
                    WorkSequenceChangeHistory.board_id == board["board_id"]
                )
            ).all()
            assert any(item.change_type == "ITEM_REORDERED" for item in history)
            assert sum(item.change_type == "ITEM_STATUS_CHANGED" for item in history) == 2
            candidates = session.scalars(
                select(WorkSequenceNotificationCandidate).where(
                    WorkSequenceNotificationCandidate.board_id == board["board_id"]
                )
            ).all()
            assert any(item.event_type == "work_sequence.reordered" for item in candidates)
            assert any(item.event_type == "work_sequence.status_changed" for item in candidates)
            assert any(item.status == "DISMISSED" for item in candidates)
            status_history = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.target_id == status_candidate["candidate_id"],
                    ActivityHistory.event_type == "work_sequence.notification_candidate_status_changed",
                )
            ).all()
            assert len(status_history) == 1


def test_work_sequence_reorder_requires_every_item_once() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        board_response = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={
                "title": f"Invalid reorder board {uuid4().hex[:8]}",
                "idempotencyKey": f"invalid-board:{uuid4().hex}",
            },
        )
        assert board_response.status_code == 201
        board = board_response.json()
        item_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": "Only item",
                "idempotencyKey": f"invalid-item:{uuid4().hex}",
                "baseBoardRevision": board["board_revision"],
            },
        )
        assert item_response.status_code == 201
        item = item_response.json()["items"][0]

        response = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json={
                "itemIds": [item["item_id"], item["item_id"]],
                "idempotencyKey": f"invalid-reorder:{uuid4().hex}",
                "baseBoardRevision": item_response.json()["board_revision"],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "itemIds must contain every item on the board exactly once."


def test_work_sequence_requires_authentication() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/work-sequence-boards",
            json={"title": "Unauthenticated board", "idempotencyKey": f"unauth:{uuid4().hex}"},
        )

    assert response.status_code == 401


def test_competing_mutations_and_duplicate_retry_are_exactly_once() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        board_response = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"Concurrency {suffix}", "idempotencyKey": f"board:{suffix}"},
        )
        assert board_response.status_code == 201, board_response.text
        board = board_response.json()
        for index in range(2):
            added = client.post(
                f"/api/v1/work-sequence-boards/{board['board_id']}/items",
                headers=headers,
                json={
                    "title": f"Item {index}",
                    "idempotencyKey": f"item:{suffix}:{index}",
                    "baseBoardRevision": board["board_revision"],
                },
            )
            assert added.status_code == 201, added.text
            board = added.json()

        base_revision = board["board_revision"]
        reorder_payload = {
            "itemIds": [board["items"][1]["item_id"], board["items"][0]["item_id"]],
            "changeReason": "first client",
            "idempotencyKey": f"reorder:{suffix}",
            "baseBoardRevision": base_revision,
        }
        winner = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json=reorder_payload,
        )
        assert winner.status_code == 200, winner.text
        assert winner.json()["board_revision"] == base_revision + 1

        loser = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{board['items'][0]['item_id']}/status",
            headers=headers,
            json={
                "status": "IN_PROGRESS",
                "changeReason": "second client",
                "idempotencyKey": f"status:{suffix}",
                "baseBoardRevision": base_revision,
            },
        )
        assert loser.status_code == 409, loser.text
        assert loser.json()["detail"] == {
            "code": "WORK_SEQUENCE_STALE_REVISION",
            "message": "다른 사용자가 작업순서를 먼저 변경했습니다. 새로고침한 뒤 다시 시도하세요.",
            "expectedRevision": base_revision,
            "currentRevision": base_revision + 1,
        }

        replay = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json=reorder_payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == winner.json()

        reused = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json={**reorder_payload, "changeReason": "different intent"},
        )
        assert reused.status_code == 409, reused.text
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        with client.app.state.database.session() as session:
            histories = session.scalars(
                select(WorkSequenceChangeHistory).where(
                    WorkSequenceChangeHistory.mutation_key == reorder_payload["idempotencyKey"]
                )
            ).all()
            receipts = session.scalars(
                select(WorkSequenceMutationReceipt).where(
                    WorkSequenceMutationReceipt.mutation_key == reorder_payload["idempotencyKey"]
                )
            ).all()
            assert len(histories) == 1
            assert len(receipts) == 1
            assert receipts[0].change_id == histories[0].change_id
            assert receipts[0].board_revision == histories[0].board_revision == base_revision + 1
            assert session.scalar(
                select(func.count()).select_from(WorkSequenceMutationReceipt).where(
                    WorkSequenceMutationReceipt.change_id.not_in(
                        select(WorkSequenceChangeHistory.change_id)
                    )
                )
            ) == 0


def test_two_clients_using_same_board_revision_have_one_winner() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"Two clients {suffix}", "idempotencyKey": f"board:{suffix}"},
        ).json()
        for index in range(2):
            response = client.post(
                f"/api/v1/work-sequence-boards/{board['board_id']}/items",
                headers=headers,
                json={
                    "title": f"Item {index}",
                    "idempotencyKey": f"item:{suffix}:{index}",
                    "baseBoardRevision": board["board_revision"],
                },
            )
            assert response.status_code == 201, response.text
            board = response.json()

        base_revision = board["board_revision"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            reorder_future = executor.submit(
                client.put,
                f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
                headers=headers,
                json={
                    "itemIds": [board["items"][1]["item_id"], board["items"][0]["item_id"]],
                    "idempotencyKey": f"parallel-order:{suffix}",
                    "baseBoardRevision": base_revision,
                },
            )
            status_future = executor.submit(
                client.patch,
                f"/api/v1/work-sequence-boards/{board['board_id']}/items/{board['items'][0]['item_id']}/status",
                headers=headers,
                json={
                    "status": "IN_PROGRESS",
                    "idempotencyKey": f"parallel-status:{suffix}",
                    "baseBoardRevision": base_revision,
                },
            )
            responses = [reorder_future.result(), status_future.result()]

        assert sorted(response.status_code for response in responses) == [200, 409]
        stale = next(response for response in responses if response.status_code == 409)
        assert stale.json()["detail"]["code"] == "WORK_SEQUENCE_STALE_REVISION"
        snapshot = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}", headers=headers
        ).json()
        assert snapshot["board_revision"] == base_revision + 1


def test_duplicate_key_after_api_restart_returns_original_result() -> None:
    suffix = uuid4().hex
    payload = {
        "title": f"Restart replay {suffix}",
        "lineCode": "line-restart",
        "idempotencyKey": f"restart:{suffix}",
    }
    with create_test_client() as first_client:
        first = first_client.post(
            "/api/v1/work-sequence-boards",
            headers=auth_headers(first_client),
            json=payload,
        )
        assert first.status_code == 201, first.text
        original = first.json()

    with create_test_client() as restarted_client:
        replay = restarted_client.post(
            "/api/v1/work-sequence-boards",
            headers=auth_headers(restarted_client),
            json=payload,
        )
        assert replay.status_code == 201, replay.text
        assert replay.json() == original
        with restarted_client.app.state.database.session() as session:
            assert session.scalar(
                select(func.count()).select_from(WorkSequenceBoard).where(
                    WorkSequenceBoard.board_id == original["board_id"]
                )
            ) == 1
            assert session.scalar(
                select(func.count()).select_from(WorkSequenceMutationReceipt).where(
                    WorkSequenceMutationReceipt.mutation_key == payload["idempotencyKey"]
                )
            ) == 1


def test_candidate_preview_channel_and_handover_delivery_are_idempotent_and_scoped() -> None:
    suffix = uuid4().hex
    password = "candidate-delivery-password"
    with create_test_client() as client:
        headers = auth_headers(client)
        recipient = UserAccount(
            user_id=f"user-delivery-{suffix}",
            username=f"delivery-{suffix}",
            login_id=f"delivery-{suffix}",
            display_name="전달 수신자",
            role="team-member",
            password_hash=hash_password_for_dev(password),
            is_active=True,
            status="ACTIVE",
        )
        with client.app.state.database.session() as session:
            session.add(recipient)
            file_object = FileObject(
                storage_key=f"work-sequence-delivery/{suffix}.pdf",
                original_filename=f"{suffix}.pdf",
                extension="pdf",
                mime_type="application/pdf",
                file_family="pdf",
                size_bytes=10,
                hash_sha256="a" * 64,
            )
            session.add(file_object)
            session.flush()
            document_id = f"document-delivery-{suffix}"
            version_id = f"version-delivery-{suffix}"
            session.add(Document(
                document_id=document_id,
                title="포장 작업표준",
                document_type="work_instruction",
                status="PUBLISHED",
                latest_version_id=version_id,
                published_version_id=version_id,
                owner_id="user-admin",
            ))
            session.add(DocumentVersion(
                version_id=version_id,
                document_id=document_id,
                file_object_id=file_object.id,
                version_no=1,
                change_reason="후보 전달 공개 문서 검증",
                version_status="PUBLISHED",
                is_latest=True,
                is_published=True,
                created_by="user-admin",
            ))
            session.commit()

        channel_response = client.post(
            "/api/v1/notification-channels",
            headers=headers,
            json={"name": f"작업순서 전달 {suffix}", "channelType": "LINE"},
        )
        assert channel_response.status_code == 201, channel_response.text
        channel = channel_response.json()
        member_response = client.post(
            f"/api/v1/notification-channels/{channel['channel_id']}/members",
            headers=headers,
            json={"userId": recipient.user_id, "memberRole": "MEMBER"},
        )
        assert member_response.status_code == 201, member_response.text

        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"전달 작업판 {suffix}", "idempotencyKey": f"delivery-board:{suffix}"},
        ).json()
        board = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": "포장 공정 시작",
                "documentId": document_id,
                "idempotencyKey": f"delivery-item:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        item_id = board["items"][0]["item_id"]
        board = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{item_id}/status",
            headers=headers,
            json={
                "status": "IN_PROGRESS",
                "changeReason": "포장 우선 진행",
                "idempotencyKey": f"delivery-status:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        candidate = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates",
            headers=headers,
        ).json()[0]
        preview = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/delivery-preview",
            headers=headers,
            params={"channelId": channel["channel_id"]},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["can_deliver"] is True
        assert preview.json()["current_board_revision"] == board["board_revision"]
        assert {row["user_id"] for row in preview.json()["recipients"]} >= {
            "user-admin",
            recipient.user_id,
        }
        assert preview.json()["source"]["source_id"] == item_id
        assert preview.json()["source"]["change_id"] == candidate["change_id"]
        assert preview.json()["source"]["published_document_id"] == document_id
        assert preview.json()["source"]["published_document_version_id"] == version_id

        payload = {
            "channelId": channel["channel_id"],
            "deliveryMode": "HANDOVER",
            "recipientIds": [recipient.user_id],
            "title": "포장 공정 작업순서 변경",
            "body": "포장 공정을 먼저 진행합니다.",
            "reason": "현장 우선순위 공유",
            "baseBoardRevision": board["board_revision"],
            "idempotencyKey": f"candidate-delivery:{suffix}",
        }
        delivered = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/deliveries",
            headers=headers,
            json=payload,
        )
        replay = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/deliveries",
            headers=headers,
            json=payload,
        )
        assert delivered.status_code == replay.status_code == 201, delivered.text
        assert delivered.json() == replay.json()
        result = delivered.json()
        assert result["status"] == "COMPLETED"
        assert result["candidate_status"] == "SENT"
        assert result["success_count"] == 1 and result["failure_count"] == 0
        assert result["message_id"] and result["handover_id"]
        assert result["source_version_id"] == candidate["change_id"]
        assert result["related_document_id"] == document_id
        assert result["related_document_version_id"] == version_id
        assert result["recipients"][0]["handover_receipt_id"]

        reused = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/deliveries",
            headers=headers,
            json={**payload, "body": "다른 본문"},
        )
        assert reused.status_code == 409, reused.text
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        with client.app.state.database.session() as session:
            assert len(session.scalars(select(WorkSequenceCandidateDelivery).where(
                WorkSequenceCandidateDelivery.candidate_id == candidate["candidate_id"]
            )).all()) == 1
            assert len(session.scalars(select(WorkSequenceDeliveryRecipient).where(
                WorkSequenceDeliveryRecipient.delivery_id == result["delivery_id"]
            )).all()) == 1
            assert len(session.scalars(select(ChannelMessage).where(
                ChannelMessage.message_id == result["message_id"]
            )).all()) == 1
            assert len(session.scalars(select(Handover).where(
                Handover.handover_id == result["handover_id"]
            )).all()) == 1
            saved_message = session.scalar(select(ChannelMessage).where(
                ChannelMessage.message_id == result["message_id"]
            ))
            saved_handover = session.scalar(select(Handover).where(
                Handover.handover_id == result["handover_id"]
            ))
            assert saved_message is not None and saved_message.related_document_id == document_id
            assert saved_handover is not None and saved_handover.related_document_id == document_id
            assert saved_message.source_version_id == candidate["change_id"]
            assert saved_handover.source_version_id == candidate["change_id"]
            assert len(session.scalars(select(HandoverReceipt).where(
                HandoverReceipt.handover_id == result["handover_id"]
            )).all()) == 1
            common = session.scalar(select(SyncMutationReceipt).where(
                SyncMutationReceipt.operation_key == payload["idempotencyKey"]
            ))
            assert common is not None
            assert common.domain_receipt_type == "work_sequence_candidate_deliveries"


def test_candidate_delivery_stops_for_revision_or_membership_change() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        recipient = UserAccount(
            user_id=f"user-delivery-conflict-{suffix}",
            username=f"delivery-conflict-{suffix}",
            login_id=f"delivery-conflict-{suffix}",
            display_name="충돌 수신자",
            role="team-member",
            password_hash=hash_password_for_dev("candidate-delivery-password"),
            is_active=True,
            status="ACTIVE",
        )
        with client.app.state.database.session() as session:
            session.add(recipient)
            session.commit()
        channel = client.post(
            "/api/v1/notification-channels",
            headers=headers,
            json={"name": f"전달 충돌 {suffix}", "channelType": "LINE"},
        ).json()
        member = client.post(
            f"/api/v1/notification-channels/{channel['channel_id']}/members",
            headers=headers,
            json={"userId": recipient.user_id, "memberRole": "MEMBER"},
        ).json()
        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"충돌 작업판 {suffix}", "idempotencyKey": f"conflict-board:{suffix}"},
        ).json()
        for index in range(2):
            board = client.post(
                f"/api/v1/work-sequence-boards/{board['board_id']}/items",
                headers=headers,
                json={
                    "title": f"충돌 항목 {index}",
                    "idempotencyKey": f"conflict-item:{suffix}:{index}",
                    "baseBoardRevision": board["board_revision"],
                },
            ).json()
        board = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json={
                "itemIds": [board["items"][1]["item_id"], board["items"][0]["item_id"]],
                "idempotencyKey": f"conflict-order:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        candidate = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates",
            headers=headers,
        ).json()[0]

        removed = client.patch(
            f"/api/v1/notification-channels/{channel['channel_id']}/members/{member['member_id']}",
            headers=headers,
            json={"status": "REMOVED"},
        )
        assert removed.status_code == 200
        membership_conflict = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/deliveries",
            headers=headers,
            json={
                "channelId": channel["channel_id"],
                "deliveryMode": "CHANNEL",
                "recipientIds": [recipient.user_id],
                "title": "전달 충돌",
                "body": "전달 충돌",
                "reason": "멤버십 경합 검증",
                "baseBoardRevision": board["board_revision"],
                "idempotencyKey": f"membership-conflict:{suffix}",
            },
        )
        assert membership_conflict.status_code == 409, membership_conflict.text
        assert membership_conflict.json()["detail"]["code"] == "CHANNEL_MEMBERSHIP_CHANGED"

        advanced = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{board['items'][0]['item_id']}/status",
            headers=headers,
            json={
                "status": "IN_PROGRESS",
                "idempotencyKey": f"advance-revision:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        )
        assert advanced.status_code == 200, advanced.text
        stale = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/delivery-preview",
            headers=headers,
            params={"channelId": channel["channel_id"]},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["detail"]["code"] == "WORK_SEQUENCE_DELIVERY_STALE_REVISION"


def test_work_sequence_delivery_templates_are_site_scoped_without_product_default() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        before = client.get("/api/v1/work-sequence-delivery-templates", headers=headers)
        assert before.status_code == 200, before.text
        assert all(row["site_scope"] == "DEFAULT" for row in before.json())

        created = client.post(
            "/api/v1/work-sequence-delivery-templates",
            headers=headers,
            json={
                "name": f"포장 우선 안내 {suffix}",
                "title": "포장 작업순서 변경",
                "body": "포장 공정을 먼저 진행해 주세요.",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["site_scope"] == "DEFAULT"
        listed = client.get("/api/v1/work-sequence-delivery-templates", headers=headers)
        assert any(row["template_id"] == created.json()["template_id"] for row in listed.json())

        archived = client.patch(
            f"/api/v1/work-sequence-delivery-templates/{created.json()['template_id']}",
            headers=headers,
            json={"status": "ARCHIVED"},
        )
        assert archived.status_code == 200, archived.text
        listed_after = client.get("/api/v1/work-sequence-delivery-templates", headers=headers)
        assert all(row["template_id"] != created.json()["template_id"] for row in listed_after.json())


def test_partial_delivery_retry_keeps_successes_and_retries_only_failed_recipient() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        recipient = UserAccount(
            user_id=f"user-partial-{suffix}",
            username=f"partial-{suffix}",
            login_id=f"partial-{suffix}",
            display_name="부분 실패 수신자",
            role="team-member",
            password_hash=hash_password_for_dev("partial-password"),
            is_active=True,
            status="ACTIVE",
        )
        with client.app.state.database.session() as session:
            session.add(recipient)
            session.commit()
        channel = client.post(
            "/api/v1/notification-channels",
            headers=headers,
            json={"name": f"부분 재시도 {suffix}", "channelType": "LINE"},
        ).json()
        client.post(
            f"/api/v1/notification-channels/{channel['channel_id']}/members",
            headers=headers,
            json={"userId": recipient.user_id, "memberRole": "MEMBER"},
        )
        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"부분 재시도 {suffix}", "idempotencyKey": f"partial-board:{suffix}"},
        ).json()
        board = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={
                "title": "부분 재시도 항목",
                "idempotencyKey": f"partial-item:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        item_id = board["items"][0]["item_id"]
        board = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{item_id}/status",
            headers=headers,
            json={
                "status": "IN_PROGRESS",
                "idempotencyKey": f"partial-status:{suffix}",
                "baseBoardRevision": board["board_revision"],
            },
        ).json()
        candidate = client.get(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates",
            headers=headers,
        ).json()[0]
        key = f"partial-delivery:{suffix}"
        payload = {
            "channelId": channel["channel_id"],
            "deliveryMode": "HANDOVER",
            "recipientIds": [recipient.user_id],
            "title": "부분 실패 재시도",
            "body": "실패 수신자만 다시 처리합니다.",
            "reason": "부분 성공 경계 검증",
            "baseBoardRevision": board["board_revision"],
            "idempotencyKey": key,
        }
        intent_hash = canonical_hash({
            "boardId": board["board_id"],
            "candidateId": candidate["candidate_id"],
            "channelId": channel["channel_id"],
            "deliveryMode": "HANDOVER",
            "recipientIds": [recipient.user_id],
            "title": payload["title"],
            "body": payload["body"],
            "reason": payload["reason"],
            "baseBoardRevision": board["board_revision"],
        })
        delivery_id = f"wseqdelivery_seed_{suffix}"
        handover_id = f"handover_seed_{suffix}"
        message_id = f"chmsg_seed_{suffix}"
        with client.app.state.database.session() as session:
            session.add(Handover(
                handover_id=handover_id,
                idempotency_key=f"wseq:{intent_hash}",
                channel_id=channel["channel_id"],
                title=payload["title"],
                body=payload["body"],
                source_type="WORK_SEQUENCE_ITEM",
                source_id=item_id,
                status="FOLLOW_UP_REQUIRED",
                created_by="user-admin",
                entry_source="windows_client",
            ))
            session.add(ChannelMessage(
                message_id=message_id,
                channel_id=channel["channel_id"],
                message_type="HANDOVER",
                source_type="HANDOVER",
                source_id=handover_id,
                title=payload["title"],
                body=payload["body"],
                created_by="user-admin",
            ))
            session.add(WorkSequenceCandidateDelivery(
                delivery_id=delivery_id,
                idempotency_key=key,
                intent_hash_sha256=intent_hash,
                candidate_id=candidate["candidate_id"],
                board_id=board["board_id"],
                board_revision=board["board_revision"],
                change_id=candidate["change_id"],
                channel_id=channel["channel_id"],
                delivery_mode="HANDOVER",
                title=payload["title"],
                body=payload["body"],
                reason=payload["reason"],
                source_type="WORK_SEQUENCE_ITEM",
                source_id=item_id,
                requested_recipient_ids_json=f'["{recipient.user_id}"]',
                message_id=message_id,
                handover_id=handover_id,
                status="PARTIAL",
                created_by="user-admin",
            ))
            session.add(WorkSequenceDeliveryRecipient(
                delivery_recipient_id=f"wseqrecipient_seed_{suffix}",
                delivery_id=delivery_id,
                recipient_id=recipient.user_id,
                delivery_status="FAILED",
                error_code="RECEIPT_WRITE_FAILED",
                error_message="seeded failure",
                attempt_count=1,
            ))
            session.commit()

        retried = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/"
            f"{candidate['candidate_id']}/deliveries",
            headers=headers,
            json=payload,
        )
        assert retried.status_code == 201, retried.text
        assert retried.json()["delivery_id"] == delivery_id
        assert retried.json()["status"] == "COMPLETED"
        assert retried.json()["recipients"][0]["attempt_count"] == 2
        assert retried.json()["recipients"][0]["handover_receipt_id"]
