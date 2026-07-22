package com.flownote.fieldapp;

import org.junit.Test;

import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;

public final class UserErrorMessageTest {
    @Test
    public void approvedDeviceErrorsUseKoreanFieldGuidance() {
        String message = UserErrorMessage.from(
                new IOException("HTTP 403: {\"detail\":\"Terminal device is not approved or active.\"}")
        );

        assertEquals(
                "요청이 거부되었습니다. 승인 단말 상태와 사용자 권한을 확인하세요. (HTTP 403)",
                message
        );
        assertFalse(message.contains("Terminal device"));
    }

    @Test
    public void networkFailuresUseActionableKoreanGuidance() {
        assertEquals(
                "서버에 연결할 수 없습니다. 네트워크와 서버 주소를 확인하세요.",
                UserErrorMessage.from(new ConnectException("Connection refused"))
        );
        assertEquals(
                "서버 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.",
                UserErrorMessage.from(new SocketTimeoutException("timeout"))
        );
    }

    @Test
    public void invalidKeystoreUsesPreservationGuidance() {
        assertEquals(
                "단말 보안 저장소를 열 수 없습니다. 재설치하거나 초기화하지 말고 관리자에게 단말 교체 점검을 요청하세요.",
                UserErrorMessage.from(new IllegalStateException("로컬 보안 키가 없거나 암호문이 손상되었습니다."))
        );
    }
}
