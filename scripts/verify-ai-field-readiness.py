#!/usr/bin/env python3
"""Verify one approved FIELD_READINESS dataset and run it twice on one scope snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.ai_readiness import database_scope  # noqa: E402


ZERO_FIELDS = {
    "dataset_scope_violation_count", "dataset_actor_separation_violation_count",
    "matrix_gap_count", "duplicate_case_key_count", "case_approval_violation_count",
    "provenance_violation_count", "snapshot_hash_violation_count", "orphan_reference_count",
    "reference_hash_violation_count", "missing_rationale_count",
    "missing_exclusion_reason_count",
    "expected_source_balance_violation_count",
    "sample_review_scope_violation_count", "sample_review_actor_violation_count",
    "sample_review_pending_disagreement_count",
}


def _integrity(
    database: Path, *, dataset_version_id: str, customer: str, site: str, line: str | None
) -> dict[str, int]:
    sql = (ROOT / "scripts" / "sql" / "verify-ai-field-readiness.sql").read_text(encoding="utf-8")
    db_url = f"sqlite:///{database.resolve().as_posix()}"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TEMP TABLE _field_readiness_verify_scope ("
            "dataset_version_id TEXT, customer_scope TEXT, site_scope TEXT, "
            "line_scope TEXT, database_scope TEXT)"
        )
        connection.execute(
            "INSERT INTO _field_readiness_verify_scope VALUES (?, ?, ?, ?, ?)",
            (dataset_version_id, customer, site, line, database_scope(db_url)),
        )
        return dict(connection.execute(sql).fetchone())


def _delta_is_empty(case: dict[str, object]) -> bool:
    delta = case.get("previous_run_delta")
    return delta is None or (
        delta.get("candidate_ids_added") == []
        and delta.get("candidate_ids_removed") == []
        and delta.get("content_hash_changed") == []
        and delta.get("ranking_changed") is False
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--customer-scope", required=True)
    parser.add_argument("--site-scope", required=True)
    parser.add_argument("--line-scope")
    parser.add_argument("--username", required=True, help="Admin account used only through local TestClient")
    parser.add_argument(
        "--password-env", default="FLOWNOTE_FIELD_READINESS_VERIFY_PASSWORD",
        help="Environment variable containing the local verifier account password",
    )
    args = parser.parse_args()
    password = os.getenv(args.password_env)
    if not password:
        parser.error(f"{args.password_env} must contain the verifier account password")
    if not args.database.is_file():
        parser.error("database file does not exist")

    integrity = _integrity(
        args.database, dataset_version_id=args.dataset_version_id,
        customer=args.customer_scope, site=args.site_scope, line=args.line_scope,
    )
    violations = {key: integrity[key] for key in ZERO_FIELDS if integrity.get(key) != 0}
    if integrity.get("expected_source_type_count") != 4:
        violations["expected_source_type_count"] = integrity.get("expected_source_type_count", 0)
    if integrity.get("sample_review_complete_count", 0) < 1:
        violations["sample_review_complete_count"] = integrity.get("sample_review_complete_count", 0)
    if integrity.get("dataset_count") != 1 or integrity.get("case_count") != 48 or violations:
        print(json.dumps({"status": "FAILED", "integrity": integrity}, ensure_ascii=False, sort_keys=True))
        return 1

    database_url = f"sqlite:///{args.database.resolve().as_posix()}"
    settings = Settings(
        _env_file=None, environment="test", database_url=database_url,
        test_database_url=database_url, ai_customer_scope=args.customer_scope,
        ai_site_scope=args.site_scope, ai_provider_adapter_mode="FAKE",
        ai_external_call_enabled=False, ai_retention_scheduler_enabled=False,
        storage_root=str(API_ROOT / "storage" / "ai-field-readiness-verification"),
    )
    with TestClient(create_app(settings)) as client:
        login = client.post("/api/v1/auth/login", json={"username": args.username, "password": password})
        if login.status_code != 200:
            print(json.dumps({"status": "FAILED", "loginStatus": login.status_code}, sort_keys=True))
            return 1
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        runs = []
        for suffix in ("first", "second"):
            response = client.post("/api/v1/ai-search/evaluations", headers=headers, json={
                "runLabel": f"field-readiness-reproducibility-{suffix}",
                "datasetVersionId": args.dataset_version_id,
                "lineScope": args.line_scope,
                "evaluatorVersion": "candidate-ranking-v1",
                "policyVersion": "field-readiness-v1",
            })
            if response.status_code != 200:
                print(json.dumps({"status": "FAILED", "evaluationStatus": response.status_code,
                                  "detail": response.json()}, ensure_ascii=False, sort_keys=True))
                return 1
            runs.append(response.json())

    first, second = runs
    stable = (
        first["status"] == second["status"] == "PASSED"
        and first["readiness_track"] == second["readiness_track"] == "FIELD_READINESS"
        and first["dataset_snapshot_hash"] == second["dataset_snapshot_hash"]
        and first["candidate_identity_stable"] and second["candidate_identity_stable"]
        and first["ranking_stable"] and second["ranking_stable"]
        and first["source_coverage_complete"] and second["source_coverage_complete"]
        and second["top_k_inclusion_rate"] == 1.0
        and second["citation_trace_success_rate"] == 1.0
        and second["citation_semantic_match_rate"] == 1.0
        and second["conflict_disclosure_rate"] == 1.0
        and second["excluded_source_violation"] == 0
        and second["permission_leak_violation"] == 0
        and second["nonexistent_citation_violation"] == 0
        and all(_delta_is_empty(case) for case in second["cases"])
    )
    print(json.dumps({
        "status": "PASSED" if stable else "FAILED", "integrity": integrity,
        "datasetVersionId": args.dataset_version_id,
        "datasetSnapshotHash": second["dataset_snapshot_hash"],
        "firstRunId": first["run_id"], "secondRunId": second["run_id"],
        "previousRunDeltaStable": all(_delta_is_empty(case) for case in second["cases"]),
        "topKInclusionRate": second["top_k_inclusion_rate"],
        "citationTraceSuccessRate": second["citation_trace_success_rate"],
        "citationSemanticMatchRate": second["citation_semantic_match_rate"],
        "conflictDisclosureRate": second["conflict_disclosure_rate"],
        "excludedSourceViolation": second["excluded_source_violation"],
        "permissionLeakViolation": second["permission_leak_violation"],
        "nonexistentCitationViolation": second["nonexistent_citation_violation"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
