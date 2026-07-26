from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AIEvaluationDatasetBinding,
    AIFieldReadinessSampleReview,
    AISearchEvaluationCase,
    AISearchEvaluationRun,
)


REVIEW_DECISION_FIELDS = (
    "citationTrace",
    "citationMeaning",
    "conflictDisclosure",
    "permissionBoundary",
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_findings(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        [
            {
                "caseKey": str(item["caseKey"]),
                **{field: str(item[field]) for field in REVIEW_DECISION_FIELDS},
                "note": str(item["note"]),
            }
            for item in findings
        ],
        key=lambda item: item["caseKey"],
    )


def decision_snapshot(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "caseKey": item["caseKey"],
            **{field: item[field] for field in REVIEW_DECISION_FIELDS},
        }
        for item in canonical_findings(findings)
    ]


def parse_findings(row: AIFieldReadinessSampleReview) -> list[dict[str, str]]:
    try:
        value = json.loads(row.findings_json)
    except (TypeError, ValueError):
        return []
    return canonical_findings(value) if isinstance(value, list) else []


def parse_resolved_review_ids(row: AIFieldReadinessSampleReview) -> list[str]:
    try:
        value = json.loads(row.resolved_review_ids_json or "[]")
    except (TypeError, ValueError):
        return []
    return sorted(str(item) for item in value) if isinstance(value, list) else []


def review_pair_hash(first_review_id: str, second_review_id: str) -> str:
    return content_hash(sorted((first_review_id, second_review_id)))


def disagreement_case_keys(
    first: AIFieldReadinessSampleReview,
    second: AIFieldReadinessSampleReview,
) -> list[str]:
    first_decisions = {
        item["caseKey"]: {field: item[field] for field in REVIEW_DECISION_FIELDS}
        for item in parse_findings(first)
    }
    second_decisions = {
        item["caseKey"]: {field: item[field] for field in REVIEW_DECISION_FIELDS}
        for item in parse_findings(second)
    }
    return sorted(
        case_key
        for case_key in set(first_decisions) | set(second_decisions)
        if first_decisions.get(case_key) != second_decisions.get(case_key)
    )


def _evaluation_case_snapshot(
    session: Session,
    run_id: str,
) -> dict[str, tuple[str, str, bool]]:
    rows = session.scalars(
        select(AISearchEvaluationCase)
        .where(AISearchEvaluationCase.run_id == run_id)
        .order_by(AISearchEvaluationCase.case_key)
    ).all()
    return {
        row.case_key: (row.actual_evidence_json, row.ranking_hash, row.passed)
        for row in rows
    }


def _evaluation_quality_passes(
    run: AISearchEvaluationRun,
    *,
    dataset_version_id: str,
    dataset_snapshot_hash: str,
) -> bool:
    try:
        metrics = json.loads(run.metrics_json)
    except (TypeError, ValueError):
        return False
    return bool(
        metrics.get("case_count") == 48
        and metrics.get("passed_count") == 48
        and metrics.get("source_coverage_complete") is True
        and metrics.get("top_k_inclusion_rate") == 1.0
        and metrics.get("citation_trace_success_rate") == 1.0
        and metrics.get("citation_semantic_match_rate") == 1.0
        and metrics.get("conflict_disclosure_rate") == 1.0
        and metrics.get("excluded_source_violation") == 0
        and metrics.get("permission_leak_violation") == 0
        and metrics.get("nonexistent_citation_violation") == 0
        and metrics.get("readiness_track") == "FIELD_READINESS"
        and metrics.get("dataset_version_id") == dataset_version_id
        and metrics.get("dataset_snapshot_hash") == dataset_snapshot_hash
    )


def evaluation_snapshot_pair_is_stable(
    session: Session,
    *,
    dataset_version_id: str,
    dataset_snapshot_hash: str,
    run_id: str,
) -> bool:
    binding = session.scalar(
        select(AIEvaluationDatasetBinding).where(
            AIEvaluationDatasetBinding.run_id == run_id,
            AIEvaluationDatasetBinding.dataset_version_id == dataset_version_id,
            AIEvaluationDatasetBinding.dataset_snapshot_hash == dataset_snapshot_hash,
        )
    )
    run = session.scalar(
        select(AISearchEvaluationRun).where(
            AISearchEvaluationRun.run_id == run_id,
            AISearchEvaluationRun.status == "PASSED",
            AISearchEvaluationRun.candidate_identity_stable.is_(True),
            AISearchEvaluationRun.ranking_stable.is_(True),
        )
    )
    if binding is None or run is None or not _evaluation_quality_passes(
        run,
        dataset_version_id=dataset_version_id,
        dataset_snapshot_hash=dataset_snapshot_hash,
    ):
        return False
    current = _evaluation_case_snapshot(session, run_id)
    if len(current) != 48 or not all(item[2] for item in current.values()):
        return False
    comparison_ids = session.scalars(
        select(AIEvaluationDatasetBinding.run_id).where(
            AIEvaluationDatasetBinding.dataset_version_id == dataset_version_id,
            AIEvaluationDatasetBinding.dataset_snapshot_hash == dataset_snapshot_hash,
            AIEvaluationDatasetBinding.run_id != run_id,
        )
    ).all()
    return any(
        (other_run := session.scalar(
            select(AISearchEvaluationRun).where(
                AISearchEvaluationRun.run_id == comparison_id,
                AISearchEvaluationRun.status == "PASSED",
                AISearchEvaluationRun.candidate_identity_stable.is_(True),
                AISearchEvaluationRun.ranking_stable.is_(True),
            )
        )) is not None
        and _evaluation_quality_passes(
            other_run,
            dataset_version_id=dataset_version_id,
            dataset_snapshot_hash=dataset_snapshot_hash,
        )
        and _evaluation_case_snapshot(session, comparison_id) == current
        for comparison_id in comparison_ids
    )


def _group_summary(
    rows: list[AIFieldReadinessSampleReview],
) -> dict[str, object]:
    independent = sorted(
        (row for row in rows if row.review_role == "INDEPENDENT"),
        key=lambda row: (row.created_at, row.id),
    )
    consensus = [row for row in rows if row.review_role == "CONSENSUS"]
    base: dict[str, object] = {
        "evaluation_run_id": rows[0].evaluation_run_id,
        "dataset_snapshot_hash": rows[0].dataset_snapshot_hash,
        "independent_reviewer_count": len(independent),
        "independent_review_ids": [row.review_id for row in independent],
        "independent_reviewer_ids": [row.reviewer_id for row in independent],
        "sample_hash": independent[0].sample_hash if independent else None,
        "sample_case_count": 0 if not independent else len(json.loads(independent[0].sample_case_keys_json)),
        "disagreement_case_keys": [],
        "consensus_review_id": None,
        "consensus_reviewer_id": None,
        "complete": False,
    }
    if not independent:
        return {**base, "status": "NOT_STARTED"}
    if len(independent) == 1:
        return {**base, "status": "PENDING_SECOND_REVIEW"}
    first, second = independent[:2]
    if first.sample_hash != second.sample_hash:
        return {**base, "status": "INVALID_SAMPLE_MISMATCH"}
    disagreements = disagreement_case_keys(first, second)
    base["disagreement_case_keys"] = disagreements
    if not disagreements:
        return {**base, "status": "COMPLETED", "complete": True}
    pair_hash = review_pair_hash(first.review_id, second.review_id)
    expected_review_ids = sorted((first.review_id, second.review_id))
    resolution = next(
        (
            row
            for row in consensus
            if row.review_pair_hash == pair_hash
            and parse_resolved_review_ids(row) == expected_review_ids
        ),
        None,
    )
    if resolution is None:
        return {**base, "status": "PENDING_CONSENSUS"}
    resolved_case_keys = sorted(item["caseKey"] for item in parse_findings(resolution))
    if resolved_case_keys != disagreements:
        return {**base, "status": "INVALID_CONSENSUS_SCOPE"}
    return {
        **base,
        "status": "COMPLETED",
        "complete": True,
        "consensus_review_id": resolution.review_id,
        "consensus_reviewer_id": resolution.reviewer_id,
    }


def sample_review_summary(
    session: Session,
    *,
    dataset_version_id: str,
    dataset_snapshot_hash: str,
    evaluation_run_id: str | None = None,
) -> dict[str, object]:
    statement = select(AIFieldReadinessSampleReview).where(
        AIFieldReadinessSampleReview.dataset_version_id == dataset_version_id,
        AIFieldReadinessSampleReview.dataset_snapshot_hash == dataset_snapshot_hash,
    )
    if evaluation_run_id is not None:
        statement = statement.where(
            AIFieldReadinessSampleReview.evaluation_run_id == evaluation_run_id
        )
    rows = list(session.scalars(statement.order_by(AIFieldReadinessSampleReview.id)).all())
    if not rows:
        return {
            "status": "NOT_STARTED",
            "evaluation_run_id": evaluation_run_id,
            "dataset_snapshot_hash": dataset_snapshot_hash,
            "independent_reviewer_count": 0,
            "independent_review_ids": [],
            "independent_reviewer_ids": [],
            "sample_hash": None,
            "sample_case_count": 0,
            "disagreement_case_keys": [],
            "consensus_review_id": None,
            "consensus_reviewer_id": None,
            "complete": False,
        }
    grouped: dict[str, list[AIFieldReadinessSampleReview]] = defaultdict(list)
    for row in rows:
        grouped[row.evaluation_run_id].append(row)
    summaries = [_group_summary(group) for group in grouped.values()]
    complete = [summary for summary in summaries if summary["complete"]]
    selected = complete[-1] if complete else summaries[-1]
    if selected["complete"] and not evaluation_snapshot_pair_is_stable(
        session,
        dataset_version_id=dataset_version_id,
        dataset_snapshot_hash=dataset_snapshot_hash,
        run_id=str(selected["evaluation_run_id"]),
    ):
        return {**selected, "status": "INVALID_EVALUATION_PAIR", "complete": False}
    return selected
