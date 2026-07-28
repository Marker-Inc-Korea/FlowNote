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
            return "전송 대기 0건 · 모든 현장 기록을 서버에 저장했습니다.";
        }

        String preservation = "전송 대기 " + status.pendingCount
                + "건 · 이 단말에 암호화해 저장했습니다.";
        if (!hasSession) {
            return preservation + " 다시 로그인하면 자동으로 전송합니다. 문제가 계속되면 관리자에게 "
                    + deviceReference(deviceId) + "와 대기 건수를 알려주세요.";
        }
        if (status.blockedCount > 0) {
            return preservation + " 자동 재시도 한도를 넘긴 기록 " + status.blockedCount
                    + "건이 있습니다. 재전송을 누른 뒤에도 실패하면 관리자에게 "
                    + deviceReference(deviceId) + "와 대기 건수를 알려주세요.";
        }
        if (status.readyCount > 0 || status.nextRetryAtMillis <= nowMillis) {
            return preservation + " 네트워크 연결을 확인해 지금 자동 재시도합니다.";
        }

        long remainingSeconds = Math.max(
                1L,
                (status.nextRetryAtMillis - nowMillis + 999L) / 1000L
        );
        return preservation + " 다음 자동 재시도: " + duration(remainingSeconds) + " 후.";
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
