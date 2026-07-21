using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.WorkSequences;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class WorkSequenceServerAuthorityTests
{
    [Fact]
    public void OfflineAndUnrefreshedSnapshotsBlockMutationsWithKoreanGuidance()
    {
        Assert.False(WorkSequenceServerPolicy.CanMutate(null, false));
        Assert.Contains("읽기 캐시/초안", WorkSequenceServerPolicy.OfflineReadOnlyMessage);
        Assert.Contains("변경", WorkSequenceServerPolicy.OfflineReadOnlyMessage);
    }

    [Fact]
    public async Task ReorderSendsRevisionAndStableMutationKey()
    {
        var handler = new RecordingHandler(HttpStatusCode.OK, BoardJson(8));
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);
        var request = new ServerWorkSequenceReorderRequest
        {
            ItemIds = ["item-b", "item-a"],
            ActorId = "user-admin",
            ChangeReason = "우선순위 변경",
            IdempotencyKey = "wpf:order:stable-key",
            BaseBoardRevision = 7
        };

        var result = await client.ReorderWorkSequenceItemsAsync("board-a", request);

        Assert.Equal(8, result.BoardRevision);
        Assert.Contains("\"baseBoardRevision\":7", handler.RequestBody, StringComparison.Ordinal);
        Assert.Contains("\"idempotencyKey\":\"wpf:order:stable-key\"", handler.RequestBody, StringComparison.Ordinal);
    }

    [Fact]
    public async Task StaleRevisionIsParsedAndMappedToRefreshRetryGuidance()
    {
        const string conflict =
            "{\"detail\":{\"code\":\"WORK_SEQUENCE_STALE_REVISION\",\"message\":\"stale\",\"expectedRevision\":7,\"currentRevision\":8}}";
        var handler = new RecordingHandler(HttpStatusCode.Conflict, conflict);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        var exception = await Assert.ThrowsAsync<FlowNoteServerConflictException>(() =>
            client.UpdateWorkSequenceItemStatusAsync(
                "board-a",
                "item-a",
                new ServerWorkSequenceStatusUpdateRequest
                {
                    Status = "IN_PROGRESS",
                    ActorId = "user-admin",
                    IdempotencyKey = "wpf:status:key",
                    BaseBoardRevision = 7
                }));

        Assert.Equal("WORK_SEQUENCE_STALE_REVISION", exception.ConflictCode);
        Assert.Equal(7, exception.ExpectedRevision);
        Assert.Equal(8, exception.CurrentRevision);
        var message = WorkSequenceServerPolicy.ConflictMessage(exception);
        Assert.Contains("새로고침", message);
        Assert.Contains("다시 시도", message);
    }

    [Fact]
    public async Task LostResponseRetriesOnceWithTheSameMutationRequest()
    {
        var attempts = 0;
        var keys = new List<string>();
        async Task<string> Send()
        {
            attempts++;
            keys.Add("wpf:status:stable-after-restart");
            await Task.Yield();
            if (attempts == 1) throw new HttpRequestException("response lost");
            return "saved";
        }

        var result = await WorkSequenceServerPolicy.RunWithResponseLossRetryAsync(Send);

        Assert.Equal("saved", result);
        Assert.Equal(2, attempts);
        Assert.Single(keys.Distinct(StringComparer.Ordinal));
    }

    [Fact]
    public async Task ServiceUnavailableIsNotTreatedAsLostResponse()
    {
        var handler = new RecordingHandler(HttpStatusCode.ServiceUnavailable, "{\"detail\":\"maintenance\"}");
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            WorkSequenceServerPolicy.RunWithResponseLossRetryAsync(() =>
                client.CreateWorkSequenceBoardAsync(new ServerWorkSequenceBoardCreateRequest
                {
                    Title = "503 board",
                    IdempotencyKey = "wpf:board:503"
                })));

        Assert.Equal(1, handler.RequestCount);
    }

    private static string BoardJson(int revision) => $$"""
        {
          "board_id":"board-a",
          "title":"작업판",
          "description":null,
          "line_code":"line-a",
          "board_date":"2026-07-21",
          "status":"ACTIVE",
          "board_revision":{{revision}},
          "created_by":"user-admin",
          "created_at":"2026-07-21T00:00:00Z",
          "updated_at":"2026-07-21T00:00:00Z",
          "items":[]
        }
        """;

    private sealed class RecordingHandler(HttpStatusCode statusCode, string responseBody) : HttpMessageHandler
    {
        public string RequestBody { get; private set; } = string.Empty;
        public int RequestCount { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestCount++;
            RequestBody = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody, Encoding.UTF8, "application/json")
            };
        }
    }
}
