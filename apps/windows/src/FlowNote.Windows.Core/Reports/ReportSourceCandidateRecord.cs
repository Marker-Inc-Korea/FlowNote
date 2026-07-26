namespace FlowNote.Windows.Core.Reports;

public sealed record ReportSourceCandidateRecord(
    string SourceType,
    string SourceId,
    string Title,
    string Detail,
    DateTime CreatedAt,
    string? SourceVersionId = null,
    string? RelationType = null,
    int? SourceRevision = null,
    string? SourceHashSha256 = null,
    string? ServerSourceId = null)
{
    public string SnapshotLabel =>
        $"버전 {SourceVersionId ?? "없음"} · revision {SourceRevision?.ToString() ?? "해당 없음"} · " +
        $"hash {(string.IsNullOrWhiteSpace(SourceHashSha256) ? "없음" : $"{SourceHashSha256[..Math.Min(12, SourceHashSha256.Length)]}…")}";
}
