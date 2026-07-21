from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.init_db import hash_password
from app.db.models import AIQuery, UserAccount
from app.main import create_app

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"


def create_client() -> TestClient:
    scope = uuid4().hex
    return TestClient(create_app(Settings(
        _env_file=None, environment="test", database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        ai_external_call_enabled=True, ai_readiness_gate_enabled=False,
        ai_provider="TEST_PROVIDER", ai_model="test-model",
        ai_customer_scope=f"customer-{scope}", ai_site_scope=f"site-{scope}",
        ai_retention_scheduler_enabled=False,
    )))


def login(client: TestClient, username: str, password: str = "test-password") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def system_admin(client: TestClient) -> dict[str, str]:
    suffix = uuid4().hex
    username = f"ai-system-{suffix}"
    with client.app.state.database.session() as session:
        session.add(UserAccount(
            user_id=f"user-{suffix}", username=username, login_id=username,
            display_name="AI 시스템 관리자", role="system-admin",
            password_hash=hash_password("test-password"), is_active=True, status="ACTIVE",
        ))
        session.commit()
    return login(client, username)


def test_role_matrix_approval_prompt_policy_and_kill_switch_are_audited() -> None:
    with create_client() as client:
        ordinary = login(client, "admin", "1234")
        assert client.get("/api/v1/ai-operations/approvals", headers=ordinary).status_code == 403
        assert client.get("/api/v1/ai-operations/provider-reviews", headers=ordinary).status_code == 403
        auth = system_admin(client)
        settings = client.app.state.settings
        canary = f"API-KEY-CANARY-{uuid4().hex}"
        env_name = "FLOWNOTE_AI_TEST_PROVIDER_API_KEY"
        os.environ[env_name] = canary
        try:
            global_policy = client.put("/api/v1/ai-operations/policies", headers=auth, json={
                "scopeType": "GLOBAL", "killSwitchEnabled": True,
                "maxRequestsPerDay": 100, "maxConcurrency": 2, "timeoutSeconds": 10,
                "dailyCostBudgetMicros": 1000000, "queryPayloadRetentionDays": 90,
                "responseRetentionDays": 90, "auditRetentionDays": 365,
                "allowAuditExport": False, "reason": "통합 테스트 전역 즉시 중지",
            })
            assert global_policy.status_code == 200, global_policy.text
            assert global_policy.json()["providerCredentialConfigured"] is True
            assert canary not in global_policy.text
            blocked = client.post("/api/v1/ai/queries", headers=auth, json={
                "purpose": "EVIDENCE_SUMMARY", "query": "즉시 중지 상태 확인"
            })
            assert blocked.status_code == 503
            assert blocked.json()["error"]["code"] == "AI_GLOBAL_KILL_SWITCH"
            events = client.get("/api/v1/ai-operations/audit/events", headers=auth).json()
            assert any(item["reasonCode"] == "AI_GLOBAL_KILL_SWITCH" for item in events)
            resumed = client.put("/api/v1/ai-operations/policies", headers=auth, json={
                "scopeType": "GLOBAL", "killSwitchEnabled": False,
                "maxRequestsPerDay": 100, "maxConcurrency": 2, "timeoutSeconds": 10,
                "dailyCostBudgetMicros": 1000000, "queryPayloadRetentionDays": 90,
                "responseRetentionDays": 90, "auditRetentionDays": 365,
                "allowAuditExport": False, "reason": "통합 테스트 후 전역 호출 재개",
            })
            assert resumed.status_code == 200
            assert canary.encode() not in TEST_DB_PATH.read_bytes()
        finally:
            os.environ.pop(env_name, None)

        expires = datetime.now(timezone.utc) + timedelta(days=30)
        approval = client.post("/api/v1/ai-operations/approvals", headers=auth, json={
            "customerScope": settings.ai_customer_scope, "siteScope": settings.ai_site_scope,
            "provider": "TEST_PROVIDER", "modelScope": "test-model",
            "purposes": ["EVIDENCE_SUMMARY"], "sourceTypes": ["FIELD_COMMENT"],
            "dataHandlingPolicyVersion": "test-v1", "expiresAt": expires.isoformat(),
            "reason": "현재 고객과 현장의 요약만 승인",
        })
        assert approval.status_code == 201, approval.text
        approval_id = approval.json()["approvalId"]
        revoked = client.post(f"/api/v1/ai-operations/approvals/{approval_id}/revoke",
                              headers=auth, json={"reason": "통합 테스트 폐기"})
        assert revoked.status_code == 200 and revoked.json()["status"] == "REVOKED"

        created = client.post("/api/v1/ai-operations/prompts", headers=auth, json={
            "name": f"evidence-{uuid4().hex}", "version": "1",
            "templateText": "제공된 근거만 사용하고 candidate ID를 인용한다.",
            "allowedPurpose": "EVIDENCE_SUMMARY",
        })
        assert created.status_code == 201, created.text
        prompt_id = created.json()["promptVersionId"]
        for action, expected in (("review", "REVIEWED"), ("approve", "APPROVED"), ("activate", "ACTIVE")):
            response = client.post(f"/api/v1/ai-operations/prompts/{prompt_id}/{action}",
                                   headers=auth, json={"reason": f"{action} 검증"})
            assert response.status_code == 200, response.text
            assert response.json()["status"] == expected
        prompts = client.get("/api/v1/ai-operations/prompts", headers=auth).json()
        snapshot = next(row for row in prompts if row["promptVersionId"] == prompt_id)
        assert snapshot["templateHash"] and snapshot["templateText"].startswith("제공된 근거")

        checklist = {
            key: {"status": "PASS", "note": f"{key} 검토 증거", "evidenceReference": f"review://{key}"}
            for key in (
                "contract_terms", "data_retention", "training_use", "transfer_region", "tls",
                "timeout", "rate_limit_429", "server_error_5xx", "cost_limit", "kill_switch",
                "legal_approval", "customer_approval",
            )
        }
        provider_review = client.post("/api/v1/ai-operations/provider-reviews", headers=auth, json={
            "customerScope": settings.ai_customer_scope, "siteScope": settings.ai_site_scope,
            "provider": "TEST_PROVIDER", "modelScope": "test-model", "reviewVersion": "review-v1",
            "allowedPurposes": ["EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"], "checklist": checklist,
            "technicalStatus": "APPROVED", "securityStatus": "APPROVED",
            "legalStatus": "APPROVED", "customerStatus": "APPROVED",
        })
        assert provider_review.status_code == 201, provider_review.text
        assert provider_review.json()["checklistPassed"] is True
        assert provider_review.json()["providerStartApproved"] is True
        reviews = client.get(
            "/api/v1/ai-operations/provider-reviews", headers=auth,
            params={"customerScope": settings.ai_customer_scope, "siteScope": settings.ai_site_scope},
        )
        assert reviews.status_code == 200
        assert any(item["reviewId"] == provider_review.json()["reviewId"] for item in reviews.json())


def test_retention_redacts_payload_preserves_hash_references_and_records_history() -> None:
    with create_client() as client:
        auth = system_admin(client)
        settings = client.app.state.settings
        query_id = f"aiq-retention-{uuid4().hex}"
        now = datetime.now(timezone.utc)
        with client.app.state.database.session() as session:
            session.add(AIQuery(
                query_id=query_id, requested_by=session.scalar(select(UserAccount.user_id).where(
                    UserAccount.role == "system-admin").order_by(UserAccount.id.desc())),
                customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
                query_text="만료될 원문 민감 질의", query_hash="a" * 64,
                purpose="EVIDENCE_SUMMARY", status="SUCCEEDED",
                response_storage_mode="STORE_90_DAYS", response_text="만료될 응답 원문",
                response_hash="b" * 64, retention_until=now - timedelta(seconds=1),
                response_retention_until=now - timedelta(seconds=1),
            ))
            session.commit()
        result = client.post("/api/v1/ai-operations/retention/run", headers=auth)
        assert result.status_code == 200, result.text
        assert result.json()["queryPayloadsDeidentified"] == 1
        assert result.json()["responsesDeleted"] == 1
        history = client.get("/api/v1/ai-operations/retention/audit", headers=auth).json()
        assert any(item["queryId"] == query_id and item["responseTextAction"] == "DELETED" for item in history)
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == query_id))
            assert query.query_text == "[EXPIRED]" and query.response_text is None
            assert query.query_hash == "a" * 64 and query.response_hash == "b" * 64
            foreign_keys = session.execute(text("PRAGMA foreign_key_check")).all()
            assert foreign_keys == []


def test_legal_hold_blocks_retention_and_release_allows_immediate_expiry() -> None:
    with create_client() as client:
        auth = system_admin(client)
        settings = client.app.state.settings
        query_id = f"aiq-hold-{uuid4().hex}"
        other_scope_query_id = f"aiq-other-scope-{uuid4().hex}"
        now = datetime.now(timezone.utc)
        with client.app.state.database.session() as session:
            actor_id = session.scalar(select(UserAccount.user_id).where(
                UserAccount.role == "system-admin"
            ).order_by(UserAccount.id.desc()))
            session.add(AIQuery(
                query_id=query_id, requested_by=actor_id,
                customer_scope=settings.ai_customer_scope, site_scope=settings.ai_site_scope,
                query_text="legal hold 보존 대상 질의", query_hash="c" * 64,
                purpose="EVIDENCE_SUMMARY", status="SUCCEEDED",
                response_storage_mode="STORE_90_DAYS", response_text="보존 대상 응답",
                response_hash="d" * 64, retention_until=now - timedelta(seconds=1),
                response_retention_until=now - timedelta(seconds=1),
            ))
            session.add(AIQuery(
                query_id=other_scope_query_id, requested_by=actor_id,
                customer_scope="other-customer", site_scope="other-site",
                query_text="다른 scope 질의", query_hash="e" * 64,
                purpose="EVIDENCE_SUMMARY", status="SUCCEEDED",
                response_storage_mode="DO_NOT_STORE", response_hash="f" * 64,
                retention_until=now + timedelta(days=90),
            ))
            session.commit()

        audit_query_ids = {
            item["queryId"] for item in client.get(
                "/api/v1/ai-operations/audit/queries", headers=auth
            ).json()
        }
        assert query_id in audit_query_ids
        assert other_scope_query_id not in audit_query_ids
        cross_scope_hold = client.post(
            f"/api/v1/ai-operations/queries/{other_scope_query_id}/legal-holds", headers=auth,
            json={"reason": "범위 밖 시도", "authorityReference": "must-not-exist"},
        )
        assert cross_scope_hold.status_code == 404

        hold = client.post(
            f"/api/v1/ai-operations/queries/{query_id}/legal-holds", headers=auth,
            json={"reason": "분쟁 보존", "authorityReference": "legal-case-test-1"},
        )
        assert hold.status_code == 201, hold.text
        hold_id = hold.json()["holdId"]
        retained = client.post("/api/v1/ai-operations/retention/run", headers=auth)
        assert retained.status_code == 200
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == query_id))
            assert query.query_text == "legal hold 보존 대상 질의"
            assert query.response_text == "보존 대상 응답"

        blocked = client.post(
            f"/api/v1/ai-operations/queries/{query_id}/expire", headers=auth,
            json={"reason": "보존 중 즉시 만료 시도"},
        )
        assert blocked.status_code == 409
        released = client.post(
            f"/api/v1/ai-operations/legal-holds/{hold_id}/release", headers=auth,
            json={"reason": "보존 의무 종료"},
        )
        assert released.status_code == 200 and released.json()["status"] == "RELEASED"
        expired = client.post(
            f"/api/v1/ai-operations/queries/{query_id}/expire", headers=auth,
            json={"reason": "사용자 즉시 만료 요청"},
        )
        assert expired.status_code == 200, expired.text
        assert expired.json()["queryPayloadsDeidentified"] == 1
        assert expired.json()["responsesDeleted"] == 1
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == query_id))
            assert query.query_text == "[EXPIRED]" and query.response_text is None
