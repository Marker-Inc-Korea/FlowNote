package com.flownote.fieldapp;

import java.util.Locale;
import java.util.UUID;

public final class HandoverReceiptDraft {
    public final String localId;
    public final String handoverId;
    public final String receiptId;
    public final String receiptStatus;
    public final String note;
    public final String deliveryRunId;
    public final String idempotencyKey;

    public HandoverReceiptDraft(
            String localId,
            String handoverId,
            String receiptId,
            String receiptStatus,
            String note,
            String deliveryRunId,
            String idempotencyKey
    ) {
        this.localId = FieldCommentDraft.nonEmpty(localId, UUID.randomUUID().toString());
        this.handoverId = FieldCommentDraft.trimToNull(handoverId);
        this.receiptId = FieldCommentDraft.trimToNull(receiptId);
        this.receiptStatus = normalizeStatus(receiptStatus);
        this.note = FieldCommentDraft.trimToNull(note);
        this.deliveryRunId = FieldCommentDraft.trimToNull(deliveryRunId);
        this.idempotencyKey = FieldCommentDraft.nonEmpty(
                idempotencyKey,
                "android:handover-receipt:" + this.localId
        );
    }

    public boolean canQueue() {
        return handoverId != null && receiptId != null && receiptStatus != null;
    }

    private static String normalizeStatus(String value) {
        String cleaned = FieldCommentDraft.trimToNull(value);
        if (cleaned == null) {
            return null;
        }
        String normalized = cleaned.toUpperCase(Locale.ROOT);
        if ("ACKNOWLEDGED".equals(normalized) || "FOLLOW_UP_REQUIRED".equals(normalized)) {
            return normalized;
        }
        return null;
    }
}
