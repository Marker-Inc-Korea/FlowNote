from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    AIProviderOnboardingReview,
    AISearchCandidate,
    AISearchEvaluationRun,
    AISearchGroundTruthCase,
)


SOURCE_MINIMUMS = {
    "PUBLISHED_DOCUMENT_VERSION": 10,
    "FIELD_COMMENT": 100,
    "WORK_SEQUENCE_HISTORY": 20,
    "REPORT_SOURCE": 10,
}
GROUND_TRUTH_MINIMUM = 48
GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM = 2
TOP_K_INCLUSION_THRESHOLD = 1.0
CITATION_TRACE_THRESHOLD = 1.0
CITATION_SEMANTIC_MATCH_THRESHOLD = 1.0
CONFLICT_DISCLOSURE_THRESHOLD = 1.0
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
    provider: str | None = None,
    model_scope: str | None = None,
    purpose: str | None = None,
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
    category_scenario_gaps = [
        {
            "category": category,
            "scenario_type": scenario,
            "count": coverage[(category, scenario)],
            "required": GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM,
            "missing": max(GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM - coverage[(category, scenario)], 0),
        }
        for category in QUESTION_CATEGORIES
        for scenario in SCENARIO_TYPES
        if coverage[(category, scenario)] < GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM
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
                "top_k_inclusion_rate": metrics.get("top_k_inclusion_rate", metrics.get("recall_at_k", 0)),
                "excluded_source_violation": metrics.get("excluded_source_violation", 0),
                "permission_leak_violation": metrics.get("permission_leak_violation", 0),
                "nonexistent_citation_violation": metrics.get("nonexistent_citation_violation", 0),
                "citation_trace_success_rate": metrics.get("citation_trace_success_rate", 0),
                "citation_semantic_match_rate": metrics.get("citation_semantic_match_rate", 0),
                "conflict_disclosure_rate": metrics.get("conflict_disclosure_rate", 0),
            }
            break

    provider_review = None
    if provider and model_scope:
        review = session.scalar(
            select(AIProviderOnboardingReview).where(
                AIProviderOnboardingReview.customer_scope == customer_scope,
                AIProviderOnboardingReview.site_scope == site_scope,
                AIProviderOnboardingReview.provider == provider,
                AIProviderOnboardingReview.model_scope == model_scope,
            ).order_by(desc(AIProviderOnboardingReview.created_at), desc(AIProviderOnboardingReview.id))
        )
        if review is not None:
            try:
                checklist = json.loads(review.checklist_json)
            except (TypeError, ValueError):
                checklist = {}
            checklist_passed = bool(checklist) and all(
                isinstance(item, dict) and item.get("status") == "PASS"
                for item in checklist.values()
            )
            statuses = {
                "technical": review.technical_status,
                "security": review.security_status,
                "legal": review.legal_status,
                "customer": review.customer_status,
            }
            try:
                allowed_purposes = set(json.loads(review.allowed_purposes_json))
            except (TypeError, ValueError):
                allowed_purposes = set()
            purpose_allowed = purpose is None or purpose in allowed_purposes
            provider_review = {
                "review_id": review.review_id,
                "review_version": review.review_version,
                "statuses": statuses,
                "checklist_passed": checklist_passed,
                "purpose_allowed": purpose_allowed,
                "approved": (
                    checklist_passed
                    and purpose_allowed
                    and all(value == "APPROVED" for value in statuses.values())
                ),
            }
    provider_review_ready = bool(provider_review and provider_review["approved"])

    ground_truth_gap = max(GROUND_TRUTH_MINIMUM - len(ground_truth), 0)
    source_ready = not any(source_gaps.values())
    ground_truth_ready = ground_truth_gap == 0 and not category_scenario_gaps
    evaluation_ready = bool(
        latest_evaluation
        and latest_evaluation["status"] == "PASSED"
        and latest_evaluation["candidate_identity_stable"]
        and latest_evaluation["ranking_stable"]
        and latest_evaluation["case_count"] >= GROUND_TRUTH_MINIMUM
        and latest_evaluation["top_k_inclusion_rate"] >= TOP_K_INCLUSION_THRESHOLD
        and latest_evaluation["excluded_source_violation"] == 0
        and latest_evaluation["permission_leak_violation"] == 0
        and latest_evaluation["nonexistent_citation_violation"] == 0
        and latest_evaluation["citation_trace_success_rate"] >= CITATION_TRACE_THRESHOLD
        and latest_evaluation["citation_semantic_match_rate"] >= CITATION_SEMANTIC_MATCH_THRESHOLD
        and latest_evaluation["conflict_disclosure_rate"] >= CONFLICT_DISCLOSURE_THRESHOLD
    )
    ready = source_ready and ground_truth_ready and evaluation_ready and provider_review_ready
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
        "ground_truth_per_category_scenario_minimum": GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM,
        "ground_truth_gap": ground_truth_gap,
        "category_scenario_counts": [
            {
                "category": category,
                "scenario_type": scenario,
                "count": coverage[(category, scenario)],
            }
            for category in QUESTION_CATEGORIES
            for scenario in SCENARIO_TYPES
        ],
        "category_scenario_gaps": category_scenario_gaps,
        "missing_category_scenarios": [
            {"category": item["category"], "scenario_type": item["scenario_type"]}
            for item in category_scenario_gaps
        ],
        "quality_thresholds": {
            "top_k_inclusion_rate": TOP_K_INCLUSION_THRESHOLD,
            "excluded_source_violation": 0,
            "permission_leak_violation": 0,
            "nonexistent_citation_violation": 0,
            "citation_trace_success_rate": CITATION_TRACE_THRESHOLD,
            "citation_semantic_match_rate": CITATION_SEMANTIC_MATCH_THRESHOLD,
            "conflict_disclosure_rate": CONFLICT_DISCLOSURE_THRESHOLD,
        },
        "latest_evaluation": latest_evaluation,
        "provider_review": provider_review or {
            "review_id": None,
            "review_version": None,
            "statuses": {key: "PENDING" for key in ("technical", "security", "legal", "customer")},
            "checklist_passed": False,
            "purpose_allowed": False,
            "approved": False,
        },
        "source_ready": source_ready,
        "ground_truth_ready": ground_truth_ready,
        "evaluation_ready": evaluation_ready,
        "provider_review_ready": provider_review_ready,
        "provider_start_ready": ready,
    }
