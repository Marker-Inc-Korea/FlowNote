namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncResult(
    bool Success,
    string Message,
    int Attempted = 0,
    int Synced = 0,
    int Failed = 0);
