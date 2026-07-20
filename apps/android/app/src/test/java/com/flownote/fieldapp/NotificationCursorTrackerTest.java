package com.flownote.fieldapp;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertThrows;
import static org.junit.Assert.assertTrue;

public final class NotificationCursorTrackerTest {
    @Test
    public void exactFullPageContinuesUntilShortPageCompletesCatchUp() {
        NotificationCursorTracker tracker = new NotificationCursorTracker(0L, false);

        for (long cursor = 1L; cursor <= 100L; cursor++) {
            assertFalse(tracker.accept(cursor));
        }
        assertTrue(tracker.finishPage(100, 100));
        assertEquals(100L, tracker.cursor());
        assertFalse(tracker.caughtUp());

        tracker.beginPage();
        assertFalse(tracker.accept(101L));
        assertFalse(tracker.accept(102L));
        assertFalse(tracker.finishPage(2, 100));
        assertEquals(102L, tracker.cursor());
        assertTrue(tracker.caughtUp());
    }

    @Test
    public void caughtUpPageDisplaysOnlyNewCursorsAndCountsDuplicates() {
        NotificationCursorTracker tracker = new NotificationCursorTracker(20L, true);

        assertFalse(tracker.accept(20L));
        assertFalse(tracker.accept(19L));
        assertTrue(tracker.accept(21L));
        assertTrue(tracker.accept(22L));

        assertEquals(2, tracker.staleCount());
        assertEquals(2, tracker.advancedCount());
        assertEquals(22L, tracker.cursor());
    }

    @Test
    public void fullPageWithoutCursorProgressFailsInsteadOfLoopingForever() {
        NotificationCursorTracker tracker = new NotificationCursorTracker(50L, true);
        for (int index = 0; index < 100; index++) {
            assertFalse(tracker.accept(50L));
        }

        assertThrows(IllegalStateException.class, () -> tracker.finishPage(100, 100));
    }
}
