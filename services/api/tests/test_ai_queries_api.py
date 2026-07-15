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
    AISensitiveDataPolicy,
    AITransferApproval,
    FieldComment,
    NotificationChannel,
    UserAccount,
)
from app.db.init_db import hash_password_for_dev
from app.main import create_app
from test_ai_search_api import seed_ai_search_sources

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"


def create_client(*, enabled: bool = False, readiness_gate: bool = False) -> TestClient:
    scope = uuid4().hex
    settings = Settings(
        _env_file=None, environment="test", database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL, storage_root=str(API_ROOT / "storage" / "ai-query-tests"),
        ai_external_call_enabled=enabled, ai_readiness_gate_enabled=readiness_gate,
        ai_provider="TEST_PROVIDER", ai_model="test-model",
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
            approved_at=now, activated_at=now,
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
    wanted = {
        seeded["published_document_id"],
        seeded["analyzed_comment_id"],
        seeded["selected_comment_id"],
        seeded["new_comment_id"],
        seeded["history_id"],
        seeded["report_source_row_id"],
    }
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


def test_readiness_gap_blocks_operational_provider_call_with_numeric_shortage() -> None:
    with create_client(enabled=True, readiness_gate=True) as client:
        auth = headers(client)
        calls = 0

        def spy(_payload: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        client.app.state.ai_provider = spy
        response = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "준비되지 않은 범위의 근거를 요약해 주세요"
        })
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "AI_READINESS_NOT_MET"
        assert "질문 50건 부족" in response.json()["error"]["message"]
        assert calls == 0


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
        assert response.json()["error"]["code"] == "APPROVAL_REVOKED"
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
            selected = [item["candidateId"] for item in payload["sources"]]
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
        sent_ids = [item["candidateId"] for item in calls[0]["sources"]]
        assert candidate_ids[seeded["new_comment_id"]] not in sent_ids
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == response.json()["queryId"]))
            snapshots = session.scalars(select(AIQueryEvidenceCandidate).where(
                AIQueryEvidenceCandidate.query_id == query.query_id)).all()
            assert query.response_text is None
            assert query.response_hash == hashlib.sha256("검증된 응답 원문".encode()).hexdigest()
            prompt_snapshot = json.loads(query.prompt_snapshot_json)
            approval_snapshot = json.loads(query.approval_snapshot_json)
            assert prompt_snapshot["templateHash"] and prompt_snapshot["templateText"]
            assert approval_snapshot["customerScope"] == client.app.state.settings.ai_customer_scope
            assert approval_snapshot["siteScope"] == client.app.state.settings.ai_site_scope
            excluded = next(
                row for row in snapshots
                if row.candidate_id == candidate_ids[seeded["new_comment_id"]]
            )
            assert excluded.eligibility_result == "EXCLUDED"
            assert excluded.exclusion_reason == "SOURCE_FORBIDDEN"
            assert all(row.trace_id and row.content_hash for row in snapshots)


def test_four_source_minimal_payload_excludes_pii_candidate_and_preserves_stable_identity() -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        seed_policy(client)
        seeded = seed_ai_search_sources(client)
        raw_email = f"worker-{uuid4().hex[:8]}@factory.example"
        raw_phone = "010-9876-5432"
        raw_rrn = "900101-1234567"
        with client.app.state.database.session() as session:
            sensitive_comment_id = f"comment-ai-sensitive-{uuid4().hex}"
            session.add(FieldComment(
                comment_id=sensitive_comment_id,
                document_id=seeded["published_document_id"],
                document_version_id=seeded["published_version_id"],
                comment_type="issue", input_mode="free_text", signal_level="RED",
                raw_content=f"검토 연락처 {raw_email}, {raw_phone}, {raw_rrn}. 조치 완료.",
                author_id="user-admin", entry_source="field_user", status="ANALYZED",
            ))
            session.commit()
        candidate_ids = rebuild_and_candidates(client, auth, seeded)
        with client.app.state.database.session() as session:
            assert session.scalar(select(AISearchCandidate).where(
                AISearchCandidate.source_id == sensitive_comment_id
            )) is None
        four_ids = [
            candidate_ids[seeded["published_document_id"]],
            candidate_ids[seeded["selected_comment_id"]],
            candidate_ids[seeded["history_id"]],
            candidate_ids[seeded["report_source_row_id"]],
        ]
        payload_bytes: list[bytes] = []

        def spy(payload: dict[str, object]) -> dict[str, object]:
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            payload_bytes.append(encoded)
            selected = [item["candidateId"] for item in payload["sources"]]
            return {
                "response": "네 원천 근거 요약",
                "claims": [{"claimKey": "four-sources", "text": "요약", "candidateIds": selected}],
            }

        client.app.state.ai_provider = spy
        response = client.post(
            "/api/v1/ai/queries",
            headers=auth,
            json={
                "purpose": "EVIDENCE_SUMMARY",
                "query": "문서, 현장 코멘트, 작업순서, 보고서 근거를 함께 요약해 주세요",
                "candidateIds": four_ids,
            },
        )
        assert response.status_code == 200, response.text
        repeated = client.post(
            "/api/v1/ai/queries",
            headers=auth,
            json={
                "purpose": "EVIDENCE_SUMMARY",
                "query": "문서, 현장 코멘트, 작업순서, 보고서 근거를 함께 요약해 주세요",
                "candidateIds": four_ids,
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert len(payload_bytes) == 2
        encoded = payload_bytes[0]
        assert raw_email.encode() not in encoded
        assert raw_phone.encode() not in encoded
        assert raw_rrn.encode() not in encoded
        assert "[이메일 마스킹]".encode() not in encoded
        assert "[전화번호 마스킹]".encode() not in encoded
        assert "[주민번호 마스킹]".encode() not in encoded
        sent = json.loads(encoded)["sources"]
        assert {item["sourceType"] for item in sent} == {
            "PUBLISHED_DOCUMENT_VERSION", "FIELD_COMMENT", "WORK_SEQUENCE_HISTORY", "REPORT_SOURCE"
        }
        assert [item["candidateId"] for item in sent] == four_ids
        assert all(
            item["candidateId"] and item["sourceId"] and item["traceId"]
            and item["contentHash"] and item["rank"] > 0 and item["excerpt"]
            for item in sent
        )
        boundary = json.loads(encoded)
        repeated_boundary = json.loads(payload_bytes[1])
        assert boundary["sources"] == repeated_boundary["sources"]
        assert boundary["promptVersionId"] and boundary["promptVersion"]
        assert boundary["traceId"] == response.json()["queryId"]


def test_restricted_source_and_query_never_cross_provider_or_audit_log() -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        seed_policy(client)
        seeded = seed_ai_search_sources(client)
        forbidden_secret = f"token-{uuid4().hex}"
        site_term = f"site-deny-{uuid4().hex}"
        with client.app.state.database.session() as session:
            restricted_comment_id = f"comment-ai-restricted-{uuid4().hex}"
            session.add(FieldComment(
                comment_id=restricted_comment_id,
                document_id=seeded["published_document_id"],
                document_version_id=seeded["published_version_id"],
                comment_type="issue", input_mode="free_text", signal_level="RED",
                raw_content=f"api_key={forbidden_secret}", author_id="user-admin",
                entry_source="field_user", status="ANALYZED",
            ))
            session.add(
                AISensitiveDataPolicy(
                    policy_id=f"aisdp-{uuid4().hex}",
                    customer_scope=client.app.state.settings.ai_customer_scope,
                    site_scope=client.app.state.settings.ai_site_scope,
                    version="test-v1",
                    forbidden_terms_json=json.dumps([site_term]),
                    customer_identifiers_json=json.dumps(["CUST-SECRET-77"]),
                    created_by="user-admin",
                )
            )
            session.commit()
        candidate_ids = rebuild_and_candidates(client, auth, seeded)
        with client.app.state.database.session() as session:
            assert session.scalar(select(AISearchCandidate).where(
                AISearchCandidate.source_id == restricted_comment_id
            )) is None
        calls: list[bytes] = []

        def spy(payload: dict[str, object]) -> dict[str, object]:
            calls.append(json.dumps(payload, ensure_ascii=False).encode())
            selected = [item["candidateId"] for item in payload["sources"]]
            return {"response": "허용 근거", "claims": [{
                "claimKey": "safe", "text": "허용", "candidateIds": selected
            }]}

        client.app.state.ai_provider = spy
        mixed = client.post("/api/v1/ai/queries", headers=auth, json={
            "purpose": "EVIDENCE_SUMMARY",
            "query": "허용 근거만 요약",
            "candidateIds": [
                candidate_ids[seeded["published_document_id"]],
                candidate_ids[seeded["selected_comment_id"]],
            ],
        })
        assert mixed.status_code == 200, mixed.text
        assert forbidden_secret.encode() not in calls[0]
        with client.app.state.database.session() as session:
            rows = session.scalars(select(AIQueryEvidenceCandidate).where(
                AIQueryEvidenceCandidate.query_id == mixed.json()["queryId"]
            )).all()
            assert all(row.eligibility_result == "ELIGIBLE" for row in rows)

        blocked_responses = [
            client.post("/api/v1/ai/queries", headers=auth, json={
                "purpose": "EVIDENCE_SUMMARY", "query": restricted_query,
                "candidateIds": [candidate_ids[seeded["published_document_id"]]],
            })
            for restricted_query in (
                f"{site_term} 관련 내용을 알려주세요",
                "CUST-SECRET-77 고객 자료를 알려주세요",
                "/Users/operator/private/secret.txt 파일을 알려주세요",
            )
        ]
        assert all(response.status_code == 422 for response in blocked_responses)
        assert all(
            response.json()["error"]["code"] == "CONTENT_RESTRICTED"
            for response in blocked_responses
        )
        assert len(calls) == 1
        blocked = blocked_responses[0]
        with client.app.state.database.session() as session:
            query = session.scalar(select(AIQuery).where(AIQuery.query_id == blocked.json()["queryId"]))
            attempt = session.scalar(select(AICallAttempt).where(AICallAttempt.query_id == query.query_id))
            assert query.query_text == "[REDACTED]"
            assert site_term not in (attempt.sanitized_error_message or "")


def test_manager_without_linked_channel_is_source_forbidden() -> None:
    with create_client(enabled=True) as client:
        admin_auth = headers(client)
        seed_policy(client)
        seeded = seed_ai_search_sources(client)
        candidate_ids = rebuild_and_candidates(client, admin_auth, seeded)
        suffix = uuid4().hex
        manager_id = f"user-manager-{suffix}"
        with client.app.state.database.session() as session:
            session.add(UserAccount(
                user_id=manager_id, username=f"manager-{suffix}", login_id=f"manager-{suffix}",
                display_name="권한 검사 관리자", role="manager",
                password_hash=hash_password_for_dev("1234"), is_active=True, status="ACTIVE",
            ))
            session.add(NotificationChannel(
                channel_id=f"channel-private-{suffix}", name="비공개 라인 채널",
                channel_type="CUSTOM", source_type="FIELD_COMMENT",
                source_id=seeded["analyzed_comment_id"], status="ACTIVE", created_by="user-admin",
            ))
            session.commit()
        login = client.post("/api/v1/auth/login", json={"username": f"manager-{suffix}", "password": "1234"})
        manager_auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        calls = 0

        def spy(_payload: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {}

        client.app.state.ai_provider = spy
        response = client.post("/api/v1/ai/queries", headers=manager_auth, json={
            "purpose": "EVIDENCE_SUMMARY", "query": "비공개 채널 근거 요약",
            "candidateIds": [candidate_ids[seeded["analyzed_comment_id"]]],
        })
        assert response.status_code == 200
        assert response.json()["status"] == "INSUFFICIENT_EVIDENCE"
        assert calls == 0
        with client.app.state.database.session() as session:
            row = session.scalar(select(AIQueryEvidenceCandidate).where(
                AIQueryEvidenceCandidate.query_id == response.json()["queryId"]
            ))
            assert row.exclusion_reason == "SOURCE_FORBIDDEN"


def test_approval_revocation_blocks_new_query_but_offline_quality_stays_available() -> None:
    with create_client(enabled=True) as client:
        auth = headers(client)
        seed_policy(client)
        seeded = seed_ai_search_sources(client)
        candidate_ids = rebuild_and_candidates(client, auth, seeded)
        calls = 0

        def spy(payload: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            selected = [item["candidateId"] for item in payload["sources"]]
            return {"response": "승인 상태 응답", "claims": [{
                "claimKey": "approved", "text": "승인됨", "candidateIds": selected
            }]}

        client.app.state.ai_provider = spy
        request_json = {
            "purpose": "EVIDENCE_SUMMARY", "query": "공개 문서 근거 요약",
            "candidateIds": [candidate_ids[seeded["published_document_id"]]],
        }
        first = client.post("/api/v1/ai/queries", headers=auth, json=request_json)
        assert first.status_code == 200, first.text
        with client.app.state.database.session() as session:
            approval = session.scalar(select(AITransferApproval).where(
                AITransferApproval.customer_scope == client.app.state.settings.ai_customer_scope,
                AITransferApproval.site_scope == client.app.state.settings.ai_site_scope,
            ).order_by(AITransferApproval.approved_at.desc()))
            assert approval is not None
            approval.revoked_at = datetime.now(timezone.utc)
            session.commit()
        second = client.post("/api/v1/ai/queries", headers=auth, json=request_json)
        assert second.status_code == 403
        assert second.json()["error"]["code"] == "APPROVAL_REVOKED"
        assert calls == 1
        quality = client.get("/api/v1/ai-search/quality", headers=auth)
        assert quality.status_code == 200
        assert quality.json()["candidate_count"] >= 4


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
        assert denied.json()["error"]["code"] == "AI_ROLE_NOT_ALLOWED"
        assert calls == 0
        with client.app.state.database.session() as session:
            denied_query = session.scalar(select(AIQuery).where(
                AIQuery.query_id == denied.json()["queryId"]
            ))
            assert denied_query.block_code == "AI_ROLE_NOT_ALLOWED"


def test_approved_prompt_content_is_immutable() -> None:
    with create_client() as client:
        seed_policy(client)
        with client.app.state.database.session() as session:
            prompt = session.scalar(select(AIPromptVersion).order_by(AIPromptVersion.id.desc()))
            prompt.template_text = "승인 후 덮어쓰면 안 되는 변경"
            with pytest.raises(ValueError, match="immutable"):
                session.commit()
