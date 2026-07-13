package com.flownote.fieldapp;

import android.content.ContentResolver;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class FlowNoteApiClient {
    public interface AuthenticationFailureListener {
        void onAuthenticationRejected();
    }

    private final String baseUrl;
    private final ContentResolver contentResolver;
    private String accessToken;
    private AuthenticationFailureListener authenticationFailureListener;

    public FlowNoteApiClient(String baseUrl, ContentResolver contentResolver) {
        String cleaned = baseUrl == null ? "" : baseUrl.trim();
        while (cleaned.endsWith("/")) {
            cleaned = cleaned.substring(0, cleaned.length() - 1);
        }
        this.baseUrl = cleaned;
        this.contentResolver = contentResolver;
    }

    public void setAccessToken(String accessToken) {
        this.accessToken = accessToken;
    }

    public void setAuthenticationFailureListener(AuthenticationFailureListener listener) {
        this.authenticationFailureListener = listener;
    }

    static boolean shouldDiscardStoredSession(int httpStatus) {
        return httpStatus == HttpURLConnection.HTTP_UNAUTHORIZED;
    }

    public JSONObject login(String username, String password, String deviceId) throws IOException, JSONException {
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "username", username, true);
        JsonEscaper.appendStringField(body, "password", password, true);
        JsonEscaper.appendStringField(body, "deviceId", deviceId, false);
        body.append('}');
        JSONObject result = postJson(ApiPaths.LOGIN, body.toString(), false);
        accessToken = result.getString("access_token");
        return result;
    }

    public JSONArray listPublishedDocuments() throws IOException, JSONException {
        return getArray(ApiPaths.PUBLISHED_DOCUMENTS);
    }

    public JSONObject getDocument(String documentId) throws IOException, JSONException {
        return getObject(ApiPaths.document(documentId));
    }

    public JSONArray listNotifications(boolean unreadOnly) throws IOException, JSONException {
        String path = unreadOnly ? ApiPaths.NOTIFICATIONS + "?unreadOnly=true" : ApiPaths.NOTIFICATIONS;
        return getArray(path);
    }

    public JSONArray pollNotifications(long afterId, int limit) throws IOException, JSONException {
        int safeLimit = Math.max(1, Math.min(500, limit));
        return getArray(ApiPaths.NOTIFICATIONS + "?afterId=" + Math.max(0, afterId)
                + "&limit=" + safeLimit + "&unreadOnly=false");
    }

    public JSONObject markNotificationRead(String messageId) throws IOException, JSONException {
        return patchJson(ApiPaths.notificationRead(messageId), "{}");
    }

    public JSONArray listHandovers() throws IOException, JSONException {
        return getArray(ApiPaths.HANDOVERS);
    }

    public JSONObject updateHandoverReceipt(
            String handoverId,
            String receiptId,
            String receiptStatus,
            String note
    ) throws IOException, JSONException {
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "receiptStatus", receiptStatus, true);
        JsonEscaper.appendStringField(body, "note", note, false);
        body.append('}');
        return patchJson(ApiPaths.handoverReceipt(handoverId, receiptId), body.toString());
    }

    public JSONObject createFieldComment(FieldCommentDraft draft) throws IOException, JSONException {
        if (!draft.canSend()) {
            throw new IOException("FieldComment target and rawContent are required.");
        }
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "documentId", draft.documentId, false);
        JsonEscaper.appendStringField(body, "documentVersionId", draft.documentVersionId, false);
        JsonEscaper.appendStringField(body, "workRecordId", draft.workRecordId, false);
        JsonEscaper.appendStringField(body, "commentType", "issue", true);
        JsonEscaper.appendStringField(body, "inputMode", draft.normalizedInputMode(), true);
        JsonEscaper.appendStringField(body, "signalLevel", draft.signalLevel, false);
        JsonEscaper.appendStringField(body, "rawContent", draft.rawContent, true);
        JsonEscaper.appendStringField(body, "authorId", draft.authorId, false);
        JsonEscaper.appendStringField(body, "reportedBy", draft.authorId, false);
        JsonEscaper.appendStringField(body, "entrySource", "android_field_terminal", true);
        JsonEscaper.appendStringField(body, "deviceId", draft.deviceId, false);
        JsonEscaper.appendStringField(body, "idempotencyKey", draft.idempotencyKey, true);
        body.append('}');
        return postJson(ApiPaths.FIELD_COMMENTS, body.toString(), true);
    }

    public JSONObject uploadFieldCommentPhoto(String commentId, Uri photoUri, String createdBy)
            throws IOException, JSONException {
        String boundary = "FlowNoteAndroid" + System.currentTimeMillis();
        HttpURLConnection connection = openConnection(ApiPaths.fieldCommentAttachments(commentId), "POST", true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        try (OutputStream output = connection.getOutputStream()) {
            writeFormField(output, boundary, "attachmentType", "photo");
            writeFormField(output, boundary, "caption", "현장 사진 기록");
            if (createdBy != null && !createdBy.trim().isEmpty()) {
                writeFormField(output, boundary, "createdBy", createdBy);
            }
            output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            output.write(("Content-Disposition: form-data; name=\"file\"; filename=\"field-photo.jpg\"\r\n")
                    .getBytes(StandardCharsets.UTF_8));
            output.write(("Content-Type: image/jpeg\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            InputStream source = contentResolver.openInputStream(photoUri);
            if (source == null) {
                throw new IOException("Photo content cannot be opened.");
            }
            try (InputStream input = new BufferedInputStream(source)) {
                if (input == null) {
                    throw new IOException("Photo content cannot be opened.");
                }
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    output.write(buffer, 0, read);
                }
            }
            output.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }
        return new JSONObject(readResponse(connection));
    }

    private void writeFormField(OutputStream output, String boundary, String name, String value) throws IOException {
        output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        output.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        output.write(value.getBytes(StandardCharsets.UTF_8));
        output.write("\r\n".getBytes(StandardCharsets.UTF_8));
    }

    private JSONArray getArray(String path) throws IOException, JSONException {
        HttpURLConnection connection = openConnection(path, "GET", true);
        return new JSONArray(readResponse(connection));
    }

    private JSONObject getObject(String path) throws IOException, JSONException {
        HttpURLConnection connection = openConnection(path, "GET", true);
        return new JSONObject(readResponse(connection));
    }

    private JSONObject postJson(String path, String body, boolean authenticated) throws IOException, JSONException {
        HttpURLConnection connection = openConnection(path, "POST", authenticated);
        writeJsonBody(connection, body);
        return new JSONObject(readResponse(connection));
    }

    private JSONObject patchJson(String path, String body) throws IOException, JSONException {
        HttpURLConnection connection = openConnection(path, "PATCH", true);
        writeJsonBody(connection, body);
        return new JSONObject(readResponse(connection));
    }

    private void writeJsonBody(HttpURLConnection connection, String body) throws IOException {
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        try (OutputStream output = connection.getOutputStream()) {
            output.write(body.getBytes(StandardCharsets.UTF_8));
        }
    }

    private HttpURLConnection openConnection(String path, String method, boolean authenticated) throws IOException {
        if (baseUrl.isEmpty()) {
            throw new IOException("Server URL is empty.");
        }
        HttpURLConnection connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(15000);
        connection.setRequestProperty("Accept", "application/json");
        if (authenticated) {
            if (accessToken == null || accessToken.trim().isEmpty()) {
                throw new IOException("Access token is missing.");
            }
            connection.setRequestProperty("Authorization", "Bearer " + accessToken);
        }
        if ("POST".equals(method) || "PATCH".equals(method)) {
            connection.setDoOutput(true);
        }
        return connection;
    }

    private String readResponse(HttpURLConnection connection) throws IOException {
        int code = connection.getResponseCode();
        InputStream stream = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        String body = readFully(stream);
        if (code < 200 || code >= 300) {
            if (shouldDiscardStoredSession(code) && authenticationFailureListener != null) {
                authenticationFailureListener.onAuthenticationRejected();
            }
            throw new IOException("HTTP " + code + ": " + body);
        }
        return body;
    }

    private String readFully(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
            return builder.toString();
        }
    }
}
