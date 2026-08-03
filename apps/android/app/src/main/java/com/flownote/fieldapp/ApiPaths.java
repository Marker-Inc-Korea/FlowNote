package com.flownote.fieldapp;

public final class ApiPaths {
    private ApiPaths() {
    }

    public static final String LOGIN = "/api/v1/auth/login";
    public static final String PUBLISHED_DOCUMENTS = "/api/v1/documents/published";
    public static final String DOCUMENTS = "/api/v1/documents/";
    public static final String FIELD_COMMENTS = "/api/v1/field-comments";
    public static final String NOTIFICATIONS = "/api/v1/notifications";
    public static final String HANDOVERS = "/api/v1/handovers";
    public static final String NOTIFICATION_CHANNELS = "/api/v1/notification-channels";
    public static final String LOGOUT = "/api/v1/auth/logout";
    public static final String REFRESH = "/api/v1/auth/refresh";

    public static String document(String documentId) {
        return DOCUMENTS + documentId;
    }

    public static String androidViewGrant(String documentId, String versionId) {
        return DOCUMENTS + documentId + "/versions/" + versionId + "/android-view-grants";
    }

    public static String fieldCommentAttachments(String commentId) {
        return FIELD_COMMENTS + "/" + commentId + "/attachments";
    }

    public static String notificationRead(String messageId) {
        return NOTIFICATIONS + "/" + messageId + "/read";
    }

    public static String handoverReceipt(String handoverId, String receiptId) {
        return HANDOVERS + "/" + handoverId + "/receipts/" + receiptId;
    }

    public static String channelMembers(String channelId) {
        return NOTIFICATION_CHANNELS + "/" + channelId + "/members";
    }

    public static String channelMessages(String channelId) {
        return NOTIFICATION_CHANNELS + "/" + channelId + "/messages";
    }
}
