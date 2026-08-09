package com.flownote.fieldapp;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class ServerConfigurationTest {
    @Test
    public void blankStoredAddressUsesPublicExampleServer() {
        assertEquals(
                "https://flownote.example",
                ServerConfiguration.resolve("  "));
    }

    @Test
    public void explicitStoredAddressRemainsAvailableForApprovedTesting() {
        assertEquals(
                "https://test.flownote.example",
                ServerConfiguration.resolve("  https://test.flownote.example  "));
    }

    @Test
    public void localHttpAddressIsMigratedToPublicExampleServer() {
        assertEquals(
                "https://flownote.example",
                ServerConfiguration.resolve("http://10.0.2.2:5184"));
    }

    @Test
    public void invalidStoredAddressIsMigratedToPublicExampleServer() {
        assertEquals(
                "https://flownote.example",
                ServerConfiguration.resolve("not a server"));
    }
}
