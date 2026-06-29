namespace FlowNote.Windows.Core.WorkSequences;

public sealed record WorkSequenceHistoryRecord(
    long Id,
    string ChangeId,
    string BoardId,
    string? ItemId,
    string ChangeType,
    string ActorName,
    string? BeforeValue,
    string? AfterValue,
    string? ChangeReason,
    DateTime CreatedAt);
