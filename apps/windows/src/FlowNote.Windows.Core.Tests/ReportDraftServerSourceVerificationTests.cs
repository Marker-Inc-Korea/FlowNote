using System.Net;
using System.Text;
using FlowNote.Windows.Core.Reports;
using FlowNote.Windows.Core.ServerApi;
using FlowNote.Windows.Core.Storage;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ReportDraftServerSourceVerificationTests
{
    private static readonly string DatabasePath = Path.Combine(
        FlowNoteLocalDatabase.DefaultDataDirectory,
        "flownote.core-tests.sqlite");

    [Fact]
    public async Task WorkSequenceItemAndHistoryCanBeVerifiedBeforeReportSave()
    {
        var suffix = Guid.NewGuid().ToString("N");
        var itemId = $"item-{suffix}";
        var changeId = $"change-{suffix}";
        var services = new FlowNoteLocalServices(DatabasePath);
        var client = new FlowNoteServerDocumentClient(new HttpClient(
            new WorkSequenceHandler(itemId, changeId))
        {
            BaseAddress = new Uri("https://flownote.example/")
        });
        var sources = new[]
        {
            Source("WORK_SEQUENCE_ITEM", itemId, changeId),
            Source("WORK_SEQUENCE_HISTORY", changeId, changeId)
        };

        var result = await services.Reports.FreezeServerSourcesAsync(client, sources);

        Assert.True(result.Valid);
        Assert.Equal(2, result.Sources.Count);
        Assert.All(result.Verifications, verification => Assert.True(verification.Valid));
    }

    [Fact]
    public async Task WorkSequenceItemRejectsAChangedLatestVersion()
    {
        var suffix = Guid.NewGuid().ToString("N");
        var itemId = $"item-{suffix}";
        var changeId = $"change-{suffix}";
        var services = new FlowNoteLocalServices(DatabasePath);
        var client = new FlowNoteServerDocumentClient(new HttpClient(
            new WorkSequenceHandler(itemId, changeId))
        {
            BaseAddress = new Uri("https://flownote.example/")
        });

        var result = await services.Reports.FreezeServerSourcesAsync(
            client,
            [
                Source("WORK_SEQUENCE_ITEM", itemId, "older-change"),
                Source("WORK_SEQUENCE_HISTORY", changeId, changeId)
            ]);

        Assert.False(result.Valid);
        Assert.False(result.Verifications.Single(item => item.SourceType == "WORK_SEQUENCE_ITEM").Valid);
    }

    private static ReportSourceCandidateRecord Source(
        string sourceType,
        string sourceId,
        string sourceVersionId)
    {
        return new ReportSourceCandidateRecord(
            sourceType,
            sourceId,
            "작업순서 검증",
            "보고서 원천 검증",
            DateTime.UtcNow,
            sourceVersionId);
    }

    private sealed class WorkSequenceHandler(string itemId, string changeId) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var path = request.RequestUri?.AbsolutePath;
            var json = path switch
            {
                "/api/v1/work-sequence-boards" =>
                    """[{"board_id":"board-1","title":"작업순서","status":"ACTIVE","board_revision":2,"item_count":1,"updated_at":"2026-07-27T00:00:00Z"}]""",
                "/api/v1/work-sequence-boards/board-1" =>
                    $$"""{"board_id":"board-1","title":"작업순서","status":"ACTIVE","board_revision":2,"created_at":"2026-07-27T00:00:00Z","updated_at":"2026-07-27T00:00:00Z","items":[{"item_id":"{{itemId}}","board_id":"board-1","title":"혼합 공정","status":"WAITING","sort_order":1,"created_at":"2026-07-27T00:00:00Z","updated_at":"2026-07-27T00:00:00Z"}]}""",
                "/api/v1/work-sequence-boards/board-1/history" =>
                    $$"""[{"change_id":"{{changeId}}","mutation_key":"mutation-1","board_revision":2,"board_id":"board-1","item_id":"{{itemId}}","change_type":"ITEM_ADDED","created_at":"2026-07-27T00:00:01Z"}]""",
                _ => throw new InvalidOperationException($"Unexpected path: {path}")
            };
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
        }
    }
}
