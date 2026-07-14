namespace FlowNote.Windows.Core.Notifications;

public sealed record ServerNotificationCursorRecord(
    string ServerScope,
    string UserId,
    long LastSuccessCursor,
    long ObservedServerCursor,
    string Status,
    bool InitialSyncCompleted,
    DateTimeOffset? UpdatedAt,
    string? ResetConfirmedBy,
    DateTimeOffset? ResetConfirmedAt)
{
    public bool Exists => UpdatedAt.HasValue;

    public bool ResetRequired => Status == ServerNotificationCursorService.ResetRequiredStatus;
}
