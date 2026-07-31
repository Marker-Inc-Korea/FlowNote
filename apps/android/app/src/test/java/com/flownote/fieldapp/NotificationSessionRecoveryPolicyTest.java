package com.flownote.fieldapp;

import org.junit.Test;

import java.io.IOException;

import static org.junit.Assert.assertEquals;

public final class NotificationSessionRecoveryPolicyTest {
    @Test
    public void firstUnauthorizedResponseUsesRefreshToken() {
        assertEquals(
                NotificationSessionRecoveryPolicy.Action.REFRESH,
                NotificationSessionRecoveryPolicy.decide(
                        new IOException("HTTP 401: expired"),
                        true
                )
        );
    }

    @Test
    public void unauthorizedResponseAfterRefreshClearsSession() {
        assertEquals(
                NotificationSessionRecoveryPolicy.Action.CLEAR_SESSION,
                NotificationSessionRecoveryPolicy.decide(
                        new IOException("HTTP 401: rejected"),
                        false
                )
        );
    }

    @Test
    public void inactiveDeviceClearsSessionWithoutRefresh() {
        assertEquals(
                NotificationSessionRecoveryPolicy.Action.CLEAR_SESSION,
                NotificationSessionRecoveryPolicy.decide(
                        new IOException("HTTP 403: {\"code\":\"DEVICE_NOT_APPROVED\"}"),
                        true
                )
        );
    }

    @Test
    public void connectionFailurePreservesSessionForNextPoll() {
        assertEquals(
                NotificationSessionRecoveryPolicy.Action.WAIT_FOR_CONNECTION,
                NotificationSessionRecoveryPolicy.decide(
                        new IOException("network unavailable"),
                        true
                )
        );
    }
}
