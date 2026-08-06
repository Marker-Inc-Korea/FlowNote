package com.flownote.fieldapp;

import android.app.Activity;
import android.Manifest;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.Log;
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

public final class MainActivity extends Activity implements
        HandoverComposerView.Listener,
        ReceivedHandoverView.Listener,
        WorkSequenceController.Listener,
        DocumentBrowserController.Listener {
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
            if (!hasUsableSecureStorage()) {
                return;
            }
            OutboxQueueStatus queueStatus = outbox.queueStatus(System.currentTimeMillis());
            if (!retryInProgress && sessionStore.hasSession() && queueStatus.readyCount > 0) {
                retryOutbox(false);
            }
            mainHandler.postDelayed(this, OUTBOX_REFRESH_MILLIS);
        }
    };

    private SharedPreferences preferences;
    private MainUiFactory ui;
    private SecureSessionStore sessionStore;
    private HandoverSelectionCache handoverSelectionCache;
    private HandoverFollowUpDraftStore handoverFollowUpDraftStore;
    private OfflineQueueStore outbox;
    private FlowNoteApiClient apiClient;
    private WorkSequenceController workSequenceController;
    private DocumentBrowserController documentBrowserController;

    private EditText serverUrlInput;
    private EditText deviceIdInput;
    private EditText usernameInput;
    private EditText passwordInput;
    private EditText documentIdInput;
    private EditText versionIdInput;
    private EditText commentInput;
    private RadioGroup signalGroup;
    private TextView statusText;
    private OutboxStatusView outboxStatusView;
    private Button retryFailedButton;
    private TextView photoStatusText;
    private ImageView photoPreview;
    private LinearLayout contentArea;
    private HandoverComposerView handoverComposer;
    private Uri selectedPhotoUri;
    private String accessToken;
    private String refreshToken;
    private String currentUserId;
    private String currentCustomerScope;
    private String currentSiteScope;
    private WorkSequenceSource selectedWorkSequenceSource;
    private String secureStorageError;
    private volatile boolean retryInProgress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ui = new MainUiFactory(this);
        preferences = getSharedPreferences("flownote-field-app", MODE_PRIVATE);
        SecureViewerFiles.clean(this);
        buildUi();
        serverUrlInput.setText(preferences.getString("server_url", ""));
        deviceIdInput.setText(preferences.getString("device_id", ""));
        usernameInput.setText(preferences.getString("username", ""));
        try {
            sessionStore = new SecureSessionStore(this);
            handoverSelectionCache = new HandoverSelectionCache(this);
            handoverFollowUpDraftStore = new HandoverFollowUpDraftStore(this);
            outbox = new OfflineQueueStore(this);
            workSequenceController = new WorkSequenceController(this, contentArea, this);
            restoreSettings();
        } catch (RuntimeException exc) {
            secureStorageError = UserErrorMessage.from(exc);
        }
        handoverComposer.setIdentity(deviceIdInput.getText().toString(), currentUserId);
        documentBrowserController = new DocumentBrowserController(this, contentArea, this);
        if (!hasUsableSecureStorage()) {
            showSecureStorageError();
            return;
        }
        rebuildApiClient();
        restoreCachedHandoverOptions();
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
        if (outbox != null) {
            outbox.close();
        }
        if (workSequenceController != null) {
            workSequenceController.close();
        }
        if (documentBrowserController != null) {
            documentBrowserController.close();
        }
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

        outboxStatusView = new OutboxStatusView(this);
        root.addView(outboxStatusView);

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
        root.addView(loginRow);
        retryFailedButton = button("실패 항목 다시 보내기", view -> retryOutbox(true));
        retryFailedButton.setEnabled(false);
        root.addView(retryFailedButton);

        LinearLayout navRow = row();
        addRowButton(navRow, "공개 문서", view -> loadPublishedDocuments());
        addRowButton(navRow, "알림", view -> loadNotifications());
        addRowButton(navRow, "인수인계", view -> loadHandovers());
        root.addView(navRow);
        root.addView(button("오늘의 작업순서", view -> loadWorkSequences()));

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

        handoverComposer = new HandoverComposerView(this, this);
        root.addView(handoverComposer);

        contentArea = new LinearLayout(this);
        contentArea.setOrientation(LinearLayout.VERTICAL);
        root.addView(contentArea);

        setContentView(scrollView);
    }

    private TextView radioButton(String label, int id) { return ui.radioButton(label, id); }
    private EditText input(String hint, int type) { return ui.input(hint, type); }
    private LinearLayout row() { return ui.row(); }
    private TextView text(String value, int sp, String color) { return ui.text(value, sp, color); }
    private Button button(String label, View.OnClickListener call) { return ui.button(label, call); }
    private void addRowButton(LinearLayout row, String label, View.OnClickListener call) { ui.addRowButton(row, label, call); }
    private int dp(int value) { return ui.dp(value); }

    private void restoreSettings() {
        serverUrlInput.setText(preferences.getString("server_url", ""));
        deviceIdInput.setText(preferences.getString("device_id", ""));
        usernameInput.setText(preferences.getString("username", ""));
        if (sessionStore == null) {
            return;
        }
        accessToken = sessionStore.accessToken();
        refreshToken = sessionStore.refreshToken();
        currentUserId = preferences.getString("user_id", null);
        currentCustomerScope = preferences.getString("customer_scope", null);
        currentSiteScope = preferences.getString("site_scope", null);
    }

    private void saveSettings() {
        preferences.edit()
                .putString("server_url", serverUrlInput.getText().toString().trim())
                .putString("device_id", deviceIdInput.getText().toString().trim())
                .putString("username", usernameInput.getText().toString().trim())
                .putString("user_id", currentUserId)
                .putString("customer_scope", currentCustomerScope)
                .putString("site_scope", currentSiteScope)
                .commit();
        sessionStore.save(accessToken, refreshToken, currentUserId);
    }

    private void rebuildApiClient() {
        String storedAccessToken = sessionStore == null ? null : sessionStore.accessToken();
        if (storedAccessToken != null && !storedAccessToken.trim().isEmpty()) {
            accessToken = storedAccessToken;
        }
        apiClient = new FlowNoteApiClient(serverUrlInput.getText().toString(), getContentResolver());
        apiClient.setAccessToken(accessToken);
        apiClient.setAuthenticationFailureListener(this::clearRejectedSession);
        apiClient.setRefreshSession(
                refreshToken,
                currentCustomerScope,
                currentSiteScope,
                this::saveRefreshedSession
        );
    }

    private void login() {
        if (!requireSecureStorage()) {
            return;
        }
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
                currentCustomerScope = payload.getString("customer_scope");
                currentSiteScope = payload.getString("site_scope");
                saveSettings();
                postStatus("로그인 완료: " + payload.optString("display_name"));
                mainHandler.post(() -> {
                    handoverComposer.setIdentity(
                            deviceIdInput.getText().toString(),
                            currentUserId
                    );
                    restoreCachedHandoverOptions();
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
        clearHandoverSelectionCache();
        SecureViewerFiles.clean(this);
        accessToken = null;
        refreshToken = null;
        currentUserId = null;
        currentCustomerScope = null;
        currentSiteScope = null;
        selectedWorkSequenceSource = null;
        if (sessionStore != null) {
            sessionStore.clear();
        }
        if (workSequenceController != null) {
            workSequenceController.clearVisible();
        }
        contentArea.removeAllViews();
        preferences.edit().remove("customer_scope").remove("site_scope").commit();
        stopService(new Intent(this, NotificationPollingService.class));
        mainHandler.post(this::refreshOutboxStatus);
    }

    private void logout() {
        if (!requireSecureStorage()) {
            return;
        }
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
        if (!requireSecureStorage()) {
            return;
        }
        rebuildApiClient();
        documentBrowserController.show(apiClient);
    }

    private void openSecureViewer(String documentId, String versionId, String title) {
        if (!requireSecureStorage()) {
            return;
        }
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

    @Override
    public void onOpenPublishedDocument(String documentId, String versionId, String title) {
        openSecureViewer(documentId, versionId, title);
    }

    @Override
    public void onOpenDocument(String documentId, String versionId, String title) {
        openSecureViewer(documentId, versionId, title);
    }

    @Override
    public void onDocumentSelected(String documentId, String versionId) {
        selectedWorkSequenceSource = null;
        documentIdInput.setText(documentId);
        versionIdInput.setText(versionId);
        handoverComposer.setDocumentSource(documentId, versionId);
    }

    @Override
    public void onStatus(String message) { postStatus(message); }

    private void loadWorkSequences() {
        if (!requireSecureStorage() || !sessionStore.hasSession()) {
            updateStatus("승인 단말로 로그인한 뒤 작업순서를 열람하세요.");
            return;
        }
        rebuildApiClient();
        workSequenceController.show(apiClient, workSequenceScope());
    }

    @Override
    public void onStartFieldComment(WorkSequenceSource source, String itemTitle) {
        if (!source.canCreateFieldComment()) {
            updateStatus("현재 공개 문서가 없어 이 작업순서에서 FieldComment를 시작할 수 없습니다.");
            return;
        }
        selectedWorkSequenceSource = source;
        documentIdInput.setText(source.documentId);
        versionIdInput.setText(source.documentVersionId);
        commentInput.requestFocus();
        updateStatus("작업순서 원천과 공개 문서 버전을 고정했습니다. 내용만 확인해 제출하세요.");
    }

    @Override
    public void onStartHandover(WorkSequenceSource source, String itemTitle) {
        handoverComposer.setWorkSequenceSource(source, itemTitle);
        updateStatus("작업순서 원천을 인수인계에 고정했습니다. 채널·수신자와 내용을 확인하세요.");
    }

    private WorkSequenceScope workSequenceScope() {
        return new WorkSequenceScope(
                serverUrlInput.getText().toString(),
                currentCustomerScope,
                currentSiteScope,
                currentUserId,
                deviceIdInput.getText().toString()
        );
    }

    private void saveRefreshedSession(JSONObject payload) {
        try {
            accessToken = payload.getString("access_token");
            refreshToken = payload.getString("refresh_token");
            currentCustomerScope = payload.getString("customer_scope");
            currentSiteScope = payload.getString("site_scope");
            saveSettings();
        } catch (Exception exc) {
            clearRejectedSession();
        }
    }

    private void loadNotifications() {
        if (!requireSecureStorage()) {
            return;
        }
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
            String sourceType = item.optString("source_type");
            String sourceId = item.optString("source_id");
            Button button = button(
                    item.optString("channel_name") + " / " + item.optString("title"),
                    view -> openNotification(messageId, sourceType, sourceId)
            );
            contentArea.addView(button);
        }
    }

    private void openNotification(String messageId, String sourceType, String sourceId) {
        markNotificationRead(messageId);
        if ("WORK_SEQUENCE_ITEM".equals(sourceType) && !sourceId.isEmpty()) {
            rebuildApiClient();
            workSequenceController.openByItem(apiClient, workSequenceScope(), sourceId);
        }
    }

    private void markNotificationRead(String messageId) {
        if (!requireSecureStorage()) {
            return;
        }
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
        if (!requireSecureStorage()) {
            return;
        }
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
        ReceivedHandoverView receivedView = new ReceivedHandoverView(
                this,
                this,
                handoverFollowUpDraftStore,
                serverUrlInput.getText().toString(),
                currentUserId,
                deviceIdInput.getText().toString(),
                preferences.getString("delivery_run_id", null)
        );
        receivedView.show(handovers);
        contentArea.addView(receivedView);
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
            try {
                getContentResolver().takePersistableUriPermission(
                        selectedPhotoUri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION
                );
            } catch (SecurityException exc) {
                updateStatus("사진 접근 권한을 유지하지 못했습니다. 사진을 다시 선택하세요.");
                selectedPhotoUri = null;
                return;
            }
            photoStatusText.setText("사진 1장 선택됨 · 미리보기를 확인한 뒤 기기에 저장·전송하세요.");
            updateStatus("사진 선택 완료. 아래 미리보기를 확인하세요.");
            loadPhotoPreview(selectedPhotoUri);
        }
    }

    private void loadPhotoPreview(Uri photoUri) {
        executor.execute(() -> {
            try {
                Bitmap thumbnail = PhotoPreviewLoader.load(
                        getContentResolver(),
                        photoUri,
                        dp(320),
                        dp(180)
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
        if (!requireSecureStorage()) {
            return;
        }
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
                selectedWorkSequenceSource == null
                        ? FieldCommentDraft.defaultIdempotencyKey(
                                deviceIdInput.getText().toString(), localId) : null,
                selectedWorkSequenceSource
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
        commentInput.setText("");
        signalGroup.clearCheck();
        selectedWorkSequenceSource = null;
        commentInput.requestFocus();
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
        if (!requireSecureStorage()) {
            return;
        }
        if (retryInProgress) {
            if (manual) {
                updateStatus("이미 전송을 시도하고 있습니다.");
            }
            return;
        }
        OutboxQueueStatus before = outbox.queueStatus(System.currentTimeMillis());
        if (manual && before.failedCount == 0) {
            refreshOutboxStatus();
            updateStatus("다시 보낼 실패 항목이 없습니다. 전송 대기 항목은 자동으로 전송합니다.");
            return;
        }
        if (!manual && before.pendingCount == 0) {
            refreshOutboxStatus();
            return;
        }
        if (!sessionStore.hasSession()) {
            refreshOutboxStatus();
            updateStatus("현장 기록은 이 단말에 보존되어 있습니다. 다시 로그인한 뒤 전송합니다.");
            return;
        }
        retryInProgress = true;
        retryFailedButton.setEnabled(false);
        rebuildApiClient();
        updateStatus(manual ? "실패 항목만 다시 보내는 중..." : "대기 항목 자동 전송 중...");
        executor.execute(() -> {
            try {
                OfflineQueueStore.SyncSummary summary = manual
                        ? outbox.retryFailed(apiClient, currentUserId)
                        : outbox.retryPending(apiClient, currentUserId);
                if (summary.failedCount > 0) {
                    String partial = summary.partialSuccessCount > 0
                            ? ", 원천 저장 후 사진·채널 알림 재전송 대기 "
                            + summary.partialSuccessCount + "건"
                            : "";
                    postStatus(
                            "현장 기록은 이 단말에 보존되어 있습니다. 완료 " + summary.successCount +
                                    "건" + partial +
                                    ", 실패 " + summary.failedCount +
                                    "건, 대기 " + summary.remainingCount +
                                    "건입니다. " + summary.lastErrorMessage
                    );
                } else {
                    postStatus(
                            (manual ? "실패 항목 다시 보내기 완료: 성공 " : "자동 전송 완료: 성공 ")
                                    + summary.successCount +
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
        if (!hasUsableSecureStorage()) {
            outboxStatusView.showStorageError(
                    "보안 저장소 오류 · 입력을 저장하거나 전송하지 않습니다. 재설치·초기화하지 말고 관리자에게 단말 교체 점검을 요청하세요."
            );
            retryFailedButton.setEnabled(false);
            return;
        }
        OutboxQueueStatus queueStatus = outbox.queueStatus(System.currentTimeMillis());
        outboxStatusView.show(queueStatus, OutboxStatusMessage.format(
                queueStatus,
                System.currentTimeMillis(),
                sessionStore.hasSession(),
                deviceIdInput.getText().toString()
        ));
        retryFailedButton.setEnabled(
                !retryInProgress && sessionStore.hasSession() && queueStatus.failedCount > 0
        );
    }

    private void logOutboxAudit(Intent intent) {
        if (intent == null) {
            return;
        }
        if (!hasUsableSecureStorage()) {
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
                        + " failed=" + queueStatus.failedCount
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
        if (!hasUsableSecureStorage() || !sessionStore.hasSession()) {
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

    @Override
    public void onRefreshChannels() {
        if (!requireSecureStorage()) {
            return;
        }
        if (!sessionStore.hasSession()) {
            handoverComposer.showStatus("로그인한 뒤 업무 채널과 수신자를 불러오세요.");
            return;
        }
        handoverComposer.setIdentity(deviceIdInput.getText().toString(), currentUserId);
        rebuildApiClient();
        String cacheServerUrl = serverUrlInput.getText().toString();
        String cacheUserId = currentUserId;
        handoverComposer.showStatus("업무 채널을 불러오는 중...");
        executor.execute(() -> {
            try {
                JSONArray channels = apiClient.listNotificationChannels();
                handoverSelectionCache.saveChannels(
                        cacheServerUrl,
                        cacheUserId,
                        channels
                );
                mainHandler.post(() -> handoverComposer.setChannels(channels));
            } catch (Exception exc) {
                mainHandler.post(() -> handoverComposer.showStatus(
                        "채널 조회 실패: " + UserErrorMessage.from(exc)
                ));
            }
        });
    }

    @Override
    public void onChannelSelected(String channelId) {
        if (!requireSecureStorage()) {
            return;
        }
        if (!sessionStore.hasSession()) {
            handoverComposer.showStatus("로그인한 뒤 수신자를 불러오세요.");
            return;
        }
        rebuildApiClient();
        String cacheServerUrl = serverUrlInput.getText().toString();
        String cacheUserId = currentUserId;
        JSONArray cachedMembers = handoverSelectionCache.members(
                cacheServerUrl,
                cacheUserId,
                channelId
        );
        if (cachedMembers.length() > 0) {
            handoverComposer.setMembers(cachedMembers);
            handoverComposer.showStatus(
                    "마지막으로 확인한 수신자를 표시했습니다. 서버 최신 상태를 확인하는 중..."
            );
        } else {
            handoverComposer.showStatus("활성 수신자를 불러오는 중...");
        }
        executor.execute(() -> {
            try {
                JSONArray members = apiClient.listChannelMembers(channelId);
                handoverSelectionCache.saveMembers(
                        cacheServerUrl,
                        cacheUserId,
                        channelId,
                        members
                );
                mainHandler.post(() -> handoverComposer.setMembers(members));
            } catch (Exception exc) {
                mainHandler.post(() -> handoverComposer.showStatus(
                        "수신자 조회 실패: " + UserErrorMessage.from(exc)
                ));
            }
        });
    }

    @Override
    public void onQueue(HandoverDraft draft) {
        if (!requireSecureStorage()) {
            return;
        }
        if (!draft.canQueue()) {
            handoverComposer.showStatus(
                    "채널, 수신자, 원천 ID, 제목과 내용을 모두 입력하세요. 로그인 상태도 확인하세요."
            );
            return;
        }
        try {
            outbox.enqueueHandover(draft);
        } catch (Exception exc) {
            handoverComposer.showStatus("보안 임시 저장 실패: " + UserErrorMessage.from(exc));
            return;
        }
        handoverComposer.resetAfterQueued();
        refreshOutboxStatus();
        updateStatus("인수인계를 기기에 암호화해 저장했습니다. 서버 전송을 시도합니다.");
        retryOutbox(false);
    }

    @Override
    public boolean onQueueReceipt(HandoverReceiptDraft draft) {
        if (!requireSecureStorage() || !draft.canQueue()) {
            updateStatus("확인 또는 보류할 인수인계 상태를 다시 선택하세요.");
            return false;
        }
        try {
            outbox.enqueueHandoverReceipt(draft);
        } catch (Exception exc) {
            updateStatus("인수인계 상태 보존 실패: " + UserErrorMessage.from(exc));
            return false;
        }
        refreshOutboxStatus();
        updateStatus("확인·보류 상태를 기기에 보존했습니다. 연결되면 서버에 이어서 반영합니다.");
        retryOutbox(false);
        return true;
    }

    @Override
    public boolean onQueueFollowUp(HandoverFollowUpDraft draft) {
        if (!requireSecureStorage() || !draft.canQueue()) {
            updateStatus("후속 FieldComment 내용과 연결된 원천을 확인하세요. 입력 내용은 보존됩니다.");
            return false;
        }
        try {
            outbox.enqueueHandoverFollowUp(draft);
        } catch (Exception exc) {
            updateStatus("후속 FieldComment 보존 실패: " + UserErrorMessage.from(exc));
            return false;
        }
        refreshOutboxStatus();
        updateStatus("후속 FieldComment를 기기에 보존했습니다. 코멘트 저장 후 알림이 실패하면 알림만 재시도합니다.");
        retryOutbox(false);
        return true;
    }

    private boolean hasUsableSecureStorage() {
        return secureStorageError == null
                && sessionStore != null
                && handoverSelectionCache != null
                && handoverFollowUpDraftStore != null
                && outbox != null
                && workSequenceController != null;
    }

    private boolean requireSecureStorage() {
        if (hasUsableSecureStorage()) {
            return true;
        }
        showSecureStorageError();
        return false;
    }

    private void showSecureStorageError() {
        String message = secureStorageError == null
                ? "단말 보안 저장소를 열 수 없습니다. 관리자에게 단말 교체 점검을 요청하세요."
                : secureStorageError;
        updateStatus(message);
        refreshOutboxStatus();
        handoverComposer.showStatus(message);
    }

    private void restoreCachedHandoverOptions() {
        if (!sessionStore.hasSession() || currentUserId == null) {
            return;
        }
        JSONArray cached = handoverSelectionCache.channels(
                serverUrlInput.getText().toString(),
                currentUserId
        );
        if (cached.length() > 0) {
            handoverComposer.setChannels(cached);
            handoverComposer.showStatus(
                    "마지막으로 확인한 채널을 표시했습니다. 단절 중에도 작성 후 기기에 저장할 수 있습니다."
            );
        }
    }

    private void clearHandoverSelectionCache() {
        if (handoverSelectionCache == null || currentUserId == null) {
            return;
        }
        handoverSelectionCache.clear(
                serverUrlInput.getText().toString(),
                currentUserId
        );
    }
}
