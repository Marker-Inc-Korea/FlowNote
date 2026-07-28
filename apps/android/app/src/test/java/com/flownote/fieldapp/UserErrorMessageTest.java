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
                "승인되지 않았거나 비활성 상태인 단말입니다. 현장 기록 전송 대기는 이 단말에 "
                        + "보존됩니다. 재설치하지 말고 관리자에게 화면의 승인 단말 ID와 대기 건수를 알려주세요.",
                message
        );
        assertFalse(message.contains("Terminal device"));
    }

    @Test
    public void accessErrorsSeparatePermissionScopeAndHiddenSourceWithoutInternals() {
        assertEquals(
                "현재 계정에는 이 작업 권한이 없습니다. 관리자에게 역할과 계정 상태를 확인하세요.",
                UserErrorMessage.from(new IOException(
                        "HTTP 403: {\"detail\":{\"code\":\"PERMISSION_DENIED\",\"message\":\"token=secret\"}}"
                ))
        );
        assertEquals(
                "현재 서버와 다른 고객·현장 범위입니다. 서버 주소와 현장 설정을 확인하세요.",
                UserErrorMessage.from(new IOException(
                        "HTTP 404: {\"detail\":{\"code\":\"SCOPE_NOT_FOUND\",\"message\":\"/srv/app.py\"}}"
                ))
        );
        String hiddenSource = UserErrorMessage.from(new IOException(
                "HTTP 404: {\"detail\":{\"code\":\"SOURCE_NOT_VISIBLE\",\"message\":\"stack trace\"}}"
        ));
        assertEquals(
                "요청한 원천을 찾을 수 없거나 공개되지 않았습니다. 목록을 새로 조회하거나 관리자에게 공개 상태를 확인하세요.",
                hiddenSource
        );
        assertFalse(hiddenSource.contains("stack"));
        assertFalse(hiddenSource.contains("token"));
        assertFalse(hiddenSource.contains("/srv/"));
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
