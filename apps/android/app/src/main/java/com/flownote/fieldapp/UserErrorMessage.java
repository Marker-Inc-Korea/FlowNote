package com.flownote.fieldapp;

import java.net.ConnectException;
import java.net.SocketTimeoutException;

public final class UserErrorMessage {
    private UserErrorMessage() {
    }

    static boolean isSecureStorageFailure(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            String message = current.getMessage();
            if (message != null && (
                    message.contains("로컬 보안 키")
                            || message.contains("단말 보안 키")
                            || message.contains("로컬 데이터를 암호화")
                            || message.contains("첨부를 암호화")
            )) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    public static String from(Exception exception) {
        if (exception instanceof SocketTimeoutException) {
            return "서버 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.";
        }
        if (exception instanceof ConnectException) {
            return "서버에 연결할 수 없습니다. 네트워크와 서버 주소를 확인하세요.";
        }

        String message = exception.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return "요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.";
        }
        if (message.startsWith("HTTP 401")) {
            if (hasCode(message, "DEVICE_NOT_APPROVED")) {
                return deviceApprovalGuidance();
            }
            return "로그인 정보가 만료되었거나 올바르지 않습니다. 현장 기록 전송 대기는 이 단말에 "
                    + "보존됩니다. 다시 로그인하세요. 계속 실패하면 관리자에게 승인 단말 ID를 알려주세요.";
        }
        if (message.startsWith("HTTP 403")) {
            if (hasCode(message, "DEVICE_NOT_APPROVED")
                    || message.contains("Terminal device is not approved")) {
                return deviceApprovalGuidance();
            }
            return "현재 계정에는 이 작업 권한이 없습니다. 관리자에게 역할과 계정 상태를 확인하세요.";
        }
        if (message.startsWith("HTTP 404")) {
            if (hasCode(message, "SCOPE_NOT_FOUND")) {
                return "현재 서버와 다른 고객·현장 범위입니다. 서버 주소와 현장 설정을 확인하세요.";
            }
            if (hasCode(message, "SOURCE_NOT_VISIBLE")
                    || hasCode(message, "RESOURCE_NOT_FOUND")) {
                return "요청한 원천을 찾을 수 없거나 공개되지 않았습니다. 목록을 새로 조회하거나 관리자에게 공개 상태를 확인하세요.";
            }
            return "요청한 기록을 찾을 수 없거나 공개되지 않았습니다. 목록을 새로 조회하세요.";
        }
        if (message.startsWith("HTTP ")) {
            int separator = message.indexOf(':');
            String status = separator > 0 ? message.substring(0, separator) : message;
            return "서버 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요. (" + status + ")";
        }
        if (message.contains("Server URL is empty")) {
            return "서버 주소를 입력하세요.";
        }
        if (message.contains("Access token is missing")) {
            return "로그인이 필요합니다.";
        }
        if (message.contains("로컬 보안 키") || message.contains("단말 보안 키")) {
            return "단말 보안 저장소를 열 수 없습니다. 재설치하거나 초기화하지 말고 관리자에게 단말 교체 점검을 요청하세요.";
        }
        if (message.contains("로컬 데이터를 암호화") || message.contains("첨부를 암호화")) {
            return "현장 기록을 안전하게 임시 저장하지 못했습니다. 앱을 종료하지 말고 관리자에게 문의하세요.";
        }
        return "요청을 처리하지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.";
    }

    private static boolean hasCode(String message, String code) {
        return message.contains("\"code\":\"" + code + "\"")
                || message.contains("\"code\": \"" + code + "\"");
    }

    private static String deviceApprovalGuidance() {
        return "승인되지 않았거나 비활성 상태인 단말입니다. 현장 기록 전송 대기는 이 단말에 "
                + "보존됩니다. 재설치하지 말고 관리자에게 화면의 승인 단말 ID와 대기 건수를 알려주세요.";
    }
}
