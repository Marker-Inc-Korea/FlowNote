package com.flownote.fieldapp;

import org.junit.Test;
import java.util.Arrays;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

public final class WorkSequenceSourceTest {
    private WorkSequenceSource source(String server, String user, String device) {
        return new WorkSequenceSource(
                server,
                "customer-a",
                "site-a",
                user,
                device,
                "board-a",
                "item-a",
                7,
                "doc-a",
                "ver-a",
                "작업 표준",
                null
        );
    }

    @Test
    public void fieldCommentIntentMatchesServerCanonicalContract() {
        WorkSequenceSource source = source("http://server-a", "user-a", "device-a");
        assertTrue(source.canCreateFieldComment());
        assertEquals(
                "e8941c0c8a4109b874185270dcda881a365a590f03620b7e58c10a3c9031b3e8",
                source.fieldCommentIntentHash("압력 상승", "signal", "yellow")
        );
    }

    @Test
    public void handoverIntentSortsRecipientsAndMatchesServerContract() {
        WorkSequenceSource source = source("http://server-a", "user-a", "device-a");
        assertEquals(
                "49a0ac0fed16df090fb4b89a7bd901b9b0885c5224cf8e7354a3a557b61d6d21",
                source.handoverIntentHash(
                        "channel-a",
                        Arrays.asList("user-c", "user-b"),
                        "교대 확인",
                        "압력 확인"
                )
        );
    }

    @Test
    public void idempotencyIdentityChangesAcrossServerUserAndDeviceScopes() {
        String original = source("http://server-a", "user-a", "device-a")
                .idempotencyKey("field-comment", "local-a");
        assertNotEquals(original, source("http://server-b", "user-a", "device-a")
                .idempotencyKey("field-comment", "local-a"));
        assertNotEquals(original, source("http://server-a", "user-b", "device-a")
                .idempotencyKey("field-comment", "local-a"));
        assertNotEquals(original, source("http://server-a", "user-a", "device-b")
                .idempotencyKey("field-comment", "local-a"));

        WorkSequenceScope scope = new WorkSequenceScope(
                "http://server-a/", "customer-a", "site-a", "user-a", "device-a"
        );
        assertTrue(scope.matches("customer-a", "site-a", "user-a", "device-a"));
        assertFalse(scope.matches("customer-a", "site-b", "user-a", "device-a"));
    }
}
