from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import (
    AICallAttempt,
    AIPromptVersion,
    AIQuery,
    AIQueryEvidenceCandidate,
    AISearchCandidate,
    AITransferApproval,
    UserAccount,
)
from app.db.init_db import hash_password_for_dev
from app.main import create_app
from test_ai_search_api import seed_ai_search_sources

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"


def create_client(*, enabled: bool = False) -> TestClient:
    scope = uuid4().hex
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL, storage_root=str(API_ROOT / "storage" / "ai-query-tests"),
        ai_external_call_enabled=enabled, ai_provider="TEST_PROVIDER", ai_model="test-model",
        ai_customer_scope=f"customer-{scope}", ai_site_scope=f"site-{scope}",
    )
    return TestClient(create_app(settings))


def headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "1234"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_policy(client: TestClient, *, expires_delta: timedelta = timedelta(days=1),
                revoked: bool = False, model_scope: str = "test-model") -> None:
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex
    template = "근거만 사용해 응답하고 후보 ID를 인용한다."
    with client.app.state.database.session() as session:
        session.add(AIPromptVersion(
            prompt_version_id=f"aipv-{suffix}", name="evidence-summary", version=suffix[:8],
            template_hash=hashlib.sha256(template.encode()).hexdigest(), template_text=template,
            allowed_purpose="EVIDENCE_SUMMARY", created_by="user-admin", approved_by="user-admin",
            approved_at=now,
        ))
        session.add(AITransferApproval(
            approval_id=f"aita-{suffix}",
            customer_scope=client.app.state.settings.ai_customer_scope,
            site_scope=client.app.state.settings.ai_site_scope,
            provider="TEST_PROVIDER", model_scope=model_scope,
            allowed_source_types=json.dumps(["PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT",
                                             "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"]),
            data_handling_policy_version="test-v1", approved_by="user-admin", approved_at=now,
            expires_at=now + expires_delta, revoked_at=now if revoked else None, reason="테스트 승인",
        ))
        session.commit()


def rebuild_and_candidates(client: TestClient, auth: dict[str, str], seeded: dict[str, str]) -> dict[str, str]:
    response = client.post("/api/v1/ai-search/candidates/rebuild", headers=auth)
    assert response.status_code == 200
    wanted = {seeded["published_document_id"], seeded["analyzed_comment_id"], seeded["new_comment_id"]}
    with client.app.state.database.session() as session:
        candidates = session.scalars(select(AISearchCandidate).where(AISearchCandidate.source_id.in_(wanted))).all()
        return {item.source_id: item.candidate_id for item in candidates}


def test_disabled_flag_and_forbidden_scope_never_call_provider_and_leave_audit_state() -> None:
    class Spy:
        calls = 0
        def __call__(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            raise AssertionError("provider must not be called")

    with create_client() as client:
        auth = headers(client)
        spy = Spy()
        client.app.state.ai_provider = spy
        disabled = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "비밀 프롬프트 본문", "responseStorageMode": "DO_NOT_STORE"
        })
        forbidden = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EQUIPMENT_CONTROL", "query": "설비를 제어해 주세요"
        })
        assert disabled.status_code == 503
        assert disabled.json()["error"]["code"] == "AI_EXTERNAL_CALL_DISABLED"
        assert forbidden.status_code == 422
        assert forbidden.json()["error"]["code"] == "AI_SCOPE_NOT_ALLOWED"
        assert spy.calls == 0
        assert "비밀 프롬프트 본문" not in disabled.text
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == disabled.json()["queryId"]))
            attempt = session.scalar(select(AICallAttempt).where(AICallAttempt.query_id == query.query_id))
            assert query.status == "BLOCKED" and query.block_code == "AI_EXTERNAL_CALL_DISABLED"
            assert attempt.status == "BLOCKED" and attempt.error_code == "AI_EXTERNAL_CALL_DISABLED"
            assert "비밀 프롬프트 본문" not in (attempt.sanitized_error_message or "")


@pytest.mark.parametrize("approval_kind", ["missing", "expired", "revoked", "scope_mismatch"])
def test_invalid_transfer_approval_is_blocked_before_provider(approval_kind: str) -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        if approval_kind == "expired":
            seed_policy(client, expires_delta=timedelta(seconds=-1))
        elif approval_kind == "revoked":
            seed_policy(client, revoked=True)
        elif approval_kind == "scope_mismatch":
            seed_policy(client, model_scope="another-model")
        calls = 0
        def spy(_payload: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}
        client.app.state.ai_provider = spy
        response = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "근거를 요약해 주세요"
        })
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "AI_TRANSFER_NOT_APPROVED"
        assert calls == 0


def test_snapshot_rechecks_source_state_and_do_not_store_keeps_only_response_hash() -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        seed_policy(client)
        seeded = seed_ai_search_sources(client)
        candidate_ids = rebuild_and_candidates(client, auth, seeded)
        calls: list[dict[str, object]] = []
        def spy(payload: dict[str, object]) -> dict[str, object]:
            calls.append(payload)
            selected = payload["candidateIds"]
            return {"response": "검증된 응답 원문", "claims": [{
                "claimKey": "claim-1", "text": "검증된 주장", "candidateIds": [selected[0]]
            }]}
        client.app.state.ai_provider = spy
        response = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "공개 근거를 요약해 주세요",
            "candidateIds": list(candidate_ids.values()), "responseStorageMode": "DO_NOT_STORE"
        })
        assert response.status_code == 200, response.text
        assert len(calls) == 1, response.json()
        assert candidate_ids[seeded["new_comment_id"]] not in calls[0]["candidateIds"]
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == response.json()["queryId"]))
            snapshots = session.scalars(select(AIQueryEvidenceCandidate).where(
                AIQueryEvidenceCandidate.query_id == query.query_id)).all()
            assert query.response_text is None
            assert query.response_hash == hashlib.sha256("검증된 응답 원문".encode()).hexdigest()
            assert all(row.candidate_id != candidate_ids[seeded["new_comment_id"]] for row in snapshots)
            assert all(row.trace_id and row.content_hash for row in snapshots)


def test_no_evidence_and_non_admin_are_rejected_without_provider_call() -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        seed_policy(client)
        calls = 0
        def spy(_payload: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}
        client.app.state.ai_provider = spy
        response = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "없는 근거를 요약해 주세요",
            "candidateIds": [f"missing-{uuid4().hex}"]
        })
        assert response.status_code == 200
        assert response.json()["status"] == "INSUFFICIENT_EVIDENCE"
        assert response.json()["summary"] is None
        assert calls == 0
        suffix = uuid4().hex
        with client.app.state.database.session() as session:
            session.add(UserAccount(
                user_id=f"user-viewer-{suffix}", username=f"viewer-{suffix}",
                login_id=f"viewer-{suffix}", display_name="조회 사용자", role="viewer",
                password_hash=hash_password_for_dev("1234"), is_active=True, status="ACTIVE",
            ))
            session.commit()
        login = client.post("/api/v1/auth/login", json={"username": f"viewer-{suffix}", "password": "1234"})
        viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        denied = client.post("/api/v1/ai/queries", headers=viewer_headers, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "권한 없는 질의"
        })
        assert denied.status_code == 403
        assert calls == 0


def test_approved_prompt_content_is_immutable() -> None:
    with create_client() as client:
        seed_policy(client)
        with client.app.state.database.session() as session:
            prompt = session.scalar(select(AIPromptVersion).order_by(AIPromptVersion.id.desc()))
            prompt.template_text = "승인 후 덮어쓰면 안 되는 변경"
            with pytest.raises(ValueError, match="immutable"):
                session.commit()
