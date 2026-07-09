package com.flownote.fieldapp;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class ApiContractTest {
    @Test
    public void pathsMatchFastApiContracts() {
        assertEquals("/api/v1/auth/login", ApiPaths.LOGIN);
        assertEquals("/api/v1/documents/published", ApiPaths.PUBLISHED_DOCUMENTS);
        assertEquals("/api/v1/documents/doc_123", ApiPaths.document("doc_123"));
        assertEquals(
                "/api/v1/field-comments/comment_123/attachments",
                ApiPaths.fieldCommentAttachments("comment_123")
        );
        assertEquals("/api/v1/notifications/chmsg_123/read", ApiPaths.notificationRead("chmsg_123"));
        assertEquals(
                "/api/v1/handovers/handover_1/receipts/receipt_1",
                ApiPaths.handoverReceipt("handover_1", "receipt_1")
        );
    }

    @Test
    public void jsonEscaperKeepsDeviceIdAndKoreanTextValid() {
        String escaped = JsonEscaper.quote("단말 \"A\"\\라인\n");
        assertEquals("\"단말 \\\"A\\\"\\\\라인\\n\"", escaped);
    }

    @Test
    public void fieldCommentDraftRequiresTargetAndContent() {
        FieldCommentDraft draft = new FieldCommentDraft(
                "local-1",
                "doc_1",
                "ver_1",
                null,
                "현장 온도 상승",
                "signal",
                "yellow",
                "tablet-line-a-01",
                "user-worker",
                "content://photo/1",
                null
        );

        assertTrue(draft.canSend());
        assertEquals("signal", draft.normalizedInputMode());
        assertEquals("android:tablet-line-a-01:local-1", draft.idempotencyKey);
    }
}
