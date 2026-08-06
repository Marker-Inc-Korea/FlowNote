package com.flownote.fieldapp;

import java.util.UUID;

public final class FieldCommentDraft {
    public final String localId;
    public final String documentId;
    public final String documentVersionId;
    public final String workRecordId;
    public final String rawContent;
    public final String inputMode;
    public final String signalLevel;
    public final String deviceId;
    public final String authorId;
    public final String photoUri;
    public final String idempotencyKey;
    public final String sourceType;
    public final String sourceId;
    public final Integer sourceRevision;
    public final String serverScope;
    public final String intentHashSha256;
    public final String sourceCustomerScope;
    public final String sourceSiteScope;
    public final String sourceBoardId;

    public FieldCommentDraft(
            String localId,
            String documentId,
            String documentVersionId,
            String workRecordId,
            String rawContent,
            String inputMode,
            String signalLevel,
            String deviceId,
            String authorId,
            String photoUri,
            String idempotencyKey
    ) {
        this(
                localId, documentId, documentVersionId, workRecordId, rawContent,
                inputMode, signalLevel, deviceId, authorId, photoUri, idempotencyKey, null
        );
    }

    public FieldCommentDraft(
            String localId,
            String documentId,
            String documentVersionId,
            String workRecordId,
            String rawContent,
            String inputMode,
            String signalLevel,
            String deviceId,
            String authorId,
            String photoUri,
            String idempotencyKey,
            WorkSequenceSource source
    ) {
        this.localId = nonEmpty(localId, UUID.randomUUID().toString());
        this.documentId = source == null ? trimToNull(documentId) : source.documentId;
        this.documentVersionId = source == null
                ? trimToNull(documentVersionId) : source.documentVersionId;
        this.workRecordId = source == null ? trimToNull(workRecordId) : source.workRecordId;
        this.rawContent = nonEmpty(rawContent, "");
        this.inputMode = nonEmpty(inputMode, "free_text");
        this.signalLevel = trimToNull(signalLevel);
        this.deviceId = trimToNull(deviceId);
        this.authorId = trimToNull(authorId);
        this.photoUri = trimToNull(photoUri);
        this.sourceType = source == null ? null : "WORK_SEQUENCE_ITEM";
        this.sourceId = source == null ? null : source.itemId;
        this.sourceRevision = source == null ? null : source.revision;
        this.serverScope = source == null ? null : source.serverScope;
        this.intentHashSha256 = source == null ? null : source.fieldCommentIntentHash(
                this.rawContent, normalizedInputMode(), this.signalLevel
        );
        this.sourceCustomerScope = source == null ? null : source.customerScope;
        this.sourceSiteScope = source == null ? null : source.siteScope;
        this.sourceBoardId = source == null ? null : source.boardId;
        this.idempotencyKey = nonEmpty(
                idempotencyKey,
                source == null
                        ? defaultIdempotencyKey(this.deviceId, this.localId)
                        : source.idempotencyKey("field-comment", this.localId)
        );
    }

    public boolean hasTarget() {
        return documentId != null || workRecordId != null;
    }

    public boolean canSend() {
        return hasTarget() && !rawContent.trim().isEmpty();
    }

    public String normalizedInputMode() {
        if ("signal".equals(inputMode)) {
            return "signal";
        }
        return "free_text";
    }

    public static String defaultIdempotencyKey(String deviceId, String localId) {
        String sourceDeviceId = trimToNull(deviceId);
        String sourceLocalId = nonEmpty(localId, UUID.randomUUID().toString());
        if (sourceDeviceId == null) {
            sourceDeviceId = "unknown-device";
        }
        return "android:" + sourceDeviceId + ":" + sourceLocalId;
    }

    static String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String cleaned = value.trim();
        return cleaned.isEmpty() ? null : cleaned;
    }

    static String nonEmpty(String value, String fallback) {
        String cleaned = trimToNull(value);
        return cleaned == null ? fallback : cleaned;
    }
}
