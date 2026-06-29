namespace FlowNote.Windows.Core.WorkSequences;

public sealed record WorkSequenceBoardRecord(
    long Id,
    string BoardId,
    string Title,
    string? Description,
    string? LineCode,
    DateTime? BoardDate,
    string Status,
    string CreatedBy,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    int ItemCount);
