using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerFieldCommentReviewDashboardClientTests
{
    [Fact]
    public async Task DashboardKeepsCountsOwnerNextActionAndFilterContract()
    {
        var handler = new DashboardHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };

        var result = await new FlowNoteServerDocumentClient(http)
            .GetFieldCommentReviewDashboardAsync();

        Assert.Equal("/api/v1/field-comments/review-dashboard", handler.RequestUri?.AbsolutePath);
        Assert.Equal(7, result.UnreviewedCount);
        Assert.Equal(3, result.SafetyQualityRiskCount);
        Assert.Equal(2, result.OverdueCount);
        Assert.Equal("독립 검토자", result.Actions[0].Owner);
        Assert.Equal("HIGH_RISK", result.Actions[0].WorkbenchFilter);
        Assert.NotEmpty(result.Actions[0].NextAction);
    }

    private sealed class DashboardHandler : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""
                    {
                      "total_count":12,
                      "counts_by_status":{"NEW":7,"REVIEWED":5},
                      "unreviewed_count":7,
                      "conflict_count":2,
                      "safety_quality_risk_count":3,
                      "report_unlinked_count":4,
                      "unassigned_count":6,
                      "overdue_count":2,
                      "actions":[{
                        "code":"SAFETY_QUALITY_RISK",
                        "title":"안전·품질 위험",
                        "count":3,
                        "owner":"독립 검토자",
                        "next_action":"위험 원천을 먼저 확인하세요.",
                        "workbench_filter":"HIGH_RISK"
                      }]
                    }
                    """, Encoding.UTF8, "application/json")
            });
        }
    }
}
