package com.flownote.fieldapp;

import android.app.Activity;
import android.Manifest;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.Log;
import android.util.Size;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQUEST_PICK_PHOTO = 1001;
    private static final long OUTBOX_REFRESH_MILLIS = 15_000L;
    private static final String OUTBOX_LOG_TAG = "FlowNoteOutbox";
    private static final String EXTRA_OUTBOX_AUDIT_NONCE = "flownote_outbox_audit_nonce";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable outboxRefresh = new Runnable() {
        @Override
        public void run() {
            refreshOutboxStatus();
            OutboxQueueStatus queueStatus = outbox.queueStatus(System.currentTimeMillis());
            if (!retryInProgress && sessionStore.hasSession() && queueStatus.readyCount > 0) {
                retryOutbox(false);
            }
            mainHandler.postDelayed(this, OUTBOX_REFRESH_MILLIS);
        }
    };

    private SharedPreferences preferences;
    private SecureSessionStore sessionStore;
    private OfflineQueueStore outbox;
    private FlowNoteApiClient apiClient;

    private EditText serverUrlInput;
    private EditText deviceIdInput;
    private EditText usernameInput;
    private EditText passwordInput;
    private EditText documentIdInput;
    private EditText versionIdInput;
    private EditText commentInput;
    private RadioGroup signalGroup;
    private TextView statusText;
    private TextView outboxStatusText;
    private TextView photoStatusText;
    private ImageView photoPreview;
    private LinearLayout contentArea;
    private Uri selectedPhotoUri;
    private String accessToken;
    private String refreshToken;
    private String currentUserId;
    private volatile boolean retryInProgress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences("flownote-field-app", MODE_PRIVATE);
        sessionStore = new SecureSessionStore(this);
        SecureViewerFiles.clean(this);
        outbox = new OfflineQueueStore(this);
        buildUi();
        restoreSettings();
        rebuildApiClient();
        requestNotificationPermission();
        startNotificationDelivery();
        updateStatus("서버 주소와 승인 단말 ID를 확인한 뒤 로그인하세요.");
        refreshOutboxStatus();
        logOutboxAudit(getIntent());
    }

    @Override
    protected void onStart() {
        super.onStart();
        mainHandler.removeCallbacks(outboxRefresh);
        mainHandler.post(outboxRefresh);
    }

    @Override
    protected void onStop() {
        mainHandler.removeCallbacks(outboxRefresh);
        super.onStop();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        logOutboxAudit(intent);
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        outbox.close();
        super.onDestroy();
    }

    private void buildUi() {
        ScrollView scrollView = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 20, 24, 24);
        scrollView.addView(root);

        TextView title = text("FlowNote 현장 단말", 22, "#1F2A30");
        title.setPadding(0, 0, 0, 14);
        root.addView(title);

        outboxStatusText = text("", 16, "#1F2A30");
        outboxStatusText.setBackgroundColor(Color.parseColor("#E7F1EB"));
        outboxStatusText.setPadding(dp(14), dp(14), dp(14), dp(14));
        outboxStatusText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(outboxStatusText);

        statusText = text("", 14, "#3D4852");
        statusText.setPadding(0, dp(12), 0, dp(12));
        statusText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(statusText);

        serverUrlInput = input("서버 주소 예: http://10.0.0.10:8000", InputType.TYPE_CLASS_TEXT);
        deviceIdInput = input("승인 단말 ID", InputType.TYPE_CLASS_TEXT);
        usernameInput = input("사용자 ID", InputType.TYPE_CLASS_TEXT);
        passwordInput = input("비밀번호", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(serverUrlInput);
        root.addView(deviceIdInput);
        root.addView(usernameInput);
        root.addView(passwordInput);

        LinearLayout loginRow = row();
        addRowButton(loginRow, "로그인", view -> login());
        addRowButton(loginRow, "로그아웃", view -> logout());
        addRowButton(loginRow, "재전송", view -> retryOutbox(true));
        root.addView(loginRow);

        LinearLayout navRow = row();
        addRowButton(navRow, "공개 문서", view -> loadPublishedDocuments());
        addRowButton(navRow, "알림", view -> loadNotifications());
        addRowButton(navRow, "인수인계", view -> loadHandovers());
        root.addView(navRow);

        TextView formTitle = text("FieldComment / 사진 / 신호등 입력", 18, "#236C4A");
        formTitle.setPadding(0, 18, 0, 8);
        root.addView(formTitle);

        documentIdInput = input("문서 ID 또는 작업내역 대신 문서 ID", InputType.TYPE_CLASS_TEXT);
        versionIdInput = input("문서 버전 ID (선택)", InputType.TYPE_CLASS_TEXT);
        commentInput = input("현장 기록 내용", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        commentInput.setMinLines(3);
        root.addView(documentIdInput);
        root.addView(versionIdInput);
        root.addView(commentInput);

        signalGroup = new RadioGroup(this);
        signalGroup.setOrientation(RadioGroup.HORIZONTAL);
        signalGroup.addView(radioButton("녹색", 1));
        signalGroup.addView(radioButton("황색", 2));
        signalGroup.addView(radioButton("적색", 3));
        root.addView(signalGroup);

        LinearLayout commentRow = row();
        addRowButton(commentRow, "사진 선택·확인", view -> pickPhoto());
        addRowButton(commentRow, "기기에 저장·전송", view -> enqueueAndRetryComment());
        root.addView(commentRow);

        photoStatusText = text("사진 선택 안 됨", 15, "#3D4852");
        photoStatusText.setPadding(dp(12), dp(10), dp(12), dp(10));
        root.addView(photoStatusText);

        photoPreview = new ImageView(this);
        photoPreview.setAdjustViewBounds(true);
        photoPreview.setMaxHeight(dp(180));
        photoPreview.setContentDescription("선택한 현장 사진 미리보기");
        photoPreview.setVisibility(View.GONE);
        root.addView(photoPreview);

        contentArea = new LinearLayout(this);
        contentArea.setOrientation(LinearLayout.VERTICAL);
        root.addView(contentArea);

        setContentView(scrollView);
    }

    private TextView radioButton(String label, int id) {
        android.widget.RadioButton button = new android.widget.RadioButton(this);
        button.setId(id);
        button.setText(label);
        button.setTextSize(15);
        button.setMinHeight(dp(56));
        button.setPadding(dp(10), dp(8), dp(10), dp(8));
        return button;
    }

    private EditText input(String hint, int inputType) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setTextSize(15);
        editText.setInputType(inputType);
        editText.setSingleLine((inputType & InputType.TYPE_TEXT_FLAG_MULTI_LINE) == 0);
        editText.setMinHeight(dp(52));
        return editText;
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, 6, 0, 6);
        return row;
    }

    private TextView text(String value, int sp, String color) {
        TextView textView = new TextView(this);
        textView.setText(value);
        textView.setTextSize(sp);
        textView.setTextColor(Color.parseColor(color));
        return textView;
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setMinWidth(dp(72));
        button.setPadding(dp(10), dp(8), dp(10), dp(8));
        button.setOnClickListener(listener);
        return button;
    }

    private void addRowButton(
            LinearLayout target,
            String label,
            View.OnClickListener listener
    ) {
        Button button = button(label, listener);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.WRAP_CONTENT,
                1f
        );
        params.setMarginStart(dp(2));
        params.setMarginEnd(dp(2));
        target.addView(button, params);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void restoreSettings() {
        serverUrlInput.setText(preferences.getString("server_url", ""));
        deviceIdInput.setText(preferences.getString("device_id", ""));
        usernameInput.setText(preferences.getString("username", ""));
        accessToken = sessionStore.accessToken();
        refreshToken = sessionStore.refreshToken();
        currentUserId = preferences.getString("user_id", null);
    }

    private void saveSettings() {
        preferences.edit()
                .putString("server_url", serverUrlInput.getText().toString().trim())
                .putString("device_id", deviceIdInput.getText().toString().trim())
                .putString("username", usernameInput.getText().toString().trim())
                .putString("user_id", currentUserId)
                .commit();
        sessionStore.save(accessToken, refreshToken, currentUserId);
    }

    private void rebuildApiClient() {
        String storedAccessToken = sessionStore.accessToken();
        if (storedAccessToken != null && !storedAccessToken.trim().isEmpty()) {
            accessToken = storedAccessToken;
        }
        apiClient = new FlowNoteApiClient(serverUrlInput.getText().toString(), getContentResolver());
        apiClient.setAccessToken(accessToken);
        apiClient.setAuthenticationFailureListener(this::clearRejectedSession);
    }

    private void login() {
        rebuildApiClient();
        updateStatus("로그인 중...");
        executor.execute(() -> {
            try {
                JSONObject payload = apiClient.login(
                        usernameInput.getText().toString(),
                        passwordInput.getText().toString(),
                        deviceIdInput.getText().toString()
                );
                accessToken = payload.getString("access_token");
                refreshToken = payload.getString("refresh_token");
                currentUserId = payload.getString("user_id");
                saveSettings();
                postStatus("로그인 완료: " + payload.optString("display_name"));
                mainHandler.post(() -> {
                    startNotificationDelivery();
                    refreshOutboxStatus();
                    retryOutbox(false);
                });
            } catch (Exception exc) {
                postStatus("로그인 실패: " + UserErrorMessage.from(exc));
                mainHandler.post(this::refreshOutboxStatus);
            }
        });
    }

    private void clearRejectedSession() {
        SecureViewerFiles.clean(this);
        accessToken = null;
        refreshToken = null;
        currentUserId = null;
        sessionStore.clear();
        stopService(new Intent(this, NotificationPollingService.class));
        mainHandler.post(this::refreshOutboxStatus);
    }

    private void logout() {
        rebuildApiClient();
        executor.execute(() -> {
            try {
                if (accessToken != null && !accessToken.trim().isEmpty()) {
                    apiClient.logout();
                }
            } catch (Exception ignored) {
                // Local session and secure files must still be cleared when the server is offline.
            } finally {
                clearRejectedSession();
                postStatus("로그아웃했습니다. 보안 열람 임시 파일을 정리했습니다.");
                mainHandler.post(this::refreshOutboxStatus);
            }
        });
    }

    private void loadPublishedDocuments() {
        rebuildApiClient();
        updateStatus("공개 문서 조회 중...");
        executor.execute(() -> {
            try {
                JSONArray documents = apiClient.listPublishedDocuments();
                mainHandler.post(() -> showDocuments(documents));
                postStatus("공개 문서 " + documents.length() + "건");
            } catch (Exception exc) {
                postStatus("문서 조회 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showDocuments(JSONArray documents) {
        contentArea.removeAllViews();
        for (int i = 0; i < documents.length(); i++) {
            JSONObject item = documents.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String documentId = item.optString("document_id");
            Button button = button(
                    item.optString("title") + "\n" + documentId,
                    view -> loadDocumentDetail(documentId)
            );
            button.setTextAlignment(View.TEXT_ALIGNMENT_TEXT_START);
            contentArea.addView(button);
        }
    }

    private void loadDocumentDetail(String documentId) {
        updateStatus("문서 상세 조회 중...");
        executor.execute(() -> {
            try {
                JSONObject document = apiClient.getDocument(documentId);
                mainHandler.post(() -> showDocumentDetail(document));
                postStatus("문서 상세 조회 완료");
            } catch (Exception exc) {
                postStatus("문서 상세 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showDocumentDetail(JSONObject document) {
        contentArea.removeAllViews();
        documentIdInput.setText(document.optString("document_id"));
        JSONObject published = document.optJSONObject("published_version");
        if (published != null) {
            versionIdInput.setText(published.optString("version_id"));
        }
        contentArea.addView(text("문서: " + document.optString("title"), 18, "#1F2A30"));
        contentArea.addView(text("상태: " + document.optString("status"), 15, "#3D4852"));
        contentArea.addView(text("설명: " + document.optString("description"), 15, "#3D4852"));
        if (published != null) {
            String documentId = document.optString("document_id");
            String versionId = published.optString("version_id");
            String title = document.optString("title");
            contentArea.addView(button("본문 보안 열람", view -> openSecureViewer(
                    documentId, versionId, title)));
        } else {
            contentArea.addView(text("현재 열람 가능한 공개 버전이 없습니다.", 15, "#8A3B12"));
        }
    }

    private void openSecureViewer(String documentId, String versionId, String title) {
        if (accessToken == null || accessToken.trim().isEmpty()) {
            updateStatus("로그인 후 문서를 열람하세요.");
            return;
        }
        Intent intent = new Intent(this, SecureDocumentViewerActivity.class);
        intent.putExtra(SecureDocumentViewerActivity.EXTRA_SERVER_URL,
                serverUrlInput.getText().toString().trim());
        intent.putExtra(SecureDocumentViewerActivity.EXTRA_ACCESS_TOKEN, accessToken);
        intent.putExtra(SecureDocumentViewerActivity.EXTRA_DOCUMENT_ID, documentId);
        intent.putExtra(SecureDocumentViewerActivity.EXTRA_VERSION_ID, versionId);
        intent.putExtra(SecureDocumentViewerActivity.EXTRA_TITLE, title);
        startActivity(intent);
    }

    private void loadNotifications() {
        rebuildApiClient();
        updateStatus("알림 조회 중...");
        executor.execute(() -> {
            try {
                JSONArray notifications = apiClient.listNotifications(false);
                mainHandler.post(() -> showNotifications(notifications));
                postStatus("알림 " + notifications.length() + "건");
            } catch (Exception exc) {
                postStatus("알림 조회 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showNotifications(JSONArray notifications) {
        contentArea.removeAllViews();
        for (int i = 0; i < notifications.length(); i++) {
            JSONObject item = notifications.optJSONObject(i);
            if (item == null) {
                continue;
            }
            String messageId = item.optString("message_id");
            Button button = button(
                    item.optString("channel_name") + " / " + item.optString("title"),
                    view -> markNotificationRead(messageId)
            );
            contentArea.addView(button);
        }
    }

    private void markNotificationRead(String messageId) {
        executor.execute(() -> {
            try {
                apiClient.markNotificationRead(
                        messageId,
                        preferences.getString("delivery_run_id", null),
                        preferences.getString("notification_displayed_at_" + messageId, null));
                postStatus("알림 읽음 처리 완료");
            } catch (Exception exc) {
                postStatus("알림 읽음 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void loadHandovers() {
        rebuildApiClient();
        updateStatus("인수인계 조회 중...");
        executor.execute(() -> {
            try {
                JSONArray handovers = apiClient.listHandovers();
                mainHandler.post(() -> showHandovers(handovers));
                postStatus("인수인계 " + handovers.length() + "건");
            } catch (Exception exc) {
                postStatus("인수인계 조회 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showHandovers(JSONArray handovers) {
        contentArea.removeAllViews();
        for (int i = 0; i < handovers.length(); i++) {
            JSONObject handover = handovers.optJSONObject(i);
            if (handover == null) {
                continue;
            }
            contentArea.addView(text(handover.optString("title"), 17, "#1F2A30"));
            contentArea.addView(text(handover.optString("body"), 15, "#3D4852"));
            JSONArray receipts = handover.optJSONArray("receipts");
            if (receipts == null) {
                continue;
            }
            for (int j = 0; j < receipts.length(); j++) {
                JSONObject receipt = receipts.optJSONObject(j);
                if (receipt == null || !receipt.optString("recipient_id").equals(currentUserId)) {
                    continue;
                }
                String handoverId = handover.optString("handover_id");
                String receiptId = receipt.optString("receipt_id");
                LinearLayout row = row();
                addRowButton(row, "읽음", view -> updateReceipt(handoverId, receiptId, "READ"));
                addRowButton(row, "확인", view -> updateReceipt(handoverId, receiptId, "ACKNOWLEDGED"));
                addRowButton(
                        row,
                        "후속 필요",
                        view -> updateReceipt(handoverId, receiptId, "FOLLOW_UP_REQUIRED")
                );
                contentArea.addView(row);
            }
        }
    }

    private void updateReceipt(String handoverId, String receiptId, String receiptStatus) {
        executor.execute(() -> {
            try {
                apiClient.updateHandoverReceipt(
                        handoverId,
                        receiptId,
                        receiptStatus,
                        null,
                        preferences.getString("delivery_run_id", null));
                postStatus("인수인계 상태 저장 완료");
            } catch (Exception exc) {
                postStatus("인수인계 상태 저장 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void pickPhoto() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, REQUEST_PICK_PHOTO);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_PICK_PHOTO || resultCode != RESULT_OK || data == null) {
            return;
        }
        selectedPhotoUri = data.getData();
        if (selectedPhotoUri != null) {
            getContentResolver().takePersistableUriPermission(
                    selectedPhotoUri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
            );
            photoStatusText.setText("사진 1장 선택됨 · 미리보기를 확인한 뒤 기기에 저장·전송하세요.");
            updateStatus("사진 선택 완료. 아래 미리보기를 확인하세요.");
            loadPhotoPreview(selectedPhotoUri);
        }
    }

    private void loadPhotoPreview(Uri photoUri) {
        if (Build.VERSION.SDK_INT < 29) {
            photoPreview.setVisibility(View.GONE);
            photoStatusText.setText(
                    "사진 1장 선택됨 · 기기에 저장·전송하기 전에 선택한 사진을 확인했습니다."
            );
            return;
        }
        executor.execute(() -> {
            try {
                Bitmap thumbnail = getContentResolver().loadThumbnail(
                        photoUri,
                        new Size(dp(320), dp(180)),
                        null
                );
                mainHandler.post(() -> {
                    if (photoUri.equals(selectedPhotoUri)) {
                        photoPreview.setImageBitmap(thumbnail);
                        photoPreview.setVisibility(View.VISIBLE);
                    }
                });
            } catch (Exception exc) {
                mainHandler.post(() -> {
                    photoPreview.setVisibility(View.GONE);
                    photoStatusText.setText(
                            "사진 1장 선택됨 · 미리보기를 열지 못했습니다. 사진을 다시 선택해 확인하세요."
                    );
                });
            }
        });
    }

    private void enqueueAndRetryComment() {
        String localId = UUID.randomUUID().toString();
        FieldCommentDraft draft = new FieldCommentDraft(
                localId,
                documentIdInput.getText().toString(),
                versionIdInput.getText().toString(),
                null,
                commentInput.getText().toString(),
                signalGroup.getCheckedRadioButtonId() != -1 ? "signal" : "free_text",
                signalLevel(),
                deviceIdInput.getText().toString(),
                currentUserId,
                selectedPhotoUri == null ? null : selectedPhotoUri.toString(),
                FieldCommentDraft.defaultIdempotencyKey(deviceIdInput.getText().toString(), localId)
        );
        if (!draft.canSend()) {
            updateStatus("문서 ID와 현장 기록 내용을 입력하세요.");
            return;
        }
        try {
            outbox.enqueueFieldComment(draft);
        } catch (Exception exc) {
            updateStatus("보안 임시 저장 실패: " + UserErrorMessage.from(exc));
            return;
        }
        selectedPhotoUri = null;
        photoPreview.setImageDrawable(null);
        photoPreview.setVisibility(View.GONE);
        photoStatusText.setText("사진 선택 안 됨");
        refreshOutboxStatus();
        updateStatus("기기에 암호화해 저장했습니다. 서버 전송을 시도합니다.");
        retryOutbox(false);
    }

    private String signalLevel() {
        int checked = signalGroup.getCheckedRadioButtonId();
        if (checked == 1) {
            return "green";
        }
        if (checked == 2) {
            return "yellow";
        }
        if (checked == 3) {
            return "red";
        }
        return null;
    }

    private void retryOutbox(boolean manual) {
        if (retryInProgress) {
            if (manual) {
                updateStatus("이미 전송을 시도하고 있습니다.");
            }
            return;
        }
        OutboxQueueStatus before = outbox.queueStatus(System.currentTimeMillis());
        if (before.pendingCount == 0) {
            refreshOutboxStatus();
            if (manual) {
                updateStatus("전송 대기 기록이 없습니다.");
            }
            return;
        }
        if (!sessionStore.hasSession()) {
            refreshOutboxStatus();
            updateStatus("현장 기록은 이 단말에 보존되어 있습니다. 다시 로그인한 뒤 전송합니다.");
            return;
        }
        retryInProgress = true;
        rebuildApiClient();
        updateStatus((manual ? "수동" : "자동") + " 재전송 중...");
        executor.execute(() -> {
            try {
                OfflineQueueStore.SyncSummary summary = outbox.retryPending(
                        apiClient,
                        currentUserId,
                        manual
                );
                if (summary.failedCount > 0) {
                    postStatus(
                            "현장 기록은 이 단말에 보존되어 있습니다. 성공 " + summary.successCount +
                                    "건, 실패 " + summary.failedCount +
                                    "건, 대기 " + summary.remainingCount +
                                    "건입니다. 네트워크와 로그인 상태를 확인하세요."
                    );
                } else {
                    postStatus(
                            "재전송 완료: 성공 " + summary.successCount +
                                    "건, 대기 " + summary.remainingCount + "건"
                    );
                }
            } catch (Exception exc) {
                postStatus("재전송 실패: " + UserErrorMessage.from(exc));
            } finally {
                retryInProgress = false;
                mainHandler.post(this::refreshOutboxStatus);
            }
        });
    }

    private void refreshOutboxStatus() {
        OutboxQueueStatus queueStatus = outbox.queueStatus(System.currentTimeMillis());
        outboxStatusText.setText(OutboxStatusMessage.format(
                queueStatus,
                System.currentTimeMillis(),
                sessionStore.hasSession(),
                deviceIdInput.getText().toString()
        ));
    }

    private void logOutboxAudit(Intent intent) {
        if (intent == null) {
            return;
        }
        String nonce = intent.getStringExtra(EXTRA_OUTBOX_AUDIT_NONCE);
        if (nonce == null || nonce.trim().isEmpty()) {
            return;
        }
        OutboxQueueStatus queueStatus = outbox.queueStatus(System.currentTimeMillis());
        Log.i(
                OUTBOX_LOG_TAG,
                "audit_nonce=" + nonce
                        + " pending=" + queueStatus.pendingCount
                        + " blocked=" + queueStatus.blockedCount
        );
    }

    private void updateStatus(String message) {
        statusText.setText(message);
    }

    private void postStatus(String message) {
        mainHandler.post(() -> updateStatus(message));
    }

    private void startNotificationDelivery() {
        if (!sessionStore.hasSession()) {
            return;
        }
        Intent intent = new Intent(this, NotificationPollingService.class);
        startForegroundService(intent);
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1002);
        }
    }
}
