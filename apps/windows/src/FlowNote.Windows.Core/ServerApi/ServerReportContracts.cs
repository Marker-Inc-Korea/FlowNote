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

    [JsonPropertyName("sourceRevision")]
    public int? SourceRevision { get; init; }

    [JsonPropertyName("sourceHashSha256")]
    public string? SourceHashSha256 { get; init; }
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
    [JsonPropertyName("idempotencyKey")]
    public string? IdempotencyKey { get; init; }

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

    [JsonPropertyName("baseReportRevision")]
    public int? BaseReportRevision { get; init; }

    [JsonPropertyName("mutationKey")]
    public string? MutationKey { get; init; }

    [JsonPropertyName("contentHashSha256")]
    public string? ContentHashSha256 { get; init; }

    [JsonPropertyName("sourceSetHashSha256")]
    public string? SourceSetHashSha256 { get; init; }

    [JsonPropertyName("reportStatus")]
    public string ReportStatus { get; init; } = "APPROVED";

    [JsonPropertyName("reportFamilyId")]
    public string? ReportFamilyId { get; init; }

    [JsonPropertyName("replacesReportId")]
    public string? ReplacesReportId { get; init; }

    [JsonPropertyName("replacesReportRevision")]
    public int? ReplacesReportRevision { get; init; }
}

public sealed record ServerReportCorrectionCreateRequest
{
    [JsonPropertyName("correctionReason")]
    public string CorrectionReason { get; init; } = string.Empty;

    [JsonPropertyName("baseReportRevision")]
    public int BaseReportRevision { get; init; }

    [JsonPropertyName("mutationKey")]
    public string MutationKey { get; init; } = string.Empty;

    [JsonPropertyName("sourceSetHashSha256")]
    public string? SourceSetHashSha256 { get; init; }

    [JsonPropertyName("sources")]
    public IReadOnlyList<ServerReportSourceRequest>? Sources { get; init; }
}

public sealed record ServerReportSourceResponse
{
    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("source_revision")]
    public int? SourceRevision { get; init; }

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = string.Empty;

    [JsonPropertyName("source_hash_sha256")]
    public string SourceHashSha256 { get; init; } = string.Empty;

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

    [JsonPropertyName("report_revision")]
    public int ReportRevision { get; init; }

    [JsonPropertyName("content_hash_sha256")]
    public string? ContentHashSha256 { get; init; }

    [JsonPropertyName("source_set_hash_sha256")]
    public string? SourceSetHashSha256 { get; init; }

    [JsonPropertyName("report_family_id")]
    public string ReportFamilyId { get; init; } = string.Empty;

    [JsonPropertyName("replaces_report_id")]
    public string? ReplacesReportId { get; init; }

    [JsonPropertyName("replaces_report_revision")]
    public int? ReplacesReportRevision { get; init; }

    [JsonPropertyName("correction_reason")]
    public string? CorrectionReason { get; init; }

    [JsonPropertyName("superseded_by_report_id")]
    public string? SupersededByReportId { get; init; }

    [JsonPropertyName("superseded_at")]
    public DateTime? SupersededAt { get; init; }

    [JsonPropertyName("current_effective_report_id")]
    public string? CurrentEffectiveReportId { get; init; }

    [JsonPropertyName("is_current_effective")]
    public bool IsCurrentEffective { get; init; }

    [JsonPropertyName("requires_re_review")]
    public bool RequiresReReview { get; init; }

    [JsonPropertyName("replacement_state")]
    public string ReplacementState { get; init; } = "NONE";
}

public sealed record ServerReportLineageItemResponse
{
    [JsonPropertyName("report_id")]
    public string ReportId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("report_revision")]
    public int ReportRevision { get; init; }

    [JsonPropertyName("replaces_report_id")]
    public string? ReplacesReportId { get; init; }

    [JsonPropertyName("correction_reason")]
    public string? CorrectionReason { get; init; }

    [JsonPropertyName("generated_document_id")]
    public string? GeneratedDocumentId { get; init; }

    [JsonPropertyName("approved_at")]
    public DateTime? ApprovedAt { get; init; }

    [JsonPropertyName("superseded_at")]
    public DateTime? SupersededAt { get; init; }

    [JsonPropertyName("is_current_effective")]
    public bool IsCurrentEffective { get; init; }
}
