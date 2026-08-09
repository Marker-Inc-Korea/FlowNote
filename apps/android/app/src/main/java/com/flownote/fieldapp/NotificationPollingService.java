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
    private static final int PAGE_LIMIT = 100;
    private static final String TAG = "FlowNoteDelivery";

    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor();
    private SecureSessionStore sessionStore;
    private OfflineQueueStore outbox;
    private NotificationMessageLedger messageLedger;
    private SharedPreferences preferences;
    private String runId;
    private volatile boolean pollRunning;

    @Override
    public void onCreate() {
        super.onCreate();
        preferences = getSharedPreferences(SecureSessionStore.PREFERENCES_NAME, MODE_PRIVATE);
        runId = "ANDROID-DELIVERY-" + UUID.randomUUID();
        preferences.edit().putString("delivery_run_id", runId).commit();
        createChannels();
        try {
            sessionStore = new SecureSessionStore(this);
            outbox = new OfflineQueueStore(this);
            messageLedger = new NotificationMessageLedger(this);
        } catch (RuntimeException exc) {
            Log.e(TAG, runId + " secure_storage_unavailable", exc);
            startForeground(
                    SERVICE_NOTIFICATION_ID,
                    serviceNotification("보안 저장소 오류 · 관리자 점검 필요")
            );
            stopSelf();
            return;
        }
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
        if (outbox != null) {
            outbox.close();
        }
        if (messageLedger != null) {
            messageLedger.close();
        }
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
            if (UserErrorMessage.isSecureStorageFailure(exc)) {
                updateServiceNotification("보안 저장소 오류 · 관리자 점검 필요");
                stopSelf();
            } else {
                updateServiceNotification("연결 복구 대기 중");
            }
        } finally {
            pollRunning = false;
        }
    }

    private void pollWithCurrentSession(boolean allowRefresh) throws Exception {
        String serverUrl = ServerConfiguration.resolve(
                preferences.getString("server_url", null));
        String userId = preferences.getString("user_id", "anonymous");
        String scope = sha256(serverUrl + "\n" + userId).substring(0, 16);
        String cursorKey = "notification_cursor_v2_" + scope;
        String caughtUpKey = cursorKey + "_caught_up";
        long cursor = preferences.getLong(cursorKey, 0L);

        FlowNoteApiClient client = new FlowNoteApiClient(serverUrl, getContentResolver());
        client.setAccessToken(sessionStore.accessToken());
        boolean caughtUp = preferences.getBoolean(caughtUpKey, false);
        NotificationCursorTracker tracker = new NotificationCursorTracker(cursor, caughtUp);
        int pageNumber = 0;
        int totalReceived = 0;
        int totalAdvanced = 0;
        int totalStale = 0;
        while (true) {
            pageNumber++;
            tracker.beginPage();
            JSONArray items;
            try {
                items = client.pollNotifications(tracker.cursor(), PAGE_LIMIT);
            } catch (IOException exc) {
                NotificationSessionRecoveryPolicy.Action recovery =
                        NotificationSessionRecoveryPolicy.decide(exc, allowRefresh);
                if (recovery == NotificationSessionRecoveryPolicy.Action.REFRESH) {
                    refreshSession(client);
                    pollWithCurrentSession(false);
                    return;
                }
                if (recovery == NotificationSessionRecoveryPolicy.Action.CLEAR_SESSION) {
                    sessionStore.clear();
                    Log.w(TAG, runId + " session_rejected at=" + Instant.now());
                    stopSelf();
                    return;
                }
                throw exc;
            }

            for (int index = 0; index < items.length(); index++) {
                JSONObject item = items.optJSONObject(index);
                if (item == null) {
                    continue;
                }
                long itemCursor = item.optLong("cursor", 0L);
                long cursorBeforeItem = tracker.cursor();
                boolean shouldDisplay = tracker.accept(itemCursor);
                if (tracker.cursor() == cursorBeforeItem) {
                    continue;
                }
                if (shouldDisplay) {
                    String messageId = item.optString("message_id");
                    if (!messageLedger.contains(scope, messageId)) {
                        display(item);
                        messageLedger.record(scope, messageId, itemCursor);
                    }
                }
                // Commit after each displayed or catch-up item. A crash can duplicate at most
                // one visual alert, while the server receipt remains unique and idempotent.
                preferences.edit().putLong(cursorKey, tracker.cursor()).commit();
            }
            totalReceived += items.length();
            totalAdvanced += tracker.advancedCount();
            totalStale += tracker.staleCount();
            Log.i(TAG, runId + " page_ok page=" + pageNumber
                    + " cursor_before=" + tracker.pageStartCursor()
                    + " cursor_after=" + tracker.cursor()
                    + " received=" + items.length()
                    + " advanced=" + tracker.advancedCount()
                    + " stale_or_duplicate=" + tracker.staleCount()
                    + " at=" + Instant.now());
            if (!tracker.finishPage(items.length(), PAGE_LIMIT)) {
                break;
            }
        }
        preferences.edit()
                .putLong(cursorKey, tracker.cursor())
                .putBoolean(caughtUpKey, tracker.caughtUp())
                .commit();
        OfflineQueueStore.SyncSummary outboxSummary = outbox.retryPending(client, userId);
        int pendingOutbox = outboxSummary.remainingCount;
        updateServiceNotification(
                pendingOutbox == 0
                        ? "알림 연결 정상 · 전송 대기 0건"
                        : "알림 연결 정상 · 전송 대기 " + pendingOutbox + "건"
        );
        Log.i(TAG, runId + " outbox_ok success=" + outboxSummary.successCount
                + " partial=" + outboxSummary.partialSuccessCount
                + " failed=" + outboxSummary.failedCount
                + " pending=" + pendingOutbox
                + " at=" + Instant.now());
        Log.i(TAG, runId + " poll_ok cursor=" + tracker.cursor()
                + " pages=" + pageNumber
                + " received=" + totalReceived
                + " advanced=" + totalAdvanced
                + " stale_or_duplicate=" + totalStale
                + " at=" + Instant.now());
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
