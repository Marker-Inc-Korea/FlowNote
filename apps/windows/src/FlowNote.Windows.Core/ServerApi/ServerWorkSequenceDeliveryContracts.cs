using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerWorkSequenceDeliveryRecipientPreview
{
    [JsonPropertyName("user_id")]
    public string UserId { get; init; } = string.Empty;

    [JsonPropertyName("display_name")]
    public string DisplayName { get; init; } = string.Empty;

    [JsonPropertyName("member_role")]
    public string MemberRole { get; init; } = string.Empty;
}

public sealed record ServerWorkSequenceDeliverySourcePreview
{
    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("change_id")]
    public string ChangeId { get; init; } = string.Empty;

    [JsonPropertyName("item_title")]
    public string? ItemTitle { get; init; }

    [JsonPropertyName("published_document_id")]
    public string? PublishedDocumentId { get; init; }

    [JsonPropertyName("published_document_version_id")]
    public string? PublishedDocumentVersionId { get; init; }

    [JsonPropertyName("published_document_title")]
    public string? PublishedDocumentTitle { get; init; }
}

public sealed record ServerWorkSequenceDeliveryPreviewResponse
{
    [JsonPropertyName("candidate_id")]
    public string CandidateId { get; init; } = string.Empty;

    [JsonPropertyName("candidate_status")]
    public string CandidateStatus { get; init; } = string.Empty;

    [JsonPropertyName("candidate_board_revision")]
    public int CandidateBoardRevision { get; init; }

    [JsonPropertyName("current_board_revision")]
    public int CurrentBoardRevision { get; init; }

    [JsonPropertyName("expires_at")]
    public DateTime? ExpiresAt { get; init; }

    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("channel_name")]
    public string ChannelName { get; init; } = string.Empty;

    [JsonPropertyName("channel_type")]
    public string ChannelType { get; init; } = string.Empty;

    [JsonPropertyName("channel_source_type")]
    public string? ChannelSourceType { get; init; }

    [JsonPropertyName("channel_source_id")]
    public string? ChannelSourceId { get; init; }

    [JsonPropertyName("required_member_role")]
    public string RequiredMemberRole { get; init; } = string.Empty;

    [JsonPropertyName("can_deliver")]
    public bool CanDeliver { get; init; }

    [JsonPropertyName("recipients")]
    public IReadOnlyList<ServerWorkSequenceDeliveryRecipientPreview> Recipients { get; init; } = [];

    [JsonPropertyName("recipient_count")]
    public int RecipientCount { get; init; }

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public ServerWorkSequenceDeliverySourcePreview Source { get; init; } = new();

    public string ChannelSummary =>
        $"{ChannelLabelFormatter.FormatChannelType(ChannelType)} · {ChannelName} · 수신자 {RecipientCount}명";

    public string SourceSummary => string.IsNullOrWhiteSpace(Source.ItemTitle)
        ? $"변경 이력 {Source.ChangeId}"
        : $"작업 항목 {Source.ItemTitle} · 변경 이력 {Source.ChangeId}";

    public string DocumentSummary => string.IsNullOrWhiteSpace(Source.PublishedDocumentId)
        ? "연결된 공개 문서 없음"
        : $"공개 문서 {Source.PublishedDocumentTitle} · {Source.PublishedDocumentId}";
}

public sealed record ServerWorkSequenceDeliveryRequest
{
    [JsonPropertyName("channelId")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("deliveryMode")]
    public string DeliveryMode { get; init; } = string.Empty;

    [JsonPropertyName("recipientIds")]
    public IReadOnlyList<string> RecipientIds { get; init; } = [];

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = string.Empty;

    [JsonPropertyName("baseBoardRevision")]
    public int BaseBoardRevision { get; init; }

    [JsonPropertyName("idempotencyKey")]
    public string IdempotencyKey { get; init; } = string.Empty;

    public string BuildStableIdempotencyKey(string boardId, string candidateId)
    {
        static string Part(string? value)
        {
            var normalized = value?.Trim() ?? string.Empty;
            return $"{normalized.Length}:{normalized}";
        }

        var intent = string.Join(
            "\n",
            Part(boardId),
            Part(candidateId),
            Part(ChannelId),
            Part(DeliveryMode.ToUpperInvariant()),
            Part(string.Join(",", RecipientIds.Select(value => value.Trim()).Order(StringComparer.Ordinal))),
            Part(Title),
            Part(Body),
            Part(Reason),
            BaseBoardRevision.ToString(CultureInfo.InvariantCulture));
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(intent)))
            .ToLowerInvariant();
        return $"wpf:wseq-delivery:{digest}";
    }
}

public sealed record ServerWorkSequenceDeliveryRecipientResult
{
    [JsonPropertyName("recipient_id")]
    public string RecipientId { get; init; } = string.Empty;

    [JsonPropertyName("delivery_status")]
    public string DeliveryStatus { get; init; } = string.Empty;

    [JsonPropertyName("handover_receipt_id")]
    public string? HandoverReceiptId { get; init; }

    [JsonPropertyName("error_code")]
    public string? ErrorCode { get; init; }

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; init; }

    [JsonPropertyName("attempt_count")]
    public int AttemptCount { get; init; }
}

public sealed record ServerWorkSequenceDeliveryResponse
{
    [JsonPropertyName("delivery_id")]
    public string DeliveryId { get; init; } = string.Empty;

    [JsonPropertyName("candidate_id")]
    public string CandidateId { get; init; } = string.Empty;

    [JsonPropertyName("candidate_status")]
    public string CandidateStatus { get; init; } = string.Empty;

    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("board_revision")]
    public int BoardRevision { get; init; }

    [JsonPropertyName("change_id")]
    public string ChangeId { get; init; } = string.Empty;

    [JsonPropertyName("channel_id")]
    public string ChannelId { get; init; } = string.Empty;

    [JsonPropertyName("delivery_mode")]
    public string DeliveryMode { get; init; } = string.Empty;

    [JsonPropertyName("intent_hash_sha256")]
    public string IntentHashSha256 { get; init; } = string.Empty;

    [JsonPropertyName("message_id")]
    public string? MessageId { get; init; }

    [JsonPropertyName("handover_id")]
    public string? HandoverId { get; init; }

    [JsonPropertyName("source_type")]
    public string SourceType { get; init; } = string.Empty;

    [JsonPropertyName("source_id")]
    public string SourceId { get; init; } = string.Empty;

    [JsonPropertyName("source_version_id")]
    public string? SourceVersionId { get; init; }

    [JsonPropertyName("related_document_id")]
    public string? RelatedDocumentId { get; init; }

    [JsonPropertyName("related_document_version_id")]
    public string? RelatedDocumentVersionId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("success_count")]
    public int SuccessCount { get; init; }

    [JsonPropertyName("failure_count")]
    public int FailureCount { get; init; }

    [JsonPropertyName("recipients")]
    public IReadOnlyList<ServerWorkSequenceDeliveryRecipientResult> Recipients { get; init; } = [];
}

public sealed record ServerWorkSequenceDeliveryTemplateCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;
}

public sealed record ServerWorkSequenceDeliveryTemplateResponse
{
    [JsonPropertyName("template_id")]
    public string TemplateId { get; init; } = string.Empty;

    [JsonPropertyName("site_scope")]
    public string SiteScope { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("body")]
    public string Body { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;
}
