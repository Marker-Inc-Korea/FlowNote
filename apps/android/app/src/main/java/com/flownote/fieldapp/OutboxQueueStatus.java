package com.flownote.fieldapp;

public final class OutboxQueueStatus {
    public final int pendingCount;
    public final int failedCount;
    public final int readyCount;
    public final int blockedCount;
    public final long nextRetryAtMillis;

    public OutboxQueueStatus(
            int pendingCount,
            int failedCount,
            int readyCount,
            int blockedCount,
            long nextRetryAtMillis
    ) {
        this.pendingCount = pendingCount;
        this.failedCount = failedCount;
        this.readyCount = readyCount;
        this.blockedCount = blockedCount;
        this.nextRetryAtMillis = nextRetryAtMillis;
    }
}
