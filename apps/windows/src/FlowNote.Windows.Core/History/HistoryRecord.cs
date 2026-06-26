namespace FlowNote.Windows.Core.History;

public sealed record HistoryRecord(
    long Id,
    string HistoryId,
    string EventType,
    string ActorName,
    string TargetType,
    string? TargetId,
    string? TargetTitle,
    string Message,
    DateTime CreatedAt);
