package com.flownote.fieldapp;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.IBinder;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class NotificationPollingService extends Service {
    static final String SERVICE_CHANNEL_ID = "flownote_background_delivery";
    static final String MESSAGE_CHANNEL_ID = "flownote_field_notifications";
    private static final int SERVICE_NOTIFICATION_ID = 4100;
    private static final long POLL_SECONDS = 15L;
    private static final String TAG = "FlowNoteDelivery";

    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor();
    private SecureSessionStore sessionStore;
    private SharedPreferences preferences;
    private String runId;
    private volatile boolean pollRunning;

    @Override
    public void onCreate() {
        super.onCreate();
        sessionStore = new SecureSessionStore(this);
        preferences = getSharedPreferences(SecureSessionStore.PREFERENCES_NAME, MODE_PRIVATE);
        runId = "ANDROID-DELIVERY-" + UUID.randomUUID();
        preferences.edit().putString("delivery_run_id", runId).commit();
        createChannels();
        startForeground(SERVICE_NOTIFICATION_ID, serviceNotification("알림 연결 준비 중"));
        executor.scheduleWithFixedDelay(this::pollOnce, 0, POLL_SECONDS, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void pollOnce() {
        if (pollRunning || !sessionStore.hasSession()) {
            if (!sessionStore.hasSession()) {
                stopSelf();
            }
            return;
        }
        pollRunning = true;
        try {
            pollWithCurrentSession(true);
        } catch (Exception exc) {
            Log.w(TAG, runId + " poll_failed at=" + Instant.now() + " " + exc.getMessage());
            updateServiceNotification("연결 복구 대기 중");
        } finally {
            pollRunning = false;
        }
    }

    private void pollWithCurrentSession(boolean allowRefresh) throws Exception {
        String serverUrl = preferences.getString("server_url", "");
        String userId = preferences.getString("user_id", "anonymous");
        String scope = sha256(serverUrl + "\n" + userId).substring(0, 16);
        String cursorKey = "notification_cursor_v2_" + scope;
        String caughtUpKey = cursorKey + "_caught_up";
        long cursor = preferences.getLong(cursorKey, 0L);

        FlowNoteApiClient client = new FlowNoteApiClient(serverUrl, getContentResolver());
        client.setAccessToken(sessionStore.accessToken());
        JSONArray items;
        try {
            items = client.pollNotifications(cursor, 100);
        } catch (IOException exc) {
            if (allowRefresh && isUnauthorized(exc)) {
                refreshSession(client);
                pollWithCurrentSession(false);
                return;
            }
            throw exc;
        }

        boolean caughtUp = preferences.getBoolean(caughtUpKey, false);
        long nextCursor = cursor;
        for (int index = 0; index < items.length(); index++) {
            JSONObject item = items.optJSONObject(index);
            if (item == null) {
                continue;
            }
            long itemCursor = item.optLong("cursor", 0L);
            if (itemCursor <= nextCursor) {
                continue;
            }
            if (caughtUp) {
                display(item);
            }
            nextCursor = itemCursor;
            // Commit after each displayed notification. A crash can duplicate at most one
            // visual alert, while the server receipt remains unique and idempotent.
            preferences.edit().putLong(cursorKey, nextCursor).commit();
        }
        if (!caughtUp && items.length() < 100) {
            preferences.edit().putBoolean(caughtUpKey, true).commit();
        }
        updateServiceNotification("마지막 확인 " + Instant.now());
        Log.i(TAG, runId + " poll_ok cursor=" + nextCursor + " count=" + items.length()
                + " at=" + Instant.now());
        if (items.length() == 100) {
            executor.execute(this::pollOnce);
        }
    }

    private void refreshSession(FlowNoteApiClient client) throws Exception {
        try {
            JSONObject refreshed = client.refresh(sessionStore.refreshToken());
            sessionStore.save(
                    refreshed.getString("access_token"),
                    refreshed.getString("refresh_token"),
                    refreshed.getString("user_id"));
            Log.i(TAG, runId + " token_refreshed at=" + Instant.now());
        } catch (Exception exc) {
            sessionStore.clear();
            Log.w(TAG, runId + " session_rejected at=" + Instant.now());
            stopSelf();
            throw exc;
        }
    }

    private void display(JSONObject item) {
        String messageId = item.optString("message_id");
        Intent openApp = new Intent(this, MainActivity.class);
        openApp.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
                this, messageId.hashCode(), openApp,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, MESSAGE_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(item.optString("channel_name", "FlowNote 알림"))
                .setContentText(item.optString("title", "새 업무 알림"))
                .setStyle(new Notification.BigTextStyle().bigText(item.optString("body")))
                .setContentIntent(pendingIntent)
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
                .build();
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
                .notify(messageId.hashCode(), notification);
        preferences.edit().putString(
                "notification_displayed_at_" + messageId, Instant.now().toString()).commit();
        Log.i(TAG, runId + " displayed message_id=" + messageId + " event_at="
                + item.optString("created_at") + " displayed_at=" + Instant.now());
    }

    private Notification serviceNotification(String text) {
        return new Notification.Builder(this, SERVICE_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle("FlowNote 업무 알림 수신 중")
                .setContentText(text)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .build();
    }

    private void updateServiceNotification(String text) {
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE))
                .notify(SERVICE_NOTIFICATION_ID, serviceNotification(text));
    }

    private void createChannels() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(
                SERVICE_CHANNEL_ID, "백그라운드 전달 상태", NotificationManager.IMPORTANCE_LOW));
        manager.createNotificationChannel(new NotificationChannel(
                MESSAGE_CHANNEL_ID, "현장 업무 알림", NotificationManager.IMPORTANCE_HIGH));
    }

    private static boolean isUnauthorized(IOException exc) {
        return exc.getMessage() != null && exc.getMessage().startsWith("HTTP 401");
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return FlowNoteApiClient.toHex(digest);
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException(exc);
        }
    }
}
