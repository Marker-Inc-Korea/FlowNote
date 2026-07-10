namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncQueueSummary(
    int Pending,
    int Failed,
    int Synced,
    int Held)
{
    public int Total => Pending + Failed + Synced;
}
