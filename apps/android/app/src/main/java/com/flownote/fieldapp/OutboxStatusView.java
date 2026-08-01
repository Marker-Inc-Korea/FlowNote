package com.flownote.fieldapp;

import android.content.Context;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class OutboxStatusView extends LinearLayout {
    private final ImageView iconView;
    private final TextView messageView;

    public OutboxStatusView(Context context) {
        super(context);
        setOrientation(HORIZONTAL);
        setGravity(Gravity.CENTER_VERTICAL);
        setPadding(dp(14), dp(14), dp(14), dp(14));
        setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);

        iconView = new ImageView(context);
        LayoutParams iconParams = new LayoutParams(dp(28), dp(28));
        iconParams.setMarginEnd(dp(12));
        addView(iconView, iconParams);

        messageView = new TextView(context);
        messageView.setTextSize(16);
        messageView.setTextColor(Color.parseColor("#1F2A30"));
        addView(messageView, new LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f));
    }

    public void show(OutboxQueueStatus status, String message) {
        if (status.failedCount > 0) {
            update(R.drawable.ic_outbox_failed, "전송 실패 아이콘", "#FDECEC", message);
        } else if (status.pendingCount > 0) {
            update(R.drawable.ic_outbox_waiting, "전송 대기 아이콘", "#FFF4D6", message);
        } else {
            update(R.drawable.ic_outbox_complete, "전송 완료 아이콘", "#E7F1EB", message);
        }
    }

    public void showStorageError(String message) {
        update(R.drawable.ic_outbox_failed, "보안 저장소 오류 아이콘", "#FDECEC", message);
    }

    private void update(int iconResource, String iconDescription, String background, String message) {
        iconView.setImageResource(iconResource);
        iconView.setContentDescription(iconDescription);
        messageView.setText(message);
        setBackgroundColor(Color.parseColor(background));
        setContentDescription(iconDescription + ". " + message);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
