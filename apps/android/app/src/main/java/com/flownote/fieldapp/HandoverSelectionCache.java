package com.flownote.fieldapp;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Map;

final class HandoverSelectionCache {
    private static final String CHANNELS = "handover_channels_";
    private static final String MEMBERS = "handover_members_";

    private final SharedPreferences preferences;
    private final CryptoBox cryptoBox;

    HandoverSelectionCache(Context context) {
        preferences = context.getSharedPreferences(
                SecureSessionStore.PREFERENCES_NAME,
                Context.MODE_PRIVATE
        );
        cryptoBox = new CryptoBox();
    }

    void saveChannels(String serverUrl, String userId, JSONArray channels) {
        preferences.edit().putString(
                CHANNELS + scope(serverUrl, userId),
                cryptoBox.encrypt(channels.toString())
        ).commit();
    }

    JSONArray channels(String serverUrl, String userId) {
        return read(CHANNELS + scope(serverUrl, userId));
    }

    void saveMembers(
            String serverUrl,
            String userId,
            String channelId,
            JSONArray members
    ) {
        preferences.edit().putString(
                MEMBERS + scope(serverUrl, userId) + "_" + digest(channelId),
                cryptoBox.encrypt(members.toString())
        ).commit();
    }

    JSONArray members(String serverUrl, String userId, String channelId) {
        return read(MEMBERS + scope(serverUrl, userId) + "_" + digest(channelId));
    }

    void clear(String serverUrl, String userId) {
        String scope = scope(serverUrl, userId);
        SharedPreferences.Editor editor = preferences.edit();
        for (Map.Entry<String, ?> entry : preferences.getAll().entrySet()) {
            if (entry.getKey().equals(CHANNELS + scope)
                    || entry.getKey().startsWith(MEMBERS + scope + "_")) {
                editor.remove(entry.getKey());
            }
        }
        editor.commit();
    }

    private JSONArray read(String key) {
        String protectedValue = preferences.getString(key, null);
        if (protectedValue == null) {
            return new JSONArray();
        }
        try {
            return new JSONArray(cryptoBox.decrypt(protectedValue));
        } catch (JSONException exc) {
            throw new IllegalStateException("인수인계 선택 캐시가 손상되었습니다.", exc);
        }
    }

    private static String scope(String serverUrl, String userId) {
        return digest(
                FieldCommentDraft.nonEmpty(serverUrl, "")
                        + "\n"
                        + FieldCommentDraft.nonEmpty(userId, "anonymous")
        ).substring(0, 24);
    }

    private static String digest(String value) {
        try {
            return FlowNoteApiClient.toHex(
                    MessageDigest.getInstance("SHA-256").digest(
                            FieldCommentDraft.nonEmpty(value, "")
                                    .getBytes(StandardCharsets.UTF_8)
                    )
            );
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exc);
        }
    }
}
