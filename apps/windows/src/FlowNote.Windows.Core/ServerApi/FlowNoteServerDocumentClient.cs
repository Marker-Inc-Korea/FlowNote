using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net;
using FlowNote.Windows.Core.FieldComments;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerDocumentClient
{
    public const string DefaultWpfLocalUploadChangeReason = "WPF local upload sync";

    private readonly HttpClient httpClient;

    public FlowNoteServerDocumentClient(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    public async Task<ServerDocumentResponse> RegisterDocumentAsync(
        string filePath,
        string title,
        string documentType,
        string changeReason,
        string? description = null,
        string? ownerId = null,
        string? categoryId = null,
        string? versionLabel = null,
        string? createdBy = null,
        string? idempotencyKey = null,
        IEnumerable<string>? tags = null,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        AddString(form, "title", title);
        AddString(form, "documentType", documentType);
        AddString(form, "changeReason", changeReason);
        AddString(form, "description", description);
        AddString(form, "ownerId", ownerId);
        AddString(form, "categoryId", categoryId);
        AddString(form, "versionLabel", versionLabel);
        AddString(form, "createdBy", createdBy);
        AddString(form, "idempotencyKey", idempotencyKey);
        foreach (var tag in tags ?? [])
        {
            AddString(form, "tags", tag);
        }

        await using var stream = File.OpenRead(filePath);
        using var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(filePath));

        using var response = await httpClient.PostAsync("api/v1/documents", form, cancellationToken);
        return await ReadJsonResponse<ServerDocumentResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerDocumentListItem>> ListDocumentsAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/documents", cancellationToken);
        var documents = await ReadJsonResponse<List<ServerDocumentListItem>>(response, cancellationToken);
        return documents;
    }

    public async Task<IReadOnlyList<ServerDocumentVersionResponse>> ListVersionsAsync(
        string documentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync($"api/v1/documents/{documentId}/versions", cancellationToken);
        var versions = await ReadJsonResponse<List<ServerDocumentVersionResponse>>(response, cancellationToken);
        return versions;
    }

    public async Task<ServerDocumentVersionResponse> RegisterVersionAsync(
        string documentId,
        string filePath,
        string changeReason,
        string? versionLabel = null,
        string? createdBy = null,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        AddString(form, "changeReason", changeReason);
        AddString(form, "versionLabel", versionLabel);
        AddString(form, "createdBy", createdBy);

        await using var stream = File.OpenRead(filePath);
        using var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(filePath));

        using var response = await httpClient.PostAsync(
            $"api/v1/documents/{documentId}/versions",
            form,
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentVersionResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentResponse> PublishVersionAsync(
        string documentId,
        string versionId,
        string? changeReason = null,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/documents/{documentId}/versions/{versionId}/publish",
            new ServerDocumentVersionPublishRequest { ChangeReason = changeReason },
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentVersionResponse> GetPublishedVersionAsync(
        string documentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/documents/{documentId}/published",
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentVersionResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentResponse> RegisterFieldCommentAsync(
        FieldCommentRecord fieldComment,
        string? documentId = null,
        string? documentVersionId = null,
        string? idempotencyKey = null,
        CancellationToken cancellationToken = default)
    {
        var request = ServerFieldCommentCreateRequest.FromLocal(
            fieldComment,
            documentId,
            documentVersionId,
            idempotencyKey);
        return await RegisterFieldCommentAsync(request, cancellationToken);
    }

    public async Task<ServerFieldCommentResponse> RegisterFieldCommentAsync(
        ServerFieldCommentCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/field-comments", request, cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentAttachmentResponse> RegisterFieldCommentAttachmentAsync(
        string commentId,
        string filePath,
        string? attachmentType = null,
        string? caption = null,
        DateTime? capturedAt = null,
        string? createdBy = null,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        AddString(form, "attachmentType", attachmentType);
        AddString(form, "caption", caption);
        AddString(form, "capturedAt", capturedAt?.ToString("O"));
        AddString(form, "createdBy", createdBy);

        await using var stream = File.OpenRead(filePath);
        using var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(filePath));

        using var response = await httpClient.PostAsync(
            $"api/v1/field-comments/{commentId}/attachments",
            form,
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentAttachmentResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerFieldCommentAttachmentResponse>> ListFieldCommentAttachmentsAsync(
        string commentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/field-comments/{commentId}/attachments",
            cancellationToken);
        var attachments = await ReadJsonResponse<List<ServerFieldCommentAttachmentResponse>>(
            response,
            cancellationToken);
        return attachments;
    }

    public async Task<ServerDocumentAccessLogResponse> RegisterAccessLogAsync(
        string documentId,
        ServerDocumentAccessLogCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/documents/{documentId}/access-logs",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentAccessLogResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerDocumentAccessLogResponse>> ListAccessLogsAsync(
        string documentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/documents/{documentId}/access-logs",
            cancellationToken);
        var logs = await ReadJsonResponse<List<ServerDocumentAccessLogResponse>>(
            response,
            cancellationToken);
        return logs;
    }

    public async Task<ServerWorkSequenceBoardResponse> CreateWorkSequenceBoardAsync(
        ServerWorkSequenceBoardCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/work-sequence-boards",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceBoardResponse>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceBoardResponse> AddWorkSequenceItemAsync(
        string boardId,
        ServerWorkSequenceItemCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/work-sequence-boards/{boardId}/items",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceBoardResponse>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceBoardResponse> ReorderWorkSequenceItemsAsync(
        string boardId,
        ServerWorkSequenceReorderRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PutAsJsonAsync(
            $"api/v1/work-sequence-boards/{boardId}/items/order",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceBoardResponse>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceBoardResponse> UpdateWorkSequenceItemStatusAsync(
        string boardId,
        string itemId,
        ServerWorkSequenceStatusUpdateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/work-sequence-boards/{boardId}/items/{itemId}/status",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceBoardResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerWorkSequenceHistoryResponse>> ListWorkSequenceHistoryAsync(
        string boardId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/work-sequence-boards/{boardId}/history",
            cancellationToken);
        var history = await ReadJsonResponse<List<ServerWorkSequenceHistoryResponse>>(
            response,
            cancellationToken);
        return history;
    }

    public async Task<IReadOnlyList<ServerWorkSequenceNotificationCandidateResponse>> ListWorkSequenceNotificationCandidatesAsync(
        string boardId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/work-sequence-boards/{boardId}/notification-candidates",
            cancellationToken);
        var candidates = await ReadJsonResponse<List<ServerWorkSequenceNotificationCandidateResponse>>(
            response,
            cancellationToken);
        return candidates;
    }

    public async Task<ServerWorkSequenceNotificationCandidateResponse> UpdateWorkSequenceNotificationCandidateStatusAsync(
        string boardId,
        string candidateId,
        ServerWorkSequenceNotificationCandidateStatusRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/work-sequence-boards/{boardId}/notification-candidates/{candidateId}",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerWorkSequenceNotificationCandidateResponse>(response, cancellationToken);
    }

    private static void AddString(MultipartFormDataContent form, string name, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            form.Add(new StringContent(value), name);
        }
    }

    private static async Task<T> ReadJsonResponse<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(cancellationToken);
            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                throw new FlowNoteServerAuthenticationException(
                    $"Server login expired or revoked. Sign in again before retrying server sync. {errorBody}");
            }

            throw new InvalidOperationException(
                $"FlowNote API request failed: {(int)response.StatusCode} {response.ReasonPhrase}. {errorBody}");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("FlowNote API returned an empty response body.");
    }
}
