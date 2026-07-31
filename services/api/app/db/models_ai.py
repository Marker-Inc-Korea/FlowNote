from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, event, inspect
from sqlalchemy import String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class AISearchCandidate(Base):
    __tablename__ = "ai_search_candidates"
    __table_args__ = (
        CheckConstraint(
            (
                "source_type IN ('PUBLISHED_DOCUMENT_VERSION', 'FIELD_COMMENT', "
                "'WORK_SEQUENCE_HISTORY', 'REPORT_SOURCE')"
            ),
            name="ck_ai_search_candidate_source_type",
        ),
        UniqueConstraint(
            "source_type",
            "source_id",
            "source_version_id",
            name="uq_ai_search_candidates_source",
        ),
        Index("ix_ai_search_candidates_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    parent_type: Mapped[str | None] = mapped_column(String(50))
    parent_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_status: Mapped[str | None] = mapped_column(String(30))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AISearchEvaluationRun(Base):
    __tablename__ = "ai_search_evaluation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('PASSED', 'FAILED')", name="ck_ai_search_evaluation_run_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_label: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    evaluated_as_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_identity_stable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ranking_stable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchEvaluationCase(Base):
    __tablename__ = "ai_search_evaluation_cases"
    __table_args__ = (
        UniqueConstraint("run_id", "case_key", name="uq_ai_search_evaluation_case"),
        Index("ix_ai_search_evaluation_cases_case_key_id", "case_key", "id"),
        CheckConstraint(
            "expected_outcome IN ('SUFFICIENT', 'INSUFFICIENT_EVIDENCE')",
            name="ck_ai_search_evaluation_expected_outcome",
        ),
        CheckConstraint(
            "actual_outcome IN ('SUFFICIENT', 'INSUFFICIENT_EVIDENCE')",
            name="ck_ai_search_evaluation_actual_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_evaluation_runs.run_id"), nullable=False, index=True
    )
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    actual_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    actual_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    ranking_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchGroundTruthCase(Base):
    __tablename__ = "ai_search_ground_truth_cases"
    __table_args__ = (
        UniqueConstraint("customer_scope", "site_scope", "case_key", name="uq_ai_ground_truth_scope_case"),
        CheckConstraint(
            (
                "category IN ('SAFETY', 'QUALITY', 'EQUIPMENT_ANOMALY', 'WORK_HOLD', "
                "'REWORK', 'HANDOVER', 'LATEST_PUBLISHED_DOCUMENT', 'CONFLICTING_RECORDS')"
            ),
            name="ck_ai_ground_truth_category",
        ),
        CheckConstraint(
            "scenario_type IN ('NORMAL', 'EXCLUSION', 'CONFLICT')",
            name="ck_ai_ground_truth_scenario_type",
        ),
        Index(
            "ix_ai_ground_truth_scope_approved",
            "customer_scope",
            "site_scope",
            "line_scope",
            "approved_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ground_truth_case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    line_scope: Mapped[str | None] = mapped_column(String(64))
    database_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_rank_min: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_rank_max: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AISearchGroundTruthProvenance(Base):
    __tablename__ = "ai_search_ground_truth_provenance"
    __table_args__ = (
        CheckConstraint(
            "data_classification IN ('SYNTHETIC', 'TEST', 'ANONYMOUS_FIELD', 'PILOT')",
            name="ck_ai_ground_truth_provenance_classification",
        ),
        CheckConstraint(
            "readiness_track IN ('SMOKE_REGRESSION', 'FIELD_READINESS')",
            name="ck_ai_ground_truth_provenance_track",
        ),
        CheckConstraint(
            "approval_status IN ('PENDING_SECOND_APPROVAL', 'APPROVED', 'REJECTED')",
            name="ck_ai_ground_truth_provenance_approval",
        ),
        CheckConstraint(
            "second_approved_by IS NULL OR second_approved_by <> first_approved_by",
            name="ck_ai_ground_truth_distinct_approvers",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provenance_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ground_truth_case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_ground_truth_cases.ground_truth_case_id"),
        unique=True, nullable=False, index=True
    )
    data_classification: Mapped[str] = mapped_column(String(30), nullable=False)
    readiness_track: Mapped[str] = mapped_column(String(30), nullable=False)
    provenance_note: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contains_sensitive_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False)
    first_approved_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    first_approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    second_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    second_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIGroundTruthDatasetVersion(Base):
    __tablename__ = "ai_ground_truth_dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "customer_scope", "site_scope", "dataset_key", "version",
            name="uq_ai_ground_truth_dataset_version",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'IN_REVIEW', 'PENDING_FIRST_APPROVAL', "
            "'PENDING_SECOND_APPROVAL', 'APPROVED', 'SUPERSEDED', 'RETIRED')",
            name="ck_ai_ground_truth_dataset_status",
        ),
        CheckConstraint(
            "readiness_track IN ('SMOKE_REGRESSION', 'FIELD_READINESS')",
            name="ck_ai_ground_truth_dataset_track",
        ),
        CheckConstraint(
            "reviewer_id IS NULL OR reviewer_id <> author_id",
            name="ck_ai_ground_truth_dataset_reviewer_distinct",
        ),
        CheckConstraint(
            "first_approved_by IS NULL OR (first_approved_by <> author_id AND "
            "first_approved_by <> reviewer_id)",
            name="ck_ai_ground_truth_dataset_first_approver_distinct",
        ),
        CheckConstraint(
            "second_approved_by IS NULL OR (second_approved_by <> author_id AND "
            "second_approved_by <> reviewer_id AND second_approved_by <> first_approved_by)",
            name="ck_ai_ground_truth_dataset_second_approver_distinct",
        ),
        Index(
            "ix_ai_ground_truth_dataset_scope_status",
            "customer_scope", "site_scope", "line_scope", "status", "version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    dataset_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    line_scope: Mapped[str | None] = mapped_column(String(64))
    database_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    readiness_track: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT")
    author_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    first_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    second_approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    replaces_dataset_version_id: Mapped[str | None] = mapped_column(String(64))
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    second_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIGroundTruthDatasetCase(Base):
    __tablename__ = "ai_ground_truth_dataset_cases"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "ground_truth_case_id", name="uq_ai_dataset_case"),
        UniqueConstraint("dataset_version_id", "case_key", name="uq_ai_dataset_case_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_ground_truth_dataset_versions.dataset_version_id"),
        nullable=False, index=True,
    )
    ground_truth_case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_ground_truth_cases.ground_truth_case_id"),
        nullable=False, index=True,
    )
    case_key: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    added_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEvaluationDatasetBinding(Base):
    __tablename__ = "ai_evaluation_dataset_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_search_evaluation_runs.run_id"), unique=True, nullable=False, index=True
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_ground_truth_dataset_versions.dataset_version_id"),
        nullable=False, index=True,
    )
    dataset_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIFieldReadinessSampleReview(Base):
    """Independent human review of one immutable field-readiness evaluation snapshot."""

    __tablename__ = "ai_field_readiness_sample_reviews"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "evaluation_run_id",
            "reviewer_id",
            name="uq_ai_field_sample_review_actor",
        ),
        UniqueConstraint("review_pair_hash", name="uq_ai_field_sample_review_pair"),
        CheckConstraint(
            "review_role IN ('INDEPENDENT', 'CONSENSUS')",
            name="ck_ai_field_sample_review_role",
        ),
        CheckConstraint(
            "(review_role = 'INDEPENDENT' AND review_pair_hash IS NULL "
            "AND resolved_review_ids_json IS NULL) OR "
            "(review_role = 'CONSENSUS' AND review_pair_hash IS NOT NULL "
            "AND resolved_review_ids_json IS NOT NULL)",
            name="ck_ai_field_sample_review_pair_role",
        ),
        Index(
            "ix_ai_field_sample_review_dataset_run",
            "dataset_version_id",
            "evaluation_run_id",
            "review_role",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    dataset_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ai_ground_truth_dataset_versions.dataset_version_id"),
        nullable=False,
        index=True,
    )
    evaluation_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ai_search_evaluation_runs.run_id"),
        nullable=False,
        index=True,
    )
    dataset_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_role: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    sampling_plan_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    sample_case_keys_json: Mapped[str] = mapped_column(Text, nullable=False)
    sample_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_pair_hash: Mapped[str | None] = mapped_column(String(64))
    resolved_review_ids_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ai_prompt_versions_name_version"),
        CheckConstraint(
            "allowed_purpose IN ('EVIDENCE_SEARCH', 'EVIDENCE_SUMMARY')",
            name="ck_ai_prompt_version_purpose",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_version_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIQuery(Base):
    __tablename__ = "ai_queries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RECEIVED', 'BLOCKED', 'CALLING', 'SUCCEEDED', "
            "'INSUFFICIENT_EVIDENCE', 'CITATION_VALIDATION_FAILED', 'FAILED')",
            name="ck_ai_query_status",
        ),
        CheckConstraint(
            "response_storage_mode IN ('DO_NOT_STORE', 'STORE_90_DAYS')",
            name="ck_ai_query_response_storage_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False, default="DEFAULT")
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False, default="DEFAULT")
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RECEIVED")
    prompt_version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("ai_prompt_versions.prompt_version_id"))
    prompt_snapshot_json: Mapped[str | None] = mapped_column(Text)
    approval_snapshot_json: Mapped[str | None] = mapped_column(Text)
    response_storage_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="DO_NOT_STORE")
    response_text: Mapped[str | None] = mapped_column(Text)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    regeneration_of_query_id: Mapped[str | None] = mapped_column(String(64))
    regenerable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    block_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immediate_expiry_operation_key: Mapped[str | None] = mapped_column(
        String(160), unique=True, index=True
    )
    immediate_expiry_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immediate_expiry_reason: Mapped[str | None] = mapped_column(Text)


class AIQueryEvidenceCandidate(Base):
    __tablename__ = "ai_query_evidence_candidates"
    __table_args__ = (UniqueConstraint("query_id", "candidate_id", name="uq_ai_query_evidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_for_prompt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_externally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    eligibility_result: Mapped[str] = mapped_column(String(30), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIQueryCitation(Base):
    __tablename__ = "ai_query_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    citation_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    claim_key: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(64))
    trace_table: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_version_id: Mapped[str | None] = mapped_column(String(64))
    internal_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AICallAttempt(Base):
    __tablename__ = "ai_call_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    sanitized_error_message: Mapped[str | None] = mapped_column(String(255))
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    cost_micros: Mapped[int | None] = mapped_column(Integer)


class AITransferApproval(Base):
    __tablename__ = "ai_transfer_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    allowed_purposes: Mapped[str] = mapped_column(
        Text, nullable=False, default='["EVIDENCE_SEARCH", "EVIDENCE_SUMMARY"]'
    )
    allowed_source_types: Mapped[str] = mapped_column(Text, nullable=False)
    data_handling_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class AIOperationalPolicy(Base):
    """Fail-safe operational limits. Secrets are intentionally absent."""

    __tablename__ = "ai_operational_policies"
    __table_args__ = (
        UniqueConstraint("customer_scope", "site_scope", name="uq_ai_operational_policy_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    daily_cost_budget_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    query_payload_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    response_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    audit_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    allow_audit_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIProviderOnboardingReview(Base):
    """Versioned provider due-diligence and four-party start decision."""

    __tablename__ = "ai_provider_onboarding_reviews"
    __table_args__ = (
        UniqueConstraint(
            "customer_scope", "site_scope", "provider", "model_scope", "review_version",
            name="uq_ai_provider_onboarding_review_version",
        ),
        CheckConstraint(
            "technical_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_technical_status",
        ),
        CheckConstraint(
            "security_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_security_status",
        ),
        CheckConstraint(
            "legal_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_legal_status",
        ),
        CheckConstraint(
            "customer_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_ai_provider_review_customer_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    review_version: Mapped[str] = mapped_column(String(80), nullable=False)
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_purposes_json: Mapped[str] = mapped_column(Text, nullable=False)
    technical_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    security_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    legal_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    customer_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    technical_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    security_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    legal_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    customer_reviewed_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    technical_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    security_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("user_accounts.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIOperationAuditEvent(Base):
    __tablename__ = "ai_operation_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), index=True)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AIRetentionAudit(Base):
    __tablename__ = "ai_retention_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retention_audit_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    query_text_action: Mapped[str] = mapped_column(String(30), nullable=False)
    response_text_action: Mapped[str] = mapped_column(String(30), nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    operation_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIQueryLegalHold(Base):
    """Prevents retention redaction while an authorized preservation order is active."""

    __tablename__ = "ai_query_legal_holds"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'RELEASED')", name="ck_ai_query_legal_hold_status"),
        Index("ix_ai_query_legal_holds_query_status", "query_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hold_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    query_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_queries.query_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    authority_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    placed_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("user_accounts.user_id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(Text)
    operation_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    release_operation_key: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)


class AISensitiveDataPolicy(Base):
    """Versioned site policy whose raw terms never leave the operations API."""

    __tablename__ = "ai_sensitive_data_policies"
    __table_args__ = (
        CheckConstraint(
            (
                "status IN ('DRAFT', 'REVIEWED', 'APPROVED', 'ACTIVE', "
                "'SUPERSEDED', 'APPROVAL_WITHDRAWN', 'RETIRED')"
            ),
            name="ck_ai_sensitive_data_policy_status",
        ),
        UniqueConstraint(
            "customer_scope",
            "site_scope",
            "version",
            name="uq_ai_sensitive_data_policy_scope_version",
        ),
        Index(
            "ix_ai_sensitive_data_policy_scope_active",
            "customer_scope",
            "site_scope",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    customer_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    site_scope: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    forbidden_terms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    customer_identifiers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    state_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": state_revision}
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_policy_id: Mapped[str | None] = mapped_column(String(64))
    approval_withdrawn_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    approval_withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AISensitiveDataPolicyOperation(Base):
    """Idempotency receipt for a sanitized sensitive-policy mutation."""

    __tablename__ = "ai_sensitive_data_policy_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    policy_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_sensitive_data_policies.policy_id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_state_tag: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_accounts.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(AIPromptVersion, "before_update")
def prevent_approved_prompt_content_update(_mapper: object, _connection: object, target: AIPromptVersion) -> None:
    """Approved prompt content is immutable; retirement metadata may still be updated."""
    if target.approved_at is None:
        return
    state = inspect(target)
    immutable_fields = ("name", "version", "template_hash", "template_text", "allowed_purpose")
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError("Approved AI prompt versions are immutable; create a new version.")


@event.listens_for(AISensitiveDataPolicy, "before_update")
def prevent_sensitive_policy_content_update(
    _mapper: object, _connection: object, target: AISensitiveDataPolicy
) -> None:
    """Policy source lists and their hash are immutable after creation."""
    state = inspect(target)
    immutable_fields = (
        "customer_scope",
        "site_scope",
        "version",
        "forbidden_terms_json",
        "customer_identifiers_json",
        "content_hash",
        "created_by",
        "created_at",
    )
    if any(state.attrs[field].history.has_changes() for field in immutable_fields):
        raise ValueError("AI sensitive-data policy content is immutable; create a new version.")
