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
}

public sealed record ServerAISearchEvaluationCaseResponse
{
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
}

public sealed record ServerAISearchEvaluationResponse
{
    [JsonPropertyName("run_id")]
    public string RunId { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

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
