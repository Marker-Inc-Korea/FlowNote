from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import AISearchCandidate, AISearchEvaluationRun, AISearchGroundTruthCase


SOURCE_MINIMUMS = {
    "PUBLISHED_DOCUMENT_VERSION": 10,
    "FIELD_COMMENT": 100,
    "WORK_SEQUENCE_HISTORY": 20,
    "REPORT_SOURCE": 10,
}
GROUND_TRUTH_MINIMUM = 50
QUESTION_CATEGORIES = (
    "SAFETY",
    "QUALITY",
    "EQUIPMENT_ANOMALY",
    "WORK_HOLD",
    "REWORK",
    "HANDOVER",
    "LATEST_PUBLISHED_DOCUMENT",
    "CONFLICTING_RECORDS",
)
SCENARIO_TYPES = ("NORMAL", "EXCLUSION", "CONFLICT")


def database_scope(database_url: str) -> str:
    """Return a stable scope without exposing a local path or credentials."""
    driver = database_url.split(":", 1)[0].lower() or "database"
    digest = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:12]
    return f"{driver}:{digest}"


def _metadata(candidate: AISearchCandidate) -> dict[str, Any]:
    try:
        parsed = json.loads(candidate.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _line_matches(candidate: AISearchCandidate, line_scope: str | None) -> bool:
    if line_scope is None:
        return True
    value = _metadata(candidate).get("line_scope")
    if isinstance(value, list):
        return line_scope in {str(item) for item in value}
    return value == line_scope


def scope_readiness(
    session: Session,
    *,
    customer_scope: str,
    site_scope: str,
    database_scope_value: str,
    line_scope: str | None = None,
) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in session.scalars(select(AISearchCandidate)).all()
        if _line_matches(candidate, line_scope)
        and (
            candidate.source_type != "FIELD_COMMENT"
            or candidate.review_status in {"ANALYZED", "REVIEWED", "SELECTED"}
        )
    ]
    candidate_counts = Counter(candidate.source_type for candidate in candidates)
    source_gaps = {
        source_type: max(required - candidate_counts[source_type], 0)
        for source_type, required in SOURCE_MINIMUMS.items()
    }

    ground_truth_statement = select(AISearchGroundTruthCase).where(
        AISearchGroundTruthCase.customer_scope == customer_scope,
        AISearchGroundTruthCase.site_scope == site_scope,
        AISearchGroundTruthCase.database_scope == database_scope_value,
        AISearchGroundTruthCase.is_active.is_(True),
        AISearchGroundTruthCase.approved_at.is_not(None),
    )
    if line_scope is None:
        ground_truth_statement = ground_truth_statement.where(AISearchGroundTruthCase.line_scope.is_(None))
    else:
        ground_truth_statement = ground_truth_statement.where(AISearchGroundTruthCase.line_scope == line_scope)
    ground_truth = session.scalars(ground_truth_statement).all()
    coverage = Counter((case.category, case.scenario_type) for case in ground_truth)
    missing_category_scenarios = [
        {"category": category, "scenario_type": scenario}
        for category in QUESTION_CATEGORIES
        for scenario in SCENARIO_TYPES
        if coverage[(category, scenario)] == 0
    ]

    latest_evaluation = None
    for run in session.scalars(
        select(AISearchEvaluationRun).order_by(desc(AISearchEvaluationRun.created_at), desc(AISearchEvaluationRun.id))
    ).all():
        try:
            metrics = json.loads(run.metrics_json)
        except (TypeError, ValueError):
            continue
        if (
            metrics.get("customer_scope") == customer_scope
            and metrics.get("site_scope") == site_scope
            and metrics.get("database_scope") == database_scope_value
            and metrics.get("line_scope") == line_scope
        ):
            latest_evaluation = {
                "run_id": run.run_id,
                "status": run.status,
                "candidate_identity_stable": run.candidate_identity_stable,
                "ranking_stable": run.ranking_stable,
                "case_count": metrics.get("case_count", 0),
                "passed_count": metrics.get("passed_count", 0),
            }
            break

    ground_truth_gap = max(GROUND_TRUTH_MINIMUM - len(ground_truth), 0)
    source_ready = not any(source_gaps.values())
    ground_truth_ready = ground_truth_gap == 0 and not missing_category_scenarios
    evaluation_ready = bool(
        latest_evaluation
        and latest_evaluation["status"] == "PASSED"
        and latest_evaluation["candidate_identity_stable"]
        and latest_evaluation["ranking_stable"]
        and latest_evaluation["case_count"] >= GROUND_TRUTH_MINIMUM
    )
    ready = source_ready and ground_truth_ready and evaluation_ready
    return {
        "scope": {
            "customer_scope": customer_scope,
            "site_scope": site_scope,
            "line_scope": line_scope,
            "database_scope": database_scope_value,
        },
        "source_counts": {source_type: candidate_counts[source_type] for source_type in SOURCE_MINIMUMS},
        "source_minimums": SOURCE_MINIMUMS,
        "source_gaps": source_gaps,
        "ground_truth_count": len(ground_truth),
        "ground_truth_minimum": GROUND_TRUTH_MINIMUM,
        "ground_truth_gap": ground_truth_gap,
        "missing_category_scenarios": missing_category_scenarios,
        "latest_evaluation": latest_evaluation,
        "source_ready": source_ready,
        "ground_truth_ready": ground_truth_ready,
        "evaluation_ready": evaluation_ready,
        "provider_start_ready": ready,
    }
