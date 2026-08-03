package com.flownote.fieldapp;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public final class HandoverWorkflowDraftTest {
    @Test
    public void followUpKeepsDocumentSourceAndStableIdempotencyKey() {
        HandoverFollowUpDraft first = followUp("DOCUMENT", "document-1", "version-1");
        HandoverFollowUpDraft replay = followUp("DOCUMENT", "document-1", "version-1");

        assertTrue(first.canQueue());
        assertEquals(first.idempotencyKey, replay.idempotencyKey);
        FieldCommentDraft comment = first.toFieldCommentDraft();
        assertEquals("document-1", comment.documentId);
        assertEquals("version-1", comment.documentVersionId);
        assertEquals("handover-1", comment.workRecordId);
        assertTrue(comment.rawContent.contains("원천 인수인계: handover-1"));
        assertTrue(comment.rawContent.contains("원천: DOCUMENT:document-1"));
    }

    @Test
    public void followUpKeepsWorkRecordSourceWithoutDocumentTarget() {
        FieldCommentDraft comment = followUp("WORK_RECORD", "work-record-1", null)
                .toFieldCommentDraft();

        assertNull(comment.documentId);
        assertEquals("work-record-1", comment.workRecordId);
    }

    @Test
    public void receiptAcceptsOnlyCompletionStatuses() {
        HandoverReceiptDraft acknowledged = new HandoverReceiptDraft(
                "local-1", "handover-1", "receipt-1", "ACKNOWLEDGED",
                null, "run-1", null
        );
        HandoverReceiptDraft held = new HandoverReceiptDraft(
                "local-2", "handover-1", "receipt-1", "FOLLOW_UP_REQUIRED",
                "추가 확인", "run-1", null
        );
        HandoverReceiptDraft unread = new HandoverReceiptDraft(
                "local-3", "handover-1", "receipt-1", "UNREAD",
                null, "run-1", null
        );

        assertTrue(acknowledged.canQueue());
        assertTrue(held.canQueue());
        assertFalse(unread.canQueue());
    }

    private static HandoverFollowUpDraft followUp(
            String sourceType,
            String sourceId,
            String sourceVersionId
    ) {
        String content = "베어링 온도를 다시 확인합니다.";
        return new HandoverFollowUpDraft(
                "local-1",
                "handover-1",
                "channel-1",
                "교대 인수인계",
                sourceType,
                sourceId,
                sourceVersionId,
                content,
                "device-1",
                "worker-1",
                HandoverFollowUpDraft.defaultIdempotencyKey(
                        "handover-1", "worker-1", content
                )
        );
    }
}
