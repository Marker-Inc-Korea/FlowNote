namespace FlowNote.Windows.Core.WorkSequences;

public sealed record WorkSequenceItemRecord(
    long Id,
    string ItemId,
    string BoardId,
    string Title,
    string? Description,
    string? WorkOrderNo,
    string? DocumentId,
    string Status,
    string? HoldReason,
    int SortOrder,
    string? AssignedTo,
    string CreatedBy,
    DateTime CreatedAt,
    DateTime UpdatedAt);
