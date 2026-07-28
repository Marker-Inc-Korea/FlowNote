using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerAIFieldReadinessReviewClientTests
{
    [Fact]
    public async Task FixedPlanRequestCarriesDatasetAndRunAndReadsTraceContract()
    {
        var handler = new RecordingHandler(HttpStatusCode.OK, """
            {
              "datasetVersionId":"dataset-a",
              "evaluationRunId":"run-a",
              "datasetSnapshotHash":"snapshot-a",
              "samplingPlanReference":"field-review-plan://24-cell-stratified-v1/snapshot-a",
              "sampleHash":"sample-a",
              "cases":[{
                "caseKey":"case-a","category":"SAFETY","scenarioType":"NORMAL",
                "question":"안전 근거","expectedOutcome":"SUFFICIENT",
                "expectedEvidence":[{"source_type":"FIELD_COMMENT","source_id":"comment-a","trace_id":"comment-a"}],
                "actualEvidence":[],"expectedExcluded":[],"rankingHash":"rank-a","passed":true
              }]
            }
            """);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        var result = await client.GetAIFieldReadinessSamplePlanAsync("dataset-a", "run-a");

        Assert.Equal(HttpMethod.Get, handler.Method);
        Assert.Equal(
            "/api/v1/ai-search/field-readiness/sample-plan?datasetVersionId=dataset-a&evaluationRunId=run-a",
            handler.RequestUri?.PathAndQuery);
        Assert.Equal("sample-a", result.SampleHash);
        Assert.Equal("comment-a", result.Cases[0].ExpectedEvidence[0]["source_id"].ToString());
    }

    [Fact]
    public async Task ConsensusRequestKeepsPairAndOnlySubmittedFindings()
    {
        var handler = new RecordingHandler(HttpStatusCode.Created, """
            {
              "review":{"reviewId":"review-c","reviewRole":"CONSENSUS","reviewerId":"user-c",
                "sampleHash":"sample-a","findings":[],"resolvesReviewIds":["review-a","review-b"]},
              "summary":{"status":"COMPLETED","independent_reviewer_count":2,
                "independent_review_ids":["review-a","review-b"],
                "independent_reviewer_ids":["user-a","user-b"],"sample_hash":"sample-a",
                "sample_case_count":24,"disagreement_case_keys":["case-a"],
                "consensus_review_id":"review-c","consensus_reviewer_id":"user-c","complete":true}
            }
            """);
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerDocumentClient(http);

        var result = await client.CreateAIFieldReadinessSampleReviewAsync(
            new ServerAIFieldReadinessReviewCreateRequest
            {
                DatasetVersionId = "dataset-a",
                EvaluationRunId = "run-a",
                SamplingPlanReference = "field-review-plan://24-cell-stratified-v1/snapshot-a",
                ReviewRole = "CONSENSUS",
                ResolvesReviewIds = ["review-a", "review-b"],
                Findings =
                [
                    new ServerAIFieldReadinessFinding
                    {
                        CaseKey = "case-a",
                        CitationTrace = "PASS",
                        CitationMeaning = "PASS",
                        ConflictDisclosure = "NOT_APPLICABLE",
                        PermissionBoundary = "PASS",
                        Note = "고정 근거를 다시 확인함",
                    }
                ],
            });

        Assert.Equal(HttpMethod.Post, handler.Method);
        Assert.Contains("\"reviewRole\":\"CONSENSUS\"", handler.RequestBody, StringComparison.Ordinal);
        Assert.Contains("\"resolvesReviewIds\":[\"review-a\",\"review-b\"]", handler.RequestBody, StringComparison.Ordinal);
        Assert.Contains("\"caseKey\":\"case-a\"", handler.RequestBody, StringComparison.Ordinal);
        Assert.True(result.Summary.Complete);
        Assert.Equal("user-c", result.Summary.ConsensusReviewerId);
    }

    private sealed class RecordingHandler(
        HttpStatusCode statusCode,
        string responseBody) : HttpMessageHandler
    {
        public HttpMethod? Method { get; private set; }
        public Uri? RequestUri { get; private set; }
        public string RequestBody { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Method = request.Method;
            RequestUri = request.RequestUri;
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
