from __future__ import annotations

from pathlib import Path
import runpy
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import AISearchGroundTruthCase, UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"


def _ensure_smoke48_cases() -> None:
    seed_script = API_ROOT.parents[1] / "scripts" / "seed-ai-ground-truth-48.py"
    seed = runpy.run_path(str(seed_script), run_name="flownote_seed_smoke48")["seed"]
    seed(TEST_DATABASE_URL)


def _client() -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(API_ROOT / "storage" / "ai-search-tests"),
    )
    return TestClient(create_app(settings))


def _login(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _add_user(client: TestClient, role: str) -> tuple[str, dict[str, str]]:
    suffix = uuid4().hex
    user_id = f"user-aigt-{role}-{suffix}"
    username = f"aigt-{role}-{suffix}"
    with client.app.state.database.session() as session:
        session.add(UserAccount(
            user_id=user_id,
            username=username,
            login_id=username,
            display_name=f"ground-truth {role}",
            role=role,
            password_hash=hash_password_for_dev("1234"),
            is_active=True,
            status="ACTIVE",
        ))
        session.commit()
    return user_id, _login(client, username)


def test_dataset_48_lifecycle_immutable_evaluation_and_restart_persistence() -> None:
    _ensure_smoke48_cases()
    with _client() as client:
        author_headers = _login(client, "admin")
        reviewer_id, reviewer_headers = _add_user(client, "manager")
        first_id, first_headers = _add_user(client, "document-admin")
        second_id, second_headers = _add_user(client, "system-admin")
        _, viewer_headers = _add_user(client, "viewer")

        with client.app.state.database.session() as session:
            case_ids = list(session.scalars(
                select(AISearchGroundTruthCase.ground_truth_case_id).where(
                    AISearchGroundTruthCase.case_key.like("smoke48-v1-%"),
                    AISearchGroundTruthCase.is_active.is_(True),
                ).order_by(AISearchGroundTruthCase.case_key)
            ).all())
        assert len(case_ids) == 48

        dataset_key = f"wpf-smoke48-{uuid4().hex}"
        payload = {
            "datasetKey": dataset_key,
            "title": "WPF 48건 운영 검증",
            "readinessTrack": "SMOKE_REGRESSION",
            "groundTruthCaseIds": case_ids,
            "changeReason": "후보 4의 48건을 WPF 운영 계약으로 구성",
        }
        forbidden = client.post("/api/v1/ai-search/ground-truth-datasets", headers=viewer_headers, json=payload)
        assert forbidden.status_code == 403
        created = client.post("/api/v1/ai-search/ground-truth-datasets", headers=author_headers, json=payload)
        assert created.status_code == 201, created.text
        dataset = created.json()
        dataset_id = dataset["dataset_version_id"]
        assert dataset["case_count"] == 48
        assert dataset["coverage_complete"] is True
        assert len(dataset["coverage"]) == 24
        assert all(item["count"] == 2 for item in dataset["coverage"])

        same_person_review = client.post(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/transition",
            headers=author_headers, json={"action": "SUBMIT_REVIEW", "reason": "검토 요청"},
        )
        assert same_person_review.status_code == 200
        rejected = client.post(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/transition",
            headers=author_headers, json={"action": "REVIEW", "reason": "작성자 자기 검토"},
        )
        assert rejected.status_code == 409
        reviewed = client.post(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/transition",
            headers=reviewer_headers, json={"action": "REVIEW", "reason": "독립 검토 완료"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewer_id"] == reviewer_id
        first = client.post(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/transition",
            headers=first_headers, json={"action": "FIRST_APPROVE", "reason": "1차 승인"},
        )
        assert first.status_code == 200
        assert first.json()["first_approved_by"] == first_id
        second = client.post(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/transition",
            headers=second_headers, json={"action": "SECOND_APPROVE", "reason": "2차 승인"},
        )
        assert second.status_code == 200, second.text
        approved = second.json()
        assert approved["status"] == "APPROVED"
        assert approved["second_approved_by"] == second_id
        assert len(approved["snapshot_hash"]) == 64

        immutable = client.put(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}/cases",
            headers=author_headers,
            json={"groundTruthCaseIds": case_ids, "changeReason": "승인 후 수정 시도"},
        )
        assert immutable.status_code == 409

        run = client.post("/api/v1/ai-search/evaluations", headers=second_headers, json={
            "runLabel": f"WPF 48건 {uuid4().hex}", "datasetVersionId": dataset_id,
        })
        assert run.status_code == 200, run.text
        body = run.json()
        assert body["dataset_version_id"] == dataset_id
        assert body["dataset_snapshot_hash"] == approved["snapshot_hash"]
        assert body["case_count"] == 48
        detail = client.get(f"/api/v1/ai-search/evaluations/{body['run_id']}", headers=author_headers)
        assert detail.status_code == 200
        assert detail.json()["dataset_version_id"] == dataset_id
        assert len(detail.json()["cases"]) == 48

    # 앱 재시작에 해당하는 새 app/session에서도 승인 snapshot과 run 결합이 보존된다.
    with _client() as restarted:
        headers = _login(restarted, "admin")
        persisted = restarted.get(
            f"/api/v1/ai-search/ground-truth-datasets/{dataset_id}", headers=headers
        )
        assert persisted.status_code == 200
        assert persisted.json()["status"] == "APPROVED"
        persisted_run = restarted.get(
            f"/api/v1/ai-search/evaluations/{body['run_id']}", headers=headers
        )
        assert persisted_run.status_code == 200
        assert persisted_run.json()["dataset_snapshot_hash"] == approved["snapshot_hash"]
