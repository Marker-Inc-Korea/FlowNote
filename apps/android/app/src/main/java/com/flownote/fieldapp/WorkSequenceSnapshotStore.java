package com.flownote.fieldapp;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONException;
import org.json.JSONObject;

final class WorkSequenceSnapshotStore {
    static final long RETENTION_MILLIS = 7L * 24L * 60L * 60L * 1000L;
    private static final String LIST_PREFIX = "wseq_snapshot_list_";
    private static final String BOARD_PREFIX = "wseq_snapshot_board_";
    private static final String FILTER_PREFIX = "wseq_filter_";

    private final SharedPreferences preferences;
    private final CryptoBox cryptoBox;

    WorkSequenceSnapshotStore(Context context) {
        preferences = context.getSharedPreferences(
                SecureSessionStore.PREFERENCES_NAME,
                Context.MODE_PRIVATE
        );
        cryptoBox = new CryptoBox();
    }

    void saveList(WorkSequenceScope scope, JSONObject payload, long savedAt) {
        save(LIST_PREFIX + scope.storageKey(), payload, savedAt);
    }

    Snapshot loadList(WorkSequenceScope scope, long now) {
        return load(LIST_PREFIX + scope.storageKey(), now);
    }

    void saveBoard(WorkSequenceScope scope, String boardId, JSONObject payload, long savedAt) {
        save(BOARD_PREFIX + scope.storageKey() + "_" + digest(boardId), payload, savedAt);
    }

    Snapshot loadBoard(WorkSequenceScope scope, String boardId, long now) {
        return load(BOARD_PREFIX + scope.storageKey() + "_" + digest(boardId), now);
    }

    void saveFilter(WorkSequenceScope scope, String date, String line, boolean archived) {
        JSONObject value = new JSONObject();
        try {
            value.put("date", date);
            value.put("line", line);
            value.put("archived", archived);
        } catch (JSONException exc) {
            throw new IllegalStateException(exc);
        }
        save(FILTER_PREFIX + scope.storageKey(), value, System.currentTimeMillis());
    }

    JSONObject loadFilter(WorkSequenceScope scope) {
        Snapshot snapshot = load(FILTER_PREFIX + scope.storageKey(), System.currentTimeMillis());
        return snapshot == null ? new JSONObject() : snapshot.payload;
    }

    private void save(String key, JSONObject payload, long savedAt) {
        JSONObject envelope = new JSONObject();
        try {
            envelope.put("savedAt", savedAt);
            envelope.put("payload", payload);
            preferences.edit().putString(key, cryptoBox.encrypt(envelope.toString())).commit();
        } catch (JSONException exc) {
            throw new IllegalStateException("작업순서 snapshot을 저장할 수 없습니다.", exc);
        }
    }

    private Snapshot load(String key, long now) {
        String protectedValue = preferences.getString(key, null);
        if (protectedValue == null) {
            return null;
        }
        try {
            JSONObject envelope = new JSONObject(cryptoBox.decrypt(protectedValue));
            long savedAt = envelope.getLong("savedAt");
            if (savedAt > now || now - savedAt > RETENTION_MILLIS) {
                preferences.edit().remove(key).commit();
                return null;
            }
            return new Snapshot(savedAt, envelope.getJSONObject("payload"));
        } catch (JSONException | RuntimeException exc) {
            throw new IllegalStateException("작업순서 snapshot이 손상되었습니다.", exc);
        }
    }

    private static String digest(String value) {
        return new WorkSequenceScope(value, "-", "-", "-", "-").storageKey();
    }

    static final class Snapshot {
        final long savedAt;
        final JSONObject payload;

        Snapshot(long savedAt, JSONObject payload) {
            this.savedAt = savedAt;
            this.payload = payload;
        }
    }
}
