namespace FlowNote.Windows.Core.Reports;

public sealed record ReportSourceCandidateRecord(
    string SourceType,
    string SourceId,
    string Title,
    string Detail,
    DateTime CreatedAt,
    string? SourceVersionId = null,
    string? RelationType = null);
