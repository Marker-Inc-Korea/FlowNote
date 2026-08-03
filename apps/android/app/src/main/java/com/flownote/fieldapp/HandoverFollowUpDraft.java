package com.flownote.fieldapp;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.UUID;

public final class HandoverFollowUpDraft {
    public final String localId;
    public final String handoverId;
    public final String channelId;
    public final String handoverTitle;
    public final String sourceType;
    public final String sourceId;
    public final String sourceVersionId;
    public final String rawContent;
    public final String deviceId;
    public final String authorId;
    public final String idempotencyKey;

    public HandoverFollowUpDraft(
            String localId,
            String handoverId,
            String channelId,
            String handoverTitle,
            String sourceType,
            String sourceId,
            String sourceVersionId,
            String rawContent,
            String deviceId,
            String authorId,
            String idempotencyKey
    ) {
        this.localId = FieldCommentDraft.nonEmpty(localId, UUID.randomUUID().toString());
        this.handoverId = FieldCommentDraft.trimToNull(handoverId);
        this.channelId = FieldCommentDraft.trimToNull(channelId);
        this.handoverTitle = FieldCommentDraft.nonEmpty(handoverTitle, "인수인계");
        this.sourceType = normalizeSourceType(sourceType);
        this.sourceId = FieldCommentDraft.trimToNull(sourceId);
        this.sourceVersionId = FieldCommentDraft.trimToNull(sourceVersionId);
        this.rawContent = FieldCommentDraft.nonEmpty(rawContent, "");
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
        this.authorId = FieldCommentDraft.trimToNull(authorId);
        this.idempotencyKey = FieldCommentDraft.nonEmpty(
                idempotencyKey,
                defaultIdempotencyKey(this.handoverId, this.authorId, this.rawContent)
        );
    }

    public boolean canQueue() {
        return handoverId != null
                && channelId != null
                && sourceType != null
                && sourceId != null
                && !rawContent.trim().isEmpty()
                && deviceId != null
                && authorId != null;
    }

    FieldCommentDraft toFieldCommentDraft() {
        String documentId = "DOCUMENT".equals(sourceType) ? sourceId : null;
        String documentVersionId = "DOCUMENT".equals(sourceType) ? sourceVersionId : null;
        String workRecordId = "WORK_RECORD".equals(sourceType) ? sourceId : handoverId;
        String linkedContent = "원천 인수인계: " + handoverId
                + "\n원천: " + sourceType + ":" + sourceId
                + "\n" + rawContent.trim();
        return new FieldCommentDraft(
                localId,
                documentId,
                documentVersionId,
                workRecordId,
                linkedContent,
                "free_text",
                null,
                deviceId,
                authorId,
                null,
                idempotencyKey
        );
    }

    public static String defaultIdempotencyKey(
            String handoverId,
            String authorId,
            String rawContent
    ) {
        String source = FieldCommentDraft.nonEmpty(handoverId, "unknown-handover")
                + "\n" + FieldCommentDraft.nonEmpty(authorId, "unknown-user")
                + "\n" + FieldCommentDraft.nonEmpty(rawContent, "").trim();
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(source.getBytes(StandardCharsets.UTF_8));
            return "handover-follow-up:" + FlowNoteApiClient.toHex(digest);
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exc);
        }
    }

    private static String normalizeSourceType(String value) {
        String cleaned = FieldCommentDraft.trimToNull(value);
        if (cleaned == null) {
            return null;
        }
        String normalized = cleaned.toUpperCase(Locale.ROOT);
        if ("DOCUMENT".equals(normalized)
                || "FIELD_COMMENT".equals(normalized)
                || "WORK_SEQUENCE_ITEM".equals(normalized)
                || "WORK_SEQUENCE_HISTORY".equals(normalized)
                || "WORK_RECORD".equals(normalized)) {
            return normalized;
        }
        return null;
    }
}
