using System.Text.Json;
using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerFieldCommentContractTests
{
    [Fact]
    public async Task WorkbenchListEncodesRoleSignalChannelVersionAndDueFilters()
    {
        var handler = new CaptureHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };

        await new FlowNoteServerDocumentClient(http).ListFieldCommentsAsync(new ServerFieldCommentListFilter
        {
            AssignedRole = "document-admin",
            SignalLevel = "red",
            Channel = "품질 위험 A",
            DocumentVersionId = "version-3",
            ReviewDueFrom = new DateTime(2026, 8, 1, 0, 0, 0, DateTimeKind.Utc),
            ReviewDueTo = new DateTime(2026, 8, 31, 0, 0, 0, DateTimeKind.Utc)
        });

        var query = handler.RequestUri?.Query ?? string.Empty;
        Assert.Contains("assignedRole=document-admin", query);
        Assert.Contains("signalLevel=red", query);
        Assert.Contains("channel=%ED%92%88%EC%A7%88%20%EC%9C%84%ED%97%98%20A", query);
        Assert.Contains("documentVersionId=version-3", query);
        Assert.Contains("reviewDueFrom=", query);
        Assert.Contains("reviewDueTo=", query);
    }

    [Fact]
    public void DirectReviewRequestLeavesBaseRevisionUnspecified()
    {
        var request = new ServerFieldCommentReviewRequest
        {
            Status = "ANALYZED",
            AnalysisContent = "현장 기록을 분석함",
            TransitionReason = "분석 근거를 남김"
        };

        using var json = JsonDocument.Parse(JsonSerializer.Serialize(request));

        Assert.Equal(
            JsonValueKind.Null,
            json.RootElement.GetProperty("baseReviewRevision").ValueKind);
    }

    [Fact]
    public void SynchronizedReviewRequestKeepsKnownBaseRevision()
    {
        var request = new ServerFieldCommentReviewRequest
        {
            Status = "REVIEWED",
            BaseReviewRevision = 4,
            TransitionReason = "동기화 검토를 반영함"
        };

        using var json = JsonDocument.Parse(JsonSerializer.Serialize(request));

        Assert.Equal(
            4,
            json.RootElement.GetProperty("baseReviewRevision").GetInt32());
    }

    private sealed class CaptureHandler : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("[]", Encoding.UTF8, "application/json")
            });
        }
    }
}
