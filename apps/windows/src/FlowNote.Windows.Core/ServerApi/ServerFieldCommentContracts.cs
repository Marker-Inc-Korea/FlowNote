using System.Text.Json.Serialization;
using FlowNote.Windows.Core.FieldComments;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerFieldCommentCreateRequest
{
    [JsonPropertyName("documentId")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("documentVersionId")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("structureItemId")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("workRecordId")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("commentType")]
    public string CommentType { get; init; } = "issue";

    [JsonPropertyName("inputMode")]
    public string InputMode { get; init; } = "free_text";

    [JsonPropertyName("signalLevel")]
    public string? SignalLevel { get; init; }

    [JsonPropertyName("templateId")]
    public string? TemplateId { get; init; }

    [JsonPropertyName("rawContent")]
    public string RawContent { get; init; } = string.Empty;

    [JsonPropertyName("authorId")]
    public string? AuthorId { get; init; }

    [JsonPropertyName("reportedBy")]
    public string? ReportedBy { get; init; }

    [JsonPropertyName("operatorId")]
    public string? OperatorId { get; init; }

    [JsonPropertyName("entrySource")]
    public string EntrySource { get; init; } = "field_user";

    [JsonPropertyName("deviceId")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("locationCode")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("category")]
    public string? Category { get; init; }

    [JsonPropertyName("priority")]
    public int? Priority { get; init; }

    [JsonPropertyName("idempotencyKey")]
    public string? IdempotencyKey { get; init; }

    public static ServerFieldCommentCreateRequest FromLocal(
        FieldCommentRecord fieldComment,
        string? documentId = null,
        string? documentVersionId = null,
        string? idempotencyKey = null)
    {
        return new ServerFieldCommentCreateRequest
        {
            DocumentId = Clean(documentId) ?? Clean(fieldComment.DocumentId),
            DocumentVersionId = Clean(documentVersionId),
            CommentType = fieldComment.CommentType,
            InputMode = fieldComment.InputMode,
            SignalLevel = Clean(fieldComment.SignalLevel),
            RawContent = fieldComment.RawContent,
            ReportedBy = Clean(fieldComment.ReportedBy) ?? Clean(fieldComment.AuthorName),
            EntrySource = fieldComment.EntrySource,
            DeviceId = Clean(fieldComment.DeviceId),
            LocationCode = Clean(fieldComment.LocationCode),
            IdempotencyKey = Clean(idempotencyKey)
        };
    }

    private static string? Clean(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }
}

public sealed record ServerFieldCommentResponse
{
    [JsonPropertyName("comment_id")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("document_id")]
    public string? DocumentId { get; init; }

    [JsonPropertyName("document_version_id")]
    public string? DocumentVersionId { get; init; }

    [JsonPropertyName("structure_item_id")]
    public string? StructureItemId { get; init; }

    [JsonPropertyName("work_record_id")]
    public string? WorkRecordId { get; init; }

    [JsonPropertyName("comment_type")]
    public string CommentType { get; init; } = string.Empty;

    [JsonPropertyName("input_mode")]
    public string InputMode { get; init; } = string.Empty;

    [JsonPropertyName("signal_level")]
    public string? SignalLevel { get; init; }

    [JsonPropertyName("template_id")]
    public string? TemplateId { get; init; }

    [JsonPropertyName("raw_content")]
    public string RawContent { get; init; } = string.Empty;

    [JsonPropertyName("normalized_content")]
    public string? NormalizedContent { get; init; }

    [JsonPropertyName("analysis_content")]
    public string? AnalysisContent { get; init; }

    [JsonPropertyName("author_id")]
    public string? AuthorId { get; init; }

    [JsonPropertyName("reported_by")]
    public string? ReportedBy { get; init; }

    [JsonPropertyName("operator_id")]
    public string? OperatorId { get; init; }

    [JsonPropertyName("entry_source")]
    public string EntrySource { get; init; } = string.Empty;

    [JsonPropertyName("device_id")]
    public string? DeviceId { get; init; }

    [JsonPropertyName("location_code")]
    public string? LocationCode { get; init; }

    [JsonPropertyName("category")]
    public string? Category { get; init; }

    [JsonPropertyName("priority")]
    public int? Priority { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("reviewed_by")]
    public string? ReviewedBy { get; init; }

    [JsonPropertyName("analyzed_by")]
    public string? AnalyzedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; init; }

    [JsonPropertyName("reviewed_at")]
    public DateTime? ReviewedAt { get; init; }

    [JsonPropertyName("analyzed_at")]
    public DateTime? AnalyzedAt { get; init; }
}

public sealed record ServerFieldCommentAttachmentFileResponse
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
    public long? SizeBytes { get; init; }

    [JsonPropertyName("hash_sha256")]
    public string? HashSha256 { get; init; }
}

public sealed record ServerFieldCommentAttachmentResponse
{
    [JsonPropertyName("attachment_id")]
    public string AttachmentId { get; init; } = string.Empty;

    [JsonPropertyName("comment_id")]
    public string CommentId { get; init; } = string.Empty;

    [JsonPropertyName("attachment_type")]
    public string AttachmentType { get; init; } = string.Empty;

    [JsonPropertyName("caption")]
    public string? Caption { get; init; }

    [JsonPropertyName("captured_at")]
    public DateTime? CapturedAt { get; init; }

    [JsonPropertyName("created_by")]
    public string? CreatedBy { get; init; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; init; }

    [JsonPropertyName("file")]
    public ServerFieldCommentAttachmentFileResponse File { get; init; } = new();
}
