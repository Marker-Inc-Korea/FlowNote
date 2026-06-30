namespace FlowNote.Windows.Core.FieldComments;

public sealed record FieldCommentRecord(
    long Id,
    string CommentId,
    string? DocumentId,
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
    string Status,
    DateTime CreatedAt,
    DateTime? SyncedAt);
