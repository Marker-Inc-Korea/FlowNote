package com.flownote.fieldapp;

public final class OutboxQueueStatus {
    public final int pendingCount;
    public final int failedCount;
    public final int readyCount;
    public final int blockedCount;
    public final int partialSuccessCount;
    public final long nextRetryAtMillis;

    public OutboxQueueStatus(
            int pendingCount,
            int failedCount,
            int readyCount,
            int blockedCount,
            int partialSuccessCount,
            long nextRetryAtMillis
    ) {
        this.pendingCount = pendingCount;
        this.failedCount = failedCount;
        this.readyCount = readyCount;
        this.blockedCount = blockedCount;
        this.partialSuccessCount = partialSuccessCount;
        this.nextRetryAtMillis = nextRetryAtMillis;
    }
}
