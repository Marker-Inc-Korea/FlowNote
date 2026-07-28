using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerNotificationChannelCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("channelType")]
    public string ChannelType { get; init; } = string.Empty;

    [JsonPropertyName("sourceType")]
    public string? SourceType { get; init; }

    [JsonPropertyName("sourceId")]
    public string? SourceId { get; init; }

    [JsonPropertyName("sourceVersionId")]
    public string? SourceVersionId { get; init; }
}

public sealed record ServerNotificationChannelResponse
{
    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("channel_type")]
    public string ChannelType { get; init; } = string.Empty;

    [JsonPropertyName("source_type")]
    public string? SourceType { get; init; }

    [JsonPropertyName("source_id")]
    public string? SourceId { get; init; }

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    public string ChannelTypeLabel => ChannelLabelFormatter.FormatChannelType(ChannelType);

    public string StatusLabel => ChannelLabelFormatter.FormatChannelStatus(Status);
}

public sealed record ServerChannelMemberUpsertRequest
{
    [JsonPropertyName("userId")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("memberRole")]
    public string MemberRole { get; init; } = "MEMBER";
}

public sealed record ServerChannelMemberUpdateRequest
{
    [JsonPropertyName("memberRole")]
    public string? MemberRole { get; init; }

    [JsonPropertyName("status")]
    public string? Status { get; init; }
}

public sealed record ServerChannelMemberResponse
{
    [JsonPropertyName("member_id")]
    public string MemberId { get; init; } = string.Empty;

    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("member_role")]
    public string MemberRole { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("last_read_message_id")]
    public string? LastReadMessageId { get; init; }

    [JsonPropertyName("last_read_at")]
    public DateTime? LastReadAt { get; init; }

    [JsonPropertyName("added_by")]
    public string? AddedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    public string MemberRoleLabel => ChannelLabelFormatter.FormatMemberRole(MemberRole);

    public string StatusLabel => ChannelLabelFormatter.FormatMemberStatus(Status);
}

public sealed record ServerChannelMessageCreateRequest
{
    [JsonPropertyName("messageType")]
    public string MessageType { get; init; } = string.Empty;

    [JsonPropertyName("sourceType")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("sourceId")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("sourceVersionId")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string? Body { get; init; }
}

public record ServerChannelMessageResponse
{
    [JsonPropertyName("message_id")]
    public string MessageId { get; init; } = string.Empty;

    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("message_type")]
    public string MessageType { get; init; } = string.Empty;

    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string? Body { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    public string MessageTypeLabel => ChannelLabelFormatter.FormatMessageType(MessageType);

    public string SourceTypeLabel => ChannelLabelFormatter.FormatSourceType(SourceType);

    public string SourceLinkText => string.IsNullOrWhiteSpace(SourceVersionId)
        ? $"{SourceTypeLabel}: {SourceId}"
        : $"{SourceTypeLabel}: {SourceId} / {SourceVersionId}";
}

public sealed record ServerUserNotificationResponse : ServerChannelMessageResponse
{
    [JsonPropertyName("cursor")]
    public long Cursor { get; init; }

    [JsonPropertyName("channel_name")]
    public string ChannelName { get; init; } = string.Empty;

    [JsonPropertyName("read")]
    public bool Read { get; init; }

    [JsonPropertyName("read_at")]
    public DateTime? ReadAt { get; init; }

    public string ReadLabel => Read ? "읽음" : "읽지 않음";
}

public sealed record ServerNotificationPage(
    IReadOnlyList<ServerUserNotificationResponse> Items,
    long ServerCursor);

public sealed record ServerHandoverCreateRequest
{
    [JsonPropertyName("channelId")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;

    [JsonPropertyName("sourceType")]
    public string? SourceType { get; init; }

    [JsonPropertyName("sourceId")]
    public string? SourceId { get; init; }

    [JsonPropertyName("sourceVersionId")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("recipientIds")]
    public IReadOnlyList<string> RecipientIds { get; init; } = [];
}

public sealed record ServerHandoverReceiptUpdateRequest
{
    [JsonPropertyName("receiptStatus")]
    public string ReceiptStatus { get; init; } = string.Empty;

    [JsonPropertyName("note")]
    public string? Note { get; init; }
}

public sealed record ServerHandoverReceiptResponse
{
    [JsonPropertyName("receipt_id")]
    public string ReceiptId { get; init; } = string.Empty;

    [JsonPropertyName("handover_id")]
    public string HandoverId { get; init; } = string.Empty;

    [JsonPropertyName("recipient_id")]
    public string RecipientId { get; init; } = string.Empty;

    [JsonPropertyName("receipt_status")]
    public string ReceiptStatus { get; init; } = string.Empty;

    [JsonPropertyName("note")]
    public string? Note { get; init; }

    [JsonPropertyName("read_at")]
    public DateTime? ReadAt { get; init; }

    [JsonPropertyName("acknowledged_at")]
    public DateTime? AcknowledgedAt { get; init; }

    [JsonPropertyName("follow_up_required_at")]
    public DateTime? FollowUpRequiredAt { get; init; }

    [JsonPropertyName("updated_by")]
    public string? UpdatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    public string ReceiptStatusLabel => ChannelLabelFormatter.FormatReceiptStatus(ReceiptStatus);
}

public sealed record ServerHandoverResponse
{
    [JsonPropertyName("handover_id")]
    public string HandoverId { get; init; } = string.Empty;

    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;

    [JsonPropertyName("source_type")]
    public string? SourceType { get; init; }

    [JsonPropertyName("source_id")]
    public string? SourceId { get; init; }

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("sent_at")]
    public DateTime? SentAt { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("receipts")]
    public IReadOnlyList<ServerHandoverReceiptResponse> Receipts { get; init; } = [];

    public string StatusLabel => ChannelLabelFormatter.FormatHandoverStatus(Status);

    public string SourceLinkText
    {
        get
        {
            if (string.IsNullOrWhiteSpace(SourceType) || string.IsNullOrWhiteSpace(SourceId))
            {
                return "원천 없음";
            }

            var sourceTypeLabel = ChannelLabelFormatter.FormatSourceType(SourceType);
            return string.IsNullOrWhiteSpace(SourceVersionId)
                ? $"{sourceTypeLabel}: {SourceId}"
                : $"{sourceTypeLabel}: {SourceId} / {SourceVersionId}";
        }
    }
}

public sealed record ServerHandoverFollowUpResult(
    ServerFieldCommentResponse FieldComment,
    bool ChannelMessagePublished,
    string OperationKey,
    string? ChannelMessageId);

public static class ChannelLabelFormatter
{
    public static string FormatChannelType(string? value) => value switch
    {
        "LINE" => "라인",
        "EQUIPMENT" => "설비",
        "PROCESS" => "공정",
        "WORK_GROUP" => "작업조",
        "HANDOVER" => "인수인계",
        "WORK_RECORD" => "작업내역",
        "CUSTOM" => "기타",
        _ => value ?? string.Empty
    };

    public static string FormatChannelStatus(string? value) => value switch
    {
        "ACTIVE" => "운영",
        "ARCHIVED" => "보관",
        _ => value ?? string.Empty
    };

    public static string FormatMemberRole(string? value) => value switch
    {
        "OWNER" => "소유자",
        "MANAGER" => "관리자",
        "MEMBER" => "멤버",
        _ => value ?? string.Empty
    };

    public static string FormatMemberStatus(string? value) => value switch
    {
        "ACTIVE" => "활성",
        "REMOVED" => "제외",
        _ => value ?? string.Empty
    };

    public static string FormatMessageType(string? value) => value switch
    {
        "NOTICE" => "공지",
        "DOCUMENT_EVENT" => "문서",
        "FIELD_COMMENT_EVENT" => "FieldComment",
        "WORK_SEQUENCE_EVENT" => "작업순서",
        "HANDOVER" => "인수인계",
        "SYSTEM" => "시스템",
        _ => value ?? string.Empty
    };

    public static string FormatSourceType(string? value) => value switch
    {
        "DOCUMENT" => "문서",
        "FIELD_COMMENT" => "FieldComment",
        "WORK_SEQUENCE_ITEM" => "작업순서 항목",
        "WORK_SEQUENCE_HISTORY" => "작업순서 이력",
        "WORK_RECORD" => "작업내역",
        "REPORT" => "보고서",
        "HANDOVER" => "인수인계",
        "CHANNEL_MESSAGE" => "채널 메시지",
        "SYSTEM" => "시스템",
        _ => value ?? string.Empty
    };

    public static string FormatHandoverStatus(string? value) => value switch
    {
        "DRAFT" => "초안",
        "SENT" => "발송",
        "ACKNOWLEDGED" => "전체 확인",
        "FOLLOW_UP_REQUIRED" => "후속 필요",
        "ARCHIVED" => "보관",
        _ => value ?? string.Empty
    };

    public static string FormatReceiptStatus(string? value) => value switch
    {
        "UNREAD" => "보류",
        "READ" => "읽음",
        "ACKNOWLEDGED" => "확인",
        "FOLLOW_UP_REQUIRED" => "후속 필요",
        _ => value ?? string.Empty
    };
}
