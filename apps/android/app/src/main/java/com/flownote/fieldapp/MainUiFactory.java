package com.flownote.fieldapp;

import android.content.Context;
import android.graphics.Color;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.TextView;

final class MainUiFactory {
    private final Context context;

    MainUiFactory(Context context) {
        this.context = context;
    }

    RadioButton radioButton(String label, int id) {
        RadioButton button = new RadioButton(context);
        button.setId(id);
        button.setText(label);
        button.setTextSize(15);
        button.setMinHeight(dp(56));
        button.setPadding(dp(10), dp(8), dp(10), dp(8));
        return button;
    }

    EditText input(String hint, int inputType) {
        EditText editText = new EditText(context);
        editText.setHint(hint);
        editText.setTextSize(15);
        editText.setInputType(inputType);
        editText.setSingleLine((inputType & InputType.TYPE_TEXT_FLAG_MULTI_LINE) == 0);
        editText.setMinHeight(dp(56));
        return editText;
    }

    LinearLayout row() {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, 6, 0, 6);
        return row;
    }

    TextView text(String value, int sp, String color) {
        TextView textView = new TextView(context);
        textView.setText(value);
        textView.setTextSize(sp);
        textView.setTextColor(Color.parseColor(color));
        return textView;
    }

    Button button(String label, View.OnClickListener listener) {
        Button button = new Button(context);
        button.setText(label);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setMinWidth(dp(72));
        button.setPadding(dp(10), dp(8), dp(10), dp(8));
        button.setOnClickListener(listener);
        return button;
    }

    void addRowButton(LinearLayout target, String label, View.OnClickListener listener) {
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

    int dp(int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }
}
