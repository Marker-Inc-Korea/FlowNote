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

    [JsonPropertyName("latest_version")]
    public ServerDocumentVersionResponse? LatestVersion { get; init; }
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

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }
}
