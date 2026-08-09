package com.flownote.fieldapp;

import java.net.URI;
import java.net.URISyntaxException;

final class ServerConfiguration {
    static final String DEFAULT_SERVER_EXAMPLE_URL = "https://flownote.example";

    private ServerConfiguration() {
    }

    static String resolve(String storedServerUrl) {
        if (storedServerUrl == null || storedServerUrl.trim().isEmpty()) {
            return DEFAULT_SERVER_EXAMPLE_URL;
        }
        String candidate = storedServerUrl.trim();
        try {
            URI uri = new URI(candidate);
            if ("https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null) {
                return candidate;
            }
        } catch (URISyntaxException ignored) {
        }
        return DEFAULT_SERVER_EXAMPLE_URL;
    }
}
