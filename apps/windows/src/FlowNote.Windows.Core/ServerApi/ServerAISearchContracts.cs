using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerAISearchCandidateResponse
{
    [JsonPropertyName("candidate_id")]
    public string CandidateId { get; init; } = string.Empty;

    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("trace_table")]
    public string TraceTable { get; init; } = string.Empty;

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = string.Empty;

    [JsonPropertyName("trace_version_id")]
    public string? TraceVersionId { get; init; }

    [JsonPropertyName("parent_type")]
    public string? ParentType { get; init; }

    [JsonPropertyName("parent_id")]
    public string? ParentId { get; init; }

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("summary")]
    public string? Summary { get; init; }

    [JsonPropertyName("review_status")]
    public string? ReviewStatus { get; init; }

    [JsonPropertyName("content_hash")]
    public string ContentHash { get; init; } = string.Empty;

    [JsonPropertyName("refreshed_at")]
    public DateTime RefreshedAt { get; init; }
}

public sealed record ServerAISearchRebuildResponse
{
    [JsonPropertyName("candidate_count")]
    public int CandidateCount { get; init; }

    [JsonPropertyName("counts_by_source_type")]
    public IReadOnlyDictionary<string, int> CountsBySourceType { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("excluded_counts_by_reason")]
    public IReadOnlyDictionary<string, int> ExcludedCountsByReason { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("excluded_reason_guidance")]
    public IReadOnlyDictionary<string, ServerAISearchExcludedReasonGuidance> ExcludedReasonGuidance { get; init; } =
        new Dictionary<string, ServerAISearchExcludedReasonGuidance>();

    [JsonPropertyName("rebuilt_at")]
    public DateTime RebuiltAt { get; init; }
}

public sealed record ServerAISearchExcludedReasonGuidance
{
    [JsonPropertyName("label")]
    public string Label { get; init; } = string.Empty;

    [JsonPropertyName("operator_action")]
    public string OperatorAction { get; init; } = string.Empty;

    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;
}

public sealed record ServerFieldCommentReviewReadinessResponse
{
    [JsonPropertyName("total_count")]
    public int TotalCount { get; init; }

    [JsonPropertyName("counts_by_status")]
    public IReadOnlyDictionary<string, int> CountsByStatus { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("reviewed_status_count")]
    public int ReviewedStatusCount { get; init; }

    [JsonPropertyName("required_reviewed_count")]
    public int RequiredReviewedCount { get; init; }

    [JsonPropertyName("missing_reviewed_count")]
    public int MissingReviewedCount { get; init; }

    [JsonPropertyName("reviewed_ratio")]
    public decimal ReviewedRatio { get; init; }
}

public sealed record ServerAISearchQualityResponse
{
    [JsonPropertyName("candidate_count")]
    public int CandidateCount { get; init; }

    [JsonPropertyName("counts_by_source_type")]
    public IReadOnlyDictionary<string, int> CountsBySourceType { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("excluded_counts_by_reason")]
    public IReadOnlyDictionary<string, int> ExcludedCountsByReason { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("excluded_reason_guidance")]
    public IReadOnlyDictionary<string, ServerAISearchExcludedReasonGuidance> ExcludedReasonGuidance { get; init; } =
        new Dictionary<string, ServerAISearchExcludedReasonGuidance>();

    [JsonPropertyName("field_comment_review_readiness")]
    public ServerFieldCommentReviewReadinessResponse FieldCommentReviewReadiness { get; init; } = new();
}

public sealed record ServerAISearchReadinessScopeResponse
{
    [JsonPropertyName("customer_scope")]
    public string CustomerScope { get; init; } = string.Empty;

    [JsonPropertyName("site_scope")]
    public string SiteScope { get; init; } = string.Empty;

    [JsonPropertyName("line_scope")]
    public string? LineScope { get; init; }

    [JsonPropertyName("database_scope")]
    public string DatabaseScope { get; init; } = string.Empty;
}

public sealed record ServerAISearchReadinessResponse
{
    [JsonPropertyName("scope")]
    public ServerAISearchReadinessScopeResponse Scope { get; init; } = new();

    [JsonPropertyName("source_counts")]
    public IReadOnlyDictionary<string, int> SourceCounts { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("source_minimums")]
    public IReadOnlyDictionary<string, int> SourceMinimums { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("source_gaps")]
    public IReadOnlyDictionary<string, int> SourceGaps { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("ground_truth_count")]
    public int GroundTruthCount { get; init; }

    [JsonPropertyName("ground_truth_minimum")]
    public int GroundTruthMinimum { get; init; }

    [JsonPropertyName("ground_truth_gap")]
    public int GroundTruthGap { get; init; }

    [JsonPropertyName("field_readiness")]
    public ServerAISearchTrackReadinessResponse FieldReadiness { get; init; } = new();

    [JsonPropertyName("smoke_regression_readiness")]
    public ServerAISearchTrackReadinessResponse SmokeRegressionReadiness { get; init; } = new();

    [JsonPropertyName("missing_category_scenarios")]
    public IReadOnlyList<Dictionary<string, string>> MissingCategoryScenarios { get; init; } = [];

    [JsonPropertyName("provider_start_ready")]
    public bool ProviderStartReady { get; init; }

    [JsonPropertyName("ai_provider_readiness_status")]
    public string AIProviderReadinessStatus { get; init; } = "PENDING";

    [JsonPropertyName("readiness_failures")]
    public IReadOnlyList<string> ReadinessFailures { get; init; } = [];

    [JsonPropertyName("latest_approved_dataset")]
    public ServerAIGroundTruthDatasetSummary? LatestApprovedDataset { get; init; }
}

public sealed record ServerAISearchTrackReadinessResponse
{
    [JsonPropertyName("ground_truth_count")]
    public int GroundTruthCount { get; init; }

    [JsonPropertyName("ground_truth_gap")]
    public int GroundTruthGap { get; init; }

    [JsonPropertyName("ground_truth_ready")]
    public bool GroundTruthReady { get; init; }
}

public sealed record ServerAIGroundTruthCoverage
{
    [JsonPropertyName("category")] public string Category { get; init; } = string.Empty;
    [JsonPropertyName("scenario_type")] public string ScenarioType { get; init; } = string.Empty;
    [JsonPropertyName("count")] public int Count { get; init; }
    [JsonPropertyName("required")] public int Required { get; init; }
    [JsonPropertyName("missing")] public int Missing { get; init; }
}

public sealed record ServerAIGroundTruthProvenance
{
    [JsonPropertyName("approval_status")] public string ApprovalStatus { get; init; } = string.Empty;
    [JsonPropertyName("readiness_track")] public string ReadinessTrack { get; init; } = string.Empty;
    [JsonPropertyName("source_snapshot_hash")] public string SourceSnapshotHash { get; init; } = string.Empty;
}

public sealed record ServerAIGroundTruthCase
{
    [JsonPropertyName("ground_truth_case_id")] public string GroundTruthCaseId { get; init; } = string.Empty;
    [JsonPropertyName("case_key")] public string CaseKey { get; init; } = string.Empty;
    [JsonPropertyName("category")] public string Category { get; init; } = string.Empty;
    [JsonPropertyName("scenario_type")] public string ScenarioType { get; init; } = string.Empty;
    [JsonPropertyName("question")] public string Question { get; init; } = string.Empty;
    [JsonPropertyName("expected_outcome")] public string ExpectedOutcome { get; init; } = string.Empty;
    [JsonPropertyName("allowed_rank_min")] public int AllowedRankMin { get; init; }
    [JsonPropertyName("allowed_rank_max")] public int AllowedRankMax { get; init; }
    [JsonPropertyName("as_of")] public DateTimeOffset AsOf { get; init; }
    [JsonPropertyName("expected_evidence")] public IReadOnlyList<Dictionary<string, object>> ExpectedEvidence { get; init; } = [];
    [JsonPropertyName("expected_excluded")] public IReadOnlyList<Dictionary<string, object>> ExpectedExcluded { get; init; } = [];
    [JsonPropertyName("provenance")] public ServerAIGroundTruthProvenance? Provenance { get; init; }
}

public record ServerAIGroundTruthDatasetSummary
{
    [JsonPropertyName("dataset_version_id")] public string DatasetVersionId { get; init; } = string.Empty;
    [JsonPropertyName("dataset_key")] public string DatasetKey { get; init; } = string.Empty;
    [JsonPropertyName("version")] public int Version { get; init; }
    [JsonPropertyName("title")] public string Title { get; init; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; init; } = string.Empty;
    [JsonPropertyName("readiness_track")] public string ReadinessTrack { get; init; } = string.Empty;
    [JsonPropertyName("author_id")] public string AuthorId { get; init; } = string.Empty;
    [JsonPropertyName("reviewer_id")] public string? ReviewerId { get; init; }
    [JsonPropertyName("first_approved_by")] public string? FirstApprovedBy { get; init; }
    [JsonPropertyName("second_approved_by")] public string? SecondApprovedBy { get; init; }
    [JsonPropertyName("snapshot_hash")] public string? SnapshotHash { get; init; }
    [JsonPropertyName("replaces_dataset_version_id")] public string? ReplacesDatasetVersionId { get; init; }
    [JsonPropertyName("case_count")] public int CaseCount { get; init; }
    [JsonPropertyName("coverage_complete")] public bool CoverageComplete { get; init; }
    [JsonPropertyName("coverage")] public IReadOnlyList<ServerAIGroundTruthCoverage> Coverage { get; init; } = [];
}

public sealed record ServerAIGroundTruthDataset : ServerAIGroundTruthDatasetSummary
{
    [JsonPropertyName("cases")] public IReadOnlyList<ServerAIGroundTruthCase> Cases { get; init; } = [];
}

public sealed record ServerAIGroundTruthDatasetCreateRequest
{
    [JsonPropertyName("datasetKey")] public string DatasetKey { get; init; } = string.Empty;
    [JsonPropertyName("title")] public string Title { get; init; } = string.Empty;
    [JsonPropertyName("readinessTrack")] public string ReadinessTrack { get; init; } = string.Empty;
    [JsonPropertyName("groundTruthCaseIds")] public IReadOnlyList<string> GroundTruthCaseIds { get; init; } = [];
    [JsonPropertyName("changeReason")] public string ChangeReason { get; init; } = string.Empty;
    [JsonPropertyName("replacesDatasetVersionId")] public string? ReplacesDatasetVersionId { get; init; }
}

public sealed record ServerAIGroundTruthDatasetTransitionRequest(
    [property: JsonPropertyName("action")] string Action,
    [property: JsonPropertyName("reason")] string Reason);

public sealed record ServerAISearchEvidenceReferenceRequest
{
    [JsonPropertyName("candidateId")]
    public string? CandidateId { get; init; }

    [JsonPropertyName("sourceType")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("sourceId")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("sourceVersionId")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("traceId")]
    public string? TraceId { get; init; }

    [JsonPropertyName("traceVersionId")]
    public string? TraceVersionId { get; init; }

    [JsonPropertyName("exclusionReason")]
    public string? ExclusionReason { get; init; }

    [JsonPropertyName("contentHash")]
    public string? ContentHash { get; init; }

    [JsonPropertyName("rationale")]
    public string? Rationale { get; init; }
}

public sealed record ServerAIGroundTruthCaseCreateRequest
{
    [JsonPropertyName("caseKey")] public string CaseKey { get; init; } = string.Empty;
    [JsonPropertyName("category")] public string Category { get; init; } = string.Empty;
    [JsonPropertyName("scenarioType")] public string ScenarioType { get; init; } = string.Empty;
    [JsonPropertyName("question")] public string Question { get; init; } = string.Empty;
    [JsonPropertyName("expectedOutcome")] public string ExpectedOutcome { get; init; } = "SUFFICIENT";
    [JsonPropertyName("expectedEvidence")] public IReadOnlyList<ServerAISearchEvidenceReferenceRequest> ExpectedEvidence { get; init; } = [];
    [JsonPropertyName("expectedExcluded")] public IReadOnlyList<ServerAISearchEvidenceReferenceRequest> ExpectedExcluded { get; init; } = [];
    [JsonPropertyName("allowedRankMin")] public int AllowedRankMin { get; init; } = 1;
    [JsonPropertyName("allowedRankMax")] public int AllowedRankMax { get; init; } = 20;
    [JsonPropertyName("asOf")] public DateTimeOffset AsOf { get; init; }
    [JsonPropertyName("dataClassification")] public string DataClassification { get; init; } = "ANONYMOUS_FIELD";
    [JsonPropertyName("provenanceNote")] public string ProvenanceNote { get; init; } = string.Empty;
}

public sealed record ServerAISearchEvaluationCaseRequest
{
    [JsonPropertyName("caseKey")]
    public string CaseKey { get; init; } = string.Empty;

    [JsonPropertyName("question")]
    public string Question { get; init; } = string.Empty;

    [JsonPropertyName("expectedOutcome")]
    public string ExpectedOutcome { get; init; } = string.Empty;

    [JsonPropertyName("expectedEvidence")]
    public IReadOnlyList<ServerAISearchEvidenceReferenceRequest> ExpectedEvidence { get; init; } = [];

    [JsonPropertyName("expectedExcluded")]
    public IReadOnlyList<ServerAISearchEvidenceReferenceRequest> ExpectedExcluded { get; init; } = [];

    [JsonPropertyName("limit")]
    public int Limit { get; init; } = 20;
}

public sealed record ServerAISearchEvaluationRequest
{
    [JsonPropertyName("runLabel")]
    public string RunLabel { get; init; } = string.Empty;

    [JsonPropertyName("evaluateAsUserId")]
    public string? EvaluateAsUserId { get; init; }

    [JsonPropertyName("cases")]
    public IReadOnlyList<ServerAISearchEvaluationCaseRequest> Cases { get; init; } = [];

    [JsonPropertyName("datasetVersionId")]
    public string? DatasetVersionId { get; init; }
}

public sealed record ServerAISearchEvaluationCaseResponse
{
    [JsonPropertyName("evaluation_case_id")]
    public string EvaluationCaseId { get; init; } = string.Empty;

    [JsonPropertyName("case_key")]
    public string CaseKey { get; init; } = string.Empty;

    [JsonPropertyName("actual_outcome")]
    public string ActualOutcome { get; init; } = string.Empty;

    [JsonPropertyName("ranking_hash")]
    public string RankingHash { get; init; } = string.Empty;

    [JsonPropertyName("ranking_stable")]
    public bool RankingStable { get; init; }

    [JsonPropertyName("passed")]
    public bool Passed { get; init; }

    [JsonPropertyName("failure_reasons")]
    public IReadOnlyList<string> FailureReasons { get; init; } = [];

    [JsonPropertyName("expected_evidence")]
    public IReadOnlyList<Dictionary<string, object>> ExpectedEvidence { get; init; } = [];

    [JsonPropertyName("actual_evidence")]
    public IReadOnlyList<Dictionary<string, object>> ActualEvidence { get; init; } = [];

    [JsonPropertyName("excluded_evidence")]
    public IReadOnlyList<Dictionary<string, object>> ExcludedEvidence { get; init; } = [];
}

public sealed record ServerAISearchEvaluationResponse
{
    [JsonPropertyName("run_id")]
    public string RunId { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("run_label")]
    public string RunLabel { get; init; } = string.Empty;

    [JsonPropertyName("dataset_version_id")]
    public string? DatasetVersionId { get; init; }

    [JsonPropertyName("candidate_identity_stable")]
    public bool CandidateIdentityStable { get; init; }

    [JsonPropertyName("ranking_stable")]
    public bool RankingStable { get; init; }

    [JsonPropertyName("source_coverage_complete")]
    public bool SourceCoverageComplete { get; init; }

    [JsonPropertyName("provider_start_ready")]
    public bool ProviderStartReady { get; init; }

    [JsonPropertyName("cases")]
    public IReadOnlyList<ServerAISearchEvaluationCaseResponse> Cases { get; init; } = [];
}
