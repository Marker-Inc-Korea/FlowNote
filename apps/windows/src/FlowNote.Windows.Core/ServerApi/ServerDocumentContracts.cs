using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerFileObjectResponse
{
    [JsonPropertyName("storage_type")]
    public string StorageType { get; init; } = string.Empty;

    [JsonPropertyName("storage_key")]
    public string StorageKey { get; init; } = string.Empty;

    [JsonPropertyName("original_filename")]
    public string OriginalFilename { get; init; } = string.Empty;

    [JsonPropertyName("extension")]
    public string? Extension { get; init; }

    [JsonPropertyName("mime_type")]
    public string? MimeType { get; init; }

    [JsonPropertyName("file_family")]
    public string? FileFamily { get; init; }

    [JsonPropertyName("size_bytes")]
    public int? SizeBytes { get; init; }

    [JsonPropertyName("hash_sha256")]
    public string? HashSha256 { get; init; }
}

public sealed record ServerDocumentVersionResponse
{
    [JsonPropertyName("version_id")]
    public string VersionId { get; init; } = string.Empty;

    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("version_no")]
    public int VersionNo { get; init; }

    [JsonPropertyName("version_label")]
    public string? VersionLabel { get; init; }

    [JsonPropertyName("change_reason")]
    public string ChangeReason { get; init; } = string.Empty;

    [JsonPropertyName("version_status")]
    public string VersionStatus { get; init; } = string.Empty;

    [JsonPropertyName("is_latest")]
    public bool IsLatest { get; init; }

    [JsonPropertyName("is_published")]
    public bool IsPublished { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("file")]
    public ServerFileObjectResponse File { get; init; } = new();
}

public sealed record ServerDocumentResponse
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("document_type")]
    public string DocumentType { get; init; } = string.Empty;

    [JsonPropertyName("owner_id")]
    public string? OwnerId { get; init; }

    [JsonPropertyName("category_id")]
    public string? CategoryId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("latest_version_id")]
    public string? LatestVersionId { get; init; }

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("tags")]
    public IReadOnlyList<string> Tags { get; init; } = [];

    [JsonPropertyName("latest_version")]
    public ServerDocumentVersionResponse? LatestVersion { get; init; }

    [JsonPropertyName("published_version")]
    public ServerDocumentVersionResponse? PublishedVersion { get; init; }
}

public sealed record ServerDocumentListItem
{
    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("document_type")]
    public string DocumentType { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("latest_version_id")]
    public string? LatestVersionId { get; init; }

    [JsonPropertyName("latest_version_no")]
    public int? LatestVersionNo { get; init; }

    [JsonPropertyName("latest_filename")]
    public string? LatestFilename { get; init; }

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; init; }

    [JsonPropertyName("published_version_no")]
    public int? PublishedVersionNo { get; init; }

    [JsonPropertyName("published_filename")]
    public string? PublishedFilename { get; init; }

    [JsonPropertyName("tags")]
    public IReadOnlyList<string> Tags { get; init; } = [];

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }
}

public sealed record ServerDocumentVersionPublishRequest
{
    [JsonPropertyName("changeReason")]
    public string? ChangeReason { get; init; }
}

public sealed record ServerDocumentAccessLogCreateRequest
{
    [JsonPropertyName("documentVersionId")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("actorId")]
    public string? ActorId { get; init; }

    [JsonPropertyName("deviceId")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("clientIp")]
    public string? ClientIp { get; init; }

    [JsonPropertyName("userAgent")]
    public string? UserAgent { get; init; }

    [JsonPropertyName("idempotencyKey")]
    public string? IdempotencyKey { get; init; }
}

public sealed record ServerDocumentAccessLogResponse
{
    [JsonPropertyName("log_id")]
    public int LogId { get; init; }

    [JsonPropertyName("document_id")]
    public string DocumentId { get; init; } = string.Empty;

    [JsonPropertyName("document_version_id")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("actor_id")]
    public string? ActorId { get; init; }

    [JsonPropertyName("device_id")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("client_ip")]
    public string? ClientIp { get; init; }

    [JsonPropertyName("user_agent")]
    public string? UserAgent { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }
}

public sealed record ServerWorkSequenceBoardCreateRequest
{
    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("lineCode")]
    public string? LineCode { get; init; }

    [JsonPropertyName("boardDate")]
    public DateOnly? BoardDate { get; init; }

    [JsonPropertyName("createdBy")]
    public string? CreatedBy { get; init; }
}

public sealed record ServerWorkSequenceItemCreateRequest
{
    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("workOrderNo")]
    public string? WorkOrderNo { get; init; }

    [JsonPropertyName("documentId")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("assignedTo")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("createdBy")]
    public string? CreatedBy { get; init; }
}

public sealed record ServerWorkSequenceReorderRequest
{
    [JsonPropertyName("itemIds")]
    public IReadOnlyList<string> ItemIds { get; init; } = [];

    [JsonPropertyName("actorId")]
    public string? ActorId { get; init; }

    [JsonPropertyName("changeReason")]
    public string? ChangeReason { get; init; }
}

public sealed record ServerWorkSequenceStatusUpdateRequest
{
    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("actorId")]
    public string? ActorId { get; init; }

    [JsonPropertyName("changeReason")]
    public string? ChangeReason { get; init; }

    [JsonPropertyName("holdReason")]
    public string? HoldReason { get; init; }
}

public sealed record ServerWorkSequenceItemResponse
{
    [JsonPropertyName("item_id")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("work_order_no")]
    public string? WorkOrderNo { get; init; }

    [JsonPropertyName("document_id")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("hold_reason")]
    public string? HoldReason { get; init; }

    [JsonPropertyName("sort_order")]
    public int SortOrder { get; init; }

    [JsonPropertyName("assigned_to")]
    public string? AssignedTo { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }
}

public sealed record ServerWorkSequenceBoardResponse
{
    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("line_code")]
    public string? LineCode { get; init; }

    [JsonPropertyName("board_date")]
    public DateOnly? BoardDate { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<ServerWorkSequenceItemResponse> Items { get; init; } = [];
}

public sealed record ServerWorkSequenceHistoryResponse
{
    [JsonPropertyName("change_id")]
    public string ChangeId { get; init; } = string.Empty;

    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("item_id")]
    public string? ItemId { get; init; }

    [JsonPropertyName("change_type")]
    public string ChangeType { get; init; } = string.Empty;

    [JsonPropertyName("actor_id")]
    public string? ActorId { get; init; }

    [JsonPropertyName("before_value")]
    public string? BeforeValue { get; init; }

    [JsonPropertyName("after_value")]
    public string? AfterValue { get; init; }

    [JsonPropertyName("change_reason")]
    public string? ChangeReason { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }
}

public sealed record ServerWorkSequenceNotificationCandidateStatusRequest
{
    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;
}

public sealed record ServerWorkSequenceNotificationCandidateResponse
{
    [JsonPropertyName("candidate_id")]
    public string CandidateId { get; init; } = string.Empty;

    [JsonPropertyName("board_id")]
    public string BoardId { get; init; } = string.Empty;

    [JsonPropertyName("item_id")]
    public string? ItemId { get; init; }

    [JsonPropertyName("event_type")]
    public string EventType { get; init; } = string.Empty;

    [JsonPropertyName("actor_id")]
    public string? ActorId { get; init; }

    [JsonPropertyName("recipient_hint")]
    public string? RecipientHint { get; init; }

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }
}
