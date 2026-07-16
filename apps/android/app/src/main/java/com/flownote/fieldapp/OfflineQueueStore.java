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
        try (Cursor cursor = db.query("outbox", new String[]{"local_id", "payload"},
                null, null, null, null, null)) {
            while (cursor.moveToNext()) {
                String payload = cursor.getString(1);
                if (cryptoBox.isEncrypted(payload)) {
                    continue;
                }
                ContentValues values = new ContentValues();
                values.put("payload", cryptoBox.encrypt(payload));
                db.update("outbox", values, "local_id = ?", new String[]{cursor.getString(0)});
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

    public List<OutboxItem> listPending(long nowMillis) {
        List<OutboxItem> items = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().query(
                "outbox",
                null,
                "status IN ('PENDING', 'FAILED')",
                null,
                null,
                null,
                "created_at ASC"
        )) {
            while (cursor.moveToNext()) {
                OutboxItem item = readItem(cursor);
                if (OutboxRetryPolicy.shouldRetry(
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

    public SyncSummary retryPending(FlowNoteApiClient apiClient, String createdBy) {
        int success = 0;
        int failed = 0;
        for (OutboxItem item : listPending(System.currentTimeMillis())) {
            markAttempt(item.localId, item.attemptCount + 1);
            try {
                String commentId = item.serverId;
                if (commentId == null) {
                    JSONObject response = apiClient.createFieldComment(item.toDraft());
                    commentId = response.getString("comment_id");
                    markServerId(item.localId, commentId);
                }
                if (item.attachmentUri != null) {
                    if (item.attachmentUri.startsWith("encfile:")) {
                        try (InputStream input = attachmentStore.open(item.attachmentUri)) {
                            apiClient.uploadFieldCommentPhoto(commentId, input, createdBy);
                        }
                    } else {
                        // Version 1 migration keeps the persisted content URI readable until
                        // this entry is sent; every newly queued attachment is app-private ciphertext.
                        apiClient.uploadFieldCommentPhoto(
                                commentId, Uri.parse(item.attachmentUri), createdBy);
                    }
                }
                markSynced(item.localId, commentId);
                success++;
            } catch (IOException | JSONException exc) {
                markFailed(item.localId, exc.getMessage());
                failed++;
            }
        }
        return new SyncSummary(success, failed, pendingCount());
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

    private void markFailed(String localId, String error) {
        ContentValues values = new ContentValues();
        values.put("status", "FAILED");
        values.put("last_error", error);
        values.put("updated_at", System.currentTimeMillis());
        getWritableDatabase().update("outbox", values, "local_id = ?", new String[]{localId});
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

        FieldCommentDraft toDraft() throws JSONException {
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
    }

    public static final class SyncSummary {
        public final int successCount;
        public final int failedCount;
        public final int remainingCount;

        SyncSummary(int successCount, int failedCount, int remainingCount) {
            this.successCount = successCount;
            this.failedCount = failedCount;
            this.remainingCount = remainingCount;
        }
    }
}
