package com.flownote.fieldapp;

import android.content.Context;
import android.graphics.Color;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.DateFormat;
import java.util.Date;

final class WorkSequenceView extends LinearLayout {
    interface Listener {
        void onRefresh(String date, String lineCode, boolean archived);

        void onLoadMore();

        void onOpenBoard(String boardId, int revision);

        void onOpenDocument(String documentId, String versionId, String title);

        void onStartFieldComment(WorkSequenceSource source, String itemTitle);

        void onStartHandover(WorkSequenceSource source, String itemTitle);
    }

    private final Listener listener;
    private final EditText dateInput;
    private final EditText lineInput;
    private final CheckBox archivedInput;
    private final TextView stateText;
    private final LinearLayout results;
    private final Button moreButton;
    private WorkSequenceScope scope;

    WorkSequenceView(Context context, Listener listener) {
        super(context);
        this.listener = listener;
        setOrientation(VERTICAL);
        setPadding(0, dp(12), 0, dp(18));

        TextView heading = text("오늘의 작업순서", 20, "#1F2A30");
        heading.setContentDescription("오늘의 작업순서 화면");
        addView(heading);
        addView(text("날짜와 라인을 확인하고 작업판을 선택하세요. 상태 변경은 관리자용 Windows 앱에서 합니다.",
                14, "#3D4852"));

        dateInput = input("작업 날짜 (YYYY-MM-DD)");
        dateInput.setContentDescription("작업판 날짜 필터");
        lineInput = input("라인 코드 (선택)");
        lineInput.setContentDescription("작업판 라인 필터");
        archivedInput = new CheckBox(context);
        archivedInput.setText("보관 작업판 보기");
        archivedInput.setTextSize(15);
        archivedInput.setMinHeight(dp(56));
        archivedInput.setContentDescription("보관 작업판 표시 여부");
        addView(dateInput, fullWidth());
        addView(lineInput, fullWidth());
        addView(archivedInput, fullWidth());

        Button refresh = button("작업판 새로고침");
        refresh.setContentDescription("선택한 날짜와 라인의 작업판 새로고침");
        refresh.setOnClickListener(view -> listener.onRefresh(
                dateInput.getText().toString().trim(),
                lineInput.getText().toString().trim(),
                archivedInput.isChecked()
        ));
        addView(refresh, fullWidth());

        stateText = text("작업판을 불러오지 않았습니다.", 14, "#3D4852");
        stateText.setPadding(dp(12), dp(10), dp(12), dp(10));
        stateText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        addView(stateText, fullWidth());

        results = new LinearLayout(context);
        results.setOrientation(VERTICAL);
        addView(results, fullWidth());

        moreButton = button("다음 작업판 불러오기");
        moreButton.setOnClickListener(view -> listener.onLoadMore());
        moreButton.setVisibility(GONE);
        addView(moreButton, fullWidth());
    }

    void bindScope(WorkSequenceScope scope, JSONObject filter, String today) {
        this.scope = scope;
        dateInput.setText(filter.optString("date", today));
        lineInput.setText(filter.optString("line", ""));
        archivedInput.setChecked(filter.optBoolean("archived", false));
    }

    String dateFilter() {
        return dateInput.getText().toString().trim();
    }

    String lineFilter() {
        return lineInput.getText().toString().trim();
    }

    boolean archivedFilter() {
        return archivedInput.isChecked();
    }

    void showLoading(String message) {
        stateText.setText(message);
    }

    void clearForScopeChange() {
        results.removeAllViews();
        moreButton.setVisibility(GONE);
        stateText.setText("현재 로그인 scope의 작업판을 확인하는 중...");
    }

    void showList(JSONObject page, boolean offline, long savedAt) {
        results.removeAllViews();
        JSONArray boards = page.optJSONArray("items");
        if (boards == null || boards.length() == 0) {
            results.addView(text("선택한 조건에서 열람 가능한 작업판이 없습니다.", 15, "#8A3B12"));
        } else {
            for (int index = 0; index < boards.length(); index++) {
                JSONObject board = boards.optJSONObject(index);
                if (board == null) {
                    continue;
                }
                String boardId = board.optString("board_id");
                int revision = board.optInt("board_revision");
                String label = board.optString("title") + "\n"
                        + nullable(board.optString("line_code", null), "라인 미지정") + " · "
                        + board.optInt("item_count") + "개 항목 · revision " + revision;
                Button button = button(label);
                button.setTextAlignment(TEXT_ALIGNMENT_TEXT_START);
                button.setContentDescription("작업판 " + board.optString("title")
                        + ", 항목 " + board.optInt("item_count") + "개, 상세 열기");
                button.setOnClickListener(view -> listener.onOpenBoard(boardId, revision));
                results.addView(button, fullWidth());
            }
        }
        boolean hasMore = page.optBoolean("has_more", false);
        moreButton.setVisibility(hasMore ? VISIBLE : GONE);
        String refreshed = savedAt > 0 ? DateFormat.getDateTimeInstance().format(new Date(savedAt))
                : page.optString("refreshed_at", "방금");
        stateText.setText((offline ? "오프라인 읽기 · 마지막 snapshot " : "서버 갱신 완료 · ")
                + refreshed + " · " + page.optInt("total", boards == null ? 0 : boards.length()) + "건");
    }

    void showBoard(JSONObject board, boolean offline, long savedAt) {
        results.removeAllViews();
        moreButton.setVisibility(GONE);
        results.addView(text(board.optString("title"), 20, "#1F2A30"));
        results.addView(text(
                nullable(board.optString("board_date", null), "날짜 미지정") + " · "
                        + nullable(board.optString("line_code", null), "라인 미지정") + " · revision "
                        + board.optInt("board_revision"),
                15,
                "#3D4852"
        ));
        JSONArray items = board.optJSONArray("items");
        for (int index = 0; items != null && index < items.length(); index++) {
            JSONObject item = items.optJSONObject(index);
            if (item != null) {
                showItem(board, item);
            }
        }
        String refreshed = savedAt > 0 ? DateFormat.getDateTimeInstance().format(new Date(savedAt)) : "방금";
        stateText.setText((offline ? "오프라인 상세 · 마지막 snapshot " : "현재 권한·revision 확인 완료 · ")
                + refreshed);
    }

    private void showItem(JSONObject board, JSONObject item) {
        LinearLayout card = new LinearLayout(getContext());
        card.setOrientation(VERTICAL);
        card.setPadding(dp(12), dp(12), dp(12), dp(12));
        int order = item.optInt("sort_order");
        String state = statusLabel(item.optString("status"));
        TextView title = text(order + ". " + state + " · " + item.optString("title"), 18, "#1F2A30");
        title.setContentDescription("순서 " + order + ", 상태 " + state + ", " + item.optString("title"));
        card.addView(title);
        String description = item.optString("description", "").trim();
        if (!description.isEmpty()) {
            card.addView(text(description, 15, "#3D4852"));
        }
        String holdReason = item.optString("hold_reason", "").trim();
        if (!holdReason.isEmpty()) {
            card.addView(text("보류 사유: " + holdReason, 15, "#8A3B12"));
        }
        JSONObject document = item.optJSONObject("published_document");
        WorkSequenceSource source = WorkSequenceSource.from(
                board,
                item,
                scope.serverUrl,
                scope.customerScope,
                scope.siteScope,
                scope.userId,
                scope.deviceId
        );
        if (document != null) {
            Button open = button("연결 공개 문서 보안 열람");
            open.setContentDescription("작업순서 " + item.optString("title") + "의 공개 문서 열기");
            open.setOnClickListener(view -> listener.onOpenDocument(
                    document.optString("document_id"),
                    document.optString("version_id"),
                    document.optString("title")
            ));
            card.addView(open, fullWidth());
        } else if ("NOT_PUBLISHED".equals(item.optString("document_access"))) {
            card.addView(text(
                    "연결 문서가 비공개로 바뀌었거나 공개 버전이 없습니다. 관리자에게 공개 상태를 문의하세요.",
                    15,
                    "#8A3B12"
            ));
        }
        Button comment = button("이 항목에서 FieldComment·사진 시작");
        comment.setEnabled(source.canCreateFieldComment());
        comment.setContentDescription(source.canCreateFieldComment()
                ? "작업순서 원천이 자동 입력된 FieldComment 작성 시작"
                : "공개 문서가 없어 FieldComment를 시작할 수 없음");
        comment.setOnClickListener(view -> listener.onStartFieldComment(source, item.optString("title")));
        card.addView(comment, fullWidth());
        Button handover = button("이 항목에서 인수인계 시작");
        handover.setContentDescription("작업순서 원천이 자동 입력된 인수인계 작성 시작");
        handover.setOnClickListener(view -> listener.onStartHandover(source, item.optString("title")));
        card.addView(handover, fullWidth());
        results.addView(card, fullWidth());
    }

    void showError(String message, boolean hasSnapshot) {
        stateText.setText((hasSnapshot ? "마지막 snapshot은 유지됩니다. " : "") + message
                + " 필요한 역할·채널과 단말 상태는 현장 관리자에게 문의하세요."
                + " 전송 대기 입력은 outbox에 그대로 보존됩니다.");
    }

    private EditText input(String hint) {
        EditText input = new EditText(getContext());
        input.setHint(hint);
        input.setTextSize(15);
        input.setInputType(InputType.TYPE_CLASS_TEXT);
        input.setSingleLine(true);
        input.setMinHeight(dp(56));
        return input;
    }

    private Button button(String label) {
        Button button = new Button(getContext());
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setPadding(dp(12), dp(10), dp(12), dp(10));
        return button;
    }

    private TextView text(String value, int size, String color) {
        TextView text = new TextView(getContext());
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(Color.parseColor(color));
        return text;
    }

    private LayoutParams fullWidth() {
        return new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String nullable(String value, String fallback) {
        return value == null || value.isEmpty() || "null".equals(value) ? fallback : value;
    }

    private static String statusLabel(String status) {
        switch (status) {
            case "WAITING":
                return "○ 대기";
            case "IN_PROGRESS":
                return "▶ 진행";
            case "HOLD":
                return "Ⅱ 보류";
            case "COMPLETED":
                return "✓ 완료";
            default:
                return "? 상태 확인 필요";
        }
    }
}
