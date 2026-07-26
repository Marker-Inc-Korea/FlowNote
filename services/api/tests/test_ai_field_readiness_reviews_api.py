from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.init_db import hash_password_for_dev
from app.db.models import (
    AIEvaluationDatasetBinding,
    AIGroundTruthDatasetCase,
    AIGroundTruthDatasetVersion,
    AISearchEvaluationCase,
    AISearchEvaluationRun,
    AISearchGroundTruthCase,
    UserAccount,
)
from app.main import create_app
from app.services.ai_readiness import QUESTION_CATEGORIES, SCENARIO_TYPES, database_scope


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"


def _client() -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        test_database_url=f"sqlite:///{TEST_DB_PATH.as_posix()}",
        storage_root=str(API_ROOT / "storage" / "ai-field-review-tests"),
    )
    return TestClient(create_app(settings))


def _add_user(client: TestClient, role: str) -> tuple[str, dict[str, str]]:
    suffix = uuid4().hex
    user_id = f"user-aifr-{suffix}"
    username = f"aifr-{suffix}"
    with client.app.state.database.session() as session:
        session.add(
            UserAccount(
                user_id=user_id,
                username=username,
                login_id=username,
                display_name=f"AI 현장 표본 {role}",
                role=role,
                password_hash=hash_password_for_dev("1234"),
                is_active=True,
                status="ACTIVE",
            )
        )
        session.commit()
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "1234"})
    assert response.status_code == 200, response.text
    return user_id, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_approved_dataset_and_stable_runs(
    client: TestClient,
    actor_ids: list[str],
) -> tuple[str, str, list[tuple[str, str]]]:
    suffix = uuid4().hex
    dataset_id = f"aigtds-{suffix}"
    snapshot_hash = hashlib.sha256(dataset_id.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    scope = database_scope(client.app.state.settings.database_url)
    sample_keys: list[tuple[str, str]] = []
    all_case_keys: list[str] = []
    with client.app.state.database.session() as session:
        dataset = AIGroundTruthDatasetVersion(
            dataset_version_id=dataset_id,
            dataset_key=f"field-review-{suffix}",
            version=1,
            title="실제 익명 현장 표본 검토 계약 시험",
            customer_scope=client.app.state.settings.ai_customer_scope,
            site_scope=client.app.state.settings.ai_site_scope,
            line_scope=None,
            database_scope=scope,
            readiness_track="FIELD_READINESS",
            status="APPROVED",
            author_id=actor_ids[0],
            reviewer_id=actor_ids[1],
            first_approved_by=actor_ids[2],
            second_approved_by=actor_ids[3],
            snapshot_hash=snapshot_hash,
            change_reason="독립 표본 검토 API 시험",
            submitted_at=now,
            reviewed_at=now,
            first_approved_at=now,
            second_approved_at=now,
        )
        session.add(dataset)
        session.flush()
        for category in QUESTION_CATEGORIES:
            for scenario in SCENARIO_TYPES:
                for variant in range(2):
                    case_key = f"aifr-{suffix}-{category}-{scenario}-{variant}"
                    case_id = f"aigt-{uuid4().hex}"
                    case = AISearchGroundTruthCase(
                            ground_truth_case_id=case_id,
                            case_key=case_key,
                            customer_scope=client.app.state.settings.ai_customer_scope,
                            site_scope=client.app.state.settings.ai_site_scope,
                            line_scope=None,
                            database_scope=scope,
                            category=category,
                            scenario_type=scenario,
                            question=f"{category} {scenario} 승인 질문 {variant}",
                            expected_outcome="SUFFICIENT",
                            expected_evidence_json="[]",
                            excluded_evidence_json="[]",
                            allowed_rank_min=1,
                            allowed_rank_max=20,
                            as_of=now,
                            approved_by=actor_ids[0],
                            approved_at=now,
                            is_active=True,
                        )
                    session.add(case)
                    session.flush()
                    session.add(
                        AIGroundTruthDatasetCase(
                            dataset_version_id=dataset_id,
                            ground_truth_case_id=case_id,
                            case_key=case_key,
                            snapshot_hash=hashlib.sha256(case_key.encode()).hexdigest(),
                            added_by=actor_ids[0],
                        )
                    )
                    all_case_keys.append(case_key)
                    if variant == 0:
                        sample_keys.append((case_key, scenario))
        run_ids = [f"aiseval-{uuid4().hex}", f"aiseval-{uuid4().hex}"]
        metrics = json.dumps({
            "case_count": 48,
            "passed_count": 48,
            "source_coverage_complete": True,
            "top_k_inclusion_rate": 1.0,
            "citation_trace_success_rate": 1.0,
            "citation_semantic_match_rate": 1.0,
            "conflict_disclosure_rate": 1.0,
            "excluded_source_violation": 0,
            "permission_leak_violation": 0,
            "nonexistent_citation_violation": 0,
            "readiness_track": "FIELD_READINESS",
            "dataset_version_id": dataset_id,
            "dataset_snapshot_hash": snapshot_hash,
        })
        for run_id in run_ids:
            session.add(
                AISearchEvaluationRun(
                    run_id=run_id,
                    run_label="동일 snapshot 독립 표본 검토 시험",
                    requested_by=actor_ids[0],
                    evaluated_as_user_id=actor_ids[0],
                    status="PASSED",
                    candidate_identity_stable=True,
                    ranking_stable=True,
                    metrics_json=metrics,
                )
            )
            session.flush()
            session.add(
                AIEvaluationDatasetBinding(
                    run_id=run_id,
                    dataset_version_id=dataset_id,
                    dataset_snapshot_hash=snapshot_hash,
                )
            )
            for case_key in all_case_keys:
                session.add(
                    AISearchEvaluationCase(
                        evaluation_case_id=f"aisevalcase-{uuid4().hex}",
                        run_id=run_id,
                        case_key=case_key,
                        question=f"{case_key} 질문",
                        expected_outcome="SUFFICIENT",
                        actual_outcome="SUFFICIENT",
                        expected_evidence_json="[]",
                        actual_evidence_json="[]",
                        excluded_evidence_json="[]",
                        ranking_hash=hashlib.sha256(case_key.encode()).hexdigest(),
                        passed=True,
                    )
                )
        session.commit()
    return dataset_id, run_ids[1], sample_keys


def _findings(sample_keys: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "caseKey": case_key,
            "citationTrace": "PASS",
            "citationMeaning": "PASS",
            "conflictDisclosure": "PASS" if scenario == "CONFLICT" else "NOT_APPLICABLE",
            "permissionBoundary": "PASS",
            "note": "고정 원천과 평가 후보를 독립 확인함",
        }
        for case_key, scenario in sample_keys
    ]


def test_two_independent_sample_reviews_require_third_person_consensus() -> None:
    with _client() as client:
        dataset_actors = [_add_user(client, role)[0] for role in (
            "manager", "manager", "document-admin", "system-admin"
        )]
        first_id, first_headers = _add_user(client, "manager")
        second_id, second_headers = _add_user(client, "assistant-manager")
        third_id, third_headers = _add_user(client, "department-manager")
        dataset_id, run_id, sample_keys = _seed_approved_dataset_and_stable_runs(
            client, dataset_actors
        )
        base_payload = {
            "datasetVersionId": dataset_id,
            "evaluationRunId": run_id,
            "samplingPlanReference": "field-review-plan://24-cell-stratified-v1",
            "reviewRole": "INDEPENDENT",
            "findings": _findings(sample_keys),
        }
        first = client.post(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=first_headers,
            json=base_payload,
        )
        assert first.status_code == 201, first.text
        assert first.json()["summary"]["status"] == "PENDING_SECOND_REVIEW"
        assert first.json()["summary"]["independent_reviewer_ids"] == [first_id]
        concealed = client.get(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=second_headers,
            params={"datasetVersionId": dataset_id, "evaluationRunId": run_id},
        )
        assert concealed.status_code == 200
        assert concealed.json()["reviews"][0]["findings"] is None
        assert concealed.json()["reviews"][0]["decisionHash"] is None

        second_payload = {**base_payload, "findings": _findings(sample_keys)}
        second_payload["findings"][0]["citationMeaning"] = "FAIL"
        second_payload["findings"][0]["note"] = "인용 의미가 기대 근거와 다르다고 판단함"
        second = client.post(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=second_headers,
            json=second_payload,
        )
        assert second.status_code == 201, second.text
        second_body = second.json()
        assert second_body["summary"]["status"] == "PENDING_CONSENSUS"
        assert second_body["summary"]["independent_reviewer_ids"] == [first_id, second_id]
        assert second_body["summary"]["disagreement_case_keys"] == [sample_keys[0][0]]

        consensus_payload = {
            "datasetVersionId": dataset_id,
            "evaluationRunId": run_id,
            "samplingPlanReference": "field-review-plan://24-cell-stratified-v1",
            "reviewRole": "CONSENSUS",
            "resolvesReviewIds": second_body["summary"]["independent_review_ids"],
            "findings": [{
                "caseKey": sample_keys[0][0],
                "citationTrace": "PASS",
                "citationMeaning": "PASS",
                "conflictDisclosure": "NOT_APPLICABLE",
                "permissionBoundary": "PASS",
                "note": "제3 검토에서 고정 근거 의미가 일치함을 합의함",
            }],
        }
        self_consensus = client.post(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=first_headers,
            json=consensus_payload,
        )
        assert self_consensus.status_code == 409
        consensus = client.post(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=third_headers,
            json=consensus_payload,
        )
        assert consensus.status_code == 201, consensus.text
        assert consensus.json()["summary"]["status"] == "COMPLETED"
        assert consensus.json()["summary"]["complete"] is True
        assert consensus.json()["summary"]["consensus_reviewer_id"] == third_id
        assert sorted(consensus.json()["review"]["resolvesReviewIds"]) == sorted(
            second_body["summary"]["independent_review_ids"]
        )

        listed = client.get(
            "/api/v1/ai-search/field-readiness/sample-reviews",
            headers=third_headers,
            params={"datasetVersionId": dataset_id, "evaluationRunId": run_id},
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["reviews"]) == 3
        assert listed.json()["summary"]["complete"] is True

        verification_sql = (
            API_ROOT.parents[1] / "scripts" / "sql" / "verify-ai-field-readiness.sql"
        ).read_text(encoding="utf-8")
        with sqlite3.connect(TEST_DB_PATH) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                "CREATE TEMP TABLE _field_readiness_verify_scope ("
                "dataset_version_id TEXT, customer_scope TEXT, site_scope TEXT, "
                "line_scope TEXT, database_scope TEXT)"
            )
            connection.execute(
                "INSERT INTO _field_readiness_verify_scope VALUES (?, ?, ?, ?, ?)",
                (
                    dataset_id,
                    client.app.state.settings.ai_customer_scope,
                    client.app.state.settings.ai_site_scope,
                    None,
                    database_scope(client.app.state.settings.database_url),
                ),
            )
            verification = dict(connection.execute(verification_sql).fetchone())
        assert verification["sample_review_complete_count"] == 1
        assert verification["sample_review_pending_disagreement_count"] == 0
        assert verification["sample_review_scope_violation_count"] == 0
        assert verification["sample_review_actor_violation_count"] == 0
