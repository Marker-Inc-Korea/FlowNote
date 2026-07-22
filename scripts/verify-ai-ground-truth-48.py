#!/usr/bin/env python3
"""Run SQL integrity checks and two reproducibility evaluations for smoke48-v1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=API_ROOT / "data" / "flownote.test.sqlite3",
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        default=ROOT / "data" / "local" / "ai-smoke-regression",
        help="Git-excluded directory that keeps one immutable evidence JSON per verification run.",
    )
    args = parser.parse_args()
    if "test" not in str(args.database).lower():
        parser.error("database path must visibly identify a test database")

    sql = (ROOT / "scripts" / "sql" / "verify-ai-ground-truth-48.sql").read_text(encoding="utf-8")
    with sqlite3.connect(args.database) as connection:
        connection.row_factory = sqlite3.Row
        integrity = dict(connection.execute(sql).fetchone())
        case_ids = [
            row[0] for row in connection.execute(
                "SELECT ground_truth_case_id FROM ai_search_ground_truth_cases "
                "WHERE case_key LIKE 'smoke48-v1-%' ORDER BY case_key"
            )
        ]
    violations = {key: value for key, value in integrity.items() if key != "case_count" and value != 0}
    if integrity["case_count"] != 48 or violations:
        print(json.dumps({"integrity": integrity, "status": "FAILED"}, ensure_ascii=False, sort_keys=True))
        return 1

    database_url = f"sqlite:///{args.database.resolve().as_posix()}"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        test_database_url=database_url,
        storage_root=str(API_ROOT / "storage" / "ai-ground-truth-48"),
        ai_external_call_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        login = client.post("/api/v1/auth/login", json={"username": "ai-gt-first", "password": "1234"})
        if login.status_code != 200:
            print(login.text)
            return 1
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        runs = []
        for suffix in ("first", "second"):
            response = client.post("/api/v1/ai-search/evaluations", headers=headers, json={
                "runLabel": f"smoke48-v1-reproducibility-{suffix}",
                "evaluateAsUserId": "user-ai-gt-first",
                "groundTruthCaseIds": case_ids,
                "evaluatorVersion": "candidate-ranking-v1",
                "policyVersion": "smoke48-v1",
            })
            if response.status_code != 200:
                print(response.text)
                return 1
            runs.append(response.json())
        readiness_response = client.get("/api/v1/ai-search/readiness", headers=headers)
        if readiness_response.status_code != 200:
            print(readiness_response.text)
            return 1
        readiness = readiness_response.json()
        blocked_provider = client.post("/api/v1/ai/queries", headers=headers, json={
            "purpose": "EVIDENCE_SUMMARY",
            "query": "smoke48-v1 외부 provider 비활성 게이트 확인",
            "candidateIds": [],
            "responseStorageMode": "DO_NOT_STORE",
        })
        blocked_payload = blocked_provider.json()
        disabled_code = blocked_payload.get("error", {}).get("code")

    first, second = runs
    quality_passed = (
        second["top_k_inclusion_rate"] == 1
        and second["citation_trace_success_rate"] == 1
        and second["citation_semantic_match_rate"] == 1
        and second["conflict_disclosure_rate"] == 1
        and second["excluded_source_violation"] == 0
        and second["permission_leak_violation"] == 0
        and second["nonexistent_citation_violation"] == 0
    )
    stable = (
        first["status"] == second["status"] == "PASSED"
        and first["candidate_identity_stable"] and second["candidate_identity_stable"]
        and first["ranking_stable"] and second["ranking_stable"]
        and quality_passed
        and second["readiness_track"] == "SMOKE_REGRESSION"
        and second["provider_start_ready"] is False
        and readiness["provider_start_ready"] is False
        and readiness["ground_truth_count"] == readiness["field_readiness"]["ground_truth_count"]
        and readiness["smoke_regression_readiness"]["ground_truth_count"] >= 48
        and blocked_provider.status_code == 503
        and disabled_code == "AI_EXTERNAL_CALL_DISABLED"
        and all(case["previous_run_delta"] is None or (
            case["previous_run_delta"]["candidate_ids_added"] == []
            and case["previous_run_delta"]["candidate_ids_removed"] == []
            and case["previous_run_delta"]["content_hash_changed"] == []
            and case["previous_run_delta"]["ranking_changed"] is False
        ) for case in second["cases"])
    )
    result = {
        "status": "PASSED" if stable else "FAILED",
        "integrity": integrity,
        "firstRunId": first["run_id"],
        "secondRunId": second["run_id"],
        "readinessTrack": second["readiness_track"],
        "caseCount": second["case_count"],
        "topKInclusionRate": second["top_k_inclusion_rate"],
        "citationTraceSuccessRate": second["citation_trace_success_rate"],
        "citationSemanticMatchRate": second["citation_semantic_match_rate"],
        "conflictDisclosureRate": second["conflict_disclosure_rate"],
        "permissionLeakViolation": second["permission_leak_violation"],
        "nonexistentCitationViolation": second["nonexistent_citation_violation"],
        "excludedSourceViolation": second["excluded_source_violation"],
        "ai_scope_or_disabled": disabled_code,
        "providerStartReady": readiness["provider_start_ready"],
        "fieldReadinessGroundTruthCount": readiness["field_readiness"]["ground_truth_count"],
        "smokeRegressionGroundTruthCount": readiness["smoke_regression_readiness"]["ground_truth_count"],
    }
    with sqlite3.connect(args.database) as connection:
        connection.row_factory = sqlite3.Row
        status_distribution = {
            row["status"]: row["count"] for row in connection.execute(
                "SELECT status, count(*) AS count FROM field_comments "
                "WHERE comment_id LIKE 'comment-smoke48-v1-%' "
                "AND comment_id NOT LIKE 'comment-smoke48-v1-negative-%' GROUP BY status ORDER BY status"
            )
        }
        tag_axis_distribution = {
            row["tag_type"]: row["count"] for row in connection.execute(
                "SELECT td.tag_type, count(DISTINCT dt.document_id) AS count "
                "FROM document_tags dt JOIN tag_definitions td USING (tag_id) "
                "WHERE dt.document_id LIKE 'doc-smoke48-v1-%' "
                "AND dt.document_id NOT LIKE 'doc-smoke48-v1-negative-%' "
                "AND td.tag_type IN ('equipment','item','process','error_type') GROUP BY td.tag_type"
            )
        }
        source_type_distribution = {
            row["source_type"]: row["count"] for row in connection.execute(
                "SELECT rs.source_type, count(*) AS count FROM report_sources rs JOIN reports r USING (report_id) "
                "WHERE r.report_id LIKE 'report-smoke48-v1-%' GROUP BY rs.source_type ORDER BY rs.source_type"
            )
        }
        matrix_contracts = [dict(row) for row in connection.execute(
            "SELECT c.case_key, c.category, c.scenario_type, c.expected_outcome, "
            "c.expected_evidence_json AS expected_evidence, c.excluded_evidence_json AS expected_excluded "
            "FROM ai_search_ground_truth_cases c WHERE c.case_key LIKE 'smoke48-v1-%' ORDER BY c.case_key"
        )]
    actual_by_case = {item["case_key"]: item for item in second["cases"]}
    evidence = {
        **result,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "databaseFingerprint": readiness["scope"]["database_scope"],
        "statusDistribution": status_distribution,
        "sourceTypeDistribution": source_type_distribution,
        "tagAxisDistribution": tag_axis_distribution,
        "matrix": [
            {
                "caseKey": item["case_key"],
                "category": item["category"],
                "scenarioType": item["scenario_type"],
                "expectedOutcome": item["expected_outcome"],
                "expectedEvidence": json.loads(item["expected_evidence"]),
                "expectedExcluded": json.loads(item["expected_excluded"]),
                "actual": actual_by_case[item["case_key"]],
            }
            for item in matrix_contracts
        ],
    }
    args.evidence_directory.mkdir(parents=True, exist_ok=True)
    evidence_path = args.evidence_directory / f"smoke48-v1-evidence-{second['run_id']}.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    result["evidencePath"] = str(evidence_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
