using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerAIFieldReadinessSamplePlan
{
    [JsonPropertyName("datasetVersionId")] public string DatasetVersionId { get; init; } = string.Empty;
    [JsonPropertyName("evaluationRunId")] public string EvaluationRunId { get; init; } = string.Empty;
    [JsonPropertyName("datasetSnapshotHash")] public string DatasetSnapshotHash { get; init; } = string.Empty;
    [JsonPropertyName("samplingPlanReference")] public string SamplingPlanReference { get; init; } = string.Empty;
    [JsonPropertyName("sampleHash")] public string SampleHash { get; init; } = string.Empty;
    [JsonPropertyName("cases")] public IReadOnlyList<ServerAIFieldReadinessSampleCase> Cases { get; init; } = [];
}

public sealed record ServerAIFieldReadinessSampleCase
{
    [JsonPropertyName("caseKey")] public string CaseKey { get; init; } = string.Empty;
    [JsonPropertyName("category")] public string Category { get; init; } = string.Empty;
    [JsonPropertyName("scenarioType")] public string ScenarioType { get; init; } = string.Empty;
    [JsonPropertyName("question")] public string Question { get; init; } = string.Empty;
    [JsonPropertyName("expectedOutcome")] public string ExpectedOutcome { get; init; } = string.Empty;
    [JsonPropertyName("expectedEvidence")] public IReadOnlyList<Dictionary<string, object>> ExpectedEvidence { get; init; } = [];
    [JsonPropertyName("actualEvidence")] public IReadOnlyList<Dictionary<string, object>> ActualEvidence { get; init; } = [];
    [JsonPropertyName("expectedExcluded")] public IReadOnlyList<Dictionary<string, object>> ExpectedExcluded { get; init; } = [];
    [JsonPropertyName("rankingHash")] public string RankingHash { get; init; } = string.Empty;
    [JsonPropertyName("passed")] public bool Passed { get; init; }
}

public sealed record ServerAIFieldReadinessFinding
{
    [JsonPropertyName("caseKey")] public string CaseKey { get; init; } = string.Empty;
    [JsonPropertyName("citationTrace")] public string CitationTrace { get; init; } = "PASS";
    [JsonPropertyName("citationMeaning")] public string CitationMeaning { get; init; } = "PASS";
    [JsonPropertyName("conflictDisclosure")] public string ConflictDisclosure { get; init; } = "NOT_APPLICABLE";
    [JsonPropertyName("permissionBoundary")] public string PermissionBoundary { get; init; } = "PASS";
    [JsonPropertyName("note")] public string Note { get; init; } = string.Empty;
}

public sealed record ServerAIFieldReadinessReviewCreateRequest
{
    [JsonPropertyName("datasetVersionId")] public string DatasetVersionId { get; init; } = string.Empty;
    [JsonPropertyName("evaluationRunId")] public string EvaluationRunId { get; init; } = string.Empty;
    [JsonPropertyName("samplingPlanReference")] public string SamplingPlanReference { get; init; } = string.Empty;
    [JsonPropertyName("reviewRole")] public string ReviewRole { get; init; } = "INDEPENDENT";
    [JsonPropertyName("resolvesReviewIds")] public IReadOnlyList<string> ResolvesReviewIds { get; init; } = [];
    [JsonPropertyName("findings")] public IReadOnlyList<ServerAIFieldReadinessFinding> Findings { get; init; } = [];
}

public sealed record ServerAIFieldReadinessReview
{
    [JsonPropertyName("reviewId")] public string ReviewId { get; init; } = string.Empty;
    [JsonPropertyName("reviewRole")] public string ReviewRole { get; init; } = string.Empty;
    [JsonPropertyName("reviewerId")] public string ReviewerId { get; init; } = string.Empty;
    [JsonPropertyName("sampleHash")] public string SampleHash { get; init; } = string.Empty;
    [JsonPropertyName("findings")] public IReadOnlyList<ServerAIFieldReadinessFinding>? Findings { get; init; }
    [JsonPropertyName("decisionHash")] public string? DecisionHash { get; init; }
    [JsonPropertyName("resolvesReviewIds")] public IReadOnlyList<string> ResolvesReviewIds { get; init; } = [];
}

public sealed record ServerAIFieldReadinessReviewSummary
{
    [JsonPropertyName("status")] public string Status { get; init; } = "NOT_STARTED";
    [JsonPropertyName("evaluation_run_id")] public string? EvaluationRunId { get; init; }
    [JsonPropertyName("dataset_snapshot_hash")] public string? DatasetSnapshotHash { get; init; }
    [JsonPropertyName("independent_reviewer_count")] public int IndependentReviewerCount { get; init; }
    [JsonPropertyName("independent_review_ids")] public IReadOnlyList<string> IndependentReviewIds { get; init; } = [];
    [JsonPropertyName("independent_reviewer_ids")] public IReadOnlyList<string> IndependentReviewerIds { get; init; } = [];
    [JsonPropertyName("sample_hash")] public string? SampleHash { get; init; }
    [JsonPropertyName("sample_case_count")] public int SampleCaseCount { get; init; }
    [JsonPropertyName("disagreement_case_keys")] public IReadOnlyList<string> DisagreementCaseKeys { get; init; } = [];
    [JsonPropertyName("consensus_review_id")] public string? ConsensusReviewId { get; init; }
    [JsonPropertyName("consensus_reviewer_id")] public string? ConsensusReviewerId { get; init; }
    [JsonPropertyName("complete")] public bool Complete { get; init; }
}

public sealed record ServerAIFieldReadinessReviewListResponse
{
    [JsonPropertyName("reviews")] public IReadOnlyList<ServerAIFieldReadinessReview> Reviews { get; init; } = [];
    [JsonPropertyName("summary")] public ServerAIFieldReadinessReviewSummary Summary { get; init; } = new();
}

public sealed record ServerAIFieldReadinessReviewCreateResponse
{
    [JsonPropertyName("review")] public ServerAIFieldReadinessReview Review { get; init; } = new();
    [JsonPropertyName("summary")] public ServerAIFieldReadinessReviewSummary Summary { get; init; } = new();
}
