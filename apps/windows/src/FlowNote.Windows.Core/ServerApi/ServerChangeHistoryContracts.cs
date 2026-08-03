using System.Text.Json;
using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerChangeHistoryQuery
{
    public DateTimeOffset? OccurredFrom { get; init; }
    public DateTimeOffset? OccurredTo { get; init; }
    public string? ActorId { get; init; }
    public string? ActorRole { get; init; }
    public string? DeviceId { get; init; }
    public string? TargetType { get; init; }
    public string? TargetId { get; init; }
    public string? TargetQuery { get; init; }
    public string? TargetVersionId { get; init; }
    public int? TargetRevision { get; init; }
    public string? Result { get; init; }
    public string? RiskLevel { get; init; }
    public string? RunId { get; init; }
    public string? CorrelationId { get; init; }
    public bool? ActionRequired { get; init; }
    public int Limit { get; init; } = 50;
    public string? Cursor { get; init; }
}

public sealed record ServerChangeHistoryPage
{
    [JsonPropertyName("readModelVersion")]
    public int ReadModelVersion { get; init; }

    [JsonPropertyName("sourceAuthority")]
    public string SourceAuthority { get; init; } = string.Empty;

    [JsonPropertyName("rebuildable")]
    public bool Rebuildable { get; init; }

    [JsonPropertyName("snapshotAnchorId")]
    public long SnapshotAnchorId { get; init; }

    [JsonPropertyName("totalCount")]
    public int TotalCount { get; init; }

    [JsonPropertyName("actionRequiredCount")]
    public int ActionRequiredCount { get; init; }

    [JsonPropertyName("totalsByResult")]
    public IReadOnlyDictionary<string, int> TotalsByResult { get; init; } =
        new Dictionary<string, int>();

    [JsonPropertyName("totalsByRisk")]
    public IReadOnlyDictionary<string, int> TotalsByRisk { get; init; } =
        new Dictionary<string, int>();

    [JsonPropertyName("items")]
    public IReadOnlyList<ServerChangeHistoryItem> Items { get; init; } = [];

    [JsonPropertyName("nextCursor")]
    public string? NextCursor { get; init; }
}

public sealed record ServerChangeHistoryItem
{
    [JsonPropertyName("eventId")] public string EventId { get; init; } = string.Empty;
    [JsonPropertyName("occurredAt")] public DateTimeOffset OccurredAt { get; init; }
    [JsonPropertyName("eventType")] public string EventType { get; init; } = string.Empty;
    [JsonPropertyName("actorId")] public string ActorId { get; init; } = string.Empty;
    [JsonPropertyName("actorDisplayName")] public string ActorDisplayName { get; init; } = string.Empty;
    [JsonPropertyName("actorRole")] public string ActorRole { get; init; } = string.Empty;
    [JsonPropertyName("deviceId")] public string? DeviceId { get; init; }
    [JsonPropertyName("targetType")] public string TargetType { get; init; } = string.Empty;
    [JsonPropertyName("targetId")] public string TargetId { get; init; } = string.Empty;
    [JsonPropertyName("targetTitle")] public string TargetTitle { get; init; } = string.Empty;
    [JsonPropertyName("targetVersionId")] public string? TargetVersionId { get; init; }
    [JsonPropertyName("targetRevision")] public int? TargetRevision { get; init; }
    [JsonPropertyName("result")] public string Result { get; init; } = string.Empty;
    [JsonPropertyName("resultCode")] public string ResultCode { get; init; } = string.Empty;
    [JsonPropertyName("httpStatus")] public int HttpStatus { get; init; }
    [JsonPropertyName("riskLevel")] public string RiskLevel { get; init; } = "LOW";
    [JsonPropertyName("actionRequired")] public bool ActionRequired { get; init; }
    [JsonPropertyName("issueKinds")] public IReadOnlyList<string> IssueKinds { get; init; } = [];
    [JsonPropertyName("impact")] public string Impact { get; init; } = string.Empty;
    [JsonPropertyName("currentStatus")] public string CurrentStatus { get; init; } = string.Empty;
    [JsonPropertyName("currentRevision")] public int? CurrentRevision { get; init; }
    [JsonPropertyName("assignee")] public string Assignee { get; init; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; init; } = string.Empty;
    [JsonPropertyName("actionRoute")] public string ActionRoute { get; init; } = "AUDIT_DETAIL";
    [JsonPropertyName("runId")] public string? RunId { get; init; }
    [JsonPropertyName("correlationId")] public string CorrelationId { get; init; } = string.Empty;
    [JsonPropertyName("linkedMutation")] public bool LinkedMutation { get; init; }
    [JsonPropertyName("permissionDeniedChangeDetected")]
    public bool PermissionDeniedChangeDetected { get; init; }
    [JsonPropertyName("missingAuditFields")]
    public IReadOnlyList<string> MissingAuditFields { get; init; } = [];
    [JsonPropertyName("rawAuditPath")] public string RawAuditPath { get; init; } = string.Empty;

    public string OccurredAtLabel => OccurredAt.LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss");
    public string RiskLabel => RiskLevel switch
    {
        "CRITICAL" => "긴급",
        "HIGH" => "높음",
        "MEDIUM" => "보통",
        _ => "낮음"
    };
    public string ResultLabel => Result switch
    {
        "SUCCESS" => "성공",
        "CONFLICT" => "충돌",
        "REJECTED" => "거부/실패",
        _ => Result
    };
    public string TargetRevisionLabel => TargetRevision is null ? "-" : $"r{TargetRevision}";
    public string ActionRequiredLabel => ActionRequired ? "조치 필요" : "확인";
}

public sealed record ServerChangeHistoryDetail
{
    [JsonPropertyName("readModelVersion")] public int ReadModelVersion { get; init; }
    [JsonPropertyName("sourceAuthority")] public string SourceAuthority { get; init; } = string.Empty;
    [JsonPropertyName("rebuildable")] public bool Rebuildable { get; init; }
    [JsonPropertyName("item")] public ServerChangeHistoryItem Item { get; init; } = new();
    [JsonPropertyName("auditEnvelope")] public ServerAuditEnvelopeDetail AuditEnvelope { get; init; } = new();
}

public sealed record ServerAuditEnvelopeDetail
{
    [JsonPropertyName("eventId")] public string EventId { get; init; } = string.Empty;
    [JsonPropertyName("schemaVersion")] public int SchemaVersion { get; init; }
    [JsonPropertyName("eventType")] public string EventType { get; init; } = string.Empty;
    [JsonPropertyName("actorId")] public string ActorId { get; init; } = string.Empty;
    [JsonPropertyName("actorRole")] public string ActorRole { get; init; } = string.Empty;
    [JsonPropertyName("sessionId")] public string SessionId { get; init; } = string.Empty;
    [JsonPropertyName("deviceId")] public string? DeviceId { get; init; }
    [JsonPropertyName("targetType")] public string TargetType { get; init; } = string.Empty;
    [JsonPropertyName("targetId")] public string TargetId { get; init; } = string.Empty;
    [JsonPropertyName("targetVersionId")] public string? TargetVersionId { get; init; }
    [JsonPropertyName("targetRevision")] public int? TargetRevision { get; init; }
    [JsonPropertyName("reason")] public string? Reason { get; init; }
    [JsonPropertyName("approvalStatus")] public string ApprovalStatus { get; init; } = string.Empty;
    [JsonPropertyName("approvedBy")] public string? ApprovedBy { get; init; }
    [JsonPropertyName("approvalReference")] public string? ApprovalReference { get; init; }
    [JsonPropertyName("beforeHashSha256")] public string? BeforeHashSha256 { get; init; }
    [JsonPropertyName("afterHashSha256")] public string? AfterHashSha256 { get; init; }
    [JsonPropertyName("result")] public string Result { get; init; } = string.Empty;
    [JsonPropertyName("resultCode")] public string ResultCode { get; init; } = string.Empty;
    [JsonPropertyName("httpStatus")] public int HttpStatus { get; init; }
    [JsonPropertyName("runId")] public string? RunId { get; init; }
    [JsonPropertyName("correlationId")] public string CorrelationId { get; init; } = string.Empty;
    [JsonPropertyName("domainAuditType")] public string? DomainAuditType { get; init; }
    [JsonPropertyName("domainAuditId")] public string? DomainAuditId { get; init; }
    [JsonPropertyName("safePayload")] public JsonElement SafePayload { get; init; }
    [JsonPropertyName("serverTime")] public DateTimeOffset ServerTime { get; init; }
}
