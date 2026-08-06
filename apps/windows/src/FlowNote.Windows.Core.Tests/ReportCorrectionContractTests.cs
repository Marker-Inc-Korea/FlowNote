using System.Net;
using System.Text;
using System.Text.Json;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ReportCorrectionContractTests
{
    [Fact]
    public async Task CorrectionCreationCarriesBaseRevisionReasonAndSourceSetHash()
    {
        var handler = new CorrectionHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        var response = await client.CreateReportCorrectionAsync(
            "report-base",
            new ServerReportCorrectionCreateRequest
            {
                CorrectionReason = "확정 뒤 발견한 오류 정정",
                BaseReportRevision = 7,
                MutationKey = "wpf:correction:report-base:r7",
                SourceSetHashSha256 = new string('b', 64)
            });

        Assert.Equal("report-correction", response.ReportId);
        Assert.Equal("report-family", response.ReportFamilyId);
        Assert.Equal("report-base", response.ReplacesReportId);
        Assert.True(response.RequiresReReview);
        Assert.Equal("/api/v1/reports/report-base/corrections", handler.LastPath);
        using var request = JsonDocument.Parse(handler.LastRequestBody!);
        Assert.Equal(7, request.RootElement.GetProperty("baseReportRevision").GetInt32());
        Assert.Equal("확정 뒤 발견한 오류 정정", request.RootElement.GetProperty("correctionReason").GetString());
        Assert.Equal(new string('b', 64), request.RootElement.GetProperty("sourceSetHashSha256").GetString());
    }

    [Fact]
    public async Task LineageResponseKeepsCurrentAndSupersededGeneratedDocuments()
    {
        var handler = new LineageHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };

        var lineage = await new FlowNoteServerDocumentClient(http).ListReportLineageAsync("report-correction");

        Assert.Equal(2, lineage.Count);
        Assert.Equal("SUPERSEDED", lineage[0].Status);
        Assert.Equal("document-old", lineage[0].GeneratedDocumentId);
        Assert.True(lineage[1].IsCurrentEffective);
        Assert.Equal("document-new", lineage[1].GeneratedDocumentId);
    }

    private sealed class CorrectionHandler : HttpMessageHandler
    {
        public string? LastPath { get; private set; }
        public string? LastRequestBody { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            LastPath = request.RequestUri?.AbsolutePath;
            LastRequestBody = await request.Content!.ReadAsStringAsync(cancellationToken);
            const string json = """
                {
                  "report_id":"report-correction",
                  "report_type":"field_review",
                  "title":"정정 보고서",
                  "status":"DRAFT",
                  "ai_draft_used":false,
                  "created_at":"2026-08-06T00:00:00Z",
                  "updated_at":"2026-08-06T00:00:00Z",
                  "sources":[],
                  "report_revision":1,
                  "source_set_hash_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                  "report_family_id":"report-family",
                  "replaces_report_id":"report-base",
                  "replaces_report_revision":7,
                  "correction_reason":"확정 뒤 발견한 오류 정정",
                  "current_effective_report_id":"report-base",
                  "is_current_effective":false,
                  "requires_re_review":true
                }
                """;
            return new HttpResponseMessage(HttpStatusCode.Created)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            };
        }
    }

    private sealed class LineageHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Assert.Equal("/api/v1/reports/report-correction/lineage", request.RequestUri?.AbsolutePath);
            const string json = """
                [
                  {
                    "report_id":"report-base",
                    "title":"기존 보고서",
                    "status":"SUPERSEDED",
                    "report_revision":8,
                    "generated_document_id":"document-old",
                    "is_current_effective":false
                  },
                  {
                    "report_id":"report-correction",
                    "title":"정정 보고서",
                    "status":"APPROVED",
                    "report_revision":3,
                    "replaces_report_id":"report-base",
                    "correction_reason":"수치 오류 정정",
                    "generated_document_id":"document-new",
                    "is_current_effective":true
                  }
                ]
                """;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });
        }
    }
}
