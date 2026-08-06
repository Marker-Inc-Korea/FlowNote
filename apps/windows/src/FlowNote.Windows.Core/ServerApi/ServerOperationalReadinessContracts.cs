using System.Text.Json;
using System.Text.Json.Serialization;

namespace FlowNote.Windows.Core.ServerApi;

public sealed record ServerOperationalReadinessQuery
{
    public string? AreaCode { get; init; }
    public string? Severity { get; init; }
    public string? BlockerCode { get; init; }
    public string? TargetQuery { get; init; }
    public int Limit { get; init; } = 50;
    public string? Cursor { get; init; }
}

public sealed record ServerOperationalReadinessPage
{
    [JsonPropertyName("readModelVersion")] public int ReadModelVersion { get; init; }
    [JsonPropertyName("sourceAuthority")] public string SourceAuthority { get; init; } = string.Empty;
    [JsonPropertyName("rebuildable")] public bool Rebuildable { get; init; }
    [JsonPropertyName("snapshotAnchorId")] public long SnapshotAnchorId { get; init; }
    [JsonPropertyName("asOf")] public DateTimeOffset AsOf { get; init; }
    [JsonPropertyName("cursorExpiresAt")] public DateTimeOffset CursorExpiresAt { get; init; }
    [JsonPropertyName("refreshRequired")] public bool RefreshRequired { get; init; }
    [JsonPropertyName("refreshReason")] public string? RefreshReason { get; init; }
    [JsonPropertyName("counts")] public ServerOperationalReadinessCounts Counts { get; init; } = new();
    [JsonPropertyName("filteredTotalCount")] public int FilteredTotalCount { get; init; }
    [JsonPropertyName("areas")] public IReadOnlyList<ServerOperationalReadinessArea> Areas { get; init; } = [];
    [JsonPropertyName("items")] public IReadOnlyList<ServerOperationalReadinessItem> Items { get; init; } = [];
    [JsonPropertyName("nextCursor")] public string? NextCursor { get; init; }
    [JsonPropertyName("aiFieldReadiness")] public ServerAIFieldReadinessSummary AIFieldReadiness { get; init; } = new();
}

public sealed record ServerOperationalReadinessCounts
{
    [JsonPropertyName("normal")] public int Normal { get; init; }
    [JsonPropertyName("warning")] public int Warning { get; init; }
    [JsonPropertyName("blocked")] public int Blocked { get; init; }
}

public sealed record ServerOperationalReadinessArea
{
    [JsonPropertyName("areaCode")] public string AreaCode { get; init; } = string.Empty;
    [JsonPropertyName("areaName")] public string AreaName { get; init; } = string.Empty;
    [JsonPropertyName("status")] public string Status { get; init; } = string.Empty;
    [JsonPropertyName("statusLabel")] public string StatusLabel { get; init; } = string.Empty;
    [JsonPropertyName("statusIcon")] public string StatusIcon { get; init; } = string.Empty;
    [JsonPropertyName("assessedCount")] public int AssessedCount { get; init; }
    [JsonPropertyName("normalCount")] public int NormalCount { get; init; }
    [JsonPropertyName("warningCount")] public int WarningCount { get; init; }
    [JsonPropertyName("blockedCount")] public int BlockedCount { get; init; }
    [JsonPropertyName("failure")] public ServerReadinessFailure? Failure { get; init; }
    [JsonPropertyName("requiredRoles")] public IReadOnlyList<string> RequiredRoles { get; init; } = [];

    public string StatusDisplay => $"{StatusIcon} {StatusLabel}";
    public string FailureDisplay => Failure?.Message ?? string.Empty;
}

public sealed record ServerReadinessFailure
{
    [JsonPropertyName("code")] public string Code { get; init; } = string.Empty;
    [JsonPropertyName("message")] public string Message { get; init; } = string.Empty;
    [JsonPropertyName("responsibleRole")] public string ResponsibleRole { get; init; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; init; } = string.Empty;
    [JsonPropertyName("sourcePreserved")] public bool SourcePreserved { get; init; }
}

public sealed record ServerOperationalReadinessItem
{
    [JsonPropertyName("itemId")] public string ItemId { get; init; } = string.Empty;
    [JsonPropertyName("areaCode")] public string AreaCode { get; init; } = string.Empty;
    [JsonPropertyName("areaName")] public string AreaName { get; init; } = string.Empty;
    [JsonPropertyName("severity")] public string Severity { get; init; } = string.Empty;
    [JsonPropertyName("severityLabel")] public string SeverityLabel { get; init; } = string.Empty;
    [JsonPropertyName("statusIcon")] public string StatusIcon { get; init; } = string.Empty;
    [JsonPropertyName("blockerCodes")] public IReadOnlyList<string> BlockerCodes { get; init; } = [];
    [JsonPropertyName("targetType")] public string TargetType { get; init; } = string.Empty;
    [JsonPropertyName("targetId")] public string TargetId { get; init; } = string.Empty;
    [JsonPropertyName("targetTitle")] public string TargetTitle { get; init; } = string.Empty;
    [JsonPropertyName("currentStatus")] public string CurrentStatus { get; init; } = string.Empty;
    [JsonPropertyName("sourceRevision")] public int? SourceRevision { get; init; }
    [JsonPropertyName("responsibleRole")] public string ResponsibleRole { get; init; } = string.Empty;
    [JsonPropertyName("assignee")] public string Assignee { get; init; } = string.Empty;
    [JsonPropertyName("nextAction")] public string NextAction { get; init; } = string.Empty;
    [JsonPropertyName("actionRoute")] public string ActionRoute { get; init; } = string.Empty;
    [JsonPropertyName("actionTargetId")] public string ActionTargetId { get; init; } = string.Empty;
    [JsonPropertyName("oldestAt")] public DateTimeOffset OldestAt { get; init; }
    [JsonPropertyName("latestEventId")] public string? LatestEventId { get; init; }
    [JsonPropertyName("auditPath")] public string? AuditPath { get; init; }
    [JsonPropertyName("resolvedWhen")] public string ResolvedWhen { get; init; } = string.Empty;

    public string SeverityDisplay => $"{StatusIcon} {SeverityLabel}";
    public string BlockerDisplay => string.Join(", ", BlockerCodes);
    public string OldestAtLabel => OldestAt.LocalDateTime.ToString("yyyy-MM-dd HH:mm:ss");
}

public sealed record ServerAIFieldReadinessSummary
{
    [JsonPropertyName("status")] public string Status { get; init; } = string.Empty;
    [JsonPropertyName("providerStartReady")] public bool ProviderStartReady { get; init; }
    [JsonPropertyName("acceptedDataClassification")] public string AcceptedDataClassification { get; init; } = string.Empty;
    [JsonPropertyName("groundTruthCount")] public int? GroundTruthCount { get; init; }
    [JsonPropertyName("groundTruthGap")] public int? GroundTruthGap { get; init; }
    [JsonPropertyName("latestEvaluation")] public JsonElement? LatestEvaluation { get; init; }
    [JsonPropertyName("readinessFailures")] public IReadOnlyList<string> ReadinessFailures { get; init; } = [];
    [JsonPropertyName("syntheticIncluded")] public bool SyntheticIncluded { get; init; }
    [JsonPropertyName("separationNotice")] public string SeparationNotice { get; init; } = string.Empty;
    [JsonPropertyName("failure")] public ServerReadinessFailure? Failure { get; init; }

    public string StatusLabel => Status switch
    {
        "PASS" => "✓ 준비됨",
        "FAIL" => "⛔ 미충족",
        "PENDING" => "⚠ 준비 중",
        _ => "? 집계 없음"
    };
}

public sealed record ServerOperationalReadinessDetail
{
    [JsonPropertyName("readModelVersion")] public int ReadModelVersion { get; init; }
    [JsonPropertyName("sourceAuthority")] public string SourceAuthority { get; init; } = string.Empty;
    [JsonPropertyName("asOf")] public DateTimeOffset AsOf { get; init; }
    [JsonPropertyName("item")] public ServerOperationalReadinessItem Item { get; init; } = new();
}
