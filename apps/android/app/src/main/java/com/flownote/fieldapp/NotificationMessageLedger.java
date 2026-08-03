package com.flownote.fieldapp;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

final class NotificationMessageLedger extends SQLiteOpenHelper {
    private static final String DB_NAME = "flownote_android_notifications.db";
    private static final int DB_VERSION = 1;

    NotificationMessageLedger(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
                "CREATE TABLE processed_notification_messages (" +
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, " +
                        "server_user_scope TEXT NOT NULL, " +
                        "message_id TEXT NOT NULL, " +
                        "cursor INTEGER NOT NULL, " +
                        "processed_at INTEGER NOT NULL, " +
                        "UNIQUE(server_user_scope, message_id))"
        );
        db.execSQL(
                "CREATE INDEX ix_processed_notifications_scope_cursor " +
                        "ON processed_notification_messages(server_user_scope, cursor)"
        );
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        throw new IllegalStateException(
                "No notification ledger migration is defined for version " + oldVersion
        );
    }

    boolean contains(String scope, String messageId) {
        try (Cursor cursor = getReadableDatabase().query(
                "processed_notification_messages",
                new String[]{"id"},
                "server_user_scope = ? AND message_id = ?",
                new String[]{scope, messageId},
                null,
                null,
                null,
                "1"
        )) {
            return cursor.moveToFirst();
        }
    }

    void record(String scope, String messageId, long cursor) {
        ContentValues values = new ContentValues();
        values.put("server_user_scope", scope);
        values.put("message_id", messageId);
        values.put("cursor", cursor);
        values.put("processed_at", System.currentTimeMillis());
        getWritableDatabase().insertWithOnConflict(
                "processed_notification_messages",
                null,
                values,
                SQLiteDatabase.CONFLICT_IGNORE
        );
    }
}
