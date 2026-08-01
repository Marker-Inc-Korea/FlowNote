package com.flownote.fieldapp;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.net.Uri;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class OfflineQueueStore extends SQLiteOpenHelper {
    private static final String DB_NAME = "flownote_android_outbox.db";
    // The table shape remains version 1 so an approved APK rollback can still
    // open the database after all pending items have been drained.
    private static final int DB_VERSION = 1;
    private final Context context;
    private final CryptoBox cryptoBox;
    private final EncryptedAttachmentStore attachmentStore;

    public OfflineQueueStore(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
        this.context = context.getApplicationContext();
        cryptoBox = new CryptoBox();
        attachmentStore = new EncryptedAttachmentStore(context, cryptoBox);
        migratePlaintextPayloads();
        cleanupSyncedAttachments();
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
                "CREATE TABLE outbox (" +
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, " +
                        "local_id TEXT NOT NULL UNIQUE, " +
                        "kind TEXT NOT NULL, " +
                        "payload TEXT NOT NULL, " +
                        "attachment_uri TEXT, " +
                        "status TEXT NOT NULL, " +
                        "server_id TEXT, " +
                        "idempotency_key TEXT NOT NULL, " +
                        "attempt_count INTEGER NOT NULL DEFAULT 0, " +
                        "last_attempt_at INTEGER NOT NULL DEFAULT 0, " +
                        "last_error TEXT, " +
                        "created_at INTEGER NOT NULL, " +
                        "updated_at INTEGER NOT NULL)"
        );
        db.execSQL("CREATE INDEX ix_outbox_status ON outbox(status, updated_at)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        throw new IllegalStateException("No Android outbox migration is defined for version " + oldVersion);
    }

    private void migratePlaintextPayloads() {
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try (Cursor cursor = db.query("outbox", new String[]{"local_id", "payload", "last_error"},
                null, null, null, null, null)) {
            while (cursor.moveToNext()) {
                String payload = cursor.getString(1);
                ContentValues values = new ContentValues();
                if (!cryptoBox.isEncrypted(payload)) {
                    values.put("payload", cryptoBox.encrypt(payload));
                }
                String lastError = cursor.getString(2);
                if (lastError != null && !cryptoBox.isEncrypted(lastError)) {
                    values.put("last_error", cryptoBox.encrypt(lastError));
                }
                if (values.size() > 0) {
                    db.update("outbox", values, "local_id = ?", new String[]{cursor.getString(0)});
                }
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public String enqueueFieldComment(FieldCommentDraft draft) throws IOException {
        long now = System.currentTimeMillis();
        String localId = FieldCommentDraft.nonEmpty(draft.localId, UUID.randomUUID().toString());
        String attachmentReference = null;
        if (draft.photoUri != null) {
            attachmentReference = attachmentStore.importFrom(
                    context.getContentResolver(), Uri.parse(draft.photoUri), localId);
        }
        ContentValues values = new ContentValues();
        values.put("local_id", localId);
        values.put("kind", "field_comment");
        values.put("payload", cryptoBox.encrypt(toPayload(draft).toString()));
        values.put("attachment_uri", attachmentReference);
        values.put("status", "PENDING");
        values.put("idempotency_key", draft.idempotencyKey);
        values.put("attempt_count", 0);
        values.put("last_attempt_at", 0);
        values.put("created_at", now);
        values.put("updated_at", now);
        getWritableDatabase().insertWithOnConflict("outbox", null, values, SQLiteDatabase.CONFLICT_IGNORE);
        return localId;
    }

    public String enqueueHandover(HandoverDraft draft) {
        long now = System.currentTimeMillis();
        String localId = FieldCommentDraft.nonEmpty(draft.localId, UUID.randomUUID().toString());
        ContentValues values = new ContentValues();
        values.put("local_id", localId);
        values.put("kind", "handover");
        values.put("payload", cryptoBox.encrypt(toPayload(draft).toString()));
        values.put("status", "PENDING");
        values.put("idempotency_key", draft.idempotencyKey);
        values.put("attempt_count", 0);
        values.put("last_attempt_at", 0);
        values.put("created_at", now);
        values.put("updated_at", now);
        getWritableDatabase().insertWithOnConflict(
                "outbox",
                null,
                values,
                SQLiteDatabase.CONFLICT_IGNORE
        );
        return localId;
    }

    public List<OutboxItem> listPending(long nowMillis) {
        return listPending(nowMillis, false);
    }

    private List<OutboxItem> listPending(long nowMillis, boolean failedOnly) {
        List<OutboxItem> items = new ArrayList<>();
        String selection = failedOnly
                ? "status = 'FAILED'"
                : "status IN ('PENDING', 'FAILED')";
        try (Cursor cursor = getReadableDatabase().query(
                "outbox",
                null,
                selection,
                null,
                null,
                null,
                "created_at ASC"
        )) {
            while (cursor.moveToNext()) {
                OutboxItem item = readItem(cursor);
                if ((failedOnly && OutboxRetryPolicy.canRetryManually(item.status))
                        || OutboxRetryPolicy.shouldRetry(
                        item.status,
                        item.attemptCount,
                        nowMillis,
                        item.lastAttemptAt
                )) {
                    items.add(item);
                }
            }
        }
        return items;
    }

    public int pendingCount() {
        try (Cursor cursor = getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM outbox WHERE status IN ('PENDING', 'FAILED')",
                null
        )) {
            return cursor.moveToFirst() ? cursor.getInt(0) : 0;
        }
    }

    public OutboxQueueStatus queueStatus(long nowMillis) {
        int pending = 0;
        int failed = 0;
        int ready = 0;
        int blocked = 0;
        long nextRetryAt = Long.MAX_VALUE;
        try (Cursor cursor = getReadableDatabase().query(
                "outbox",
                new String[]{"status", "attempt_count", "last_attempt_at"},
                "status IN ('PENDING', 'FAILED')",
                null,
                null,
                null,
                null
        )) {
            while (cursor.moveToNext()) {
                pending++;
                String status = cursor.getString(0);
                if ("FAILED".equals(status)) {
                    failed++;
                }
                int attemptCount = cursor.getInt(1);
                long lastAttemptAt = cursor.getLong(2);
                if (attemptCount >= OutboxRetryPolicy.MAX_AUTOMATIC_ATTEMPTS) {
                    blocked++;
                    continue;
                }
                if (OutboxRetryPolicy.shouldRetry(status, attemptCount, nowMillis, lastAttemptAt)) {
                    ready++;
                    nextRetryAt = Math.min(nextRetryAt, nowMillis);
                } else {
                    nextRetryAt = Math.min(
                            nextRetryAt,
                            lastAttemptAt + OutboxRetryPolicy.delayMillis(attemptCount)
                    );
                }
            }
        }
        return new OutboxQueueStatus(pending, failed, ready, blocked, nextRetryAt);
    }

    public SyncSummary retryPending(FlowNoteApiClient apiClient, String createdBy) {
        return syncItems(apiClient, createdBy, listPending(System.currentTimeMillis(), false));
    }

    public SyncSummary retryFailed(FlowNoteApiClient apiClient, String createdBy) {
        return syncItems(apiClient, createdBy, listPending(System.currentTimeMillis(), true));
    }

    private SyncSummary syncItems(
            FlowNoteApiClient apiClient,
            String createdBy,
            List<OutboxItem> items
    ) {
        int success = 0;
        int failed = 0;
        int partial = 0;
        String lastErrorMessage = null;
        for (OutboxItem item : items) {
            markAttempt(item.localId, item.attemptCount + 1);
            boolean partialSuccess = "field_comment".equals(item.kind)
                    && item.serverId != null
                    && item.attachmentUri != null;
            try {
                String serverId;
                if ("field_comment".equals(item.kind)) {
                    serverId = item.serverId;
                    if (serverId == null) {
                        JSONObject response = apiClient.createFieldComment(item.toFieldCommentDraft());
                        serverId = response.getString("comment_id");
                        markServerId(item.localId, serverId);
                        partialSuccess = item.attachmentUri != null;
                    }
                    if (item.attachmentUri != null) {
                        String attachmentKey = "android-photo:" + item.localId;
                        if (item.attachmentUri.startsWith("encfile:")) {
                            try (InputStream input = attachmentStore.open(item.attachmentUri)) {
                                apiClient.uploadFieldCommentPhoto(
                                        serverId,
                                        input,
                                        createdBy,
                                        attachmentKey
                                );
                            }
                        } else {
                            // Version 1 migration keeps the persisted content URI readable until
                            // this entry is sent; new attachments use app-private ciphertext.
                            apiClient.uploadFieldCommentPhoto(
                                    serverId,
                                    Uri.parse(item.attachmentUri),
                                    createdBy,
                                    attachmentKey
                            );
                        }
                    }
                } else if ("handover".equals(item.kind)) {
                    JSONObject response = apiClient.createHandover(item.toHandoverDraft());
                    serverId = response.getString("handover_id");
                } else {
                    throw new IOException("지원하지 않는 outbox 종류입니다.");
                }
                markSynced(item.localId, serverId);
                attachmentStore.delete(item.attachmentUri);
                success++;
            } catch (IOException | JSONException exc) {
                lastErrorMessage = UserErrorMessage.from(exc);
                markFailed(item.localId, lastErrorMessage);
                failed++;
                if (partialSuccess) {
                    partial++;
                }
                if (exc instanceof IOException
                        && FlowNoteApiClient.isAuthenticationRejected((IOException) exc)) {
                    break;
                }
            }
        }
        return new SyncSummary(success, partial, failed, pendingCount(), lastErrorMessage);
    }

    private JSONObject toPayload(FieldCommentDraft draft) {
        JSONObject payload = new JSONObject();
        try {
            payload.put("localId", draft.localId);
            payload.put("documentId", draft.documentId);
            payload.put("documentVersionId", draft.documentVersionId);
            payload.put("workRecordId", draft.workRecordId);
            payload.put("rawContent", draft.rawContent);
            payload.put("inputMode", draft.inputMode);
            payload.put("signalLevel", draft.signalLevel);
            payload.put("deviceId", draft.deviceId);
            payload.put("authorId", draft.authorId);
            payload.put("photoUri", draft.photoUri);
            payload.put("idempotencyKey", draft.idempotencyKey);
        } catch (JSONException exc) {
            throw new IllegalStateException(exc);
        }
        return payload;
    }

    private JSONObject toPayload(HandoverDraft draft) {
        JSONObject payload = new JSONObject();
        try {
            payload.put("localId", draft.localId);
            payload.put("channelId", draft.channelId);
            payload.put("title", draft.title);
            payload.put("body", draft.body);
            payload.put("sourceType", draft.sourceType);
            payload.put("sourceId", draft.sourceId);
            payload.put("sourceVersionId", draft.sourceVersionId);
            payload.put("recipientIds", new org.json.JSONArray(draft.recipientIds));
            payload.put("deviceId", draft.deviceId);
            payload.put("authorId", draft.authorId);
            payload.put("idempotencyKey", draft.idempotencyKey);
        } catch (JSONException exc) {
            throw new IllegalStateException(exc);
        }
        return payload;
    }

    private OutboxItem readItem(Cursor cursor) {
        return new OutboxItem(
                cursor.getString(cursor.getColumnIndexOrThrow("local_id")),
                cursor.getString(cursor.getColumnIndexOrThrow("kind")),
                cryptoBox.decrypt(cursor.getString(cursor.getColumnIndexOrThrow("payload"))),
                cursor.getString(cursor.getColumnIndexOrThrow("attachment_uri")),
                cursor.getString(cursor.getColumnIndexOrThrow("status")),
                cursor.getString(cursor.getColumnIndexOrThrow("server_id")),
                cursor.getString(cursor.getColumnIndexOrThrow("idempotency_key")),
                cursor.getInt(cursor.getColumnIndexOrThrow("attempt_count")),
                cursor.getLong(cursor.getColumnIndexOrThrow("last_attempt_at"))
        );
    }

    private void markAttempt(String localId, int attemptCount) {
        ContentValues values = new ContentValues();
        values.put("attempt_count", attemptCount);
        values.put("last_attempt_at", System.currentTimeMillis());
        values.put("updated_at", System.currentTimeMillis());
        getWritableDatabase().update("outbox", values, "local_id = ?", new String[]{localId});
    }

    private void markServerId(String localId, String serverId) {
        ContentValues values = new ContentValues();
        values.put("server_id", serverId);
        values.put("updated_at", System.currentTimeMillis());
        getWritableDatabase().update("outbox", values, "local_id = ?", new String[]{localId});
    }

    private void markSynced(String localId, String serverId) {
        ContentValues values = new ContentValues();
        values.put("status", "SYNCED");
        values.put("server_id", serverId);
        values.putNull("last_error");
        values.put("updated_at", System.currentTimeMillis());
        getWritableDatabase().update("outbox", values, "local_id = ?", new String[]{localId});
    }

    private void markFailed(String localId, String safeError) {
        ContentValues values = new ContentValues();
        values.put("status", "FAILED");
        values.put("last_error", cryptoBox.encrypt(safeError));
        values.put("updated_at", System.currentTimeMillis());
        getWritableDatabase().update("outbox", values, "local_id = ?", new String[]{localId});
    }

    private void cleanupSyncedAttachments() {
        try (Cursor cursor = getReadableDatabase().query(
                "outbox",
                new String[]{"attachment_uri"},
                "status = 'SYNCED' AND attachment_uri IS NOT NULL",
                null,
                null,
                null,
                null
        )) {
            while (cursor.moveToNext()) {
                attachmentStore.delete(cursor.getString(0));
            }
        }
    }

    public static final class OutboxItem {
        public final String localId;
        public final String kind;
        public final String payload;
        public final String attachmentUri;
        public final String status;
        public final String serverId;
        public final String idempotencyKey;
        public final int attemptCount;
        public final long lastAttemptAt;

        OutboxItem(
                String localId,
                String kind,
                String payload,
                String attachmentUri,
                String status,
                String serverId,
                String idempotencyKey,
                int attemptCount,
                long lastAttemptAt
        ) {
            this.localId = localId;
            this.kind = kind;
            this.payload = payload;
            this.attachmentUri = attachmentUri;
            this.status = status;
            this.serverId = serverId;
            this.idempotencyKey = idempotencyKey;
            this.attemptCount = attemptCount;
            this.lastAttemptAt = lastAttemptAt;
        }

        FieldCommentDraft toFieldCommentDraft() throws JSONException {
            JSONObject json = new JSONObject(payload);
            return new FieldCommentDraft(
                    json.optString("localId", localId),
                    json.optString("documentId", null),
                    json.optString("documentVersionId", null),
                    json.optString("workRecordId", null),
                    json.optString("rawContent", ""),
                    json.optString("inputMode", "free_text"),
                    json.optString("signalLevel", null),
                    json.optString("deviceId", null),
                    json.optString("authorId", null),
                    attachmentUri,
                    idempotencyKey
            );
        }

        HandoverDraft toHandoverDraft() throws JSONException {
            JSONObject json = new JSONObject(payload);
            org.json.JSONArray recipients = json.optJSONArray("recipientIds");
            List<String> recipientIds = new ArrayList<>();
            if (recipients != null) {
                for (int index = 0; index < recipients.length(); index++) {
                    String recipientId = recipients.optString(index, null);
                    if (recipientId != null) {
                        recipientIds.add(recipientId);
                    }
                }
            }
            return new HandoverDraft(
                    json.optString("localId", localId),
                    json.optString("channelId", null),
                    json.optString("title", ""),
                    json.optString("body", ""),
                    json.optString("sourceType", null),
                    json.optString("sourceId", null),
                    json.optString("sourceVersionId", null),
                    recipientIds,
                    json.optString("deviceId", null),
                    json.optString("authorId", null),
                    idempotencyKey
            );
        }
    }

    public static final class SyncSummary {
        public final int successCount;
        public final int partialSuccessCount;
        public final int failedCount;
        public final int remainingCount;
        public final String lastErrorMessage;

        SyncSummary(
                int successCount,
                int partialSuccessCount,
                int failedCount,
                int remainingCount,
                String lastErrorMessage
        ) {
            this.successCount = successCount;
            this.partialSuccessCount = partialSuccessCount;
            this.failedCount = failedCount;
            this.remainingCount = remainingCount;
            this.lastErrorMessage = lastErrorMessage;
        }
    }
}
