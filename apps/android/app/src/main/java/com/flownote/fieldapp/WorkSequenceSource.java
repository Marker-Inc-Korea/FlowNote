package com.flownote.fieldapp;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class WorkSequenceSource {
    final String serverScope;
    final String customerScope;
    final String siteScope;
    final String userId;
    final String deviceId;
    final String boardId;
    final String itemId;
    final int revision;
    final String documentId;
    final String documentVersionId;
    final String documentTitle;
    final String workRecordId;

    WorkSequenceSource(
            String serverScope,
            String customerScope,
            String siteScope,
            String userId,
            String deviceId,
            String boardId,
            String itemId,
            int revision,
            String documentId,
            String documentVersionId,
            String documentTitle,
            String workRecordId
    ) {
        this.serverScope = FieldCommentDraft.trimToNull(serverScope);
        this.customerScope = FieldCommentDraft.trimToNull(customerScope);
        this.siteScope = FieldCommentDraft.trimToNull(siteScope);
        this.userId = FieldCommentDraft.trimToNull(userId);
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
        this.boardId = FieldCommentDraft.trimToNull(boardId);
        this.itemId = FieldCommentDraft.trimToNull(itemId);
        this.revision = revision;
        this.documentId = FieldCommentDraft.trimToNull(documentId);
        this.documentVersionId = FieldCommentDraft.trimToNull(documentVersionId);
        this.documentTitle = FieldCommentDraft.trimToNull(documentTitle);
        this.workRecordId = FieldCommentDraft.trimToNull(workRecordId);
    }

    static WorkSequenceSource from(
            JSONObject board,
            JSONObject item,
            String serverScope,
            String customerScope,
            String siteScope,
            String userId,
            String deviceId
    ) {
        JSONObject document = item.optJSONObject("published_document");
        return new WorkSequenceSource(
                serverScope,
                customerScope,
                siteScope,
                userId,
                deviceId,
                board.optString("board_id", null),
                item.optString("item_id", null),
                board.optInt("board_revision", 0),
                document == null ? null : document.optString("document_id", null),
                document == null ? null : document.optString("version_id", null),
                document == null ? null : document.optString("title", null),
                item.optString("work_record_id", null)
        );
    }

    boolean canCreateFieldComment() {
        return isComplete() && documentId != null && documentVersionId != null;
    }

    boolean isComplete() {
        return serverScope != null && customerScope != null && siteScope != null
                && userId != null && deviceId != null && boardId != null && itemId != null
                && revision > 0;
    }

    String idempotencyKey(String kind, String localId) {
        Map<String, Object> identity = new LinkedHashMap<>();
        identity.put("deviceId", deviceId);
        identity.put("itemId", itemId);
        identity.put("kind", kind);
        identity.put("localId", localId);
        identity.put("serverScope", serverScope);
        identity.put("userId", userId);
        return "android:wseq:" + CanonicalIntentHash.sha256(identity);
    }

    String fieldCommentIntentHash(String rawContent, String inputMode, String signalLevel) {
        Map<String, Object> intent = scopeIntent();
        intent.put("documentId", documentId);
        intent.put("documentVersionId", documentVersionId);
        intent.put("inputMode", inputMode);
        intent.put("rawContent", rawContent);
        intent.put("signalLevel", signalLevel);
        intent.put("sourceId", itemId);
        intent.put("sourceRevision", revision);
        intent.put("sourceType", "WORK_SEQUENCE_ITEM");
        intent.put("workRecordId", workRecordId);
        return CanonicalIntentHash.sha256(intent);
    }

    String handoverIntentHash(
            String channelId,
            List<String> recipientIds,
            String title,
            String body
    ) {
        Map<String, Object> intent = scopeIntent();
        ArrayList<String> sortedRecipients = new ArrayList<>(recipientIds);
        Collections.sort(sortedRecipients);
        intent.put("body", body);
        intent.put("channelId", channelId);
        intent.put("recipientIds", sortedRecipients);
        intent.put("relatedDocumentId", documentId);
        intent.put("relatedDocumentVersionId", documentVersionId);
        intent.put("sourceId", itemId);
        intent.put("sourceRevision", revision);
        intent.put("sourceType", "WORK_SEQUENCE_ITEM");
        intent.put("title", title);
        return CanonicalIntentHash.sha256(intent);
    }

    private Map<String, Object> scopeIntent() {
        Map<String, Object> intent = new LinkedHashMap<>();
        intent.put("customerScope", customerScope);
        intent.put("deviceId", deviceId);
        intent.put("serverScope", serverScope);
        intent.put("siteScope", siteScope);
        intent.put("userId", userId);
        return intent;
    }
}
