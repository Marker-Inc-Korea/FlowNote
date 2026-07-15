namespace FlowNote.Windows.Core.FieldComments;

public sealed record FieldCommentReviewFilter(
    string? Status = null,
    string? DocumentText = null,
    string? AuthorText = null,
    string? TagText = null,
    string? AssignedTo = null,
    string? LineText = null,
    string? EquipmentText = null,
    string? ProcessText = null,
    string? ErrorTypeText = null,
    int? OlderThanDays = null,
    bool? HasAttachments = null,
    bool? ReportLinked = null,
    DateTime? CreatedFrom = null,
    DateTime? CreatedTo = null,
    int Limit = 300);
