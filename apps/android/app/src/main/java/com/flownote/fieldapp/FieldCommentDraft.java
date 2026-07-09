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
        this.localId = nonEmpty(localId, UUID.randomUUID().toString());
        this.documentId = trimToNull(documentId);
        this.documentVersionId = trimToNull(documentVersionId);
        this.workRecordId = trimToNull(workRecordId);
        this.rawContent = nonEmpty(rawContent, "");
        this.inputMode = nonEmpty(inputMode, "free_text");
        this.signalLevel = trimToNull(signalLevel);
        this.deviceId = trimToNull(deviceId);
        this.authorId = trimToNull(authorId);
        this.photoUri = trimToNull(photoUri);
        this.idempotencyKey = nonEmpty(idempotencyKey, defaultIdempotencyKey(this.deviceId, this.localId));
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
