namespace FlowNote.Windows.Core.Sync;

public sealed record ServerSyncFailureMetric(string Reason, int Count);

public sealed record ServerSyncOperationalMetrics(
    int QueueDepth,
    TimeSpan? OldestWaitingTime,
    int SyncedLastHour,
    IReadOnlyList<ServerSyncFailureMetric> FailureReasons)
{
    public string OldestWaitingText => OldestWaitingTime is null
        ? "없음"
        : OldestWaitingTime.Value.TotalDays >= 1
            ? $"{OldestWaitingTime.Value.TotalDays:F1}일"
            : OldestWaitingTime.Value.TotalHours >= 1
                ? $"{OldestWaitingTime.Value.TotalHours:F1}시간"
                : $"{Math.Max(0, OldestWaitingTime.Value.TotalMinutes):F0}분";

    public string FailureDistributionText => FailureReasons.Count == 0
        ? "없음"
        : string.Join(", ", FailureReasons.Select(item => $"{item.Reason} {item.Count}건"));
}
