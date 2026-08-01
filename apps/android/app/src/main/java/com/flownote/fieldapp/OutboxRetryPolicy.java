package com.flownote.fieldapp;

public final class OutboxRetryPolicy {
    public static final int MAX_AUTOMATIC_ATTEMPTS = 12;

    private OutboxRetryPolicy() {
    }

    public static boolean shouldRetry(String status, int attemptCount, long nowMillis, long lastAttemptMillis) {
        if (!"PENDING".equals(status) && !"FAILED".equals(status)) {
            return false;
        }
        if (attemptCount >= MAX_AUTOMATIC_ATTEMPTS) {
            return false;
        }
        return nowMillis - lastAttemptMillis >= delayMillis(attemptCount);
    }

    public static boolean canRetryManually(String status) {
        return "FAILED".equals(status);
    }

    public static long delayMillis(int attemptCount) {
        if (attemptCount <= 0) {
            return 0L;
        }
        long seconds = 15L;
        for (int i = 1; i < attemptCount; i++) {
            seconds = Math.min(seconds * 2L, 15L * 60L);
        }
        return seconds * 1000L;
    }
}
