package com.flownote.fieldapp;

import android.content.Context;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.UUID;

final class ReceivedHandoverView extends LinearLayout {
    interface Listener {
        boolean onQueueReceipt(HandoverReceiptDraft draft);

        boolean onQueueFollowUp(HandoverFollowUpDraft draft);
    }

    private final Listener listener;
    private final HandoverFollowUpDraftStore draftStore;
    private final String serverUrl;
    private final String userId;
    private final String deviceId;
    private final String deliveryRunId;

    ReceivedHandoverView(
            Context context,
            Listener listener,
            HandoverFollowUpDraftStore draftStore,
            String serverUrl,
            String userId,
            String deviceId,
            String deliveryRunId
    ) {
        super(context);
        this.listener = listener;
        this.draftStore = draftStore;
        this.serverUrl = FieldCommentDraft.nonEmpty(serverUrl, "");
        this.userId = FieldCommentDraft.nonEmpty(userId, "anonymous");
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
        this.deliveryRunId = FieldCommentDraft.trimToNull(deliveryRunId);
        setOrientation(VERTICAL);
    }

    void show(JSONArray handovers) {
        removeAllViews();
        int receivedCount = 0;
        for (int index = 0; index < handovers.length(); index++) {
            JSONObject handover = handovers.optJSONObject(index);
            JSONObject receipt = myReceipt(handover);
            if (handover == null || receipt == null) {
                continue;
            }
            receivedCount++;
            addHandover(handover, receipt);
        }
        if (receivedCount == 0) {
            addView(text("받은 인수인계가 없습니다.", 15, "#3D4852"));
        }
    }

    private void addHandover(JSONObject handover, JSONObject receipt) {
        String handoverId = handover.optString("handover_id");
        String receiptId = receipt.optString("receipt_id");
        String title = handover.optString("title", "인수인계");
        String sourceType = handover.optString("source_type");
        String sourceId = handover.optString("source_id");
        String sourceVersionId = handover.optString("source_version_id", null);

        LinearLayout card = new LinearLayout(getContext());
        card.setOrientation(VERTICAL);
        card.setPadding(dp(12), dp(14), dp(12), dp(16));
        card.setBackgroundColor(android.graphics.Color.parseColor("#F5F7F8"));

        card.addView(text(title, 18, "#1F2A30"));
        card.addView(text(handover.optString("body"), 15, "#3D4852"));
        card.addView(text(
                "상태: " + receiptLabel(receipt.optString("receipt_status"))
                        + " · 원천: " + sourceLabel(sourceType) + " " + sourceId,
                14,
                "#3D4852"
        ));

        EditText followUpInput = new EditText(getContext());
        followUpInput.setHint("보류 사유 또는 후속 FieldComment 내용");
        followUpInput.setTextSize(15);
        followUpInput.setMinHeight(dp(88));
        followUpInput.setMinLines(3);
        followUpInput.setSingleLine(false);
        followUpInput.setInputType(
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
        );
        followUpInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(500)});
        try {
            followUpInput.setText(draftStore.load(serverUrl, userId, handoverId));
        } catch (RuntimeException exc) {
            followUpInput.setError("보존된 입력을 열지 못했습니다. 관리자에게 단말 보안 저장소 점검을 요청하세요.");
        }
        followUpInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence value, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence value, int start, int before, int count) {
                try {
                    draftStore.save(serverUrl, userId, handoverId, value.toString());
                } catch (RuntimeException exc) {
                    followUpInput.setError("입력을 암호화해 보존하지 못했습니다. 전송하지 말고 관리자에게 점검을 요청하세요.");
                }
            }

            @Override
            public void afterTextChanged(Editable value) {
            }
        });
        card.addView(followUpInput, fullWidth());

        LinearLayout receiptRow = new LinearLayout(getContext());
        receiptRow.setOrientation(HORIZONTAL);
        addButton(receiptRow, "확인", view -> listener.onQueueReceipt(
                receiptDraft(handoverId, receiptId, "ACKNOWLEDGED", followUpInput.getText().toString())
        ));
        addButton(receiptRow, "보류", view -> {
            String note = FieldCommentDraft.trimToNull(followUpInput.getText().toString());
            listener.onQueueReceipt(receiptDraft(
                    handoverId,
                    receiptId,
                    "FOLLOW_UP_REQUIRED",
                    note == null ? "현장 확인 후 후속 조치가 필요합니다." : note
            ));
            followUpInput.requestFocus();
        });
        card.addView(receiptRow, fullWidth());

        Button followUpButton = button("같은 원천에 후속 FieldComment 저장");
        followUpButton.setOnClickListener(view -> {
            String content = followUpInput.getText().toString();
            HandoverFollowUpDraft draft = new HandoverFollowUpDraft(
                    UUID.randomUUID().toString(),
                    handoverId,
                    handover.optString("channel_id"),
                    title,
                    sourceType,
                    sourceId,
                    sourceVersionId,
                    content,
                    deviceId,
                    userId,
                    HandoverFollowUpDraft.defaultIdempotencyKey(handoverId, userId, content)
            );
            if (listener.onQueueFollowUp(draft)) {
                try {
                    draftStore.remove(serverUrl, userId, handoverId);
                    followUpInput.setText("");
                } catch (RuntimeException exc) {
                    followUpInput.setError(
                            "전송 대기 저장은 끝났지만 입력란을 비우지 못했습니다. 같은 내용은 중복 생성되지 않습니다."
                    );
                }
            }
        });
        card.addView(followUpButton, fullWidth());

        LayoutParams cardParams = fullWidth();
        cardParams.setMargins(0, 0, 0, dp(12));
        addView(card, cardParams);
    }

    private HandoverReceiptDraft receiptDraft(
            String handoverId,
            String receiptId,
            String status,
            String note
    ) {
        String localId = UUID.randomUUID().toString();
        return new HandoverReceiptDraft(
                localId,
                handoverId,
                receiptId,
                status,
                note,
                deliveryRunId,
                "android:handover-receipt:" + localId
        );
    }

    private JSONObject myReceipt(JSONObject handover) {
        if (handover == null) {
            return null;
        }
        JSONArray receipts = handover.optJSONArray("receipts");
        if (receipts == null) {
            return null;
        }
        for (int index = 0; index < receipts.length(); index++) {
            JSONObject receipt = receipts.optJSONObject(index);
            if (receipt != null && userId.equals(receipt.optString("recipient_id"))) {
                return receipt;
            }
        }
        return null;
    }

    private void addButton(LinearLayout row, String label, View.OnClickListener click) {
        Button button = button(label);
        button.setOnClickListener(click);
        LayoutParams params = new LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f);
        params.setMarginEnd(dp(4));
        row.addView(button, params);
    }

    private Button button(String label) {
        Button button = new Button(getContext());
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setPadding(dp(12), dp(8), dp(12), dp(8));
        return button;
    }

    private TextView text(String value, int size, String color) {
        TextView text = new TextView(getContext());
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(android.graphics.Color.parseColor(color));
        text.setPadding(0, dp(4), 0, dp(4));
        return text;
    }

    private LayoutParams fullWidth() {
        return new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String receiptLabel(String value) {
        return switch (value) {
            case "ACKNOWLEDGED" -> "확인";
            case "FOLLOW_UP_REQUIRED" -> "보류·후속 필요";
            case "READ" -> "읽음";
            default -> "미확인";
        };
    }

    private static String sourceLabel(String value) {
        return switch (value) {
            case "DOCUMENT" -> "문서";
            case "FIELD_COMMENT" -> "FieldComment";
            case "WORK_SEQUENCE_ITEM", "WORK_SEQUENCE_HISTORY" -> "작업순서";
            case "WORK_RECORD" -> "작업내역";
            default -> "원천";
        };
    }
}
