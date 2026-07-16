namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncQueueSummary(
    int Pending,
    int Failed,
    int Synced,
    int Held,
    int Discarded = 0)
{
    public int Total => Pending + Failed + Synced + Discarded;
}
