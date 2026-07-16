package com.flownote.fieldapp;

import android.content.Context;
import android.content.SharedPreferences;

final class SecureSessionStore {
    static final String PREFERENCES_NAME = "flownote-field-app";
    private static final String ACCESS = "access_token_protected";
    private static final String REFRESH = "refresh_token_protected";

    private final SharedPreferences preferences;
    private final CryptoBox cryptoBox;

    SecureSessionStore(Context context) {
        preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE);
        cryptoBox = new CryptoBox();
        migrateLegacyToken("access_token", ACCESS);
        migrateLegacyToken("refresh_token", REFRESH);
    }

    private void migrateLegacyToken(String legacyKey, String protectedKey) {
        String legacy = preferences.getString(legacyKey, null);
        if (legacy != null) {
            preferences.edit().putString(protectedKey, cryptoBox.encrypt(legacy)).remove(legacyKey).commit();
        }
    }

    String accessToken() {
        return cryptoBox.decrypt(preferences.getString(ACCESS, null));
    }

    String refreshToken() {
        return cryptoBox.decrypt(preferences.getString(REFRESH, null));
    }

    void save(String accessToken, String refreshToken, String userId) {
        preferences.edit()
                .putString(ACCESS, cryptoBox.encrypt(accessToken))
                .putString(REFRESH, cryptoBox.encrypt(refreshToken))
                .putString("user_id", userId)
                .commit();
    }

    void clear() {
        preferences.edit().remove(ACCESS).remove(REFRESH).remove("user_id").commit();
    }

    boolean hasSession() {
        return preferences.contains(ACCESS) && preferences.contains(REFRESH);
    }
}
