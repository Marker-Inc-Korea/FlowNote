using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerReportSourceRequest
{
    [JsonPropertyName("sourceType")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("sourceId")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("sourceVersionId")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("relationType")]
    public string? RelationType { get; init; }
}

public sealed record ServerReportDraftCreateRequest
{
    [JsonPropertyName("reportType")]
    public string ReportType { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("summary")]
    public string? Summary { get; init; }

    [JsonPropertyName("analysisContent")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("conclusion")]
    public string? Conclusion { get; init; }

    [JsonPropertyName("actionPlan")]
    public string? ActionPlan { get; init; }

    [JsonPropertyName("workRecordId")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("structureItemId")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("periodStart")]
    public DateTime? PeriodStart { get; init; }

    [JsonPropertyName("periodEnd")]
    public DateTime? PeriodEnd { get; init; }

    [JsonPropertyName("sources")]
    public IReadOnlyList<ServerReportSourceRequest> Sources { get; init; } = [];
}

public sealed record ServerReportSaveRequest
{
    [JsonPropertyName("draftReportId")]
    public string? DraftReportId { get; init; }

    [JsonPropertyName("reportType")]
    public string? ReportType { get; init; }

    [JsonPropertyName("title")]
    public string? Title { get; init; }

    [JsonPropertyName("summary")]
    public string? Summary { get; init; }

    [JsonPropertyName("analysisContent")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("conclusion")]
    public string? Conclusion { get; init; }

    [JsonPropertyName("actionPlan")]
    public string? ActionPlan { get; init; }

    [JsonPropertyName("workRecordId")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("structureItemId")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("periodStart")]
    public DateTime? PeriodStart { get; init; }

    [JsonPropertyName("periodEnd")]
    public DateTime? PeriodEnd { get; init; }

    [JsonPropertyName("sources")]
    public IReadOnlyList<ServerReportSourceRequest>? Sources { get; init; }

    [JsonPropertyName("saveAsDocument")]
    public bool SaveAsDocument { get; init; }

    [JsonPropertyName("documentTitle")]
    public string? DocumentTitle { get; init; }

    [JsonPropertyName("documentStatus")]
    public string DocumentStatus { get; init; } = "IN_REVIEW";
}

public sealed record ServerReportSourceResponse
{
    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("relation_type")]
    public string? RelationType { get; init; }

    [JsonPropertyName("summary")]
    public string? Summary { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }
}

public sealed record ServerReportDocumentSummary
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("latest_version_id")]
    public string? LatestVersionId { get; init; }

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; init; }
}

public sealed record ServerReportResponse
{
    [JsonPropertyName("report_id")]
    public string ReportId { get; init; } = string.Empty;

    [JsonPropertyName("report_type")]
    public string ReportType { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("summary")]
    public string? Summary { get; init; }

    [JsonPropertyName("analysis_content")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("conclusion")]
    public string? Conclusion { get; init; }

    [JsonPropertyName("action_plan")]
    public string? ActionPlan { get; init; }

    [JsonPropertyName("work_record_id")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("structure_item_id")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("period_start")]
    public DateTime? PeriodStart { get; init; }

    [JsonPropertyName("period_end")]
    public DateTime? PeriodEnd { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("ai_draft_used")]
    public bool AiDraftUsed { get; init; }

    [JsonPropertyName("generated_document_id")]
    public string? GeneratedDocumentId { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("reviewed_by")]
    public string? ReviewedBy { get; init; }

    [JsonPropertyName("approved_by")]
    public string? ApprovedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("reviewed_at")]
    public DateTime? ReviewedAt { get; init; }

    [JsonPropertyName("approved_at")]
    public DateTime? ApprovedAt { get; init; }

    [JsonPropertyName("sources")]
    public IReadOnlyList<ServerReportSourceResponse> Sources { get; init; } = [];

    [JsonPropertyName("generated_document")]
    public ServerReportDocumentSummary? GeneratedDocument { get; init; }
}
