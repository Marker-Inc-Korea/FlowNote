package com.flownote.fieldapp;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class WorkSequenceScope {
    final String serverUrl;
    final String customerScope;
    final String siteScope;
    final String userId;
    final String deviceId;

    WorkSequenceScope(
            String serverUrl,
            String customerScope,
            String siteScope,
            String userId,
            String deviceId
    ) {
        this.serverUrl = normalizedServer(serverUrl);
        this.customerScope = FieldCommentDraft.trimToNull(customerScope);
        this.siteScope = FieldCommentDraft.trimToNull(siteScope);
        this.userId = FieldCommentDraft.trimToNull(userId);
        this.deviceId = FieldCommentDraft.trimToNull(deviceId);
    }

    boolean isComplete() {
        return !serverUrl.isEmpty() && customerScope != null && siteScope != null
                && userId != null && deviceId != null;
    }

    String storageKey() {
        return digest(serverUrl + "\n" + customerScope + "\n" + siteScope + "\n"
                + userId + "\n" + deviceId).substring(0, 32);
    }

    boolean matchesResponse(org.json.JSONObject response) {
        return matches(
                response.optString("customer_scope", null),
                response.optString("site_scope", null),
                response.optString("user_id", null),
                response.optString("device_id", null)
        );
    }

    boolean matches(String customer, String site, String user, String device) {
        return customerScope.equals(customer)
                && siteScope.equals(site)
                && userId.equals(user)
                && deviceId.equals(device);
    }

    private static String normalizedServer(String value) {
        String cleaned = FieldCommentDraft.nonEmpty(value, "").trim();
        while (cleaned.endsWith("/")) {
            cleaned = cleaned.substring(0, cleaned.length() - 1);
        }
        return cleaned;
    }

    private static String digest(String value) {
        try {
            return FlowNoteApiClient.toHex(MessageDigest.getInstance("SHA-256").digest(
                    value.getBytes(StandardCharsets.UTF_8)
            ));
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exc);
        }
    }
}
