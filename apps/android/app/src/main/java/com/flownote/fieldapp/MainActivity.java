package com.flownote.fieldapp;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
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

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private SharedPreferences preferences;
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
    private LinearLayout contentArea;
    private Uri selectedPhotoUri;
    private String accessToken;
    private String currentUserId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences("flownote-field-app", MODE_PRIVATE);
        outbox = new OfflineQueueStore(this);
        buildUi();
        restoreSettings();
        rebuildApiClient();
        updateStatus("서버 주소와 승인 단말 ID를 확인한 뒤 로그인하세요.");
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

        serverUrlInput = input("서버 주소 예: http://10.0.0.10:8000", InputType.TYPE_CLASS_TEXT);
        deviceIdInput = input("승인 단말 ID", InputType.TYPE_CLASS_TEXT);
        usernameInput = input("사용자 ID", InputType.TYPE_CLASS_TEXT);
        passwordInput = input("비밀번호", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(serverUrlInput);
        root.addView(deviceIdInput);
        root.addView(usernameInput);
        root.addView(passwordInput);

        LinearLayout loginRow = row();
        loginRow.addView(button("로그인", view -> login()));
        loginRow.addView(button("재전송", view -> retryOutbox()));
        root.addView(loginRow);

        LinearLayout navRow = row();
        navRow.addView(button("공개 문서", view -> loadPublishedDocuments()));
        navRow.addView(button("알림", view -> loadNotifications()));
        navRow.addView(button("인수인계", view -> loadHandovers()));
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
        commentRow.addView(button("사진 선택", view -> pickPhoto()));
        commentRow.addView(button("저장/전송", view -> enqueueAndRetryComment()));
        root.addView(commentRow);

        statusText = text("", 14, "#3D4852");
        statusText.setPadding(0, 16, 0, 16);
        root.addView(statusText);

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
        return button;
    }

    private EditText input(String hint, int inputType) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setTextSize(15);
        editText.setInputType(inputType);
        editText.setSingleLine((inputType & InputType.TYPE_TEXT_FLAG_MULTI_LINE) == 0);
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
        button.setAllCaps(false);
        button.setOnClickListener(listener);
        return button;
    }

    private void restoreSettings() {
        serverUrlInput.setText(preferences.getString("server_url", ""));
        deviceIdInput.setText(preferences.getString("device_id", ""));
        usernameInput.setText(preferences.getString("username", ""));
        accessToken = preferences.getString("access_token", null);
        currentUserId = preferences.getString("user_id", null);
    }

    private void saveSettings() {
        preferences.edit()
                .putString("server_url", serverUrlInput.getText().toString().trim())
                .putString("device_id", deviceIdInput.getText().toString().trim())
                .putString("username", usernameInput.getText().toString().trim())
                .putString("access_token", accessToken)
                .putString("user_id", currentUserId)
                .apply();
    }

    private void rebuildApiClient() {
        apiClient = new FlowNoteApiClient(serverUrlInput.getText().toString(), getContentResolver());
        apiClient.setAccessToken(accessToken);
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
                currentUserId = payload.getString("user_id");
                saveSettings();
                postStatus("로그인 완료: " + payload.optString("display_name"));
            } catch (Exception exc) {
                postStatus("로그인 실패: " + exc.getMessage());
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
                postStatus("문서 조회 실패: " + exc.getMessage());
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
                postStatus("문서 상세 실패: " + exc.getMessage());
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
                postStatus("알림 조회 실패: " + exc.getMessage());
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
                apiClient.markNotificationRead(messageId);
                postStatus("알림 읽음 처리 완료");
            } catch (Exception exc) {
                postStatus("알림 읽음 실패: " + exc.getMessage());
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
                postStatus("인수인계 조회 실패: " + exc.getMessage());
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
                row.addView(button("읽음", view -> updateReceipt(handoverId, receiptId, "READ")));
                row.addView(button("확인", view -> updateReceipt(handoverId, receiptId, "ACKNOWLEDGED")));
                row.addView(button("후속필요", view -> updateReceipt(handoverId, receiptId, "FOLLOW_UP_REQUIRED")));
                contentArea.addView(row);
            }
        }
    }

    private void updateReceipt(String handoverId, String receiptId, String receiptStatus) {
        executor.execute(() -> {
            try {
                apiClient.updateHandoverReceipt(handoverId, receiptId, receiptStatus, null);
                postStatus("인수인계 상태 저장 완료");
            } catch (Exception exc) {
                postStatus("인수인계 상태 저장 실패: " + exc.getMessage());
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
            updateStatus("사진 선택 완료");
        }
    }

    private void enqueueAndRetryComment() {
        String localId = UUID.randomUUID().toString();
        FieldCommentDraft draft = new FieldCommentDraft(
                localId,
                documentIdInput.getText().toString(),
                versionIdInput.getText().toString(),
                null,
                commentInput.getText().toString(),
                signalGroup.getCheckedRadioButtonId() > 0 ? "signal" : "free_text",
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
        outbox.enqueueFieldComment(draft);
        selectedPhotoUri = null;
        updateStatus("임시 저장 완료. 서버 전송을 시도합니다.");
        retryOutbox();
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

    private void retryOutbox() {
        rebuildApiClient();
        updateStatus("재전송 중...");
        executor.execute(() -> {
            OfflineQueueStore.SyncSummary summary = outbox.retryPending(apiClient, currentUserId);
            postStatus(
                    "재전송 완료: 성공 " + summary.successCount +
                            "건, 실패 " + summary.failedCount +
                            "건, 대기 " + summary.remainingCount + "건"
            );
        });
    }

    private void updateStatus(String message) {
        statusText.setText(message);
    }

    private void postStatus(String message) {
        mainHandler.post(() -> updateStatus(message));
    }
}
