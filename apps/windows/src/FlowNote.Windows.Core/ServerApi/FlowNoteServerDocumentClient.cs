using System.Net.Http.Headers;
using System.Net.Http.Json;
using FlowNote.Windows.Core.FieldNotes;

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

    public async Task<ServerFieldNoteResponse> RegisterFieldNoteAsync(
        FieldNoteRecord fieldNote,
        string? documentId = null,
        string? documentVersionId = null,
        CancellationToken cancellationToken = default)
    {
        var request = ServerFieldNoteCreateRequest.FromLocal(fieldNote, documentId, documentVersionId);
        return await RegisterFieldNoteAsync(request, cancellationToken);
    }

    public async Task<ServerFieldNoteResponse> RegisterFieldNoteAsync(
        ServerFieldNoteCreateRequest request,
        CancellationToken cancellationToken = default)
    {
        using var response = await httpClient.PostAsJsonAsync("api/v1/field-notes", request, cancellationToken);
        return await ReadJsonResponse<ServerFieldNoteResponse>(response, cancellationToken);
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
            throw new InvalidOperationException(
                $"FlowNote API request failed: {(int)response.StatusCode} {response.ReasonPhrase}. {errorBody}");
        }

        var result = await response.Content.ReadFromJsonAsync<T>(cancellationToken);
        return result ?? throw new InvalidOperationException("FlowNote API returned an empty response body.");
    }
}
