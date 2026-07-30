from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    AIEvaluationDatasetBinding,
    AIGroundTruthDatasetVersion,
    AIProviderOnboardingReview,
    AISearchCandidate,
    AISearchEvaluationRun,
    AISearchGroundTruthCase,
    AISearchGroundTruthProvenance,
)
from app.services.ai_field_readiness_reviews import sample_review_summary


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
SOURCE_LABELS = {
    "PUBLISHED_DOCUMENT_VERSION": "공개 문서",
    "FIELD_COMMENT": "현장 코멘트",
    "WORK_SEQUENCE_HISTORY": "작업순서 이력",
    "REPORT_SOURCE": "보고서 근거",
}
CATEGORY_LABELS = {
    "SAFETY": "안전",
    "QUALITY": "품질",
    "EQUIPMENT_ANOMALY": "설비 이상",
    "WORK_HOLD": "작업 보류",
    "REWORK": "재작업",
    "HANDOVER": "인수인계",
    "LATEST_PUBLISHED_DOCUMENT": "최신 공개 문서",
    "CONFLICTING_RECORDS": "상충 기록",
}
SCENARIO_LABELS = {
    "NORMAL": "일반",
    "EXCLUSION": "제외",
    "CONFLICT": "상충",
}


def _operator_action(
    code: str,
    title: str,
    detail: str,
    owner: str,
    next_action: str,
) -> dict[str, str]:
    return {
        "code": code,
        "title": title,
        "detail": detail,
        "owner": owner,
        "next_action": next_action,
    }


def operator_readiness_actions(
    readiness: dict[str, Any],
    *,
    external_call_enabled: bool,
    provider_adapter_mode: str,
    provider: str,
    model_scope: str,
    network_test_scope_enabled: bool,
    environment: str,
) -> list[dict[str, str]]:
    """Build Korean operator guidance without exposing credentials or local paths."""
    actions: list[dict[str, str]] = []
    source_gaps = readiness["source_gaps"]
    if "SOURCE_COVERAGE_INCOMPLETE" in readiness["readiness_failures"]:
        gap_text = ", ".join(
            f"{SOURCE_LABELS.get(source_type, source_type)} {missing}건"
            for source_type, missing in source_gaps.items()
            if missing
        )
        actions.append(_operator_action(
            "SOURCE_COVERAGE_INCOMPLETE",
            "실제 현장 원천이 부족합니다",
            gap_text or "필수 원천 유형의 준비도를 다시 확인해야 합니다.",
            "현장 데이터 책임자",
            "고객 승인 범위의 실제 원천을 축적한 뒤 검색 후보를 다시 생성하세요.",
        ))
    if "GROUND_TRUTH_COVERAGE_INCOMPLETE" in readiness["readiness_failures"]:
        gaps = readiness["category_scenario_gaps"]
        gap_text = ", ".join(
            f"{CATEGORY_LABELS.get(item['category'], item['category'])}/"
            f"{SCENARIO_LABELS.get(item['scenario_type'], item['scenario_type'])} "
            f"{item['missing']}건"
            for item in gaps
        )
        actions.append(_operator_action(
            "GROUND_TRUTH_COVERAGE_INCOMPLETE",
            "고객 승인 익명 현장 사례가 부족합니다",
            (
                f"현재 {readiness['ground_truth_count']}/{readiness['ground_truth_minimum']}건"
                + (f" · 부족 칸 {gap_text}" if gap_text else "")
            ),
            "현장 데이터 책임자·평가 책임자",
            "저장소 밖 승인 환경에서 원문을 익명화하고 독립 2인 승인을 받은 사례만 추가하세요.",
        ))
    if "NO_APPROVED_DATASET_VERSION" in readiness["readiness_failures"]:
        actions.append(_operator_action(
            "NO_APPROVED_DATASET_VERSION",
            "승인된 실제 현장 dataset이 없습니다",
            "작성자·검토자·1차 승인자·2차 승인자가 분리된 FIELD_READINESS snapshot이 필요합니다.",
            "dataset 작성자·검토자·독립 승인자",
            "48건과 24칸×2건을 충족한 dataset을 네 역할로 검토·승인하세요.",
        ))
    if "LATEST_APPROVED_DATASET_EVALUATION_MISSING_OR_FAILED" in readiness["readiness_failures"]:
        actions.append(_operator_action(
            "LATEST_APPROVED_DATASET_EVALUATION_MISSING_OR_FAILED",
            "승인 snapshot의 회귀 평가가 없거나 실패했습니다",
            "같은 snapshot의 두 평가에서 candidate ID, content hash와 순위가 안정돼야 합니다.",
            "평가 책임자",
            "승인 dataset을 바꾸지 않은 채 전체 평가를 두 번 실행하고 실패 case의 trace를 확인하세요.",
        ))
    if "INDEPENDENT_SAMPLE_REVIEW_INCOMPLETE" in readiness["readiness_failures"]:
        review = readiness["human_sample_review"]
        actions.append(_operator_action(
            "INDEPENDENT_SAMPLE_REVIEW_INCOMPLETE",
            "24칸 독립 검토가 끝나지 않았습니다",
            (
                f"상태 {review['status']} · 독립 검토자 {review['independent_reviewer_count']}/2명"
                f" · 표본 {review['sample_case_count']}/24칸"
            ),
            "독립 검토자 2인·필요 시 제3 합의자",
            "두 사람이 같은 고정 표본을 blind 검토하고 불일치는 앞선 두 사람과 다른 검토자가 합의하세요.",
        ))
    if "PROVIDER_REVIEW_INCOMPLETE" in readiness["readiness_failures"]:
        actions.append(_operator_action(
            "PROVIDER_REVIEW_INCOMPLETE",
            "provider 심사가 끝나지 않았습니다",
            "기술·정보보호·법무·고객 승인과 계약·지역·보존·비용·장애 격리 증거가 모두 필요합니다.",
            "정보보호·법무·고객 데이터 책임자",
            "실제 provider 구현 전에 네 승인 영역과 필수 체크리스트를 별도 심사하세요.",
        ))

    normalized_mode = provider_adapter_mode.strip().upper() or "DISABLED"
    if not external_call_enabled:
        actions.append(_operator_action(
            "EXTERNAL_CALL_FEATURE_DISABLED",
            "외부 AI 호출 기능이 비활성입니다",
            "서버 기능 플래그가 꺼져 있어 실제 provider로 전송하지 않습니다.",
            "시스템 관리자",
            "계약·전송 지역·법적 승인과 모든 준비도 항목이 끝나기 전에는 활성화하지 마세요.",
        ))
    if normalized_mode == "DISABLED":
        actions.append(_operator_action(
            "PROVIDER_ADAPTER_DISABLED",
            "provider 어댑터가 비활성입니다",
            "외부 네트워크 어댑터가 구성되지 않았습니다.",
            "시스템 관리자·개발 책임자",
            "provider 심사 완료 뒤 승인된 구현과 장애 격리 절차를 별도 작업으로 연결하세요.",
        ))
    elif normalized_mode == "FAKE":
        actions.append(_operator_action(
            "FAKE_PROVIDER_ONLY",
            "합성 provider만 연결돼 있습니다",
            "FAKE 어댑터는 회귀 시험용이며 실제 provider 네트워크 준비도를 증명하지 않습니다.",
            "평가 책임자",
            "합성 회귀 결과를 FIELD_READINESS나 실제 provider 승인 근거로 합산하지 마세요.",
        ))
    elif normalized_mode == "NETWORK_TEST" and (
        not network_test_scope_enabled or environment != "test"
    ):
        actions.append(_operator_action(
            "NETWORK_TEST_SCOPE_BLOCKED",
            "provider 네트워크 시험 범위가 차단됐습니다",
            "NETWORK_TEST는 명시적 시험 scope와 test 환경에서만 사용할 수 있습니다.",
            "시스템 관리자·정보보호 책임자",
            "운영 연결로 전환하지 말고 승인된 격리 시험 환경과 전송 범위를 먼저 확인하세요.",
        ))
    if provider.strip().upper() == "UNCONFIGURED" or model_scope.strip().upper() == "UNCONFIGURED":
        actions.append(_operator_action(
            "PROVIDER_OR_MODEL_UNCONFIGURED",
            "provider 또는 model 범위가 확정되지 않았습니다",
            "승인 대상 provider/model이 설정되지 않아 계약·지역·목적 범위를 대조할 수 없습니다.",
            "법무·정보보호·고객 데이터 책임자",
            "계약과 고객 승인에 적힌 provider/model을 확정한 뒤 같은 범위로 심사하세요.",
        ))
    return actions


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
        and _metadata(candidate).get("readiness_track", "FIELD_READINESS") == "FIELD_READINESS"
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

    ground_truth_statement = select(AISearchGroundTruthCase, AISearchGroundTruthProvenance).join(
        AISearchGroundTruthProvenance,
        AISearchGroundTruthProvenance.ground_truth_case_id == AISearchGroundTruthCase.ground_truth_case_id,
    ).where(
        AISearchGroundTruthCase.customer_scope == customer_scope,
        AISearchGroundTruthCase.site_scope == site_scope,
        AISearchGroundTruthCase.database_scope == database_scope_value,
        AISearchGroundTruthCase.is_active.is_(True),
        AISearchGroundTruthCase.approved_at.is_not(None),
        AISearchGroundTruthProvenance.approval_status == "APPROVED",
    )
    if line_scope is None:
        ground_truth_statement = ground_truth_statement.where(AISearchGroundTruthCase.line_scope.is_(None))
    else:
        ground_truth_statement = ground_truth_statement.where(AISearchGroundTruthCase.line_scope == line_scope)
    ground_truth_rows = session.execute(ground_truth_statement).all()
    field_ground_truth = [
        case
        for case, provenance in ground_truth_rows
        if provenance.readiness_track == "FIELD_READINESS"
        and provenance.data_classification == "ANONYMOUS_FIELD"
    ]
    smoke_ground_truth = [
        case for case, provenance in ground_truth_rows if provenance.readiness_track == "SMOKE_REGRESSION"
    ]
    ground_truth = field_ground_truth
    coverage = Counter((case.category, case.scenario_type) for case in ground_truth)
    smoke_coverage = Counter((case.category, case.scenario_type) for case in smoke_ground_truth)
    latest_approved_dataset = session.scalar(
        select(AIGroundTruthDatasetVersion).where(
            AIGroundTruthDatasetVersion.customer_scope == customer_scope,
            AIGroundTruthDatasetVersion.site_scope == site_scope,
            AIGroundTruthDatasetVersion.database_scope == database_scope_value,
            AIGroundTruthDatasetVersion.line_scope == line_scope,
            AIGroundTruthDatasetVersion.readiness_track == "FIELD_READINESS",
            AIGroundTruthDatasetVersion.status == "APPROVED",
        ).order_by(
            desc(AIGroundTruthDatasetVersion.second_approved_at),
            desc(AIGroundTruthDatasetVersion.version),
        )
    )
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
    latest_smoke_evaluation = None
    for run in session.scalars(
        select(AISearchEvaluationRun).order_by(desc(AISearchEvaluationRun.created_at), desc(AISearchEvaluationRun.id))
    ).all():
        try:
            metrics = json.loads(run.metrics_json)
        except (TypeError, ValueError):
            continue
        scope_matches = (
            metrics.get("customer_scope") == customer_scope
            and metrics.get("site_scope") == site_scope
            and metrics.get("database_scope") == database_scope_value
            and metrics.get("line_scope") == line_scope
        )
        binding = session.scalar(select(AIEvaluationDatasetBinding).where(
            AIEvaluationDatasetBinding.run_id == run.run_id
        ))
        dataset_matches = bool(
            latest_approved_dataset
            and binding
            and binding.dataset_version_id == latest_approved_dataset.dataset_version_id
            and binding.dataset_snapshot_hash == latest_approved_dataset.snapshot_hash
        )
        if scope_matches:
            evaluation_summary = {
                "run_id": run.run_id,
                "run_label": run.run_label,
                "created_at": run.created_at,
                "status": run.status,
                "candidate_identity_stable": run.candidate_identity_stable,
                "ranking_stable": run.ranking_stable,
                "case_count": metrics.get("case_count", 0),
                "passed_count": metrics.get("passed_count", 0),
                "source_coverage_complete": metrics.get("source_coverage_complete", False),
                "top_k_inclusion_rate": metrics.get("top_k_inclusion_rate", metrics.get("recall_at_k", 0)),
                "excluded_source_violation": metrics.get("excluded_source_violation", 0),
                "permission_leak_violation": metrics.get("permission_leak_violation", 0),
                "nonexistent_citation_violation": metrics.get("nonexistent_citation_violation", 0),
                "citation_trace_success_rate": metrics.get("citation_trace_success_rate", 0),
                "citation_semantic_match_rate": metrics.get("citation_semantic_match_rate", 0),
                "conflict_disclosure_rate": metrics.get("conflict_disclosure_rate", 0),
                "dataset_version_id": binding.dataset_version_id if binding else None,
                "dataset_snapshot_hash": binding.dataset_snapshot_hash if binding else None,
            }
            if (
                metrics.get("readiness_track") == "FIELD_READINESS"
                and dataset_matches
                and latest_evaluation is None
            ):
                latest_evaluation = evaluation_summary
            elif metrics.get("readiness_track") == "SMOKE_REGRESSION" and latest_smoke_evaluation is None:
                latest_smoke_evaluation = evaluation_summary
            if latest_evaluation is not None and latest_smoke_evaluation is not None:
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
    smoke_category_scenario_gaps = [
        {
            "category": category,
            "scenario_type": scenario,
            "count": smoke_coverage[(category, scenario)],
            "required": GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM,
            "missing": max(GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM - smoke_coverage[(category, scenario)], 0),
        }
        for category in QUESTION_CATEGORIES
        for scenario in SCENARIO_TYPES
        if smoke_coverage[(category, scenario)] < GROUND_TRUTH_PER_CATEGORY_SCENARIO_MINIMUM
    ]
    smoke_ground_truth_gap = max(GROUND_TRUTH_MINIMUM - len(smoke_ground_truth), 0)
    smoke_ground_truth_ready = smoke_ground_truth_gap == 0 and not smoke_category_scenario_gaps
    evaluation_ready = bool(
        latest_evaluation
        and latest_evaluation["status"] == "PASSED"
        and latest_evaluation["candidate_identity_stable"]
        and latest_evaluation["ranking_stable"]
        and latest_evaluation["case_count"] >= GROUND_TRUTH_MINIMUM
        and latest_evaluation["source_coverage_complete"]
        and latest_evaluation["top_k_inclusion_rate"] >= TOP_K_INCLUSION_THRESHOLD
        and latest_evaluation["excluded_source_violation"] == 0
        and latest_evaluation["permission_leak_violation"] == 0
        and latest_evaluation["nonexistent_citation_violation"] == 0
        and latest_evaluation["citation_trace_success_rate"] >= CITATION_TRACE_THRESHOLD
        and latest_evaluation["citation_semantic_match_rate"] >= CITATION_SEMANTIC_MATCH_THRESHOLD
        and latest_evaluation["conflict_disclosure_rate"] >= CONFLICT_DISCLOSURE_THRESHOLD
    )
    dataset_ready = latest_approved_dataset is not None
    human_sample_review = (
        sample_review_summary(
            session,
            dataset_version_id=latest_approved_dataset.dataset_version_id,
            dataset_snapshot_hash=latest_approved_dataset.snapshot_hash or "",
        )
        if latest_approved_dataset is not None
        else {
            "status": "NOT_STARTED",
            "evaluation_run_id": None,
            "dataset_snapshot_hash": None,
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
    )
    human_sample_review_ready = bool(human_sample_review["complete"])
    approval_actors = {
        "author_id": latest_approved_dataset.author_id if latest_approved_dataset else None,
        "reviewer_id": latest_approved_dataset.reviewer_id if latest_approved_dataset else None,
        "first_approved_by": (
            latest_approved_dataset.first_approved_by if latest_approved_dataset else None
        ),
        "second_approved_by": (
            latest_approved_dataset.second_approved_by if latest_approved_dataset else None
        ),
    }
    assigned_approval_actors = {
        actor for actor in approval_actors.values() if actor is not None
    }
    approval_actor_separation = {
        **approval_actors,
        "required_actor_count": 4,
        "distinct_actor_count": len(assigned_approval_actors),
        "complete": (
            all(actor is not None for actor in approval_actors.values())
            and len(assigned_approval_actors) == 4
        ),
        "missing_roles": [
            role for role, actor in approval_actors.items() if actor is None
        ],
    }
    ready = (
        source_ready
        and ground_truth_ready
        and dataset_ready
        and evaluation_ready
        and human_sample_review_ready
        and provider_review_ready
    )
    readiness_failures = []
    if not source_ready:
        readiness_failures.append("SOURCE_COVERAGE_INCOMPLETE")
    if not ground_truth_ready:
        readiness_failures.append("GROUND_TRUTH_COVERAGE_INCOMPLETE")
    if not dataset_ready:
        readiness_failures.append("NO_APPROVED_DATASET_VERSION")
    if dataset_ready and not evaluation_ready:
        readiness_failures.append("LATEST_APPROVED_DATASET_EVALUATION_MISSING_OR_FAILED")
    if not human_sample_review_ready:
        readiness_failures.append("INDEPENDENT_SAMPLE_REVIEW_INCOMPLETE")
    if not provider_review_ready:
        readiness_failures.append("PROVIDER_REVIEW_INCOMPLETE")
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
        "field_readiness": {
            "accepted_data_classification": "ANONYMOUS_FIELD",
            "ground_truth_count": len(field_ground_truth),
            "ground_truth_gap": ground_truth_gap,
            "ground_truth_ready": ground_truth_ready,
            "latest_evaluation": latest_evaluation,
        },
        "smoke_regression_readiness": {
            "accepted_data_classifications": ["SYNTHETIC", "TEST"],
            "ground_truth_count": len(smoke_ground_truth),
            "ground_truth_gap": smoke_ground_truth_gap,
            "ground_truth_ready": smoke_ground_truth_ready,
            "latest_evaluation": latest_smoke_evaluation,
        },
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
        "smoke_category_scenario_counts": [
            {
                "category": category,
                "scenario_type": scenario,
                "count": smoke_coverage[(category, scenario)],
            }
            for category in QUESTION_CATEGORIES
            for scenario in SCENARIO_TYPES
        ],
        "smoke_category_scenario_gaps": smoke_category_scenario_gaps,
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
        "latest_approved_dataset": None if latest_approved_dataset is None else {
            "dataset_version_id": latest_approved_dataset.dataset_version_id,
            "dataset_key": latest_approved_dataset.dataset_key,
            "version": latest_approved_dataset.version,
            "snapshot_hash": latest_approved_dataset.snapshot_hash,
            "approved_at": latest_approved_dataset.second_approved_at,
        },
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
        "dataset_ready": dataset_ready,
        "human_sample_review": human_sample_review,
        "human_sample_review_ready": human_sample_review_ready,
        "approval_actor_separation": approval_actor_separation,
        "provider_review_ready": provider_review_ready,
        "provider_start_ready": ready,
        "ai_provider_readiness_status": (
            "PASS" if ready else "FAIL" if dataset_ready and latest_evaluation is not None else "PENDING"
        ),
        "readiness_failures": readiness_failures,
        "external_ai_calls_blocked": not ready,
        "non_ai_core_flows_blocked": False,
        "candidate_regeneration_allowed": True,
        "quality_inspection_allowed": True,
    }
