package com.flownote.fieldapp;

public final class JsonEscaper {
    private JsonEscaper() {
    }

    public static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder builder = new StringBuilder(value.length() + 2);
        builder.append('"');
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"':
                    builder.append("\\\"");
                    break;
                case '\\':
                    builder.append("\\\\");
                    break;
                case '\n':
                    builder.append("\\n");
                    break;
                case '\r':
                    builder.append("\\r");
                    break;
                case '\t':
                    builder.append("\\t");
                    break;
                default:
                    if (ch < 0x20) {
                        builder.append(String.format("\\u%04x", (int) ch));
                    } else {
                        builder.append(ch);
                    }
                    break;
            }
        }
        builder.append('"');
        return builder.toString();
    }

    public static void appendStringField(StringBuilder builder, String name, String value, boolean includeNull) {
        if (value == null && !includeNull) {
            return;
        }
        if (builder.length() > 1) {
            builder.append(',');
        }
        builder.append(quote(name)).append(':').append(quote(value));
    }
}
