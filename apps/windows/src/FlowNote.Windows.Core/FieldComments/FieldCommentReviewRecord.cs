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
    DateTime? SyncedAt,
    int ReviewRevision = 1,
    bool ConflictFlag = false,
    string? ConflictBasis = null)
{
    public string StatusLabel => Status switch
    {
        "NEW" => "신규",
        "ASSIGNED" => "담당배정",
        "NEEDS_REVIEW" => "검토필요",
        "ANALYZED" => "분석완료",
        "REVIEWED" => "검토완료",
        "SELECTED" => "보고서선정",
        "EXCLUDED" => "제외",
        "ARCHIVED" => "보관",
        _ => Status
    };

    public string PriorityLabel
    {
        get
        {
            var flags = new List<string>();
            if (ReviewDueAt is not null && ReviewDueAt.Value < DateTime.UtcNow && Status is not ("SELECTED" or "EXCLUDED" or "ARCHIVED"))
            {
                flags.Add("기한초과");
            }
            if (ConflictFlag)
            {
                flags.Insert(0, "상충검토");
            }
            if (string.IsNullOrWhiteSpace(AssignedTo))
            {
                flags.Add("담당없음");
            }
            if (DocumentVersionNo is null || string.IsNullOrWhiteSpace(AuthorName) || string.IsNullOrWhiteSpace(AnalysisContent))
            {
                flags.Add("근거누락");
            }
            return flags.Count == 0 ? "일반" : string.Join("·", flags);
        }
    }
}
