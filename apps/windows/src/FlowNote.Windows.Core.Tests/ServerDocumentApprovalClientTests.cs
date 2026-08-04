using System.Net;
using System.Text;
using System.Text.Json;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerDocumentApprovalClientTests
{
    [Fact]
    public async Task PublishPinsApprovalVersionRevisionAndMutationKey()
    {
        var handler = new CaptureApprovalHandler(HttpStatusCode.OK, DocumentResponseJson);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerApprovalClient(http);
        var approval = new ServerDocumentApprovalResponse(
            "approval-1", "document-1", "version-3", 7, new string('a', 64),
            "APPROVED", "author-1", "reviewer-1", null, "검토 요청", null,
            "승인 완료", "reviewer-1", null, DateTimeOffset.UtcNow, []);

        await client.PublishAsync(approval, "승인 공개", "publish-key-1");

        Assert.Equal(
            "/api/v1/documents/document-1/versions/version-3/publish",
            handler.RequestUri?.AbsolutePath);
        using var json = JsonDocument.Parse(handler.RequestBody!);
        Assert.Equal("approval-1", json.RootElement.GetProperty("approvalId").GetString());
        Assert.Equal(7, json.RootElement.GetProperty("baseRevision").GetInt32());
        Assert.Equal("publish-key-1", json.RootElement.GetProperty("mutationKey").GetString());
    }

    [Fact]
    public async Task StaleApprovalMessageIsKeptForUserRecoveryGuidance()
    {
        var handler = new CaptureApprovalHandler(
            HttpStatusCode.Conflict,
            "{\"detail\":{\"code\":\"APPROVAL_STALE\",\"message\":\"승인 대상이 변경되어 공개할 수 없습니다. 새 검토 요청이 필요합니다.\"}}");
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };

        var error = await Assert.ThrowsAsync<FlowNoteServerApprovalException>(() =>
            new FlowNoteServerApprovalClient(http).CancelAsync(
                "approval-1", "승인 취소 확인", "cancel-key-1"));

        Assert.Equal(409, error.StatusCode);
        Assert.Contains("새 검토 요청", error.Message);
    }

    private sealed class CaptureApprovalHandler(HttpStatusCode statusCode, string responseBody)
        : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }
        public string? RequestBody { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            RequestBody = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json")
            };
        }
    }

    private const string DocumentResponseJson = """
        {
          "document_id": "document-1",
          "title": "현장 표준서",
          "revision": 8,
          "latest_version_id": "version-3",
          "latest_version": {
            "version_id": "version-3",
            "file": { "hash_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
          }
        }
        """;
}
