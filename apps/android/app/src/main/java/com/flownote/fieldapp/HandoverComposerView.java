package com.flownote.fieldapp;

import android.content.Context;
import android.text.InputFilter;
import android.text.InputType;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.AdapterView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

final class HandoverComposerView extends LinearLayout {
    interface Listener {
        void onRefreshChannels();

        void onChannelSelected(String channelId);

        void onQueue(HandoverDraft draft);
    }

    private static final String[] SOURCE_LABELS = {
            "작업순서", "문서", "FieldComment", "작업내역"
    };
    private static final String[] SOURCE_VALUES = {
            "WORK_SEQUENCE_ITEM", "DOCUMENT", "FIELD_COMMENT", "WORK_RECORD"
    };

    private final Listener listener;
    private final Spinner channelSpinner;
    private final Spinner sourceSpinner;
    private final EditText sourceIdInput;
    private final EditText sourceVersionInput;
    private final EditText titleInput;
    private final EditText bodyInput;
    private final LinearLayout recipientArea;
    private final TextView formStatus;
    private final List<ChannelOption> channels = new ArrayList<>();
    private final List<CheckBox> recipientChecks = new ArrayList<>();
    private String deviceId;
    private String authorId;
    private boolean bindingChannels;
    private WorkSequenceSource workSequenceSource;

    HandoverComposerView(Context context, Listener listener) {
        super(context);
        this.listener = listener;
        setOrientation(VERTICAL);
        setPadding(0, dp(18), 0, dp(18));

        TextView heading = text("인수인계 작성", 18);
        heading.setTextColor(android.graphics.Color.parseColor("#236C4A"));
        addView(heading);
        addView(text(
                "업무 채널과 수신자를 고르고 작업순서·문서·FieldComment·작업내역 중 하나를 연결하세요.",
                14
        ));

        Button refresh = button("채널·수신자 새로 불러오기");
        refresh.setOnClickListener(view -> listener.onRefreshChannels());
        addView(refresh, fullWidth());

        channelSpinner = spinner();
        channelSpinner.setContentDescription("인수인계 업무 채널");
        channelSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (!bindingChannels && position >= 0 && position < channels.size()) {
                    listener.onChannelSelected(channels.get(position).id);
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
                clearRecipients("업무 채널을 선택하세요.");
            }
        });
        addView(label("업무 채널"));
        addView(channelSpinner, fullWidth());

        addView(label("수신자"));
        recipientArea = new LinearLayout(context);
        recipientArea.setOrientation(VERTICAL);
        addView(recipientArea, fullWidth());
        clearRecipients("채널을 불러오면 활성 멤버가 표시됩니다.");

        addView(label("원천 종류"));
        sourceSpinner = spinner();
        ArrayAdapter<String> sourceAdapter = new ArrayAdapter<>(
                context,
                android.R.layout.simple_spinner_item,
                SOURCE_LABELS
        );
        sourceAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        sourceSpinner.setAdapter(sourceAdapter);
        sourceSpinner.setContentDescription("인수인계 원천 종류");
        addView(sourceSpinner, fullWidth());

        sourceIdInput = input("원천 ID", 64, false);
        sourceVersionInput = input("문서 버전 ID (문서일 때 선택)", 64, false);
        titleInput = input("인수인계 제목", 120, false);
        bodyInput = input("다음 작업자가 확인할 짧은 내용", 500, true);
        bodyInput.setMinLines(3);
        addView(sourceIdInput);
        addView(sourceVersionInput);
        addView(titleInput);
        addView(bodyInput);

        Button save = button("기기에 암호화 저장·전송");
        save.setOnClickListener(view -> listener.onQueue(buildDraft()));
        addView(save, fullWidth());

        formStatus = text("아직 작성하지 않았습니다.", 14);
        formStatus.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        formStatus.setPadding(dp(12), dp(10), dp(12), dp(10));
        addView(formStatus, fullWidth());
    }

    void setIdentity(String deviceId, String authorId) {
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
        this.authorId = FieldCommentDraft.trimToNull(authorId);
    }

    void setChannels(JSONArray payload) {
        String previous = selectedChannelId();
        bindingChannels = true;
        channels.clear();
        ArrayList<String> labels = new ArrayList<>();
        for (int index = 0; index < payload.length(); index++) {
            JSONObject item = payload.optJSONObject(index);
            if (item == null || !"ACTIVE".equals(item.optString("status"))) {
                continue;
            }
            ChannelOption option = new ChannelOption(
                    item.optString("channel_id"),
                    item.optString("name")
            );
            if (option.id.isEmpty()) {
                continue;
            }
            channels.add(option);
            labels.add(option.label);
        }
        ArrayAdapter<String> adapter = new ArrayAdapter<>(
                getContext(),
                android.R.layout.simple_spinner_item,
                labels
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        channelSpinner.setAdapter(adapter);
        int selected = indexOf(previous);
        if (selected >= 0) {
            channelSpinner.setSelection(selected);
        }
        bindingChannels = false;
        if (channels.isEmpty()) {
            clearRecipients("선택할 수 있는 활성 업무 채널이 없습니다. 관리자에게 채널 멤버십을 요청하세요.");
            formStatus.setText("채널 0건 · 작성할 수 없습니다.");
            return;
        }
        formStatus.setText("채널 " + channels.size() + "건을 불러왔습니다. 수신자를 확인하세요.");
        listener.onChannelSelected(channels.get(Math.max(0, selected)).id);
    }

    void setMembers(JSONArray payload) {
        recipientArea.removeAllViews();
        recipientChecks.clear();
        for (int index = 0; index < payload.length(); index++) {
            JSONObject item = payload.optJSONObject(index);
            if (item == null || !"ACTIVE".equals(item.optString("status"))) {
                continue;
            }
            String userId = item.optString("user_id");
            if (userId.isEmpty() || userId.equals(authorId)) {
                continue;
            }
            CheckBox checkBox = new CheckBox(getContext());
            checkBox.setText(userId);
            checkBox.setTag(userId);
            checkBox.setTextSize(15);
            checkBox.setMinHeight(dp(56));
            checkBox.setContentDescription("인수인계 수신자 " + userId);
            recipientChecks.add(checkBox);
            recipientArea.addView(checkBox, fullWidth());
        }
        if (recipientChecks.isEmpty()) {
            clearRecipients("선택한 채널에 다른 활성 수신자가 없습니다.");
        } else {
            formStatus.setText("수신자 " + recipientChecks.size() + "명을 불러왔습니다.");
        }
    }

    void showStatus(String message) {
        formStatus.setText(message);
    }

    void setDocumentSource(String documentId, String versionId) {
        workSequenceSource = null;
        sourceSpinner.setEnabled(true);
        sourceIdInput.setEnabled(true);
        sourceVersionInput.setEnabled(true);
        sourceSpinner.setSelection(1);
        sourceIdInput.setText(documentId);
        sourceVersionInput.setText(versionId);
        formStatus.setText("선택한 문서를 인수인계 원천으로 연결했습니다.");
    }

    void setWorkSequenceSource(WorkSequenceSource source, String itemTitle) {
        workSequenceSource = source;
        sourceSpinner.setSelection(0);
        sourceSpinner.setEnabled(false);
        sourceIdInput.setText(source.itemId);
        sourceIdInput.setEnabled(false);
        sourceVersionInput.setText("revision " + source.revision);
        sourceVersionInput.setEnabled(false);
        titleInput.setText("작업순서 인수인계: " + itemTitle);
        formStatus.setText("작업순서 원천과 공개 문서 버전을 고정했습니다. 채널과 수신자를 확인하세요.");
    }

    void resetAfterQueued() {
        workSequenceSource = null;
        sourceSpinner.setEnabled(true);
        sourceIdInput.setEnabled(true);
        sourceVersionInput.setEnabled(true);
        titleInput.setText("");
        bodyInput.setText("");
        sourceIdInput.setText("");
        sourceVersionInput.setText("");
        for (CheckBox checkBox : recipientChecks) {
            checkBox.setChecked(false);
        }
        formStatus.setText("기기에 암호화해 저장했습니다. 새 인수인계 입력란을 비웠습니다.");
        titleInput.requestFocus();
    }

    private HandoverDraft buildDraft() {
        ArrayList<String> recipients = new ArrayList<>();
        for (CheckBox checkBox : recipientChecks) {
            if (checkBox.isChecked()) {
                recipients.add(String.valueOf(checkBox.getTag()));
            }
        }
        String localId = UUID.randomUUID().toString();
        return new HandoverDraft(
                localId,
                selectedChannelId(),
                titleInput.getText().toString(),
                bodyInput.getText().toString(),
                SOURCE_VALUES[sourceSpinner.getSelectedItemPosition()],
                sourceIdInput.getText().toString(),
                sourceVersionInput.getText().toString(),
                recipients,
                deviceId,
                authorId,
                workSequenceSource == null
                        ? HandoverDraft.defaultIdempotencyKey(deviceId, localId) : null,
                workSequenceSource
        );
    }

    private String selectedChannelId() {
        int position = channelSpinner.getSelectedItemPosition();
        return position >= 0 && position < channels.size() ? channels.get(position).id : null;
    }

    private int indexOf(String channelId) {
        for (int index = 0; index < channels.size(); index++) {
            if (channels.get(index).id.equals(channelId)) {
                return index;
            }
        }
        return -1;
    }

    private void clearRecipients(String message) {
        recipientArea.removeAllViews();
        recipientChecks.clear();
        recipientArea.addView(text(message, 14), fullWidth());
    }

    private Spinner spinner() {
        Spinner value = new Spinner(getContext());
        value.setMinimumHeight(dp(56));
        value.setFocusable(true);
        return value;
    }

    private EditText input(String hint, int maxLength, boolean multiline) {
        EditText value = new EditText(getContext());
        value.setHint(hint);
        value.setTextSize(15);
        value.setMinHeight(dp(56));
        value.setFilters(new InputFilter[]{new InputFilter.LengthFilter(maxLength)});
        value.setInputType(
                InputType.TYPE_CLASS_TEXT
                        | (multiline ? InputType.TYPE_TEXT_FLAG_MULTI_LINE : 0)
        );
        value.setSingleLine(!multiline);
        return value;
    }

    private TextView label(String value) {
        TextView label = text(value, 14);
        label.setPadding(0, dp(12), 0, dp(4));
        return label;
    }

    private TextView text(String value, int size) {
        TextView text = new TextView(getContext());
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(android.graphics.Color.parseColor("#3D4852"));
        return text;
    }

    private Button button(String value) {
        Button button = new Button(getContext());
        button.setText(value);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(56));
        button.setPadding(dp(12), dp(8), dp(12), dp(8));
        return button;
    }

    private LayoutParams fullWidth() {
        return new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class ChannelOption {
        final String id;
        final String label;

        ChannelOption(String id, String name) {
            this.id = id == null ? "" : id;
            String cleanedName = name == null ? "" : name.trim();
            this.label = cleanedName.isEmpty() ? this.id : cleanedName + " · " + this.id;
        }
    }
}
