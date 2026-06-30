namespace FlowNote.Windows.Core.FileWatching;

public sealed record FileWatchCandidateRecord(
    long Id,
    string CandidateId,
    string SourcePath,
    string FileName,
    long SizeBytes,
    DateTime LastWriteTimeUtc,
    string Status,
    string? DocumentId,
    string? DocumentTitle,
    string DetectedBy,
    DateTime DetectedAt,
    string? VersionLabel,
    string? ChangeReason,
    string? ResolvedBy,
    DateTime? ResolvedAt);
