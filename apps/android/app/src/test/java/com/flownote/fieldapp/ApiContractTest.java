package com.flownote.fieldapp;

import org.junit.Test;

import java.util.Arrays;
import java.util.Collections;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class ApiContractTest {
    @Test
    public void pathsMatchFastApiContracts() {
        assertEquals("/api/v1/auth/login", ApiPaths.LOGIN);
        assertEquals("/api/v1/documents/published", ApiPaths.PUBLISHED_DOCUMENTS);
        assertEquals("/api/v1/documents/doc_123", ApiPaths.document("doc_123"));
        assertEquals(
                "/api/v1/documents/doc_123/versions/ver_1/android-view-grants",
                ApiPaths.androidViewGrant("doc_123", "ver_1")
        );
        assertEquals(
                "/api/v1/field-comments/comment_123/attachments",
                ApiPaths.fieldCommentAttachments("comment_123")
        );
        assertEquals("/api/v1/notifications/chmsg_123/read", ApiPaths.notificationRead("chmsg_123"));
        assertEquals(
                "/api/v1/handovers/handover_1/receipts/receipt_1",
                ApiPaths.handoverReceipt("handover_1", "receipt_1")
        );
        assertEquals("/api/v1/notification-channels", ApiPaths.NOTIFICATION_CHANNELS);
        assertEquals(
                "/api/v1/notification-channels/channel_1/members",
                ApiPaths.channelMembers("channel_1")
        );
    }

    @Test
    public void approvedTerminalLoginUsesFixedVirtualDeviceIdContract() {
        String virtualDeviceId = "test-android-virtual-terminal-001";
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "username", "test-viewer", true);
        JsonEscaper.appendStringField(body, "password", "test-password", true);
        JsonEscaper.appendStringField(body, "deviceId", virtualDeviceId, false);
        body.append('}');

        assertTrue(body.toString().contains("\"deviceId\":\"test-android-virtual-terminal-001\""));
        assertTrue(UserErrorMessage.from(new java.io.IOException("HTTP 403: rejected"))
                .contains("작업 권한"));
        assertTrue(UserErrorMessage.from(new java.io.IOException("HTTP 401: revoked"))
                .contains("다시 로그인"));
        assertTrue(FlowNoteApiClient.shouldDiscardStoredSession(401));
        assertTrue(!FlowNoteApiClient.shouldDiscardStoredSession(403));
        assertTrue(FlowNoteApiClient.shouldDiscardStoredSession(
                403,
                "{\"detail\":{\"code\":\"DEVICE_NOT_APPROVED\"}}"
        ));
        assertTrue(!FlowNoteApiClient.shouldDiscardStoredSession(
                403,
                "{\"detail\":{\"code\":\"PERMISSION_DENIED\"}}"
        ));
    }

    @Test
    public void jsonEscaperKeepsDeviceIdAndKoreanTextValid() {
        String escaped = JsonEscaper.quote("단말 \"A\"\\라인\n");
        assertEquals("\"단말 \\\"A\\\"\\\\라인\\n\"", escaped);
    }

    @Test
    public void fieldCommentDraftRequiresTargetAndContent() {
        FieldCommentDraft draft = new FieldCommentDraft(
                "local-1",
                "doc_1",
                "ver_1",
                null,
                "현장 온도 상승",
                "signal",
                "yellow",
                "tablet-line-a-01",
                "user-worker",
                "content://photo/1",
                null
        );

        assertTrue(draft.canSend());
        assertEquals("signal", draft.normalizedInputMode());
        assertEquals("android:tablet-line-a-01:local-1", draft.idempotencyKey);
    }

    @Test
    public void handoverDraftRequiresChannelRecipientSourceAndIdentity() {
        HandoverDraft draft = new HandoverDraft(
                "local-handover-1",
                "channel_1",
                "야간조 확인",
                "다음 조에서 압력 수치를 확인하세요.",
                "work_record",
                "work-record-1",
                null,
                Arrays.asList("user-b", "user-b", "user-c"),
                "tablet-line-a-01",
                "user-a",
                null
        );

        assertTrue(draft.canQueue());
        assertEquals("WORK_RECORD", draft.sourceType);
        assertEquals(Arrays.asList("user-b", "user-c"), draft.recipientIds);
        assertEquals(
                "android:tablet-line-a-01:handover:local-handover-1",
                draft.idempotencyKey
        );
    }

    @Test
    public void handoverDraftRejectsFreeMessageWithoutOperationalSource() {
        HandoverDraft draft = new HandoverDraft(
                "local-handover-2",
                "channel_1",
                "자유 메시지",
                "원천 연결이 없습니다.",
                "CHAT",
                null,
                null,
                Collections.singletonList("user-b"),
                "tablet-line-a-01",
                "user-a",
                null
        );

        assertFalse(draft.canQueue());
    }

    @Test
    public void authenticationRejectionDistinguishesInactiveDeviceFromRoleDenial() {
        assertTrue(FlowNoteApiClient.isAuthenticationRejected(
                new java.io.IOException("HTTP 401: expired")
        ));
        assertTrue(FlowNoteApiClient.isAuthenticationRejected(
                new java.io.IOException("HTTP 403: {\"code\":\"DEVICE_NOT_APPROVED\"}")
        ));
        assertFalse(FlowNoteApiClient.isAuthenticationRejected(
                new java.io.IOException("HTTP 403: {\"code\":\"PERMISSION_DENIED\"}")
        ));
    }

    @Test
    public void legacyPhotoPreviewUsesBoundedPowerOfTwoSampling() {
        assertEquals(4, PhotoPreviewLoader.sampleSize(2400, 1600, 320, 180));
        assertEquals(1, PhotoPreviewLoader.sampleSize(300, 160, 320, 180));
    }
}
