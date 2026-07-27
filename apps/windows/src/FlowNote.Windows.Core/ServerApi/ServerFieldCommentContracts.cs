using System.Text.Json.Serialization;
using FlowNote.Windows.Core.FieldComments;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerFieldCommentCreateRequest
{
    [JsonPropertyName("documentId")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("documentVersionId")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("structureItemId")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("workRecordId")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("commentType")]
    public string CommentType { get; init; } = "issue";

    [JsonPropertyName("inputMode")]
    public string InputMode { get; init; } = "free_text";

    [JsonPropertyName("signalLevel")]
    public string? SignalLevel { get; init; }

    [JsonPropertyName("templateId")]
    public string? TemplateId { get; init; }

    [JsonPropertyName("rawContent")]
    public string RawContent { get; init; } = string.Empty;

    [JsonPropertyName("authorId")]
    public string? AuthorId { get; init; }

    [JsonPropertyName("reportedBy")]
    public string? ReportedBy { get; init; }

    [JsonPropertyName("operatorId")]
    public string? OperatorId { get; init; }

    [JsonPropertyName("entrySource")]
    public string EntrySource { get; init; } = "field_user";

    [JsonPropertyName("deviceId")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("locationCode")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("category")]
    public string? Category { get; init; }

    [JsonPropertyName("priority")]
    public int? Priority { get; init; }

    [JsonPropertyName("idempotencyKey")]
    public string? IdempotencyKey { get; init; }

    public static ServerFieldCommentCreateRequest FromLocal(
        FieldCommentRecord fieldComment,
        string? documentId = null,
        string? documentVersionId = null,
        string? idempotencyKey = null,
        string? authorId = null)
    {
        return new ServerFieldCommentCreateRequest
        {
            DocumentId = Clean(documentId) ?? Clean(fieldComment.DocumentId),
            DocumentVersionId = Clean(documentVersionId),
            CommentType = fieldComment.CommentType,
            InputMode = fieldComment.InputMode,
            SignalLevel = Clean(fieldComment.SignalLevel),
            RawContent = fieldComment.RawContent,
            AuthorId = Clean(authorId),
            ReportedBy = Clean(fieldComment.ReportedBy) ?? Clean(fieldComment.AuthorName),
            EntrySource = fieldComment.EntrySource,
            DeviceId = Clean(fieldComment.DeviceId),
            LocationCode = Clean(fieldComment.LocationCode),
            IdempotencyKey = Clean(idempotencyKey)
        };
    }

    private static string? Clean(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }
}

public sealed record ServerFieldCommentResponse
{
    [JsonPropertyName("comment_id")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("document_id")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("document_version_id")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("structure_item_id")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("work_record_id")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("comment_type")]
    public string CommentType { get; init; } = string.Empty;

    [JsonPropertyName("input_mode")]
    public string InputMode { get; init; } = string.Empty;

    [JsonPropertyName("signal_level")]
    public string? SignalLevel { get; init; }

    [JsonPropertyName("template_id")]
    public string? TemplateId { get; init; }

    [JsonPropertyName("raw_content")]
    public string RawContent { get; init; } = string.Empty;

    [JsonPropertyName("normalized_content")]
    public string? NormalizedContent { get; init; }

    [JsonPropertyName("analysis_content")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("author_id")]
    public string? AuthorId { get; init; }

    [JsonPropertyName("reported_by")]
    public string? ReportedBy { get; init; }

    [JsonPropertyName("operator_id")]
    public string? OperatorId { get; init; }

    [JsonPropertyName("entry_source")]
    public string EntrySource { get; init; } = string.Empty;

    [JsonPropertyName("device_id")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("category")]
    public string? Category { get; init; }

    [JsonPropertyName("priority")]
    public int? Priority { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("source_hash_sha256")]
    public string SourceHashSha256 { get; init; } = string.Empty;

    [JsonPropertyName("reviewed_by")]
    public string? ReviewedBy { get; init; }

    [JsonPropertyName("analyzed_by")]
    public string? AnalyzedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("reviewed_at")]
    public DateTime? ReviewedAt { get; init; }

    [JsonPropertyName("analyzed_at")]
    public DateTime? AnalyzedAt { get; init; }

    [JsonPropertyName("review_revision")]
    public int ReviewRevision { get; init; } = 1;

    [JsonPropertyName("assigned_to")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("review_due_at")]
    public DateTime? ReviewDueAt { get; init; }

    [JsonPropertyName("last_transition_reason")]
    public string? LastTransitionReason { get; init; }

    [JsonPropertyName("conflict_flag")]
    public bool ConflictFlag { get; init; }

    [JsonPropertyName("conflict_basis")]
    public string? ConflictBasis { get; init; }

    [JsonPropertyName("workbench_flags")]
    public IReadOnlyList<string> WorkbenchFlags { get; init; } = [];

    [JsonPropertyName("attachment_count")]
    public int AttachmentCount { get; init; }

    [JsonPropertyName("channel_access")]
    public string ChannelAccess { get; init; } = "NOT_LINKED";
}

public sealed record ServerFieldCommentReviewRequest
{
    [JsonPropertyName("status")]
    public string? Status { get; init; }

    [JsonPropertyName("normalizedContent")]
    public string? NormalizedContent { get; init; }

    [JsonPropertyName("analysisContent")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("reviewedBy")]
    public string? ReviewedBy { get; init; }

    [JsonPropertyName("analyzedBy")]
    public string? AnalyzedBy { get; init; }

    [JsonPropertyName("assignedTo")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("reviewDueAt")]
    public DateTime? ReviewDueAt { get; init; }

    [JsonPropertyName("transitionReason")]
    public string TransitionReason { get; init; } = "WPF 관리자 검토 동기화";

    [JsonPropertyName("conflictFlag")]
    public bool? ConflictFlag { get; init; }

    [JsonPropertyName("conflictBasis")]
    public string? ConflictBasis { get; init; }

    [JsonPropertyName("baseReviewRevision")]
    public int? BaseReviewRevision { get; init; }

    [JsonPropertyName("mutationKey")]
    public string MutationKey { get; init; } = string.Empty;

    public static ServerFieldCommentReviewRequest FromLocal(
        FieldCommentRecord fieldComment,
        string? actorId = null,
        string? mutationKey = null,
        int? baseReviewRevision = null)
    {
        var status = Clean(fieldComment.Status);
        return new ServerFieldCommentReviewRequest
        {
            Status = status,
            NormalizedContent = Clean(fieldComment.NormalizedContent),
            AnalysisContent = Clean(fieldComment.AnalysisContent),
            ReviewedBy = status is "REVIEWED" or "SELECTED" or "EXCLUDED" or "ARCHIVED"
                ? Clean(actorId)
                : null,
            AnalyzedBy = status is "ANALYZED" or "REVIEWED" or "SELECTED"
                ? Clean(actorId)
                : null,
            AssignedTo = Clean(fieldComment.AssignedTo),
            ReviewDueAt = fieldComment.ReviewDueAt,
            ConflictFlag = fieldComment.ConflictFlag,
            ConflictBasis = Clean(fieldComment.ConflictBasis),
            TransitionReason = Clean(fieldComment.LastTransitionReason) ?? "WPF 관리자 검토 동기화",
            BaseReviewRevision = baseReviewRevision ?? fieldComment.ReviewRevision,
            MutationKey = Clean(mutationKey) ?? throw new ArgumentException("Mutation key is required.", nameof(mutationKey))
        };
    }

    private static string? Clean(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }
}

public sealed record ServerFieldCommentBulkReviewItemRequest
{
    [JsonPropertyName("commentId")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("baseReviewRevision")]
    public int BaseReviewRevision { get; init; }

    [JsonPropertyName("mutationKey")]
    public string MutationKey { get; init; } = string.Empty;
}

public sealed record ServerFieldCommentBulkReviewRequest
{
    [JsonPropertyName("items")]
    public IReadOnlyList<ServerFieldCommentBulkReviewItemRequest> Items { get; init; } = [];

    [JsonPropertyName("status")]
    public string? Status { get; init; }

    [JsonPropertyName("normalizedContent")]
    public string? NormalizedContent { get; init; }

    [JsonPropertyName("analysisContent")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("assignedTo")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("reviewDueAt")]
    public DateTime? ReviewDueAt { get; init; }

    [JsonPropertyName("transitionReason")]
    public string? TransitionReason { get; init; }

    [JsonPropertyName("conflictFlag")]
    public bool? ConflictFlag { get; init; }

    [JsonPropertyName("conflictBasis")]
    public string? ConflictBasis { get; init; }
}

public sealed record ServerFieldCommentBulkReviewItemResponse
{
    [JsonPropertyName("comment_id")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("allowed")]
    public bool Allowed { get; init; }

    [JsonPropertyName("success")]
    public bool? Success { get; init; }

    [JsonPropertyName("from_status")]
    public string? FromStatus { get; init; }

    [JsonPropertyName("target_status")]
    public string? TargetStatus { get; init; }

    [JsonPropertyName("failure_code")]
    public string? FailureCode { get; init; }

    [JsonPropertyName("failure_reason")]
    public string? FailureReason { get; init; }

    [JsonPropertyName("review_revision")]
    public int? ReviewRevision { get; init; }

    [JsonPropertyName("receipt")]
    public string? Receipt { get; init; }

    [JsonPropertyName("field_comment")]
    public ServerFieldCommentResponse? FieldComment { get; init; }

    public string ResultLabel => Success switch
    {
        true => "성공",
        false => "실패",
        null when Allowed => "실행 가능",
        _ => "실행 불가"
    };

    public string RecoveryGuidance => FailureCode switch
    {
        "FIELD_COMMENT_STALE_REVIEW_REVISION" => "다른 검토가 먼저 반영됨 · 최신 revision 조회 후 다시 선택",
        "HTTP_403" => "권한이 변경되었거나 부족함 · 역할/채널 권한 확인",
        "IDEMPOTENCY_KEY_REUSED" => "같은 mutation key의 요청 내용이 다름 · 원래 요청으로 결과 복구",
        null or "" => Success is true ? "서버 revision/receipt 반영 완료" : "사전검증 통과",
        _ => "실패 원인을 해소한 뒤 실패 항목만 새 mutation key로 재실행"
    };
}

public sealed record ServerFieldCommentBulkReviewResponse
{
    [JsonPropertyName("requested_count")]
    public int RequestedCount { get; init; }

    [JsonPropertyName("success_count")]
    public int SuccessCount { get; init; }

    [JsonPropertyName("failure_count")]
    public int FailureCount { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<ServerFieldCommentBulkReviewItemResponse> Items { get; init; } = [];
}

public sealed record ServerFieldCommentQualityItemResponse
{
    [JsonPropertyName("issue_type")]
    public string IssueType { get; init; } = string.Empty;

    [JsonPropertyName("comment_id")]
    public string? CommentId { get; init; }

    [JsonPropertyName("report_id")]
    public string? ReportId { get; init; }

    [JsonPropertyName("age_days")]
    public int? AgeDays { get; init; }

    [JsonPropertyName("detail")]
    public string Detail { get; init; } = string.Empty;
}

public sealed record ServerFieldCommentAttachmentFileResponse
{
    [JsonPropertyName("storage_type")]
    public string StorageType { get; init; } = string.Empty;

    [JsonPropertyName("storage_key")]
    public string StorageKey { get; init; } = string.Empty;

    [JsonPropertyName("original_filename")]
    public string OriginalFilename { get; init; } = string.Empty;

    [JsonPropertyName("extension")]
    public string? Extension { get; init; }

    [JsonPropertyName("mime_type")]
    public string? MimeType { get; init; }

    [JsonPropertyName("file_family")]
    public string? FileFamily { get; init; }

    [JsonPropertyName("size_bytes")]
    public long? SizeBytes { get; init; }

    [JsonPropertyName("hash_sha256")]
    public string? HashSha256 { get; init; }
}

public sealed record ServerFieldCommentAttachmentResponse
{
    [JsonPropertyName("attachment_id")]
    public string AttachmentId { get; init; } = string.Empty;

    [JsonPropertyName("comment_id")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("attachment_type")]
    public string AttachmentType { get; init; } = string.Empty;

    [JsonPropertyName("caption")]
    public string? Caption { get; init; }

    [JsonPropertyName("captured_at")]
    public DateTime? CapturedAt { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("file")]
    public ServerFieldCommentAttachmentFileResponse File { get; init; } = new();
}

public sealed record ServerFieldCommentAuditResponse
{
    [JsonPropertyName("history_id")]
    public string HistoryId { get; init; } = string.Empty;

    [JsonPropertyName("event_type")]
    public string EventType { get; init; } = string.Empty;

    [JsonPropertyName("change_reason")]
    public string? ChangeReason { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }
}

public sealed record ServerFieldCommentTraceDocumentResponse
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("generated_version_ids")]
    public IReadOnlyList<string> GeneratedVersionIds { get; init; } = [];
}

public sealed record ServerFieldCommentTraceReportResponse
{
    [JsonPropertyName("report_id")]
    public string ReportId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("generated_document")]
    public ServerFieldCommentTraceDocumentResponse? GeneratedDocument { get; init; }
}

public sealed record ServerFieldCommentTraceResponse
{
    [JsonPropertyName("field_comment")]
    public ServerFieldCommentResponse FieldComment { get; init; } = new();

    [JsonPropertyName("audit")]
    public IReadOnlyList<ServerFieldCommentAuditResponse> Audit { get; init; } = [];

    [JsonPropertyName("reports")]
    public IReadOnlyList<ServerFieldCommentTraceReportResponse> Reports { get; init; } = [];
}
