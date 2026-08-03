using System.Net;
using System.Text;
using System.Text.Json;
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

    [Fact]
    public async Task DraftMovesToReviewedWithRevisionAndStableIntent()
    {
        var services = new FlowNoteLocalServices(DatabasePath);
        var handler = new ReportReviewHandler();
        var client = new FlowNoteServerDocumentClient(new HttpClient(handler)
        {
            BaseAddress = new Uri("https://flownote.example/")
        });
        var draft = new ServerReportResponse
        {
            ReportId = "report-review-test",
            ReportType = "field_review",
            Title = "검토 전 보고서",
            Status = "DRAFT",
            ReportRevision = 3,
            ContentHashSha256 = new string('a', 64),
            SourceSetHashSha256 = new string('b', 64)
        };

        var reviewed = await services.Reports.MoveServerDraftToReviewAsync(
            client,
            draft,
            "검토 보고서",
            "검토 요약",
            "검토 본문");

        Assert.Equal("REVIEWED", reviewed.Status);
        Assert.Equal(4, reviewed.ReportRevision);
        using var request = JsonDocument.Parse(handler.LastRequestBody!);
        Assert.Equal("REVIEWED", request.RootElement.GetProperty("reportStatus").GetString());
        Assert.Equal(3, request.RootElement.GetProperty("baseReportRevision").GetInt32());
        Assert.Equal("검토 본문", request.RootElement.GetProperty("analysisContent").GetString());
        Assert.StartsWith("wpf:report-review:report-review-test:r3:",
            request.RootElement.GetProperty("mutationKey").GetString());
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

    private sealed class ReportReviewHandler : HttpMessageHandler
    {
        public string? LastRequestBody { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Assert.Equal("/api/v1/reports", request.RequestUri?.AbsolutePath);
            LastRequestBody = await request.Content!.ReadAsStringAsync(cancellationToken);
            const string json = """
                {
                  "report_id":"report-review-test",
                  "report_type":"field_review",
                  "title":"검토 보고서",
                  "summary":"검토 요약",
                  "analysis_content":"검토 본문",
                  "status":"REVIEWED",
                  "ai_draft_used":false,
                  "created_at":"2026-08-03T00:00:00Z",
                  "updated_at":"2026-08-03T00:00:01Z",
                  "sources":[],
                  "report_revision":4,
                  "content_hash_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "source_set_hash_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                }
                """;
            return new HttpResponseMessage(HttpStatusCode.Created)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            };
        }
    }
}
