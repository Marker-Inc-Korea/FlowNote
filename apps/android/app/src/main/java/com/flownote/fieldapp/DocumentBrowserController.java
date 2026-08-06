package com.flownote.fieldapp;

import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class DocumentBrowserController implements AutoCloseable {
    interface Listener {
        void onStatus(String message);

        void onDocumentSelected(String documentId, String versionId);

        void onOpenDocument(String documentId, String versionId, String title);
    }

    private final Context context;
    private final LinearLayout contentArea;
    private final Listener listener;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private FlowNoteApiClient apiClient;

    DocumentBrowserController(Context context, LinearLayout contentArea, Listener listener) {
        this.context = context;
        this.contentArea = contentArea;
        this.listener = listener;
    }

    void show(FlowNoteApiClient apiClient) {
        this.apiClient = apiClient;
        listener.onStatus("공개 문서 조회 중...");
        executor.execute(() -> {
            try {
                JSONArray documents = apiClient.listPublishedDocuments();
                mainHandler.post(() -> showDocuments(documents));
                listener.onStatus("공개 문서 " + documents.length() + "건");
            } catch (Exception exc) {
                listener.onStatus("문서 조회 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showDocuments(JSONArray documents) {
        contentArea.removeAllViews();
        for (int index = 0; index < documents.length(); index++) {
            JSONObject item = documents.optJSONObject(index);
            if (item == null) {
                continue;
            }
            String documentId = item.optString("document_id");
            Button button = button(item.optString("title") + "\n" + documentId);
            button.setTextAlignment(View.TEXT_ALIGNMENT_TEXT_START);
            button.setContentDescription("공개 문서 " + item.optString("title") + " 상세 열기");
            button.setOnClickListener(view -> loadDetail(documentId));
            contentArea.addView(button);
        }
    }

    private void loadDetail(String documentId) {
        listener.onStatus("문서 상세 조회 중...");
        executor.execute(() -> {
            try {
                JSONObject document = apiClient.getDocument(documentId);
                mainHandler.post(() -> showDetail(document));
                listener.onStatus("문서 상세 조회 완료");
            } catch (Exception exc) {
                listener.onStatus("문서 상세 실패: " + UserErrorMessage.from(exc));
            }
        });
    }

    private void showDetail(JSONObject document) {
        contentArea.removeAllViews();
        JSONObject published = document.optJSONObject("published_version");
        if (published != null) {
            listener.onDocumentSelected(
                    document.optString("document_id"),
                    published.optString("version_id")
            );
        }
        contentArea.addView(text("문서: " + document.optString("title"), 18, "#1F2A30"));
        contentArea.addView(text("상태: " + document.optString("status"), 15, "#3D4852"));
        contentArea.addView(text("설명: " + document.optString("description"), 15, "#3D4852"));
        if (published != null) {
            String documentId = document.optString("document_id");
            String versionId = published.optString("version_id");
            String title = document.optString("title");
            Button open = button("본문 보안 열람");
            open.setOnClickListener(view -> listener.onOpenDocument(documentId, versionId, title));
            contentArea.addView(open);
        } else {
            contentArea.addView(text("현재 열람 가능한 공개 버전이 없습니다.", 15, "#8A3B12"));
        }
    }

    private Button button(String label) {
        Button button = new Button(context);
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setPadding(dp(10), dp(8), dp(10), dp(8));
        return button;
    }

    private TextView text(String value, int size, String color) {
        TextView text = new TextView(context);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(Color.parseColor(color));
        return text;
    }

    private int dp(int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    @Override
    public void close() {
        executor.shutdownNow();
    }
}
