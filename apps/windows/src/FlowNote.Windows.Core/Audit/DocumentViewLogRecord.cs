namespace FlowNote.Windows.Core.Audit;

public sealed record DocumentViewLogRecord(
    long Id,
    string DocumentId,
    int VersionNo,
    string UserName,
    DateTime ViewStartedAt,
    DateTime? ClosedAt,
    string? CloseReason);
