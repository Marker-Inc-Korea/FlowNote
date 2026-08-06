using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerApprovalClient(HttpClient httpClient)
{
    public async Task<IReadOnlyList<ServerDocumentApprovalResponse>> ListAsync(
        bool assignedToMe = false,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/document-approvals?assignedToMe={assignedToMe.ToString().ToLowerInvariant()}",
            cancellationToken);
        return await ReadAsync<List<ServerDocumentApprovalResponse>>(response, cancellationToken);
    }

    public async Task<ServerApprovalDocumentResponse> GetDocumentAsync(
        string documentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/documents/{Uri.EscapeDataString(documentId)}",
            cancellationToken);
        return await ReadAsync<ServerApprovalDocumentResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentApprovalResponse> RequestAsync(
        ServerDocumentApprovalCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/document-approvals", request, cancellationToken);
        return await ReadAsync<ServerDocumentApprovalResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentApprovalResponse> DecideAsync(
        string approvalId,
        string decision,
        string reason,
        string mutationKey,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/document-approvals/{Uri.EscapeDataString(approvalId)}/decision",
            new ServerDocumentApprovalDecisionRequest(decision, reason, mutationKey),
            cancellationToken);
        return await ReadAsync<ServerDocumentApprovalResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentApprovalResponse> CancelAsync(
        string approvalId,
        string reason,
        string mutationKey,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/document-approvals/{Uri.EscapeDataString(approvalId)}/cancel",
            new ServerDocumentApprovalCancelRequest(reason, mutationKey),
            cancellationToken);
        return await ReadAsync<ServerDocumentApprovalResponse>(response, cancellationToken);
    }

    public async Task<ServerApprovalDocumentResponse> PublishAsync(
        ServerDocumentApprovalResponse approval,
        string reason,
        string mutationKey,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/documents/{Uri.EscapeDataString(approval.DocumentId)}/versions/" +
            $"{Uri.EscapeDataString(approval.VersionId)}/publish",
            new ServerApprovedDocumentPublishRequest(
                approval.ApprovalId,
                approval.BaseDocumentRevision,
                reason,
                mutationKey),
            cancellationToken);
        return await ReadAsync<ServerApprovalDocumentResponse>(response, cancellationToken);
    }

    private static async Task<T> ReadAsync<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new FlowNoteServerApprovalException(
                (int)response.StatusCode,
                ReadError(body));
        }
        return JsonSerializer.Deserialize<T>(body, JsonOptions)
            ?? throw new InvalidOperationException("서버 승인 응답이 비어 있습니다.");
    }

    private static string ReadError(string body)
    {
        try
        {
            using var json = JsonDocument.Parse(body);
            var detail = json.RootElement.GetProperty("detail");
            if (detail.ValueKind == JsonValueKind.String)
            {
                return detail.GetString() ?? "서버 승인 요청을 처리하지 못했습니다.";
            }
            if (detail.TryGetProperty("message", out var message))
            {
                return message.GetString() ?? "서버 승인 요청을 처리하지 못했습니다.";
            }
            return detail.ToString();
        }
        catch (JsonException)
        {
            return "서버 승인 요청을 처리하지 못했습니다.";
        }
    }

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
}

public sealed class FlowNoteServerApprovalException(int statusCode, string message)
    : InvalidOperationException(message)
{
    public int StatusCode { get; } = statusCode;
}

public sealed record ServerDocumentApprovalCreateRequest(
    [property: JsonPropertyName("documentId")] string DocumentId,
    [property: JsonPropertyName("versionId")] string VersionId,
    [property: JsonPropertyName("baseDocumentRevision")] int BaseDocumentRevision,
    [property: JsonPropertyName("sourceFileHashSha256")] string SourceFileHashSha256,
    [property: JsonPropertyName("reviewerUserId")] string? ReviewerUserId,
    [property: JsonPropertyName("reviewerRole")] string? ReviewerRole,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("dueAt")] DateTimeOffset? DueAt,
    [property: JsonPropertyName("mutationKey")] string MutationKey);

public sealed record ServerDocumentApprovalDecisionRequest(
    [property: JsonPropertyName("decision")] string Decision,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("mutationKey")] string MutationKey);

public sealed record ServerDocumentApprovalCancelRequest(
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("mutationKey")] string MutationKey);

public sealed record ServerApprovedDocumentPublishRequest(
    [property: JsonPropertyName("approvalId")] string ApprovalId,
    [property: JsonPropertyName("baseRevision")] int BaseRevision,
    [property: JsonPropertyName("changeReason")] string ChangeReason,
    [property: JsonPropertyName("mutationKey")] string MutationKey);

public sealed record ServerDocumentApprovalResponse(
    [property: JsonPropertyName("approval_id")] string ApprovalId,
    [property: JsonPropertyName("document_id")] string DocumentId,
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("base_document_revision")] int BaseDocumentRevision,
    [property: JsonPropertyName("source_file_hash_sha256")] string SourceFileHashSha256,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("requester_id")] string RequesterId,
    [property: JsonPropertyName("reviewer_user_id")] string? ReviewerUserId,
    [property: JsonPropertyName("reviewer_role")] string? ReviewerRole,
    [property: JsonPropertyName("request_reason")] string RequestReason,
    [property: JsonPropertyName("due_at")] DateTimeOffset? DueAt,
    [property: JsonPropertyName("decision_reason")] string? DecisionReason,
    [property: JsonPropertyName("decided_by")] string? DecidedBy,
    [property: JsonPropertyName("stale_reason")] string? StaleReason,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt,
    [property: JsonPropertyName("events")] IReadOnlyList<ServerDocumentApprovalEvent> Events)
{
    public string StatusDisplay => Status switch
    {
        "REQUESTED" => "◷ 검토 요청",
        "APPROVED" => "✓ 승인",
        "REJECTED" => "✕ 반려",
        "CANCELLED" => "⊘ 취소",
        "STALE" => "⚠ 변경됨·재요청 필요",
        "PUBLISHED" => "● 공개",
        _ => Status
    };

    public string ReviewerDisplay => ReviewerUserId ?? ReviewerRole ?? "미지정";
    public string NextAction => Status switch
    {
        "REQUESTED" => $"담당 검토자 {ReviewerDisplay}의 결정이 필요합니다.",
        "APPROVED" => "정확한 승인 버전을 공개할 수 있습니다.",
        "REJECTED" => $"원본과 승인 기록은 보존됩니다. 반려 사유를 반영해 새 버전으로 다시 요청하세요: {DecisionReason}",
        "STALE" => $"원본과 승인 기록은 보존됩니다. 현재 version/hash로 새 요청을 만드세요: {StaleReason}",
        "PUBLISHED" => "현장 공개본에 반영되었습니다.",
        _ => "상태 이력을 확인하세요."
    };
}

public sealed record ServerDocumentApprovalEvent(
    [property: JsonPropertyName("event_type")] string EventType,
    [property: JsonPropertyName("actor_id")] string ActorId,
    [property: JsonPropertyName("actor_role")] string ActorRole,
    [property: JsonPropertyName("reason")] string? Reason,
    [property: JsonPropertyName("created_at")] DateTimeOffset CreatedAt);

public sealed record ServerApprovalDocumentResponse(
    [property: JsonPropertyName("document_id")] string DocumentId,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("revision")] int Revision,
    [property: JsonPropertyName("latest_version_id")] string? LatestVersionId,
    [property: JsonPropertyName("latest_version")] ServerApprovalVersionResponse? LatestVersion)
{
    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("published_version_id")]
    public string? PublishedVersionId { get; init; }

    [JsonPropertyName("publication_approval_id")]
    public string? PublicationApprovalId { get; init; }

    [JsonPropertyName("published_version")]
    public ServerApprovalVersionResponse? PublishedVersion { get; init; }

    [JsonPropertyName("tags")]
    public IReadOnlyList<string> Tags { get; init; } = [];
}

public sealed record ServerApprovalVersionResponse(
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("file")] ServerApprovalFileResponse File)
{
    [JsonPropertyName("version_no")]
    public int VersionNo { get; init; }

    [JsonPropertyName("version_status")]
    public string VersionStatus { get; init; } = string.Empty;

    [JsonPropertyName("is_latest")]
    public bool IsLatest { get; init; }

    [JsonPropertyName("is_published")]
    public bool IsPublished { get; init; }
}

public sealed record ServerApprovalFileResponse(
    [property: JsonPropertyName("hash_sha256")] string? HashSha256);
