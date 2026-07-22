using System.Net;
using System.Text;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerAIOperationsClientTests
{
    [Fact]
    public async Task LostResponseRetriesSameOperationKeyThenReadsBackQueryHoldAndAudit()
    {
        var handler = new LostResponseThenReadBackHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerAIOperationsClient(http);
        var request = new ServerAILegalHoldCreateRequest
        {
            Reason = "분쟁 보존",
            AuthorityReference = "CASE-001",
            OperationKey = "wpf:ai:hold:stable-operation-key",
            ExpectedStateTag = new string('a', 64)
        };

        var result = await client.PlaceLegalHoldAndReadBackAsync("query-a", request);

        Assert.Equal(2, handler.PostBodies.Count);
        Assert.All(handler.PostBodies, body =>
            Assert.Contains("wpf:ai:hold:stable-operation-key", body, StringComparison.Ordinal));
        Assert.Equal("ACTIVE", result.ActiveHold?.Status);
        Assert.Single(result.Holds);
        Assert.Single(result.AuditEvents);
    }

    [Fact]
    public async Task ConflictHasKoreanRefreshGuidanceAndIsNotRetried()
    {
        var handler = new ConflictHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var client = new FlowNoteServerAIOperationsClient(http);

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ExpireQueryAndReadBackAsync("query-a", new ServerAIQueryMutationRequest
            {
                Reason = "즉시 만료",
                OperationKey = "wpf:ai:expire:stable-operation-key",
                ExpectedStateTag = new string('b', 64)
            }));

        Assert.Equal(1, handler.RequestCount);
        Assert.Contains("충돌", error.Message);
        Assert.Contains("새로고침", error.Message);
    }

    private sealed class LostResponseThenReadBackHandler : HttpMessageHandler
    {
        public List<string> PostBodies { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Post)
            {
                PostBodies.Add(await request.Content!.ReadAsStringAsync(cancellationToken));
                if (PostBodies.Count == 1) throw new HttpRequestException("응답 유실");
                return Json(HttpStatusCode.Created, "{\"holdId\":\"hold-a\",\"status\":\"ACTIVE\"}");
            }
            return Json(HttpStatusCode.OK, DetailJson);
        }

        private const string DetailJson = """
            {
              "queryId":"query-a","requestedBy":"system-admin","customerScope":"customer-a",
              "siteScope":"site-a","purpose":"EVIDENCE_SUMMARY","status":"SUCCEEDED",
              "queryPayloadExpired":false,"responseStored":true,
              "retentionUntil":"2026-08-01T00:00:00Z","responseRetentionUntil":"2026-08-01T00:00:00Z",
              "activeHold":{"holdId":"hold-a","queryId":"query-a","status":"ACTIVE",
                "reason":"분쟁 보존","authorityReference":"CASE-001","placedBy":"system-admin",
                "placedAt":"2026-07-22T00:00:00Z"},
              "holds":[{"holdId":"hold-a","queryId":"query-a","status":"ACTIVE",
                "reason":"분쟁 보존","authorityReference":"CASE-001","placedBy":"system-admin",
                "placedAt":"2026-07-22T00:00:00Z"}],
              "retentionAudits":[],
              "auditEvents":[{"eventId":"audit-a","eventType":"QUERY_LEGAL_HOLD_PLACED",
                "actorId":"system-admin","targetType":"AI_QUERY_LEGAL_HOLD","targetId":"hold-a",
                "occurredAt":"2026-07-22T00:00:00Z"}],
              "stateTag":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            }
            """;
    }

    private sealed class ConflictHandler : HttpMessageHandler
    {
        public int RequestCount { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            RequestCount++;
            return Task.FromResult(Json(HttpStatusCode.Conflict,
                "{\"detail\":{\"code\":\"AI_QUERY_STALE_STATE\",\"message\":\"stale\"}}"));
        }
    }

    private static HttpResponseMessage Json(HttpStatusCode status, string body) => new(status)
    {
        Content = new StringContent(body, Encoding.UTF8, "application/json")
    };
}
