from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    Document,
    DocumentVersion,
    FileObject,
    ReconciliationItem,
    ReconciliationRun,
    ServerIdentity,
)
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"


def create_test_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        storage_root=str(API_ROOT / "storage" / "sync-reconciliation-tests"),
    )
    return TestClient(create_app(settings))


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_manifest_is_stable_and_epoch_increment_is_explicit() -> None:
    with create_test_client() as client:
        before = client.get("/api/v1/health/sync-manifest")
        assert before.status_code == 200
        headers = auth_headers(client)
        incremented = client.post("/api/v1/sync/server-epoch/increment", headers=headers)
        assert incremented.status_code == 200, incremented.text
        after = client.get("/api/v1/sync/manifest")
        assert after.status_code == 200
        assert after.json()["server_instance_id"] == before.json()["server_instance_id"]
        assert after.json()["server_epoch"] == before.json()["server_epoch"] + 1
        assert after.json()["api_contract_min"] <= 1 <= after.json()["api_contract_max"]
        with client.app.state.database.session() as session:
            identity = session.get(ServerIdentity, 1)
            assert identity is not None
            identity.server_instance_id = "srv-illegal-replacement"
            with pytest.raises(ValueError, match="immutable"):
                session.commit()
            session.rollback()


def test_reconciliation_classifies_and_preserves_divergence_after_approval() -> None:
    suffix = uuid4().hex
    key = f"wpf:document:recon-{suffix}:v1"
    content_hash = sha256(b"same-source").hexdigest()
    with create_test_client() as client:
        headers = auth_headers(client)
        with client.app.state.database.session() as session:
            file_object = FileObject(
                storage_key=f"tests/reconciliation/{suffix}.txt",
                original_filename="source.txt",
                hash_sha256=content_hash,
                size_bytes=11,
            )
            session.add(file_object)
            session.flush()
            document = Document(
                document_id=f"doc-{suffix}",
                idempotency_key=key,
                title="복구 판정 문서",
                document_type="일반문서",
                status="WORKING",
                revision=1,
            )
            session.add(document)
            session.flush()
            version = DocumentVersion(
                version_id=f"ver-{suffix}",
                document_id=document.document_id,
                file_object_id=file_object.id,
                version_no=1,
                change_reason="reconciliation test",
                version_status="WORKING",
                is_latest=True,
            )
            session.add(version)
            document.latest_version_id = version.version_id
            session.commit()

        created = client.post(
            "/api/v1/sync/reconciliation-runs",
            headers=headers,
            json={
                "clientId": f"wpf-{suffix}",
                "previousServerInstanceId": "srv-before",
                "previousServerEpoch": 1,
                "triggerReason": "EPOCH_CHANGED",
                "clientCursor": 12,
                "items": [
                    {
                        "clientItemId": "confirmed",
                        "entityType": "document",
                        "localId": f"local-{suffix}",
                        "localVersionNo": 1,
                        "idempotencyKey": key,
                        "localHashSha256": content_hash,
                    },
                    {
                        "clientItemId": "absent",
                        "entityType": "document_version",
                        "localId": f"local-{suffix}",
                        "localVersionNo": 2,
                        "idempotencyKey": f"missing-{suffix}",
                        "localHashSha256": content_hash,
                    },
                    {
                        "clientItemId": "diverged",
                        "entityType": "document",
                        "localId": f"local-{suffix}",
                        "localVersionNo": 1,
                        "idempotencyKey": key,
                        "localHashSha256": sha256(b"different").hexdigest(),
                    },
                ],
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert [(item["verdict"], item["proposed_action"]) for item in body["items"]] == [
            ("CONFIRMED", "REBOUND"),
            ("ABSENT", "REQUEUE"),
            ("DIVERGED", "CONFLICT"),
        ]
        applied = client.post(
            f"/api/v1/sync/reconciliation-runs/{body['run_id']}/apply",
            headers=headers,
            json={
                "approvalReason": "장애 주입 결과 검토 완료",
                "resolutions": [
                    {"itemId": item["item_id"], "action": item["proposed_action"], "reason": "검토 완료"}
                    for item in body["items"]
                ],
            },
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "APPLIED"
        with client.app.state.database.session() as session:
            run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.run_id == body["run_id"]))
            divergence = session.scalar(
                select(ReconciliationItem).where(
                    ReconciliationItem.run_id == body["run_id"],
                    ReconciliationItem.verdict == "DIVERGED",
                )
            )
            assert run is not None and run.status == "APPLIED"
            assert divergence is not None and divergence.resolution_action == "CONFLICT"


@pytest.mark.parametrize(
    "trigger_reason",
    ["RESTORED_CURRENT", "CURSOR_REGRESSED", "EMPTY_DATABASE", "INSTANCE_CHANGED"],
)
def test_each_recovery_injection_creates_an_independent_preserved_run(trigger_reason: str) -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        response = client.post(
            "/api/v1/sync/reconciliation-runs",
            headers=auth_headers(client),
            json={
                "clientId": f"wpf-fault-{suffix}",
                "previousServerInstanceId": f"srv-old-{suffix}",
                "previousServerEpoch": 1,
                "triggerReason": trigger_reason,
                "clientCursor": 0,
                "items": [],
            },
        )
        assert response.status_code == 201, response.text
        run_id = response.json()["run_id"]
        assert run_id.startswith("recon-")
        with client.app.state.database.session() as session:
            run = session.scalar(select(ReconciliationRun).where(ReconciliationRun.run_id == run_id))
            assert run is not None
            assert run.trigger_reason == trigger_reason
            assert run.status == "REVIEW_REQUIRED"
