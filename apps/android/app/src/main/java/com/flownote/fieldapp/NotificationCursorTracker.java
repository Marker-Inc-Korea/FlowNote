package com.flownote.fieldapp;

/**
 * Pure cursor state used by the foreground polling service. Keeping the page
 * transition outside Android APIs makes the exact-full-page recovery boundary
 * regression-testable on the JVM.
 */
final class NotificationCursorTracker {
    private long cursor;
    private boolean caughtUp;
    private long pageStartCursor;
    private int advancedCount;
    private int staleCount;

    NotificationCursorTracker(long cursor, boolean caughtUp) {
        this.cursor = Math.max(0L, cursor);
        this.caughtUp = caughtUp;
        beginPage();
    }

    void beginPage() {
        pageStartCursor = cursor;
        advancedCount = 0;
        staleCount = 0;
    }

    boolean accept(long itemCursor) {
        if (itemCursor <= cursor) {
            staleCount++;
            return false;
        }
        cursor = itemCursor;
        advancedCount++;
        return caughtUp;
    }

    boolean finishPage(int receivedCount, int pageLimit) {
        if (receivedCount < pageLimit) {
            caughtUp = true;
            return false;
        }
        if (cursor <= pageStartCursor) {
            throw new IllegalStateException("가득 찬 알림 page에서 cursor가 전진하지 않았습니다.");
        }
        return true;
    }

    long cursor() {
        return cursor;
    }

    long pageStartCursor() {
        return pageStartCursor;
    }

    boolean caughtUp() {
        return caughtUp;
    }

    int advancedCount() {
        return advancedCount;
    }

    int staleCount() {
        return staleCount;
    }
}
