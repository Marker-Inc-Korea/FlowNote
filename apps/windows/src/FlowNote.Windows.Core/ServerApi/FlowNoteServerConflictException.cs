namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerConflictException(
    string conflictCode,
    string message,
    int? expectedRevision,
    int? currentRevision,
    string? currentStatus,
    string? currentLatestVersionId,
    string? currentPublishedVersionId,
    string responseBody,
    string? schemaVersion = null,
    string? conflictKind = null,
    IReadOnlyList<string>? allowedActions = null,
    bool autoMergeAllowed = false,
    int retryNotBeforeSeconds = 0) : InvalidOperationException(message)
{
    public string ConflictCode { get; } = conflictCode;
    public int? ExpectedRevision { get; } = expectedRevision;
    public int? CurrentRevision { get; } = currentRevision;
    public string? CurrentStatus { get; } = currentStatus;
    public string? CurrentLatestVersionId { get; } = currentLatestVersionId;
    public string? CurrentPublishedVersionId { get; } = currentPublishedVersionId;
    public string ResponseBody { get; } = responseBody;
    public string? SchemaVersion { get; } = schemaVersion;
    public string? ConflictKind { get; } = conflictKind;
    public IReadOnlyList<string> AllowedActions { get; } = allowedActions ?? [];
    public bool AutoMergeAllowed { get; } = autoMergeAllowed;
    public int RetryNotBeforeSeconds { get; } = Math.Max(0, retryNotBeforeSeconds);
}
