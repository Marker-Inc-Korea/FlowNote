package com.flownote.fieldapp;

import java.io.IOException;

final class NotificationSessionRecoveryPolicy {
    enum Action {
        REFRESH,
        CLEAR_SESSION,
        WAIT_FOR_CONNECTION
    }

    private NotificationSessionRecoveryPolicy() {
    }

    static Action decide(IOException exception, boolean allowRefresh) {
        String message = exception.getMessage();
        if (message != null && message.startsWith("HTTP 401")) {
            return allowRefresh ? Action.REFRESH : Action.CLEAR_SESSION;
        }
        if (FlowNoteApiClient.isAuthenticationRejected(exception)) {
            return Action.CLEAR_SESSION;
        }
        return Action.WAIT_FOR_CONNECTION;
    }
}
