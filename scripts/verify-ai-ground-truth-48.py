#!/usr/bin/env python3
"""Run SQL integrity checks and two reproducibility evaluations for smoke48-v1."""

from __future__ import annotations

import argparse
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

    first, second = runs
    stable = (
        first["status"] == second["status"] == "PASSED"
        and first["candidate_identity_stable"] and second["candidate_identity_stable"]
        and first["ranking_stable"] and second["ranking_stable"]
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
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
