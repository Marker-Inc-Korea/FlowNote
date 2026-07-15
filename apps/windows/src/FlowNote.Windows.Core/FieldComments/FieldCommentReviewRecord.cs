namespace FlowNote.Windows.Core.FieldComments;

public sealed record FieldCommentReviewRecord(
    long Id,
    string CommentId,
    string? DocumentId,
    string DocumentTitle,
    string? DocumentTags,
    int? DocumentVersionNo,
    string CommentType,
    string InputMode,
    string? SignalLevel,
    string RawContent,
    string? NormalizedContent,
    string? AnalysisContent,
    string AuthorName,
    string? ReportedBy,
    string? OperatorName,
    string EntrySource,
    string? DeviceId,
    string? LocationCode,
    string? AssignedTo,
    DateTime? ReviewDueAt,
    string Status,
    int AttachmentCount,
    DateTime CreatedAt,
    DateTime? SyncedAt)
{
    public string StatusLabel => Status switch
    {
        "NEW" => "신규",
        "NEEDS_REVIEW" => "검토필요",
        "ANALYZED" => "분석완료",
        "REVIEWED" => "검토완료",
        "SELECTED" => "보고서선정",
        "EXCLUDED" => "제외",
        "ARCHIVED" => "보관",
        _ => Status
    };
}
