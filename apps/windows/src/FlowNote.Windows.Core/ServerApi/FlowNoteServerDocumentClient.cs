using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using FlowNote.Windows.Core.FieldComments;
using FlowNote.Windows.Core.Sync;

namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerDocumentClient
{
    public const string DefaultWpfLocalUploadChangeReason = "WPF local upload sync";

    private readonly HttpClient httpClient;

    public FlowNoteServerDocumentClient(HttpClient httpClient)
    {
        this.httpClient = httpClient;
    }

    public Uri BaseAddress => httpClient.BaseAddress
        ?? throw new InvalidOperationException("서버 기본 URL이 설정되지 않았습니다.");

    public async Task<ServerSyncManifest> GetSyncManifestAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/sync/manifest", cancellationToken);
        return await ReadJsonResponse<ServerSyncManifest>(response, cancellationToken);
    }

    public async Task<ServerReconciliationRun> CreateReconciliationRunAsync(
        ReconciliationRunCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/sync/reconciliation-runs", request, cancellationToken);
        return await ReadJsonResponse<ServerReconciliationRun>(response, cancellationToken);
    }

    public async Task<ServerReconciliationRun> ApplyReconciliationRunAsync(
        string runId,
        ReconciliationApplyRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/sync/reconciliation-runs/{Uri.EscapeDataString(runId)}/apply",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerReconciliationRun>(response, cancellationToken);
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

    public async Task<ServerDocumentResponse> GetDocumentAsync(
        string documentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/documents/{Uri.EscapeDataString(documentId)}",
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentResponse>(response, cancellationToken);
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
        string? idempotencyKey = null,
        int? baseRevision = null,
        string? baseVersionId = null,
        string? fileHashSha256 = null,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        AddString(form, "changeReason", changeReason);
        AddString(form, "versionLabel", versionLabel);
        AddString(form, "createdBy", createdBy);
        AddString(form, "idempotencyKey", idempotencyKey);
        AddString(form, "baseRevision", baseRevision?.ToString());
        AddString(form, "baseVersionId", baseVersionId);
        AddString(form, "fileHashSha256", fileHashSha256);

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
        int? baseRevision = null,
        string? expectedPublishedVersionId = null,
        string? mutationKey = null,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/documents/{documentId}/versions/{versionId}/publish",
            new ServerDocumentVersionPublishRequest
            {
                ChangeReason = changeReason,
                BaseRevision = baseRevision,
                ExpectedPublishedVersionId = expectedPublishedVersionId,
                MutationKey = mutationKey
            },
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentResponse> UpdateDocumentStatusAsync(
        string documentId,
        string status,
        string? changeReason = null,
        int? baseRevision = null,
        string? mutationKey = null,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/documents/{documentId}/status",
            new ServerDocumentStatusUpdateRequest
            {
                Status = status,
                ChangeReason = changeReason,
                BaseRevision = baseRevision,
                MutationKey = mutationKey
            },
            cancellationToken);
        return await ReadJsonResponse<ServerDocumentResponse>(response, cancellationToken);
    }

    public async Task<ServerDocumentResponse> MergeDocumentTagsAsync(
        string documentId,
        int baseRevision,
        IReadOnlyList<string> addedTags,
        IReadOnlyList<string> removedTags,
        string intentHash,
        string mutationKey,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PutAsJsonAsync(
            $"api/v1/documents/{Uri.EscapeDataString(documentId)}/tags",
            new ServerDocumentTagMutationRequest
            {
                BaseRevision = baseRevision,
                AddedTags = addedTags,
                RemovedTags = removedTags,
                IntentHash = intentHash,
                MutationKey = mutationKey
            },
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

    public async Task<ServerControlledCopyDownloadResult> DownloadControlledCopyAsync(
        string documentId,
        string versionId,
        string destinationPath,
        CancellationToken cancellationToken = default)
    {
        using var grantResponse = await httpClient.PostAsync(
            $"api/v1/documents/{Uri.EscapeDataString(documentId)}/versions/{Uri.EscapeDataString(versionId)}/controlled-copy",
            null,
            cancellationToken);
        var grant = await ReadJsonResponse<ServerControlledCopyGrantResponse>(grantResponse, cancellationToken);
        if (string.IsNullOrWhiteSpace(grant.DownloadUrl) ||
            !string.Equals(grant.DocumentId, documentId, StringComparison.Ordinal) ||
            !string.Equals(grant.DocumentVersionId, versionId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("서버 controlled copy 승인 응답의 문서 또는 버전이 요청과 일치하지 않습니다.");
        }

        using var response = await httpClient.GetAsync(
            grant.DownloadUrl.TrimStart('/'),
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            await ReadJsonResponse<object>(response, cancellationToken);
        }

        await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
        var partialPath = $"{destinationPath}.{grant.GrantId}.flownote-partial";
        await using var destination = new FileStream(
            partialPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            1024 * 1024,
            useAsync: true);
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var buffer = new byte[1024 * 1024];
        long size = 0;
        int read;
        while ((read = await source.ReadAsync(buffer, cancellationToken)) > 0)
        {
            await destination.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
            digest.AppendData(buffer, 0, read);
            size += read;
        }
        await destination.FlushAsync(cancellationToken);
        var actualHash = Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant();
        var responseHash = response.Headers.TryGetValues("X-Content-SHA256", out var hashValues)
            ? hashValues.SingleOrDefault()
            : null;
        if (size != grant.SizeBytes ||
            !string.Equals(actualHash, grant.HashSha256, StringComparison.OrdinalIgnoreCase) ||
            (!string.IsNullOrWhiteSpace(responseHash) &&
             !string.Equals(actualHash, responseHash, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException("다운로드 파일의 크기 또는 SHA-256 해시가 서버 승인 버전과 일치하지 않습니다.");
        }

        destination.Close();
        File.Move(partialPath, destinationPath, overwrite: true);

        return new ServerControlledCopyDownloadResult(
            grant.GrantId,
            grant.Filename,
            size,
            actualHash);
    }

    public async Task<ServerFieldCommentResponse> RegisterFieldCommentAsync(
        FieldCommentRecord fieldComment,
        string? documentId = null,
        string? documentVersionId = null,
        string? idempotencyKey = null,
        CancellationToken cancellationToken = default,
        string? authorId = null)
    {
        var request = ServerFieldCommentCreateRequest.FromLocal(
            fieldComment,
            documentId,
            documentVersionId,
            idempotencyKey,
            authorId);
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
        string? idempotencyKey = null,
        string? fileSha256 = null,
        CancellationToken cancellationToken = default)
    {
        using var form = new MultipartFormDataContent();
        AddString(form, "attachmentType", attachmentType);
        AddString(form, "caption", caption);
        AddString(form, "capturedAt", capturedAt?.ToString("O"));
        AddString(form, "createdBy", createdBy);
        AddString(form, "idempotencyKey", idempotencyKey);
        AddString(form, "parentCommentId", commentId);
        AddString(form, "fileSha256", fileSha256);

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

    public async Task<ServerFieldCommentResponse> UpdateFieldCommentReviewAsync(
        string commentId,
        ServerFieldCommentReviewRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PatchAsJsonAsync(
            $"api/v1/field-comments/{commentId}",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentBulkReviewResponse> PreviewFieldCommentBulkReviewAsync(
        ServerFieldCommentBulkReviewRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/field-comments/bulk-review/preview",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentBulkReviewResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentBulkReviewResponse> ExecuteFieldCommentBulkReviewAsync(
        ServerFieldCommentBulkReviewRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/field-comments/bulk-review/execute",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentBulkReviewResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerFieldCommentQualityItemResponse>> ListFieldCommentQualityIssuesAsync(
        int agingDays = 7,
        CancellationToken cancellationToken = default)
    {
        var days = Math.Clamp(agingDays, 1, 3650);
        using var response = await httpClient.GetAsync(
            $"api/v1/field-comments/quality-workbench?agingDays={days}",
            cancellationToken);
        return await ReadJsonResponse<List<ServerFieldCommentQualityItemResponse>>(
            response,
            cancellationToken);
    }

    public async Task<ServerFieldCommentReviewDashboardResponse> GetFieldCommentReviewDashboardAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            "api/v1/field-comments/review-dashboard",
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentReviewDashboardResponse>(response, cancellationToken);
    }

    public async Task<ServerFieldCommentResponse> GetFieldCommentAsync(
        string commentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync($"api/v1/field-comments/{commentId}", cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerFieldCommentResponse>> ListFieldCommentsAsync(
        ServerFieldCommentListFilter filter,
        CancellationToken cancellationToken = default)
    {
        var query = new List<string>();
        AddQuery(query, "assignedRole", filter.AssignedRole);
        AddQuery(query, "signalLevel", filter.SignalLevel);
        AddQuery(query, "channel", filter.Channel);
        AddQuery(query, "documentVersionId", filter.DocumentVersionId);
        AddQuery(query, "reviewDueFrom", filter.ReviewDueFrom?.ToUniversalTime().ToString("O"));
        AddQuery(query, "reviewDueTo", filter.ReviewDueTo?.ToUniversalTime().ToString("O"));
        query.Add($"limit={Math.Clamp(filter.Limit, 1, 500)}");
        using var response = await httpClient.GetAsync(
            $"api/v1/field-comments?{string.Join("&", query)}",
            cancellationToken);
        return await ReadJsonResponse<List<ServerFieldCommentResponse>>(response, cancellationToken);
    }

    private static void AddQuery(List<string> query, string name, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            query.Add($"{name}={Uri.EscapeDataString(value.Trim())}");
        }
    }

    public async Task<ServerFieldCommentTraceResponse> GetFieldCommentTraceabilityAsync(
        string commentId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/field-comments/{commentId}/traceability",
            cancellationToken);
        return await ReadJsonResponse<ServerFieldCommentTraceResponse>(response, cancellationToken);
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

    public async Task<ServerReportResponse> CreateReportDraftAsync(
        ServerReportDraftCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/reports/drafts", request, cancellationToken);
        return await ReadJsonResponse<ServerReportResponse>(response, cancellationToken);
    }

    public async Task<ServerReportResponse> SaveReportAsync(
        ServerReportSaveRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/reports", request, cancellationToken);
        return await ReadJsonResponse<ServerReportResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerReportResponse>> ListReportsAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/reports", cancellationToken);
        var reports = await ReadJsonResponse<List<ServerReportResponse>>(response, cancellationToken);
        return reports;
    }

    public async Task<ServerReportResponse> GetReportAsync(
        string reportId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync($"api/v1/reports/{reportId}", cancellationToken);
        return await ReadJsonResponse<ServerReportResponse>(response, cancellationToken);
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

    public async Task<IReadOnlyList<ServerWorkSequenceBoardListItem>> ListWorkSequenceBoardsAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/work-sequence-boards", cancellationToken);
        return await ReadJsonResponse<List<ServerWorkSequenceBoardListItem>>(response, cancellationToken);
    }

    public async Task<ServerWorkSequenceBoardResponse> GetWorkSequenceBoardAsync(
        string boardId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/work-sequence-boards/{Uri.EscapeDataString(boardId)}",
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

    public async Task<ServerAISearchRebuildResponse> RebuildAISearchCandidatesAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsync("api/v1/ai-search/candidates/rebuild", null, cancellationToken);
        return await ReadJsonResponse<ServerAISearchRebuildResponse>(response, cancellationToken);
    }

    public async Task<ServerAISearchQualityResponse> GetAISearchQualityAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/ai-search/quality", cancellationToken);
        return await ReadJsonResponse<ServerAISearchQualityResponse>(response, cancellationToken);
    }

    public async Task<ServerAISearchReadinessResponse> GetAISearchReadinessAsync(
        string? lineScope = null,
        CancellationToken cancellationToken = default)
    {
        var path = "api/v1/ai-search/readiness";
        if (!string.IsNullOrWhiteSpace(lineScope))
        {
            path += $"?lineScope={Uri.EscapeDataString(lineScope.Trim())}";
        }

        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<ServerAISearchReadinessResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerAISearchCandidateResponse>> ListAISearchCandidatesAsync(
        string? sourceType = null,
        string? sourceId = null,
        int limit = 100,
        CancellationToken cancellationToken = default)
    {
        var query = new List<string> { $"limit={Math.Clamp(limit, 1, 500)}" };
        if (!string.IsNullOrWhiteSpace(sourceType))
        {
            query.Add($"sourceType={Uri.EscapeDataString(sourceType.Trim())}");
        }

        if (!string.IsNullOrWhiteSpace(sourceId))
        {
            query.Add($"sourceId={Uri.EscapeDataString(sourceId.Trim())}");
        }

        using var response = await httpClient.GetAsync(
            $"api/v1/ai-search/candidates?{string.Join("&", query)}",
            cancellationToken);
        var candidates = await ReadJsonResponse<List<ServerAISearchCandidateResponse>>(response, cancellationToken);
        return candidates;
    }

    public async Task<ServerAISearchEvaluationResponse> RunAISearchEvaluationAsync(
        ServerAISearchEvaluationRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/ai-search/evaluations",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerAISearchEvaluationResponse>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerAIGroundTruthCase>> ListAIGroundTruthCasesAsync(
        bool includePending = false,
        CancellationToken cancellationToken = default)
    {
        var path = $"api/v1/ai-search/ground-truth-cases?includePending={includePending.ToString().ToLowerInvariant()}";
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<List<ServerAIGroundTruthCase>>(response, cancellationToken);
    }

    public async Task<ServerAIGroundTruthCase> CreateAIGroundTruthCaseAsync(
        ServerAIGroundTruthCaseCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/ai-search/ground-truth-cases", request, cancellationToken);
        return await ReadJsonResponse<ServerAIGroundTruthCase>(response, cancellationToken);
    }

    public async Task<ServerAIGroundTruthCase> SecondApproveAIGroundTruthCaseAsync(
        string groundTruthCaseId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsync(
            $"api/v1/ai-search/ground-truth-cases/{Uri.EscapeDataString(groundTruthCaseId)}/second-approval",
            null, cancellationToken);
        return await ReadJsonResponse<ServerAIGroundTruthCase>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerAIGroundTruthDatasetSummary>> ListAIGroundTruthDatasetsAsync(
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync("api/v1/ai-search/ground-truth-datasets", cancellationToken);
        return await ReadJsonResponse<List<ServerAIGroundTruthDatasetSummary>>(response, cancellationToken);
    }

    public async Task<ServerAIGroundTruthDataset> GetAIGroundTruthDatasetAsync(
        string datasetVersionId,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.GetAsync(
            $"api/v1/ai-search/ground-truth-datasets/{Uri.EscapeDataString(datasetVersionId)}",
            cancellationToken);
        return await ReadJsonResponse<ServerAIGroundTruthDataset>(response, cancellationToken);
    }

    public async Task<ServerAIGroundTruthDataset> CreateAIGroundTruthDatasetAsync(
        ServerAIGroundTruthDatasetCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/ai-search/ground-truth-datasets", request, cancellationToken);
        return await ReadJsonResponse<ServerAIGroundTruthDataset>(response, cancellationToken);
    }

    public async Task<ServerAIGroundTruthDataset> TransitionAIGroundTruthDatasetAsync(
        string datasetVersionId,
        string action,
        string reason,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            $"api/v1/ai-search/ground-truth-datasets/{Uri.EscapeDataString(datasetVersionId)}/transition",
            new ServerAIGroundTruthDatasetTransitionRequest(action, reason), cancellationToken);
        return await ReadJsonResponse<ServerAIGroundTruthDataset>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<ServerAISearchEvaluationResponse>> ListAISearchEvaluationsAsync(
        string? datasetVersionId = null,
        CancellationToken cancellationToken = default)
    {
        var path = "api/v1/ai-search/evaluations";
        if (!string.IsNullOrWhiteSpace(datasetVersionId))
            path += $"?datasetVersionId={Uri.EscapeDataString(datasetVersionId)}";
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<List<ServerAISearchEvaluationResponse>>(response, cancellationToken);
    }

    public async Task<ServerAISearchEvaluationResponse> GetAISearchEvaluationAsync(
        string runId,
        string? compareToRunId = null,
        CancellationToken cancellationToken = default)
    {
        var path = $"api/v1/ai-search/evaluations/{Uri.EscapeDataString(runId)}";
        if (!string.IsNullOrWhiteSpace(compareToRunId))
            path += $"?compareToRunId={Uri.EscapeDataString(compareToRunId)}";
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<ServerAISearchEvaluationResponse>(response, cancellationToken);
    }

    public async Task<ServerAIFieldReadinessSamplePlan> GetAIFieldReadinessSamplePlanAsync(
        string datasetVersionId,
        string evaluationRunId,
        CancellationToken cancellationToken = default)
    {
        var path = "api/v1/ai-search/field-readiness/sample-plan"
            + $"?datasetVersionId={Uri.EscapeDataString(datasetVersionId)}"
            + $"&evaluationRunId={Uri.EscapeDataString(evaluationRunId)}";
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<ServerAIFieldReadinessSamplePlan>(response, cancellationToken);
    }

    public async Task<ServerAIFieldReadinessReviewListResponse> ListAIFieldReadinessSampleReviewsAsync(
        string datasetVersionId,
        string evaluationRunId,
        CancellationToken cancellationToken = default)
    {
        var path = "api/v1/ai-search/field-readiness/sample-reviews"
            + $"?datasetVersionId={Uri.EscapeDataString(datasetVersionId)}"
            + $"&evaluationRunId={Uri.EscapeDataString(evaluationRunId)}";
        using var response = await httpClient.GetAsync(path, cancellationToken);
        return await ReadJsonResponse<ServerAIFieldReadinessReviewListResponse>(response, cancellationToken);
    }

    public async Task<ServerAIFieldReadinessReviewCreateResponse> CreateAIFieldReadinessSampleReviewAsync(
        ServerAIFieldReadinessReviewCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync(
            "api/v1/ai-search/field-readiness/sample-reviews",
            request,
            cancellationToken);
        return await ReadJsonResponse<ServerAIFieldReadinessReviewCreateResponse>(response, cancellationToken);
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
            if (response.StatusCode is HttpStatusCode.Unauthorized
                or HttpStatusCode.Forbidden
                or HttpStatusCode.NotFound)
            {
                throw ServerAccessDenialPolicy.CreateException(response.StatusCode, errorBody);
            }

            if (response.StatusCode == HttpStatusCode.Conflict)
            {
                throw ParseConflict(errorBody);
            }

            throw new InvalidOperationException(
                "서버 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("FlowNote API returned an empty response body.");
    }

    private static FlowNoteServerConflictException ParseConflict(string errorBody)
    {
        try
        {
            using var json = JsonDocument.Parse(errorBody);
            if (!json.RootElement.TryGetProperty("detail", out var detail))
            {
                return UnstructuredConflict(errorBody);
            }

            if (detail.ValueKind == JsonValueKind.String)
            {
                return new FlowNoteServerConflictException(
                    "SERVER_CONFLICT",
                    detail.GetString() ?? "서버 요청이 충돌했습니다.",
                    null,
                    null,
                    null,
                    null,
                    null,
                    errorBody);
            }

            string? ReadString(string name) =>
                detail.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
                    ? value.GetString()
                    : null;
            int? ReadInt(string name) =>
                detail.TryGetProperty(name, out var value) && value.TryGetInt32(out var number)
                    ? number
                    : null;
            return new FlowNoteServerConflictException(
                ReadString("code") ?? "SERVER_CONFLICT",
                ReadString("message") ?? "서버 문서 변경과 로컬 요청이 충돌했습니다.",
                ReadInt("expectedRevision"),
                ReadInt("currentRevision"),
                ReadString("currentStatus"),
                ReadString("currentLatestVersionId"),
                ReadString("currentPublishedVersionId"),
                errorBody);
        }
        catch (JsonException)
        {
            return UnstructuredConflict(errorBody);
        }
    }

    private static FlowNoteServerConflictException UnstructuredConflict(string errorBody) =>
        new(
            "SERVER_CONFLICT",
            "서버가 충돌을 반환했지만 상세 응답을 해석하지 못했습니다.",
            null,
            null,
            null,
            null,
            null,
            errorBody);
}
