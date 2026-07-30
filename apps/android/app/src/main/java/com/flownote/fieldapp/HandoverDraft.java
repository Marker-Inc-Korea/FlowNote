package com.flownote.fieldapp;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

public final class HandoverDraft {
    public final String localId;
    public final String channelId;
    public final String title;
    public final String body;
    public final String sourceType;
    public final String sourceId;
    public final String sourceVersionId;
    public final List<String> recipientIds;
    public final String deviceId;
    public final String authorId;
    public final String idempotencyKey;

    public HandoverDraft(
            String localId,
            String channelId,
            String title,
            String body,
            String sourceType,
            String sourceId,
            String sourceVersionId,
            List<String> recipientIds,
            String deviceId,
            String authorId,
            String idempotencyKey
    ) {
        this.localId = FieldCommentDraft.nonEmpty(localId, UUID.randomUUID().toString());
        this.channelId = FieldCommentDraft.trimToNull(channelId);
        this.title = FieldCommentDraft.nonEmpty(title, "");
        this.body = FieldCommentDraft.nonEmpty(body, "");
        this.sourceType = normalizeSourceType(sourceType);
        this.sourceId = FieldCommentDraft.trimToNull(sourceId);
        this.sourceVersionId = FieldCommentDraft.trimToNull(sourceVersionId);
        this.recipientIds = immutableRecipients(recipientIds);
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
        this.authorId = FieldCommentDraft.trimToNull(authorId);
        this.idempotencyKey = FieldCommentDraft.nonEmpty(
                idempotencyKey,
                defaultIdempotencyKey(this.deviceId, this.localId)
        );
    }

    public boolean canQueue() {
        return channelId != null
                && !title.trim().isEmpty()
                && !body.trim().isEmpty()
                && sourceType != null
                && sourceId != null
                && !recipientIds.isEmpty()
                && deviceId != null
                && authorId != null;
    }

    public static String defaultIdempotencyKey(String deviceId, String localId) {
        String sourceDeviceId = FieldCommentDraft.trimToNull(deviceId);
        String sourceLocalId = FieldCommentDraft.nonEmpty(localId, UUID.randomUUID().toString());
        return "android:"
                + (sourceDeviceId == null ? "unknown-device" : sourceDeviceId)
                + ":handover:"
                + sourceLocalId;
    }

    private static String normalizeSourceType(String value) {
        String cleaned = FieldCommentDraft.trimToNull(value);
        if (cleaned == null) {
            return null;
        }
        String normalized = cleaned.toUpperCase(Locale.ROOT);
        if ("WORK_SEQUENCE_ITEM".equals(normalized)
                || "DOCUMENT".equals(normalized)
                || "FIELD_COMMENT".equals(normalized)
                || "WORK_RECORD".equals(normalized)) {
            return normalized;
        }
        return null;
    }

    private static List<String> immutableRecipients(List<String> values) {
        if (values == null) {
            return Collections.emptyList();
        }
        ArrayList<String> result = new ArrayList<>();
        for (String value : values) {
            String cleaned = FieldCommentDraft.trimToNull(value);
            if (cleaned != null && !result.contains(cleaned)) {
                result.add(cleaned);
            }
        }
        return Collections.unmodifiableList(result);
    }
}
