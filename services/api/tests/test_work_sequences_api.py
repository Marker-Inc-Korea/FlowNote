from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    ActivityHistory,
    WorkSequenceChangeHistory,
    WorkSequenceItem,
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
            },
        )
        assert board_response.status_code == 201, board_response.text
        board = board_response.json()
        assert board["board_id"].startswith("wseqboard_")
        assert board["items"] == []

        first_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={"title": f"Prepare material {suffix}", "assignedTo": "line-a"},
        )
        assert first_response.status_code == 201, first_response.text
        first_item = first_response.json()["items"][0]

        second_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={"title": f"Start press run {suffix}", "workOrderNo": f"WO-{suffix}"},
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
            },
        )
        assert reorder_response.status_code == 200, reorder_response.text
        reordered = reorder_response.json()["items"]
        assert [item["item_id"] for item in reordered] == [second_item["item_id"], first_item["item_id"]]
        assert [item["sort_order"] for item in reordered] == [1, 2]

        status_response = client.patch(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/{second_item['item_id']}/status",
            headers=headers,
            json={"status": "HOLD", "changeReason": "Material is delayed.", "holdReason": "Material is delayed."},
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
        assert "STATUS_CHANGED" in history_types
        assert "HOLD_REASON_CHANGED" in history_types

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
            assert any(item.change_type == "HOLD_REASON_CHANGED" for item in history)
            candidates = session.scalars(
                select(WorkSequenceNotificationCandidate).where(
                    WorkSequenceNotificationCandidate.board_id == board["board_id"]
                )
            ).all()
            assert any(item.event_type == "work_sequence.reordered" for item in candidates)
            assert any(item.event_type == "work_sequence.status_changed" for item in candidates)
            assert any(item.event_type == "work_sequence.hold_reason_changed" for item in candidates)
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
            json={"title": f"Invalid reorder board {uuid4().hex[:8]}"},
        )
        assert board_response.status_code == 201
        board = board_response.json()
        item_response = client.post(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items",
            headers=headers,
            json={"title": "Only item"},
        )
        assert item_response.status_code == 201
        item = item_response.json()["items"][0]

        response = client.put(
            f"/api/v1/work-sequence-boards/{board['board_id']}/items/order",
            headers=headers,
            json={"itemIds": [item["item_id"], item["item_id"]]},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "itemIds must contain every item on the board exactly once."


def test_work_sequence_requires_authentication() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/work-sequence-boards",
            json={"title": "Unauthenticated board"},
        )

    assert response.status_code == 401
