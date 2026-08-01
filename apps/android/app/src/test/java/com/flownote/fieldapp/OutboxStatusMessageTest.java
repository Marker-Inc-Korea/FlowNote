package com.flownote.fieldapp;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public final class OutboxStatusMessageTest {
    @Test
    public void emptyQueueConfirmsServerStorage() {
        assertEquals(
                "전송 완료 · 대기 0건 · 모든 현장 기록을 서버에 저장했습니다.",
                OutboxStatusMessage.format(
                        new OutboxQueueStatus(0, 0, 0, 0, 0L),
                        1_000L,
                        true,
                        "tablet-a"
                )
        );
    }

    @Test
    public void waitingQueueShowsPreservationAndNextRetry() {
        String message = OutboxStatusMessage.format(
                new OutboxQueueStatus(2, 0, 0, 0, 76_000L),
                1_000L,
                true,
                "tablet-a"
        );

        assertTrue(message.contains("전송 대기"));
        assertTrue(message.contains("서버 미저장 2건"));
        assertTrue(message.contains("암호화해 보존"));
        assertTrue(message.contains("1분 15초 후"));
    }

    @Test
    public void rejectedSessionExplainsLoginAndAdministratorContact() {
        String message = OutboxStatusMessage.format(
                new OutboxQueueStatus(1, 1, 1, 0, 0L),
                1_000L,
                false,
                "tablet-a"
        );

        assertTrue(message.contains("다시 로그인"));
        assertTrue(message.contains("실패 항목만"));
        assertTrue(message.contains("승인 단말 ID tablet-a"));
        assertTrue(message.contains("실패 건수"));
    }

    @Test
    public void exhaustedQueueRequiresManualRetry() {
        String message = OutboxStatusMessage.format(
                new OutboxQueueStatus(3, 2, 0, 2, Long.MAX_VALUE),
                1_000L,
                true,
                ""
        );

        assertTrue(message.contains("자동 재시도 한도"));
        assertTrue(message.contains("실패 항목 다시 보내기"));
        assertTrue(message.contains("실패 2건 / 전체 대기 3건"));
        assertTrue(message.contains("화면의 승인 단말 ID"));
    }
}
