package com.flownote.fieldapp;

import java.util.Locale;

public final class OutboxStatusMessage {
    private OutboxStatusMessage() {
    }

    public static String format(
            OutboxQueueStatus status,
            long nowMillis,
            boolean hasSession,
            String deviceId
    ) {
        if (status.pendingCount == 0) {
            return "전송 완료 · 대기 0건 · 모든 현장 기록을 서버에 저장했습니다.";
        }

        String preservation = "이 단말에 암호화해 보존 중입니다.";
        if (status.failedCount > 0) {
            String failure = "전송 실패 · 실패 " + status.failedCount
                    + "건 / 전체 대기 " + status.pendingCount + "건 · " + preservation;
            if (status.partialSuccessCount > 0) {
                failure += " 부분 성공 " + status.partialSuccessCount
                        + "건은 FieldComment 원천 저장이 끝났고 사진 또는 채널 알림만 재시도합니다.";
            }
            if (!hasSession) {
                return failure + " 다시 로그인한 뒤 실패 항목만 보낼 수 있습니다. 관리자에게 "
                        + deviceReference(deviceId) + "와 실패 건수를 알려주세요.";
            }
            if (status.blockedCount > 0) {
                return failure + " 자동 재시도 한도를 넘긴 기록 " + status.blockedCount
                        + "건이 있습니다. ‘실패 항목 다시 보내기’를 누른 뒤에도 실패하면 관리자에게 "
                        + deviceReference(deviceId) + "와 실패 건수를 알려주세요.";
            }
            return failure + " 자동 재시도 예정이며 ‘실패 항목 다시 보내기’로 즉시 시도할 수 있습니다.";
        }

        String waiting = "전송 대기 · 서버 미저장 " + status.pendingCount + "건 · " + preservation;
        if (!hasSession) {
            return waiting + " 다시 로그인하면 자동으로 전송합니다. 문제가 계속되면 관리자에게 "
                    + deviceReference(deviceId) + "와 대기 건수를 알려주세요.";
        }
        if (status.readyCount > 0 || status.nextRetryAtMillis <= nowMillis) {
            return waiting + " 네트워크 연결을 확인해 지금 자동 전송합니다.";
        }

        long remainingSeconds = Math.max(
                1L,
                (status.nextRetryAtMillis - nowMillis + 999L) / 1000L
        );
        return waiting + " 다음 자동 전송: " + duration(remainingSeconds) + " 후.";
    }

    private static String deviceReference(String deviceId) {
        String cleaned = deviceId == null ? "" : deviceId.trim();
        if (cleaned.isEmpty()) {
            return "화면의 승인 단말 ID";
        }
        return String.format(Locale.ROOT, "승인 단말 ID %s", cleaned);
    }

    private static String duration(long seconds) {
        if (seconds < 60L) {
            return seconds + "초";
        }
        long minutes = seconds / 60L;
        long remainder = seconds % 60L;
        if (remainder == 0L) {
            return minutes + "분";
        }
        return minutes + "분 " + remainder + "초";
    }
}
