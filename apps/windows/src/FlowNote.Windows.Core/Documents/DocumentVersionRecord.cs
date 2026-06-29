namespace FlowNote.Windows.Core.Documents;

public sealed record DocumentVersionRecord(
    long Id,
    string DocumentId,
    int VersionNo,
    string FileName,
    string? LocalPath,
    string? Comment,
    string CreatedBy,
    DateTime CreatedAt,
    string VersionStatus = "WORKING",
    bool IsLatest = false,
    bool IsPublished = false,
    DateTime? PublishedAt = null);
