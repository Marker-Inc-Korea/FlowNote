namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerConflictException(
    string conflictCode,
    string message,
    int? expectedRevision,
    int? currentRevision,
    string? currentStatus,
    string? currentLatestVersionId,
    string? currentPublishedVersionId,
    string responseBody) : InvalidOperationException(message)
{
    public string ConflictCode { get; } = conflictCode;
    public int? ExpectedRevision { get; } = expectedRevision;
    public int? CurrentRevision { get; } = currentRevision;
    public string? CurrentStatus { get; } = currentStatus;
    public string? CurrentLatestVersionId { get; } = currentLatestVersionId;
    public string? CurrentPublishedVersionId { get; } = currentPublishedVersionId;
    public string ResponseBody { get; } = responseBody;
}
