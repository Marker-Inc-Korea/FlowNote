package com.flownote.fieldapp;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

final class CanonicalIntentHash {
    private CanonicalIntentHash() {
    }

    static String sha256(Map<String, ?> value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                    jsonObject(new TreeMap<>(value)).getBytes(StandardCharsets.UTF_8)
            );
            return FlowNoteApiClient.toHex(digest);
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exc);
        }
    }

    private static String jsonObject(Map<String, ?> value) {
        StringBuilder result = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, ?> entry : value.entrySet()) {
            if (!first) {
                result.append(',');
            }
            first = false;
            result.append(JsonEscaper.quote(entry.getKey())).append(':');
            appendValue(result, entry.getValue());
        }
        return result.append('}').toString();
    }

    private static void appendValue(StringBuilder target, Object value) {
        if (value == null) {
            target.append("null");
        } else if (value instanceof String) {
            target.append(JsonEscaper.quote((String) value));
        } else if (value instanceof Number || value instanceof Boolean) {
            target.append(value);
        } else if (value instanceof List<?>) {
            target.append('[');
            List<?> items = (List<?>) value;
            for (int index = 0; index < items.size(); index++) {
                if (index > 0) {
                    target.append(',');
                }
                appendValue(target, items.get(index));
            }
            target.append(']');
        } else if (value instanceof Map<?, ?>) {
            TreeMap<String, Object> nested = new TreeMap<>();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                nested.put(String.valueOf(entry.getKey()), entry.getValue());
            }
            target.append(jsonObject(nested));
        } else {
            target.append(JsonEscaper.quote(String.valueOf(value)));
        }
    }
}
