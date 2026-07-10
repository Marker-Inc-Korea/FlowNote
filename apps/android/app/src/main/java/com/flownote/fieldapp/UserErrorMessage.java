package com.flownote.fieldapp;

import java.net.ConnectException;
import java.net.SocketTimeoutException;

public final class UserErrorMessage {
    private UserErrorMessage() {
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
            return "로그인 정보가 만료되었거나 올바르지 않습니다. 다시 로그인하세요. (HTTP 401)";
        }
        if (message.startsWith("HTTP 403")) {
            return "요청이 거부되었습니다. 승인 단말 상태와 사용자 권한을 확인하세요. (HTTP 403)";
        }
        if (message.startsWith("HTTP 404")) {
            return "요청한 기록을 찾을 수 없습니다. 목록을 새로 조회하세요. (HTTP 404)";
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
        return "요청을 처리하지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.";
    }
}
