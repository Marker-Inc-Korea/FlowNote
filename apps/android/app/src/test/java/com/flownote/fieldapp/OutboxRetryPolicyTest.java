package com.flownote.fieldapp;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class OutboxRetryPolicyTest {
    @Test
    public void pendingItemsRetryImmediatelyBeforeFirstAttempt() {
        assertTrue(OutboxRetryPolicy.shouldRetry("PENDING", 0, 1000L, 1000L));
    }

    @Test
    public void failedItemsUseBoundedBackoff() {
        long now = 60_000L;
        assertFalse(OutboxRetryPolicy.shouldRetry("FAILED", 1, now, now - 10_000L));
        assertTrue(OutboxRetryPolicy.shouldRetry("FAILED", 1, now, now - 15_000L));
        assertEquals(15_000L, OutboxRetryPolicy.delayMillis(1));
        assertEquals(30_000L, OutboxRetryPolicy.delayMillis(2));
        assertEquals(60_000L, OutboxRetryPolicy.delayMillis(3));
        assertEquals(15L * 60L * 1000L, OutboxRetryPolicy.delayMillis(7));
        assertEquals(15L * 60L * 1000L, OutboxRetryPolicy.delayMillis(20));
    }

    @Test
    public void syncedAndExhaustedItemsDoNotRetryAutomatically() {
        assertFalse(OutboxRetryPolicy.shouldRetry("SYNCED", 0, 1000L, 0L));
        assertFalse(OutboxRetryPolicy.shouldRetry("FAILED", 12, 1000L, 0L));
        assertTrue(OutboxRetryPolicy.canRetryManually("FAILED"));
        assertFalse(OutboxRetryPolicy.canRetryManually("PENDING"));
        assertFalse(OutboxRetryPolicy.canRetryManually("SYNCED"));
    }
}
