namespace FlowNote.Windows.Core.Notifications;

public sealed record ServerNotificationBatchResult(
    ServerNotificationCursorRecord State,
    int ReceivedCount,
    int ProcessedCount,
    int DuplicateCount,
    bool ResetRequired);
