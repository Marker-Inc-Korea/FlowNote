package com.flownote.fieldapp;

import android.content.ContentResolver;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

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

    static boolean shouldDiscardStoredSession(int httpStatus, String responseBody) {
        if (shouldDiscardStoredSession(httpStatus)) {
            return true;
        }
        if (httpStatus != HttpURLConnection.HTTP_FORBIDDEN || responseBody == null) {
            return false;
        }
        return responseBody.contains("DEVICE_NOT_APPROVED")
                || responseBody.contains("Terminal device is not approved");
    }

    static boolean isAuthenticationRejected(IOException exception) {
        String message = exception.getMessage();
        return message != null && (
                message.startsWith("HTTP 401")
                        || (message.startsWith("HTTP 403")
                        && (message.contains("DEVICE_NOT_APPROVED")
                        || message.contains("Terminal device is not approved")))
        );
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

    public JSONObject refresh(String refreshToken) throws IOException, JSONException {
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "refresh_token", refreshToken, true);
        body.append('}');
        JSONObject result = postJson(ApiPaths.REFRESH, body.toString(), false);
        accessToken = result.getString("access_token");
        return result;
    }

    public JSONArray listPublishedDocuments() throws IOException, JSONException {
        return getArray(ApiPaths.PUBLISHED_DOCUMENTS);
    }

    public JSONObject getDocument(String documentId) throws IOException, JSONException {
        return getObject(ApiPaths.document(documentId));
    }

    public void logout() throws IOException, JSONException {
        postJson(ApiPaths.LOGOUT, "{}", true);
    }

    public SecureDocumentPayload downloadSecureDocument(
            String documentId,
            String versionId,
            File destination
    ) throws IOException, JSONException {
        JSONObject grant = postJson(ApiPaths.androidViewGrant(documentId, versionId), "{}", true);
        String streamUrl = grant.getString("stream_url");
        long expectedSize = grant.getLong("size_bytes");
        String expectedHash = grant.getString("hash_sha256");
        HttpURLConnection connection = openConnection(streamUrl, "GET", true);
        connection.setRequestProperty("Accept", grant.getString("mime_type"));
        try {
            int code = connection.getResponseCode();
            if (code < 200 || code >= 300) {
                String error = readFully(connection.getErrorStream());
                if (shouldDiscardStoredSession(code, error)
                        && authenticationFailureListener != null) {
                    authenticationFailureListener.onAuthenticationRejected();
                }
                throw new IOException("HTTP " + code + ": " + error);
            }
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException exc) {
                throw new IOException("SHA-256 verification is unavailable.", exc);
            }
            long received = 0;
            try (InputStream input = new BufferedInputStream(connection.getInputStream());
                 FileOutputStream output = new FileOutputStream(destination)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    received += read;
                    if (received > expectedSize) {
                        throw new IOException("수신 문서 크기가 서버 계약을 초과했습니다.");
                    }
                    digest.update(buffer, 0, read);
                    output.write(buffer, 0, read);
                }
                output.getFD().sync();
            }
            String actualHash = toHex(digest.digest());
            String headerHash = connection.getHeaderField("X-Content-SHA256");
            if (received != expectedSize
                    || !expectedHash.equalsIgnoreCase(actualHash)
                    || headerHash == null
                    || !expectedHash.equalsIgnoreCase(headerHash)) {
                throw new IOException("수신 문서 무결성 검증에 실패했습니다.");
            }
            return new SecureDocumentPayload(
                    destination,
                    grant.getString("media_kind"),
                    grant.getString("mime_type"),
                    grant.getInt("max_pdf_pages"),
                    grant.getInt("auto_close_seconds")
            );
        } catch (IOException | JSONException exc) {
            SecureViewerFiles.delete(destination);
            throw exc;
        } finally {
            connection.disconnect();
        }
    }

    static String toHex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(String.format(java.util.Locale.ROOT, "%02x", value & 0xff));
        }
        return result.toString();
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

    public JSONObject markNotificationRead(
            String messageId, String deliveryRunId, String displayedAt
    ) throws IOException, JSONException {
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "deliveryRunId", deliveryRunId, false);
        JsonEscaper.appendStringField(body, "displayedAt", displayedAt, false);
        body.append('}');
        return patchJson(ApiPaths.notificationRead(messageId), body.toString());
    }

    public JSONArray listHandovers() throws IOException, JSONException {
        return getArray(ApiPaths.HANDOVERS);
    }

    public JSONArray listNotificationChannels() throws IOException, JSONException {
        return getArray(ApiPaths.NOTIFICATION_CHANNELS + "?status=ACTIVE");
    }

    public JSONArray listChannelMembers(String channelId) throws IOException, JSONException {
        return getArray(ApiPaths.channelMembers(channelId));
    }

    public JSONObject createHandover(HandoverDraft draft) throws IOException, JSONException {
        if (!draft.canQueue()) {
            throw new IOException("Handover channel, recipients, source, title, and body are required.");
        }
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "channelId", draft.channelId, true);
        JsonEscaper.appendStringField(body, "title", draft.title, true);
        JsonEscaper.appendStringField(body, "body", draft.body, true);
        JsonEscaper.appendStringField(body, "sourceType", draft.sourceType, true);
        JsonEscaper.appendStringField(body, "sourceId", draft.sourceId, true);
        JsonEscaper.appendStringField(body, "sourceVersionId", draft.sourceVersionId, false);
        body.append(",\"recipientIds\":[");
        for (int index = 0; index < draft.recipientIds.size(); index++) {
            if (index > 0) {
                body.append(',');
            }
            body.append(JsonEscaper.quote(draft.recipientIds.get(index)));
        }
        body.append(']');
        JsonEscaper.appendStringField(body, "entrySource", "android_field_terminal", false);
        JsonEscaper.appendStringField(body, "deviceId", draft.deviceId, false);
        JsonEscaper.appendStringField(body, "idempotencyKey", draft.idempotencyKey, false);
        body.append('}');
        return postJson(ApiPaths.HANDOVERS, body.toString(), true);
    }

    public JSONObject updateHandoverReceipt(
            String handoverId,
            String receiptId,
            String receiptStatus,
            String note,
            String deliveryRunId
    ) throws IOException, JSONException {
        StringBuilder body = new StringBuilder("{");
        JsonEscaper.appendStringField(body, "receiptStatus", receiptStatus, true);
        JsonEscaper.appendStringField(body, "note", note, false);
        JsonEscaper.appendStringField(body, "deliveryRunId", deliveryRunId, false);
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

    public JSONObject uploadFieldCommentPhoto(
            String commentId,
            Uri photoUri,
            String createdBy,
            String idempotencyKey
    )
            throws IOException, JSONException {
        InputStream source = contentResolver.openInputStream(photoUri);
        if (source == null) {
            throw new IOException("Photo content cannot be opened.");
        }
        return uploadFieldCommentPhoto(commentId, source, createdBy, idempotencyKey);
    }

    public JSONObject uploadFieldCommentPhoto(
            String commentId,
            InputStream photoInput,
            String createdBy,
            String idempotencyKey
    )
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
            writeFormField(output, boundary, "parentCommentId", commentId);
            if (idempotencyKey != null && !idempotencyKey.trim().isEmpty()) {
                writeFormField(output, boundary, "idempotencyKey", idempotencyKey);
            }
            output.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            output.write(("Content-Disposition: form-data; name=\"file\"; filename=\"field-photo.jpg\"\r\n")
                    .getBytes(StandardCharsets.UTF_8));
            output.write(("Content-Type: image/jpeg\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            try (InputStream input = new BufferedInputStream(photoInput)) {
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
            if (shouldDiscardStoredSession(code, body)
                    && authenticationFailureListener != null) {
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
