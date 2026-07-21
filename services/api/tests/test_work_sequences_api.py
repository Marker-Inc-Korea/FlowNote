from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import (
    ActivityHistory,
    WorkSequenceBoard,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
    WorkSequenceMutationReceipt,
    WorkSequenceNotificationCandidate,
)
from app.main import create_app


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
        sent_response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/notification-candidates/{status_candidate['candidate_id']}",
            headers=headers,
            json={"status": "SENT"},
        )
        assert sent_response.status_code == 200, sent_response.text
        assert sent_response.json()["status"] == "SENT"

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
            assert any(item.status == "SENT" for item in candidates)
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
