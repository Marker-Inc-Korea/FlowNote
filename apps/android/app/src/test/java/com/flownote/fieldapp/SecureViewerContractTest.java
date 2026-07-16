package com.flownote.fieldapp;

import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;

public final class SecureViewerContractTest {
    @Test
    public void sha256HexMatchesServerIntegrityContract() throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("FlowNote secure stream".getBytes(StandardCharsets.UTF_8));
        assertEquals(
                "bd7acdba460a609ac5a8d26a37b31761e28b0b47ad215a14be5f59abaf05861d",
                FlowNoteApiClient.toHex(digest)
        );
    }

    @Test
    public void streamContractNeverUsesControlledCopyOrFilenamePath() {
        String path = ApiPaths.androidViewGrant("doc_a", "ver_a");
        assertFalse(path.contains("controlled-copy"));
        assertFalse(path.contains("filename"));
    }
}
