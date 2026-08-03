package com.flownote.fieldapp;

import android.content.Context;
import android.content.SharedPreferences;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class HandoverFollowUpDraftStore {
    private static final String PREFIX = "handover_follow_up_draft_";

    private final SharedPreferences preferences;
    private final CryptoBox cryptoBox;

    HandoverFollowUpDraftStore(Context context) {
        preferences = context.getSharedPreferences(
                SecureSessionStore.PREFERENCES_NAME,
                Context.MODE_PRIVATE
        );
        cryptoBox = new CryptoBox();
    }

    void save(String serverUrl, String userId, String handoverId, String content) {
        String cleaned = FieldCommentDraft.trimToNull(content);
        SharedPreferences.Editor editor = preferences.edit();
        String key = key(serverUrl, userId, handoverId);
        if (cleaned == null) {
            editor.remove(key);
        } else {
            editor.putString(key, cryptoBox.encrypt(cleaned));
        }
        editor.commit();
    }

    String load(String serverUrl, String userId, String handoverId) {
        String value = preferences.getString(key(serverUrl, userId, handoverId), null);
        return value == null ? "" : cryptoBox.decrypt(value);
    }

    void remove(String serverUrl, String userId, String handoverId) {
        preferences.edit().remove(key(serverUrl, userId, handoverId)).commit();
    }

    private static String key(String serverUrl, String userId, String handoverId) {
        return PREFIX + digest(
                FieldCommentDraft.nonEmpty(serverUrl, "")
                        + "\n" + FieldCommentDraft.nonEmpty(userId, "anonymous")
                        + "\n" + FieldCommentDraft.nonEmpty(handoverId, "unknown")
        );
    }

    private static String digest(String value) {
        try {
            return FlowNoteApiClient.toHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8))
            );
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exc);
        }
    }
}
