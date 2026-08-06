using System.Net;
using System.Text;
using FlowNote.Windows.Core.Auth;
using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class ServerChangeHistoryClientTests
{
    [Fact]
    public async Task ListPreservesAllFiltersTotalsAndCursorContract()
    {
        var handler = new ChangeHistoryHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };
        var query = new ServerChangeHistoryQuery
        {
            OccurredFrom = DateTimeOffset.Parse("2026-08-01T00:00:00+09:00"),
            OccurredTo = DateTimeOffset.Parse("2026-08-03T23:59:59+09:00"),
            ActorId = "user-a",
            ActorRole = "manager",
            DeviceId = "device-a",
            TargetType = "document",
            TargetQuery = "작업표준서 A",
            TargetVersionId = "version-a",
            TargetRevision = 7,
            Result = "CONFLICT",
            RiskLevel = "HIGH",
            RunId = "run-a",
            CorrelationId = "corr-a",
            ActionRequired = true,
            Limit = 25,
            Cursor = "cursor-a"
        };

        var result = await new FlowNoteServerAuditClient(http).ListChangeHistoryAsync(query);

        var queryValues = ParseQuery(handler.RequestUri!);
        Assert.Equal("user-a", queryValues["actorId"]);
        Assert.Equal("manager", queryValues["actorRole"]);
        Assert.Equal("device-a", queryValues["deviceId"]);
        Assert.Equal("document", queryValues["targetType"]);
        Assert.Equal("작업표준서 A", queryValues["targetQuery"]);
        Assert.Equal("version-a", queryValues["targetVersionId"]);
        Assert.Equal("7", queryValues["targetRevision"]);
        Assert.Equal("CONFLICT", queryValues["result"]);
        Assert.Equal("HIGH", queryValues["riskLevel"]);
        Assert.Equal("run-a", queryValues["runId"]);
        Assert.Equal("corr-a", queryValues["correlationId"]);
        Assert.Equal("true", queryValues["actionRequired"]);
        Assert.Equal("25", queryValues["limit"]);
        Assert.Equal("cursor-a", queryValues["cursor"]);
        Assert.Equal(3, result.TotalCount);
        Assert.Equal(2, result.ActionRequiredCount);
        Assert.Equal("next-a", result.NextCursor);
        Assert.Equal("문서 충돌 검토", result.Items[0].NextAction);
        Assert.Equal("높음", result.Items[0].RiskLabel);
    }

    [Fact]
    public void ChangeHistoryRolePolicyMatchesGovernanceBoundary()
    {
        Assert.True(RolePermissionPolicy.CanReadChangeHistory("admin"));
        Assert.True(RolePermissionPolicy.CanReadChangeHistory("document-admin"));
        Assert.True(RolePermissionPolicy.CanReadChangeHistory("department-manager"));
        Assert.False(RolePermissionPolicy.CanReadChangeHistory("line-foreman"));
        Assert.False(RolePermissionPolicy.CanReadChangeHistory("viewer"));
    }

    [Fact]
    public async Task OperationalReadinessPreservesSnapshotFiltersAndSeparateAIFieldTrack()
    {
        var handler = new ReadinessHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://server.example/") };

        var result = await new FlowNoteServerAuditClient(http).ListOperationalReadinessAsync(
            new ServerOperationalReadinessQuery
            {
                AreaCode = "FIELD_COMMENT",
                Severity = "BLOCKED",
                BlockerCode = "FIELD_COMMENT_REVIEW_OVERDUE",
                TargetQuery = "comment-a",
                Limit = 25,
                Cursor = "cursor-r"
            });

        var queryValues = ParseQuery(handler.RequestUri!);
        Assert.Equal("FIELD_COMMENT", queryValues["areaCode"]);
        Assert.Equal("BLOCKED", queryValues["severity"]);
        Assert.Equal("FIELD_COMMENT_REVIEW_OVERDUE", queryValues["blockerCode"]);
        Assert.Equal("comment-a", queryValues["targetQuery"]);
        Assert.Equal("cursor-r", queryValues["cursor"]);
        Assert.True(result.RefreshRequired);
        Assert.Equal("⛔ 차단", result.Items[0].SeverityDisplay);
        Assert.Equal("comment-a", result.Items[0].ActionTargetId);
        Assert.Equal("FieldComment 검토", result.Areas[0].AreaName);
        Assert.False(result.AIFieldReadiness.SyntheticIncluded);
        Assert.Contains("합성", result.AIFieldReadiness.SeparationNotice);
    }

    private static Dictionary<string, string> ParseQuery(Uri uri) =>
        uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(item => item.Split('=', 2))
            .ToDictionary(
                item => Uri.UnescapeDataString(item[0]),
                item => Uri.UnescapeDataString(item[1]));

    private sealed class ChangeHistoryHandler : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(ResponseJson, Encoding.UTF8, "application/json")
            });
        }

        private const string ResponseJson = """
            {
              "readModelVersion":1,
              "sourceAuthority":"audit_event_envelopes",
              "rebuildable":true,
              "snapshotAnchorId":91,
              "totalCount":3,
              "actionRequiredCount":2,
              "totalsByResult":{"CONFLICT":2,"SUCCESS":1},
              "totalsByRisk":{"HIGH":2,"LOW":1},
              "nextCursor":"next-a",
              "items":[{
                "eventId":"event-a","occurredAt":"2026-08-03T01:00:00Z",
                "eventType":"document.status_changed","actorId":"user-a",
                "actorDisplayName":"관리자 A","actorRole":"manager","deviceId":"device-a",
                "targetType":"document","targetId":"document-a","targetTitle":"작업표준서 A",
                "targetVersionId":"version-a","targetRevision":7,
                "result":"CONFLICT","resultCode":"DOCUMENT_STALE_REVISION","httpStatus":409,
                "riskLevel":"HIGH","actionRequired":true,"issueKinds":["CONFLICT"],
                "impact":"서버 권위 상태와 충돌","currentStatus":"IN_REVIEW","currentRevision":8,
                "assignee":"manager-a","nextAction":"문서 충돌 검토",
                "actionRoute":"DOCUMENT_CONFLICT","runId":"run-a","correlationId":"corr-a",
                "linkedMutation":true,"permissionDeniedChangeDetected":false,
                "missingAuditFields":[],"rawAuditPath":"/api/v1/change-history/event-a"
              }]
            }
            """;
    }

    private sealed class ReadinessHandler : HttpMessageHandler
    {
        public Uri? RequestUri { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(ResponseJson, Encoding.UTF8, "application/json")
            });
        }

        private const string ResponseJson = """
            {
              "readModelVersion":1,
              "sourceAuthority":"audit_event_envelopes + current_authority_tables",
              "rebuildable":true,
              "snapshotAnchorId":120,
              "asOf":"2026-08-06T01:00:00Z",
              "cursorExpiresAt":"2026-08-06T01:15:00Z",
              "refreshRequired":true,
              "refreshReason":"새 event가 있습니다.",
              "counts":{"normal":0,"warning":1,"blocked":1},
              "filteredTotalCount":1,
              "nextCursor":"next-r",
              "areas":[{
                "areaCode":"FIELD_COMMENT","areaName":"FieldComment 검토",
                "status":"BLOCKED","statusLabel":"차단","statusIcon":"⛔",
                "assessedCount":3,"normalCount":1,"warningCount":1,"blockedCount":1,
                "failure":null,"requiredRoles":[]
              }],
              "items":[{
                "itemId":"ready-a","areaCode":"FIELD_COMMENT","areaName":"FieldComment 검토",
                "severity":"BLOCKED","severityLabel":"차단","statusIcon":"⛔",
                "blockerCodes":["FIELD_COMMENT_REVIEW_OVERDUE"],
                "targetType":"field_comment","targetId":"comment-a","targetTitle":"품질 의견",
                "currentStatus":"NEEDS_REVIEW","sourceRevision":3,
                "responsibleRole":"검토 책임자","assignee":"manager-a",
                "nextAction":"검토 화면에서 판정하세요.","actionRoute":"FIELD_COMMENT_REVIEW",
                "actionTargetId":"comment-a",
                "oldestAt":"2026-08-05T01:00:00Z","latestEventId":"event-a",
                "auditPath":"/api/v1/change-history/event-a",
                "resolvedWhen":"blocker가 계산되지 않을 때"
              }],
              "aiFieldReadiness":{
                "status":"PENDING","providerStartReady":false,
                "acceptedDataClassification":"ANONYMOUS_FIELD",
                "groundTruthCount":2,"groundTruthGap":98,"latestEvaluation":null,
                "readinessFailures":["GROUND_TRUTH_COVERAGE_INCOMPLETE"],
                "syntheticIncluded":false,
                "separationNotice":"실제 현장 자료와 합성 자료를 분리합니다.",
                "failure":null
              }
            }
            """;
    }
}
