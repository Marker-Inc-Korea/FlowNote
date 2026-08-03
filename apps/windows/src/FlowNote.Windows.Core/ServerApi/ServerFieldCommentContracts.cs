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

    [JsonPropertyName("assigned_role")]
    public string? AssignedRole { get; init; }

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

    [JsonPropertyName("channel_labels")]
    public IReadOnlyList<string> ChannelLabels { get; init; } = [];
}

public sealed record ServerFieldCommentListFilter
{
    public string? AssignedRole { get; init; }
    public string? SignalLevel { get; init; }
    public string? Channel { get; init; }
    public string? DocumentVersionId { get; init; }
    public DateTime? ReviewDueFrom { get; init; }
    public DateTime? ReviewDueTo { get; init; }
    public int Limit { get; init; } = 500;
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

    public string RetryTargetLabel => Success switch
    {
        true => "재전송 안 함",
        false when FailureCode == "FIELD_COMMENT_STALE_REVIEW_REVISION" => "재조회 후 다시 선택",
        false when FailureCode == "HTTP_403" => "관리자 확인 후 다시 선택",
        false => "실패 항목만 다시 선택",
        null when Allowed => "실행 대상",
        _ => "실행하지 않음"
    };

    public string RecoveryGuidance => FailureCode switch
    {
        "FIELD_COMMENT_STALE_REVIEW_REVISION" => WorkflowFailureGuidance.Format(
            "최신 revision 충돌로 이 항목을 저장하지 못했습니다.",
            "원천 코멘트와 이미 성공한 항목",
            "현재 사용자와 검토 담당자",
            "목록을 다시 조회해 원문을 비교한 뒤 이 실패 항목만 다시 선택하세요."),
        "HTTP_403" => WorkflowFailureGuidance.Format(
            "현재 계정의 처리 권한이 부족해 이 항목을 저장하지 못했습니다.",
            "원천 코멘트와 이미 성공한 항목",
            "현장 관리자",
            "로그인 ID와 필요한 역할·채널 권한을 관리자에게 전달하세요."),
        "IDEMPOTENCY_KEY_REUSED" => WorkflowFailureGuidance.Format(
            "같은 요청 식별값에 다른 내용이 사용되어 결과를 적용하지 못했습니다.",
            "이전 처리 결과와 원천 코멘트",
            "현재 사용자",
            "일괄 결과를 다시 확인하고 실패 항목만 새 요청으로 선택하세요."),
        null or "" => Success is true ? "서버 변경 번호와 처리 결과 보존 완료" : "실행 전 확인 완료",
        _ => WorkflowFailureGuidance.Format(
            "이 항목을 저장하지 못했습니다.",
            "원천 코멘트와 이미 성공한 항목",
            "현재 사용자 또는 오류 코드 담당자",
            "원인을 해소한 뒤 이 실패 항목만 다시 선택하세요.")
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

public sealed record ServerFieldCommentReviewActionResponse
{
    [JsonPropertyName("code")]
    public string Code { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("count")]
    public int Count { get; init; }

    [JsonPropertyName("owner")]
    public string Owner { get; init; } = string.Empty;

    [JsonPropertyName("next_action")]
    public string NextAction { get; init; } = string.Empty;

    [JsonPropertyName("workbench_filter")]
    public string WorkbenchFilter { get; init; } = string.Empty;
}

public sealed record ServerFieldCommentReviewDashboardResponse
{
    [JsonPropertyName("total_count")]
    public int TotalCount { get; init; }

    [JsonPropertyName("counts_by_status")]
    public IReadOnlyDictionary<string, int> CountsByStatus { get; init; } = new Dictionary<string, int>();

    [JsonPropertyName("unreviewed_count")]
    public int UnreviewedCount { get; init; }

    [JsonPropertyName("conflict_count")]
    public int ConflictCount { get; init; }

    [JsonPropertyName("safety_quality_risk_count")]
    public int SafetyQualityRiskCount { get; init; }

    [JsonPropertyName("report_unlinked_count")]
    public int ReportUnlinkedCount { get; init; }

    [JsonPropertyName("unassigned_count")]
    public int UnassignedCount { get; init; }

    [JsonPropertyName("overdue_count")]
    public int OverdueCount { get; init; }

    [JsonPropertyName("actions")]
    public IReadOnlyList<ServerFieldCommentReviewActionResponse> Actions { get; init; } = [];
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

    [JsonPropertyName("latest_version_id")]
    public string? LatestVersionId { get; init; }

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; init; }

    [JsonPropertyName("generated_version_ids")]
    public IReadOnlyList<string> GeneratedVersionIds { get; init; } = [];

    [JsonPropertyName("observed_version_id")]
    public string? ObservedVersionId { get; init; }
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

    [JsonPropertyName("source_revision")]
    public int? SourceRevision { get; init; }

    [JsonPropertyName("source_hash_sha256")]
    public string SourceHashSha256 { get; init; } = string.Empty;

    [JsonPropertyName("trace_id")]
    public string TraceId { get; init; } = string.Empty;

    [JsonPropertyName("generated_document")]
    public ServerFieldCommentTraceDocumentResponse? GeneratedDocument { get; init; }
}

public sealed record ServerFieldCommentTraceWorkSequenceResponse
{
    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("board_title")]
    public string BoardTitle { get; init; } = string.Empty;

    [JsonPropertyName("item_id")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("item_title")]
    public string ItemTitle { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("assigned_to")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("document_id")]
    public string? DocumentId { get; init; }
}

public sealed record ServerFieldCommentTraceResponse
{
    [JsonPropertyName("field_comment")]
    public ServerFieldCommentResponse FieldComment { get; init; } = new();

    [JsonPropertyName("source_document")]
    public ServerFieldCommentTraceDocumentResponse? SourceDocument { get; init; }

    [JsonPropertyName("attachments")]
    public IReadOnlyList<ServerFieldCommentAttachmentResponse> Attachments { get; init; } = [];

    [JsonPropertyName("audit")]
    public IReadOnlyList<ServerFieldCommentAuditResponse> Audit { get; init; } = [];

    [JsonPropertyName("work_sequences")]
    public IReadOnlyList<ServerFieldCommentTraceWorkSequenceResponse> WorkSequences { get; init; } = [];

    [JsonPropertyName("reports")]
    public IReadOnlyList<ServerFieldCommentTraceReportResponse> Reports { get; init; } = [];
}
